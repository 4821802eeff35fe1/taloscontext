"""In-app notifications with a pluggable delivery abstraction.

Rows are fanned out per workspace member so read/unread state is per user.
`NotificationChannel` implementations beyond in-app (email, Telegram bot) can
be registered later without touching the call sites.
"""
from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import BatchStatus, WorkspaceRole
from app.models.identity import WorkspaceMember
from app.models.ops import Notification

Emit = Callable[[str, dict[str, Any]], None]

KINDS = {
    "post.published", "post.partially_published", "post.failed",
    "telegram.disconnected", "telegram.flood_wait",
    "budget.warning", "budget.exceeded",
    "ai.failed", "approval.required", "schedule.misfired",
}


class NotificationChannel(ABC):
    """Delivery channel. In-app is always on; others are future extensions."""

    name: str

    @abstractmethod
    async def deliver(self, notification: Notification) -> None: ...


class InAppChannel(NotificationChannel):
    name = "in_app"

    async def deliver(self, notification: Notification) -> None:
        return None  # the DB row itself is the in-app delivery


_CHANNELS: list[NotificationChannel] = [InAppChannel()]


def register_channel(channel: NotificationChannel) -> None:
    _CHANNELS.append(channel)


class NotificationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def notify(
        self,
        *,
        workspace_id: uuid.UUID,
        kind: str,
        message: str,
        metadata: dict[str, Any] | None = None,
        min_role: WorkspaceRole | None = None,
        dedupe_key: str | None = None,
        dedupe_window: timedelta = timedelta(hours=1),
        emit: Emit | None = None,
    ) -> int:
        if kind not in KINDS:
            raise ValueError(f"Unknown notification kind {kind}")
        metadata = dict(metadata or {})
        if dedupe_key:
            metadata["dedupe_key"] = dedupe_key
            recent = await self.session.execute(
                select(Notification.id).where(
                    Notification.workspace_id == workspace_id,
                    Notification.kind == kind,
                    Notification.metadata_json.contains(f'"dedupe_key": "{dedupe_key}"'),
                    Notification.created_at >= datetime.now(UTC) - dedupe_window,
                ).limit(1)
            )
            if recent.first():
                return 0

        from app.core.rbac import _RANK  # same ranking used for authorization

        members = await self.session.execute(
            select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
        )
        created = 0
        for member in members.scalars().all():
            if min_role and _RANK[member.role] < _RANK[min_role]:
                continue
            row = Notification(
                workspace_id=workspace_id, user_id=member.user_id, kind=kind, message=message,
                metadata_json=json.dumps(metadata, default=str),
            )
            self.session.add(row)
            await self.session.flush()
            for channel in _CHANNELS:
                await channel.deliver(row)
            created += 1
        if created and emit:
            emit("notification.created", {"kind": kind, "message": message})
        elif created:
            from app.services.realtime.events import publish_event

            await publish_event(workspace_id, "notification.created", {"kind": kind, "message": message})
        return created

    async def on_batch_progress(self, publication, emit: Emit | None = None) -> None:
        from app.models.content import ContentItem
        from app.models.distribution import DistributionBatch, Publication
        from app.models.enums import PublicationStatus

        batch = await self.session.get(DistributionBatch, publication.batch_id)
        if batch is None or batch.status not in (
            BatchStatus.SUCCESS, BatchStatus.PARTIAL_FAILURE, BatchStatus.FAILED
        ):
            return
        rows = await self.session.execute(select(Publication.status).where(Publication.batch_id == batch.id))
        statuses = [r[0] for r in rows.all()]
        ok = sum(1 for s in statuses if s == PublicationStatus.SUCCESS)
        item = await self.session.get(ContentItem, batch.content_item_id)
        title = (item.title or item.topic or "Post") if item else "Post"
        kind, message = {
            BatchStatus.SUCCESS: ("post.published", f"“{title}” published to {ok}/{len(statuses)} channels."),
            BatchStatus.PARTIAL_FAILURE: (
                "post.partially_published",
                f"“{title}” published to {ok}/{len(statuses)} channels; {len(statuses) - ok} failed.",
            ),
            BatchStatus.FAILED: ("post.failed", f"“{title}” failed to publish to all {len(statuses)} channels."),
        }[batch.status]
        await self.notify(
            workspace_id=batch.workspace_id, kind=kind, message=message,
            # Parameters let clients render the message in the viewer's language;
            # `message` stays as an English fallback.
            metadata={"content_id": str(batch.content_item_id), "batch_id": str(batch.id), "title": title,
                      "published": ok, "total": len(statuses), "failed": len(statuses) - ok},
            # Each retry round can end in a new final state; key on it so a later success still notifies.
            dedupe_key=f"batch:{batch.id}:{batch.status.value}:{ok}", dedupe_window=timedelta(days=30),
            emit=emit,
        )

    async def on_publication_failed(self, publication, emit: Emit | None = None) -> None:
        await self.on_batch_progress(publication, emit)

    async def on_flood_wait(self, account, retry_at: datetime, emit: Emit | None = None) -> None:
        await self.notify(
            workspace_id=account.workspace_id, kind="telegram.flood_wait",
            message=f"Telegram asked account {account.phone_masked} to slow down; "
                    f"publishing resumes at {retry_at.strftime('%H:%M UTC')}.",
            metadata={"account_id": str(account.id), "retry_at": retry_at.isoformat(), "phone": account.phone_masked},
            dedupe_key=f"flood:{account.id}", dedupe_window=timedelta(minutes=30), emit=emit,
        )

    async def on_account_disconnected(self, account, emit: Emit | None = None) -> None:
        await self.notify(
            workspace_id=account.workspace_id, kind="telegram.disconnected",
            message=f"Telegram account {account.phone_masked} needs to be reconnected.",
            metadata={"account_id": str(account.id), "phone": account.phone_masked}, min_role=WorkspaceRole.ADMIN,
            dedupe_key=f"disconnected:{account.id}", dedupe_window=timedelta(hours=12), emit=emit,
        )
