import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import BatchStatus, PublicationStatus


class DistributionBatch(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "distribution_batches"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False
    )
    channel_set_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("channel_sets.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[BatchStatus] = mapped_column(
        SAEnum(BatchStatus, name="batch_status"), default=BatchStatus.PENDING
    )

    publications: Mapped[list["Publication"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", lazy="selectin"
    )


class Publication(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "publications"

    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("distribution_batches.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("telegram_channels.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    status: Mapped[PublicationStatus] = mapped_column(
        SAEnum(PublicationStatus, name="publication_status"), default=PublicationStatus.PENDING
    )
    attempt: Mapped[int] = mapped_column(default=0)
    rendered_text: Mapped[str] = mapped_column(Text, default="")
    resolved_cta: Mapped[str | None] = mapped_column(String(300), nullable=True)

    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    flood_wait_seconds: Mapped[int | None] = mapped_column(nullable=True)

    batch: Mapped[DistributionBatch] = relationship(back_populates="publications")
