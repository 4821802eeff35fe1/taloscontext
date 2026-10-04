import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AutopilotMode


class Schedule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "schedules"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    channel_set_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("channel_sets.id", ondelete="SET NULL"), nullable=True
    )
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    posts_per_day: Mapped[int] = mapped_column(Integer, default=1)
    days_of_week_json: Mapped[str] = mapped_column(Text, default="[0,1,2,3,4,5,6]")
    min_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    max_posts_per_day: Mapped[int] = mapped_column(Integer, default=10)
    exclude_dates_json: Mapped[str] = mapped_column(Text, default="[]")
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    randomize_within_window: Mapped[bool] = mapped_column(Boolean, default=True)
    categories_json: Mapped[str] = mapped_column(Text, default="[]")
    # None -> workspace default (WorkspaceSettings.misfire_policy)
    misfire_policy: Mapped[str | None] = mapped_column(String(30), nullable=True)

    rules: Mapped[list["ScheduleRule"]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan"
    )


class ScheduleRule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "schedule_rules"

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False
    )
    window_start: Mapped[str] = mapped_column(String(5), nullable=False)  # "HH:MM" local
    window_end: Mapped[str] = mapped_column(String(5), nullable=False)

    schedule: Mapped[Schedule] = relationship(back_populates="rules")


class AutopilotConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "autopilot_configs"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    mode: Mapped[AutopilotMode] = mapped_column(
        SAEnum(AutopilotMode, name="autopilot_mode"), default=AutopilotMode.MANUAL
    )
    channel_set_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("channel_sets.id", ondelete="SET NULL"), nullable=True
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True
    )
    posts_per_day: Mapped[int] = mapped_column(Integer, default=1)
    category_mix_json: Mapped[str] = mapped_column(
        Text, default='{"educational":0.4,"news":0.25,"expert":0.2,"recruiting":0.15}'
    )
    tone_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tone_of_voice_profiles.id", ondelete="SET NULL"), nullable=True
    )
    generate_image: Mapped[bool] = mapped_column(Boolean, default=False)
    max_cost_per_post_rub: Mapped[Numeric] = mapped_column(Numeric(12, 4), default=15)
    budget_warning_pct: Mapped[int] = mapped_column(Integer, default=80)
    daily_budget_rub: Mapped[Numeric] = mapped_column(Numeric(12, 4), default=50)
    monthly_budget_rub: Mapped[Numeric] = mapped_column(Numeric(12, 4), default=1500)
    duplicate_block_threshold: Mapped[float] = mapped_column(default=0.80)
    duplicate_warning_threshold: Mapped[float] = mapped_column(default=0.60)
    require_sources_for_news: Mapped[bool] = mapped_column(Boolean, default=True)
    max_image_regenerations: Mapped[int] = mapped_column(Integer, default=1)
