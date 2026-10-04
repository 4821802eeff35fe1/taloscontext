import uuid

from sqlalchemy import ForeignKey, String, Text
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


class KnowledgeDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "knowledge_documents"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # facts|company_info|links|people|allowed_claims|prohibited_claims|style_examples
    # good_posts|bad_posts|telegram_export|notes|file
    source_filename: Mapped[str] = mapped_column(String(300), default="")
    media_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    raw_text: Mapped[str] = mapped_column(Text, default="")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="selectin"
    )


class KnowledgeChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "knowledge_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")
