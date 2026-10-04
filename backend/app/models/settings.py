import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WorkspaceSettings(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Per-workspace preferences. Budget limits stay on AutopilotConfig (the
    budget guard reads them there); this holds everything else."""

    __tablename__ = "workspace_settings"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    default_tone_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tone_of_voice_profiles.id", ondelete="SET NULL"), nullable=True
    )
    # {"hr": "@talos_hr", "website": "https://..."} — workspace-level CTA mapping.
    cta_defaults_json: Mapped[str] = mapped_column(Text, default="{}")
    # What the scheduler does with posts whose time passed while it was down.
    misfire_policy: Mapped[str] = mapped_column(String(30), default="RESCHEDULE_NEXT_SLOT")
    misfire_grace_minutes: Mapped[int] = mapped_column(Integer, default=15)
    notification_prefs_json: Mapped[str] = mapped_column(Text, default="{}")
