import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ToneOfVoiceProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tone_of_voice_profiles"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(32), default="ru")
    addressing: Mapped[str] = mapped_column(String(50), default="")
    formality: Mapped[str] = mapped_column(String(50), default="")
    emoji_policy: Mapped[str] = mapped_column(String(50), default="minimal")
    average_length: Mapped[str] = mapped_column(String(50), default="medium")
    paragraph_style: Mapped[str] = mapped_column(String(100), default="")
    headline_style: Mapped[str] = mapped_column(String(100), default="")
    cta_style: Mapped[str] = mapped_column(String(100), default="")
    allowed_vocabulary_json: Mapped[str] = mapped_column(Text, default="[]")
    forbidden_vocabulary_json: Mapped[str] = mapped_column(Text, default="[]")
    cliches_blacklist_json: Mapped[str] = mapped_column(Text, default="[]")
    good_examples_json: Mapped[str] = mapped_column(Text, default="[]")
    bad_examples_json: Mapped[str] = mapped_column(Text, default="[]")


class KnowledgeBase(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A named collection of knowledge documents that can be switched on/off as a unit."""

    __tablename__ = "knowledge_bases"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class KnowledgeDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "knowledge_documents"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # Source format: manual|txt|md|json|csv|pdf|telegram_export (v0.1 rows hold legacy values).
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Semantic kind (KnowledgeKind): decides prompt priority.
    kind: Mapped[str] = mapped_column(String(40), default="FACT", index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Facts can expire; the newest valid fact wins over anything older or historical.
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_filename: Mapped[str] = mapped_column(String(300), default="")
    media_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    raw_text: Mapped[str] = mapped_column(Text, default="")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    parse_warnings_json: Mapped[str] = mapped_column(Text, default="[]")

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="selectin"
    )


class KnowledgeChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "knowledge_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), default="FACT")
    # When the information is from (a post's date, a fact's last update).
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Telegram export posts: message id, date, entities, media metadata, source channel.
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")
