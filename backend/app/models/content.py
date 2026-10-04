import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ContentStatus


class ContentSeries(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "content_series"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    channel_set_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("channel_sets.id", ondelete="SET NULL"), nullable=True
    )
    tone_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tone_of_voice_profiles.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(100), default="")
    # DRAFT | ACTIVE | PAUSED | COMPLETED
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    # Python format string for the issue label, e.g. "#{n:03d}" -> "#004".
    numbering_format: Mapped[str] = mapped_column(String(40), default="#{n:03d}")
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True
    )
    frequency: Mapped[str] = mapped_column(String(100), default="")
    sequence_counter: Mapped[int] = mapped_column(Integer, default=0)
    planned_topics_json: Mapped[str] = mapped_column(Text, default="[]")

    items: Mapped[list["SeriesItem"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )


class SeriesItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "series_items"

    series_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_series.id", ondelete="CASCADE"), nullable=False
    )
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)

    series: Mapped[ContentSeries] = relationship(back_populates="items")


class ContentItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "content_items"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[ContentStatus] = mapped_column(
        SAEnum(ContentStatus, name="content_status"), default=ContentStatus.IDEA, nullable=False
    )

    topic: Mapped[str] = mapped_column(String(300), default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    angle: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    plain_text: Mapped[str] = mapped_column(Text, default="")
    telegram_html: Mapped[str] = mapped_column(Text, default="")
    cta_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    sources_json: Mapped[str] = mapped_column(Text, default="[]")

    media_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    image_prompt: Mapped[str] = mapped_column(Text, default="")

    duplicate_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    duplicate_score: Mapped[float | None] = mapped_column(nullable=True)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_flags_json: Mapped[str] = mapped_column(Text, default="[]")

    tone_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tone_of_voice_profiles.id", ondelete="SET NULL"), nullable=True
    )
    channel_set_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("channel_sets.id", ondelete="SET NULL"), nullable=True
    )
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_series.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_items.id", ondelete="SET NULL"), nullable=True
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    revisions: Mapped[list["ContentRevision"]] = relationship(
        back_populates="content_item", cascade="all, delete-orphan", order_by="ContentRevision.created_at"
    )


class ContentRevision(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "content_revisions"

    content_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False
    )
    edited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="")
    plain_text: Mapped[str] = mapped_column(Text, default="")
    telegram_html: Mapped[str] = mapped_column(Text, default="")
    ai_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_requests.id", ondelete="SET NULL"), nullable=True
    )

    content_item: Mapped[ContentItem] = relationship(back_populates="revisions")
