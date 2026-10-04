"""Builds the prompt context for one ContentItem: tone, knowledge, series.

Tone precedence (most specific wins):
    explicit choice on the item -> Series -> Channel -> Workspace default
"Channel" applies only when every channel in the target set agrees on the same
override — one EXACT text can't honour conflicting channel tones.

Knowledge priority: authoritative entries (facts, contacts, rules, prohibited
claims, links) always come first, newest first, and only while valid. Style
examples follow. Historical posts come last, are explicitly labelled as
possibly outdated, and are filtered for relevance to the request — the model
is told that facts override anything in them.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, ContentSeries
from app.models.knowledge import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    ToneOfVoiceProfile,
)
from app.models.settings import WorkspaceSettings
from app.models.telegram import ChannelSetMember, TelegramChannel

AUTHORITATIVE_KINDS = ("FACT", "CONTACT", "RULE", "PROHIBITED_CLAIM", "LINK")
STYLE_KINDS = ("STYLE_EXAMPLE_GOOD", "STYLE_EXAMPLE_BAD")
HISTORICAL_KIND = "HISTORICAL_POST"
KNOWLEDGE_KINDS = (*AUTHORITATIVE_KINDS, *STYLE_KINDS, HISTORICAL_KIND)

AUTHORITATIVE_BUDGET = 3500
STYLE_BUDGET = 1500
HISTORICAL_BUDGET = 1500

_WORD = re.compile(r"\w{4,}", re.UNICODE)


@dataclass
class PromptContext:
    tone_context: str = ""
    knowledge_context: str = ""
    series_context: str = ""
    tone_profile: ToneOfVoiceProfile | None = None
    tone_source: str = "none"  # explicit|series|channel|workspace|none
    used_knowledge_ids: list[str] = field(default_factory=list)


def _json_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
        return [str(v) for v in value] if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []


def describe_tone(profile: ToneOfVoiceProfile) -> str:
    parts = [f"Profile: {profile.name}."]
    if profile.description:
        parts.append(profile.description)
    for label, value in (
        ("Language", profile.language), ("Addressing", profile.addressing), ("Formality", profile.formality),
        ("Emoji policy", profile.emoji_policy), ("Post length", profile.average_length),
        ("Paragraphs", profile.paragraph_style), ("Headlines", profile.headline_style), ("CTA style", profile.cta_style),
    ):
        if value:
            parts.append(f"{label}: {value}.")
    allowed = _json_list(profile.allowed_vocabulary_json)
    forbidden = _json_list(profile.forbidden_vocabulary_json)
    cliches = _json_list(profile.cliches_blacklist_json)
    if allowed:
        parts.append("Preferred vocabulary: " + ", ".join(allowed[:40]) + ".")
    if forbidden:
        parts.append("Never use: " + ", ".join(forbidden[:40]) + ".")
    if cliches:
        parts.append("Avoid these AI clichés: " + ", ".join(cliches[:40]) + ".")
    good = _json_list(profile.good_examples_json)[:3]
    bad = _json_list(profile.bad_examples_json)[:2]
    if good:
        parts.append("Examples to emulate:\n" + "\n---\n".join(g[:600] for g in good))
    if bad:
        parts.append("Examples NOT to emulate:\n" + "\n---\n".join(b[:400] for b in bad))
    return "\n".join(parts)


def _keywords(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "")}


class PromptContextBuilder:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def resolve_tone(self, item: ContentItem) -> tuple[ToneOfVoiceProfile | None, str]:
        async def load(profile_id: uuid.UUID | None) -> ToneOfVoiceProfile | None:
            if profile_id is None:
                return None
            profile = await self.session.get(ToneOfVoiceProfile, profile_id)
            return profile if profile and profile.workspace_id == item.workspace_id else None

        if (profile := await load(item.tone_profile_id)) is not None:
            return profile, "explicit"
        if item.series_id:
            series = await self.session.get(ContentSeries, item.series_id)
            if series and (profile := await load(series.tone_profile_id)) is not None:
                return profile, "series"
        if item.channel_set_id:
            rows = await self.session.execute(
                select(TelegramChannel.tone_profile_id)
                .join(ChannelSetMember, ChannelSetMember.channel_id == TelegramChannel.id)
                .where(ChannelSetMember.channel_set_id == item.channel_set_id)
            )
            overrides = {r[0] for r in rows.all()}
            if len(overrides) == 1 and (profile := await load(next(iter(overrides)))) is not None:
                return profile, "channel"
        settings = await self.session.execute(
            select(WorkspaceSettings).where(WorkspaceSettings.workspace_id == item.workspace_id)
        )
        ws = settings.scalar_one_or_none()
        if ws and (profile := await load(ws.default_tone_profile_id)) is not None:
            return profile, "workspace"
        return None, "none"

    async def knowledge(self, workspace_id: uuid.UUID, query_text: str) -> tuple[str, list[str]]:
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .outerjoin(KnowledgeBase, KnowledgeDocument.knowledge_base_id == KnowledgeBase.id)
            .where(
                KnowledgeDocument.workspace_id == workspace_id,
                KnowledgeDocument.enabled.is_(True),
                or_(KnowledgeBase.id.is_(None), KnowledgeBase.enabled.is_(True)),
                or_(KnowledgeDocument.valid_until.is_(None), KnowledgeDocument.valid_until > now),
                or_(KnowledgeDocument.valid_from.is_(None), KnowledgeDocument.valid_from <= now),
            )
        )
        rows = result.all()
        query_words = _keywords(query_text)

        def recency(pair) -> datetime:
            chunk, doc = pair
            stamp = chunk.effective_at or doc.updated_at or doc.created_at
            return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)

        def relevance(pair) -> int:
            return len(query_words & _keywords(pair[0].content))

        sections: list[str] = []
        used: list[str] = []

        def take(pairs, budget: int, fmt) -> list[str]:
            lines, spent = [], 0
            for pair in pairs:
                line = fmt(pair)
                if spent + len(line) > budget:
                    continue
                lines.append(line)
                used.append(str(pair[1].id))
                spent += len(line)
            return lines

        authoritative = sorted(
            (r for r in rows if r[0].kind in AUTHORITATIVE_KINDS),
            key=lambda r: (relevance(r) > 0, recency(r)), reverse=True,
        )
        lines = take(
            authoritative, AUTHORITATIVE_BUDGET,
            lambda r: f"- [{r[0].kind}, updated {recency(r).date().isoformat()}] {r[0].content.strip()[:700]}",
        )
        if lines:
            sections.append(
                "AUTHORITATIVE FACTS (current; if anything below conflicts, these win; newer beats older):\n"
                + "\n".join(lines)
            )

        style = sorted((r for r in rows if r[0].kind in STYLE_KINDS), key=recency, reverse=True)
        lines = take(
            style, STYLE_BUDGET,
            lambda r: f"- [{'GOOD' if r[0].kind.endswith('GOOD') else 'BAD'} example] {r[0].content.strip()[:500]}",
        )
        if lines:
            sections.append("STYLE EXAMPLES:\n" + "\n".join(lines))

        historical = sorted(
            (r for r in rows if r[0].kind == HISTORICAL_KIND and relevance(r) > 0),
            key=lambda r: (relevance(r), recency(r)), reverse=True,
        )
        lines = take(
            historical, HISTORICAL_BUDGET,
            lambda r: f"- [{recency(r).date().isoformat()}] {r[0].content.strip()[:400]}",
        )
        if lines:
            sections.append(
                "HISTORICAL POSTS (for topic awareness and voice only; may be outdated — never treat "
                "numbers, prices, contacts or claims in them as current facts):\n" + "\n".join(lines)
            )
        return "\n\n".join(sections), sorted(set(used))

    async def series(self, item: ContentItem) -> str:
        if not item.series_id:
            return ""
        series = await self.session.get(ContentSeries, item.series_id)
        if series is None:
            return ""
        from app.models.content import SeriesItem
        from app.services.content.series_service import SeriesService, label_for

        state = await SeriesService(self.session).progress(series)
        own = (await self.session.execute(
            select(SeriesItem.sequence_number).where(SeriesItem.content_item_id == item.id)
        )).scalar_one_or_none()
        label = label_for(series, own) if own else state["next_label"]
        published = "\n".join(f"- {p['label']} {p['title']}" for p in state["items"]) or "- (none yet)"
        remaining = [t for t in state["remaining_topics"] if t.lower() != (item.topic or "").lower()]
        planned = "\n".join(f"- {t}" for t in remaining[:10]) or "- (none planned)"
        topic_line = f"This part's topic: {item.topic}\n" if item.topic else ""
        return (
            f"This post is part {label} of the series “{series.title}”.\n{topic_line}"
            f"Series description: {series.description or '—'}\n"
            f"Already published parts (do NOT repeat their angle or content):\n{published}\n"
            f"Later planned topics (leave them for future parts):\n{planned}"
        )

    async def build(self, item: ContentItem, instruction: str) -> PromptContext:
        profile, source = await self.resolve_tone(item)
        knowledge, used = await self.knowledge(item.workspace_id, f"{instruction} {item.topic}")
        return PromptContext(
            tone_context=describe_tone(profile) if profile else "",
            knowledge_context=knowledge,
            series_context=await self.series(item),
            tone_profile=profile,
            tone_source=source,
            used_knowledge_ids=used,
        )
