"""Content Studio AI transforms (AI_REWRITE job).

All operations go through one endpoint and one job type. Each run:
- makes one TextAIProvider call (plus at most one parse retry) via AIService,
  so usage and cost are recorded like any generation;
- appends a ContentRevision linked to its AIRequest — earlier versions stay;
- refuses to apply if the post changed since the user asked (base revision),
  so an autosave racing with a transform can't silently lose edits.
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, ContentRevision
from app.models.enums import AIOperation, ContentStatus
from app.models.knowledge import ToneOfVoiceProfile
from app.models.ops import Job
from app.services.ai.factory import get_image_provider, get_text_provider
from app.services.ai.service import AIParseError, AIProviderError, AIService
from app.services.audit.service import AuditService
from app.services.content.context import PromptContextBuilder, describe_tone
from app.services.content.cta_resolver import KNOWN_CTA_KEYS
from app.services.content.html_sanitizer import sanitize_telegram_html, strip_to_plain_text
from app.services.costs.service import BudgetExceededError
from app.services.jobs.service import Emit, JobFailed

# operation -> (AIOperation, instruction, needs selection)
OPERATIONS: dict[str, tuple[AIOperation, str, bool]] = {
    "rewrite": (AIOperation.REWRITE, "Rewrite the post with fresh wording, same facts, same length.", False),
    "shorten": (AIOperation.SHORTEN, "Shorten the post by roughly 40% while keeping the key point and CTA.", False),
    "expand": (AIOperation.EXPAND, "Expand the post with one or two concrete, useful details. No filler.", False),
    "change_tone": (AIOperation.CHANGE_TONE, "Rewrite the post in the target tone of voice described below.", False),
    "improve": (AIOperation.IMPROVE, "Improve clarity, structure and flow. Fix grammar. Keep meaning and length.", False),
    "generate_headline": (AIOperation.REGENERATE_TITLE, "Write a stronger headline. Return the body unchanged.", False),
    "regenerate_fragment": (
        AIOperation.REGENERATE_FRAGMENT,
        "Rewrite ONLY the selected fragment. Every other character of the post must stay exactly the same.",
        True,
    ),
    "generate_cta": (
        AIOperation.GENERATE_CTA,
        "Choose the most fitting call-to-action key for this post. Return the body unchanged.",
        False,
    ),
    "remove_cliches": (
        AIOperation.REMOVE_CLICHES,
        "Remove AI clichés, filler phrases and empty intensifiers. Keep everything substantive.",
        False,
    ),
}

SYSTEM_PROMPT = """You edit Telegram channel posts. Return ONLY one JSON object, no prose:
{{"title": string, "telegram_html": string, "cta_key": string|null, "notes": string}}
telegram_html may use only <b> <i> <u> <s> <a href> <code> <pre> <blockquote>; paragraphs are separated by blank lines.
cta_key must be one of {cta_keys} or null. Never invent usernames, links, phone numbers or e-mails.
Tone of voice:
{tone}
Knowledge you must not contradict:
{knowledge}
"""


class TransformResult(BaseModel):
    title: str = ""
    telegram_html: str
    cta_key: str | None = None
    notes: str = Field(default="", max_length=2000)


class TransformError(Exception):
    pass


async def latest_revision(session: AsyncSession, content_id: uuid.UUID) -> ContentRevision | None:
    result = await session.execute(
        select(ContentRevision)
        .where(ContentRevision.content_item_id == content_id)
        .order_by(ContentRevision.created_at.desc(), ContentRevision.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


EDITABLE_STATUSES = {ContentStatus.DRAFT, ContentStatus.PENDING_APPROVAL, ContentStatus.APPROVED,
                     ContentStatus.REJECTED, ContentStatus.IDEA}


async def run_transform(session: AsyncSession, job: Job, payload: dict[str, Any], emit: Emit) -> dict[str, Any]:
    item = await session.get(ContentItem, uuid.UUID(payload["content_id"]))
    if item is None or item.workspace_id != job.workspace_id or item.deleted_at is not None:
        raise JobFailed("CONTENT_NOT_FOUND", "Content item no longer exists")
    if item.status not in EDITABLE_STATUSES:
        raise JobFailed("NOT_EDITABLE", f"Content is {item.status.value}; it can't be edited now")
    operation = payload["operation"]
    ai_op, instruction, needs_selection = OPERATIONS[operation]

    base = payload.get("base_revision_id")
    latest = await latest_revision(session, item.id)
    if base and latest and str(latest.id) != base:
        raise JobFailed("CONFLICT", "The post changed while the AI was working. Run the action again.")

    tone_profile = None
    if payload.get("tone_profile_id"):
        candidate = await session.get(ToneOfVoiceProfile, uuid.UUID(payload["tone_profile_id"]))
        if candidate is None or candidate.workspace_id != item.workspace_id:
            raise JobFailed("TONE_NOT_FOUND", "Tone profile not found")
        tone_profile = candidate
    builder = PromptContextBuilder(session)
    if tone_profile is None:
        tone_profile, _ = await builder.resolve_tone(item)
    knowledge, _ = await builder.knowledge(item.workspace_id, f"{item.title} {item.plain_text[:500]}")

    parts = [f"Task: {instruction}"]
    if needs_selection:
        parts.append(f"Selected fragment:\n«{payload.get('selection', '')}»")
    if payload.get("instructions"):
        parts.append(f"Additional instructions from the editor: {payload['instructions']}")
    parts.append(f"Current title: {item.title}")
    parts.append(f"Current post (Telegram HTML):\n{item.telegram_html}")

    ai_service = AIService(session, get_text_provider(), get_image_provider())
    try:
        result, ai_request = await ai_service.complete_json(
            schema=TransformResult,
            workspace_id=item.workspace_id,
            content_item_id=item.id,
            system_prompt=SYSTEM_PROMPT.format(
                cta_keys=sorted(KNOWN_CTA_KEYS),
                tone=describe_tone(tone_profile) if tone_profile else "Keep the post's current voice.",
                knowledge=knowledge or "None provided.",
            ),
            user_prompt="\n\n".join(parts),
            operation=ai_op,
        )
    except BudgetExceededError as exc:
        raise JobFailed("BUDGET_EXCEEDED", str(exc)) from exc
    except AIParseError as exc:
        raise JobFailed("AI_INVALID_RESPONSE", str(exc)) from exc
    except AIProviderError as exc:
        raise JobFailed("AI_PROVIDER_ERROR", str(exc)) from exc

    # Re-read after awaiting the provider; manual edits may have committed.
    await session.refresh(item, with_for_update=True)
    current = await latest_revision(session, item.id)
    if (base and current and str(current.id) != base) or item.status not in EDITABLE_STATUSES:
        raise JobFailed("CONFLICT", "The post changed while the AI was working. Your edits were kept.")
    if item.status == ContentStatus.APPROVED:
        item.status = ContentStatus.PENDING_APPROVAL

    if operation == "generate_cta":
        if result.cta_key and result.cta_key not in KNOWN_CTA_KEYS:
            raise JobFailed("AI_INVALID_RESPONSE", f"Model returned unknown CTA key {result.cta_key!r}")
        item.cta_key = result.cta_key
    elif operation == "generate_headline":
        item.title = (result.title or item.title)[:300]
    else:
        item.telegram_html = sanitize_telegram_html(result.telegram_html)
        item.plain_text = strip_to_plain_text(item.telegram_html)
        if result.title and operation in ("rewrite", "change_tone"):
            item.title = result.title[:300]
    if operation == "change_tone" and tone_profile is not None:
        item.tone_profile_id = tone_profile.id

    revision = ContentRevision(
        content_item_id=item.id,
        edited_by_user_id=job.created_by_user_id,
        action=operation,
        title=item.title,
        plain_text=item.plain_text,
        telegram_html=item.telegram_html,
        ai_request_id=ai_request.id,
    )
    session.add(revision)
    await session.flush()
    await AuditService(session).record(
        workspace_id=item.workspace_id, actor_user_id=job.created_by_user_id, action=f"content.ai_{operation}",
        entity_type="content", entity_id=item.id, metadata={"cost_rub": str(ai_request.total_cost_rub)},
    )
    emit("content.updated", {"content_id": str(item.id), "revision_id": str(revision.id), "operation": operation})
    return {
        "content_id": str(item.id), "revision_id": str(revision.id), "operation": operation,
        "cost_rub": str(ai_request.total_cost_rub), "notes": result.notes[:500],
        "prompt_tokens": ai_request.prompt_tokens, "completion_tokens": ai_request.completion_tokens,
    }

