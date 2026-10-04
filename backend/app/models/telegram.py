import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ChannelHealth, ChannelSetMode, TelegramAccountStatus


class TelegramAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "telegram_accounts"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    phone_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    phone_masked: Mapped[str] = mapped_column(String(32), nullable=False)
    session_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    first_name: Mapped[str] = mapped_column(String(200), default="")
    last_name: Mapped[str] = mapped_column(String(200), default="")
    username: Mapped[str | None] = mapped_column(String(200), nullable=True)
    avatar_media_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[TelegramAccountStatus] = mapped_column(
        SAEnum(TelegramAccountStatus, name="telegram_account_status"),
        default=TelegramAccountStatus.AUTH_REQUIRED,
        nullable=False,
    )
    flood_wait_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    channels: Mapped[list["TelegramChannel"]] = relationship(back_populates="account")


class TelegramChannel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "telegram_channels"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("telegram_accounts.id", ondelete="CASCADE"), nullable=False
    )

    telegram_entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    access_hash: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    username: Mapped[str | None] = mapped_column(String(200), nullable=True)
    avatar_media_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    subscriber_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    can_post: Mapped[bool] = mapped_column(Boolean, default=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    autopilot_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    default_cta_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tone_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tone_of_voice_profiles.id", ondelete="SET NULL"), nullable=True
    )
    knowledge_scope_tags: Mapped[str] = mapped_column(Text, default="")

    health: Mapped[ChannelHealth] = mapped_column(
        SAEnum(ChannelHealth, name="channel_health"), default=ChannelHealth.UNAVAILABLE
    )

    cta_overrides_json: Mapped[str] = mapped_column(Text, default="{}")

    account: Mapped[TelegramAccount] = relationship(back_populates="channels")


class ChannelSet(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "channel_sets"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    mode: Mapped[ChannelSetMode] = mapped_column(
        SAEnum(ChannelSetMode, name="channel_set_mode"), default=ChannelSetMode.EXACT
    )
    autopilot_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    members: Mapped[list["ChannelSetMember"]] = relationship(
        back_populates="channel_set", cascade="all, delete-orphan"
    )


class ChannelSetMember(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "channel_set_members"

    channel_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("channel_sets.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("telegram_channels.id", ondelete="CASCADE"), nullable=False
    )

    channel_set: Mapped[ChannelSet] = relationship(back_populates="members")
    channel: Mapped[TelegramChannel] = relationship()
