from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, ContentRevision
from app.models.enums import CONTENT_TRANSITIONS, AIOperation, ContentStatus
from app.schemas.generation import GenerationResult
from app.services.ai.service import AIService
from app.services.content.duplicate_detection import DuplicateCandidate, DuplicateDetectionService
from app.services.content.html_sanitizer import sanitize_telegram_html


class InvalidTransitionError(Exception):
    pass


class ContentService:
    def __init__(self, session: AsyncSession, ai_service: AIService):
        self.session = session
        self.ai_service = ai_service
        self.duplicate_service = DuplicateDetectionService()

    def assert_transition(self, item: ContentItem, target: ContentStatus) -> None:
        allowed = CONTENT_TRANSITIONS.get(item.status, set())
        if target not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition content {item.id} from {item.status} to {target}"
            )

    async def _recent_candidates(
        self, workspace_id: uuid.UUID, limit: int = 50
    ) -> list[DuplicateCandidate]:
        result = await self.session.execute(
            select(ContentItem)
            .where(
                ContentItem.workspace_id == workspace_id,
                ContentItem.status.in_(
                    [ContentStatus.PUBLISHED, ContentStatus.PARTIALLY_PUBLISHED, ContentStatus.SCHEDULED]
                ),
            )
            .order_by(ContentItem.created_at.desc())
            .limit(limit)
        )
        items = result.scalars().all()
        return [
            DuplicateCandidate(
                content_item_id=str(item.id),
                title=item.title,
                text=item.plain_text,
                category=item.category,
                tags=json.loads(item.tags_json or "[]"),
            )
            for item in items
        ]

    async def generate(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID | None,
        user_instruction: str,
        tone_context: str = "",
        knowledge_context: str = "",
        channel_set_id: uuid.UUID | None = None,
        tone_profile_id: uuid.UUID | None = None,
    ) -> ContentItem:
        item = ContentItem(
            workspace_id=workspace_id,
            created_by_user_id=user_id,
            status=ContentStatus.IDEA,
            channel_set_id=channel_set_id,
            tone_profile_id=tone_profile_id,
        )
        self.session.add(item)
        await self.session.flush()

        self.assert_transition(item, ContentStatus.GENERATING)
        item.status = ContentStatus.GENERATING
        await self.session.flush()

        candidates = await self._recent_candidates(workspace_id)
        recent_topics = "; ".join(c.title for c in candidates[:20]) or "None"

        try:
            result, _cost = await self.ai_service.generate_post(
                workspace_id=workspace_id,
                content_item_id=item.id,
                tone_context=tone_context,
                knowledge_context=knowledge_context,
                recent_topics=recent_topics,
                user_instruction=user_instruction,
            )
        except Exception:
            item.status = ContentStatus.FAILED
            await self.session.flush()
            raise

        self._apply_generation_result(item, result, candidates)
        item.status = ContentStatus.DRAFT
        await self.session.flush()

        self.session.add(
            ContentRevision(
                content_item_id=item.id,
                edited_by_user_id=user_id,
                action=AIOperation.GENERATE_POST.value,
                title=item.title,
                plain_text=item.plain_text,
                telegram_html=item.telegram_html,
            )
        )
        await self.session.flush()
        return item

    def _apply_generation_result(
        self, item: ContentItem, result: GenerationResult, candidates: list[DuplicateCandidate]
    ) -> None:
        item.topic = result.topic
        item.category = result.category
        item.angle = result.angle
        item.title = result.title
        item.telegram_html = sanitize_telegram_html(result.telegram_html)
        item.plain_text = result.plain_text
        item.cta_key = result.cta_key
        item.image_prompt = result.image_prompt
        item.tags_json = json.dumps(result.tags, ensure_ascii=False)
        item.sources_json = json.dumps(result.sources, ensure_ascii=False)
        item.duplicate_fingerprint = result.duplicate_fingerprint
        item.requires_review = result.requires_review
        item.risk_flags_json = json.dumps(result.risk_flags, ensure_ascii=False)

        score, _match = self.duplicate_service.score(
            candidate_title=result.title,
            candidate_text=result.plain_text,
            candidate_category=result.category,
            candidate_tags=result.tags,
            recent_items=candidates,
        )
        item.duplicate_score = score

    async def manual_edit(
        self, *, item: ContentItem, user_id: uuid.UUID | None, title: str, telegram_html: str, plain_text: str
    ) -> ContentItem:
        item.title = title
        item.telegram_html = sanitize_telegram_html(telegram_html)
        item.plain_text = plain_text
        self.session.add(
            ContentRevision(
                content_item_id=item.id,
                edited_by_user_id=user_id,
                action="manual_edit",
                title=item.title,
                plain_text=item.plain_text,
                telegram_html=item.telegram_html,
            )
        )
        await self.session.flush()
        return item

    async def submit_for_approval(self, item: ContentItem) -> ContentItem:
        self.assert_transition(item, ContentStatus.PENDING_APPROVAL)
        item.status = ContentStatus.PENDING_APPROVAL
        await self.session.flush()
        return item

    async def approve(self, item: ContentItem) -> ContentItem:
        self.assert_transition(item, ContentStatus.APPROVED)
        item.status = ContentStatus.APPROVED
        await self.session.flush()
        return item

    async def reject(self, item: ContentItem) -> ContentItem:
        self.assert_transition(item, ContentStatus.REJECTED)
        item.status = ContentStatus.REJECTED
        await self.session.flush()
        return item

    async def schedule(self, item: ContentItem, *, scheduled_at: datetime) -> ContentItem:
        self.assert_transition(item, ContentStatus.SCHEDULED)
        item.status = ContentStatus.SCHEDULED
        item.scheduled_at = scheduled_at
        await self.session.flush()
        return item

    async def mark_publishing(self, item: ContentItem) -> ContentItem:
        self.assert_transition(item, ContentStatus.PUBLISHING)
        item.status = ContentStatus.PUBLISHING
        await self.session.flush()
        return item

    async def mark_published(self, item: ContentItem, *, partial: bool) -> ContentItem:
        target = ContentStatus.PARTIALLY_PUBLISHED if partial else ContentStatus.PUBLISHED
        self.assert_transition(item, target)
        item.status = target
        item.published_at = datetime.now(UTC)
        await self.session.flush()
        return item

    async def archive(self, item: ContentItem) -> ContentItem:
        self.assert_transition(item, ContentStatus.ARCHIVED)
        item.status = ContentStatus.ARCHIVED
        await self.session.flush()
        return item
