import uuid

from sqlalchemy import BigInteger, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import MediaStatus


class MediaAsset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "media_assets"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )

    bucket: Mapped[str] = mapped_column(String(200), nullable=False)
    object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(300), default="")

    status: Mapped[MediaStatus] = mapped_column(
        SAEnum(MediaStatus, name="media_status"), default=MediaStatus.UPLOADED
    )

    generation: Mapped["MediaGeneration | None"] = relationship(
        back_populates="media_asset", uselist=False, cascade="all, delete-orphan"
    )


class MediaGeneration(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "media_generations"

    media_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media_assets.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    content_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_items.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    cost_total_rub: Mapped[Numeric] = mapped_column(Numeric(12, 4), default=0)
    ai_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_requests.id", ondelete="SET NULL"), nullable=True
    )

    media_asset: Mapped[MediaAsset] = relationship(back_populates="generation")
