import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import IdeaStatus


class Source(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sources"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(50), nullable=False)  # rss|url|manual|telegram|web_search
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    is_active: Mapped[bool] = mapped_column(default=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["SourceItem"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class SourceItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "source_items"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(2000), default="")
    url_verified: Mapped[bool] = mapped_column(default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    freshness_score: Mapped[float] = mapped_column(default=0.0)
    relevance_score: Mapped[float] = mapped_column(default=0.0)
    category: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[IdeaStatus] = mapped_column(SAEnum(IdeaStatus, name="idea_status"), default=IdeaStatus.NEW)

    source: Mapped[Source] = relationship(back_populates="items")
