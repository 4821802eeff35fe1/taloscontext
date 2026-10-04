import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AIOperation, AIRequestStatus


class AIRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ai_requests"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    content_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_items.id", ondelete="SET NULL"), nullable=True
    )

    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), default="")
    operation: Mapped[AIOperation] = mapped_column(SAEnum(AIOperation, name="ai_operation"))
    provider_request_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)

    input_rate_rub_per_m: Mapped[Numeric] = mapped_column(Numeric(12, 4), default=0)
    output_rate_rub_per_m: Mapped[Numeric] = mapped_column(Numeric(12, 4), default=0)
    input_cost_rub: Mapped[Numeric] = mapped_column(Numeric(12, 4), default=0)
    output_cost_rub: Mapped[Numeric] = mapped_column(Numeric(12, 4), default=0)
    total_cost_rub: Mapped[Numeric] = mapped_column(Numeric(12, 4), default=0)

    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[AIRequestStatus] = mapped_column(
        SAEnum(AIRequestStatus, name="ai_request_status"), default=AIRequestStatus.SUCCESS
    )
    raw_usage_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class CostEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Denormalized ledger row for fast dashboard aggregation."""

    __tablename__ = "cost_events"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    ai_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_requests.id", ondelete="SET NULL"), nullable=True
    )
    content_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("content_items.id", ondelete="SET NULL"), nullable=True
    )
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("telegram_channels.id", ondelete="SET NULL"), nullable=True
    )
    channel_set_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("channel_sets.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(100), default="")
    provider: Mapped[str] = mapped_column(String(100), default="")
    operation: Mapped[AIOperation] = mapped_column(SAEnum(AIOperation, name="ai_operation_cost_event"))
    amount_rub: Mapped[Numeric] = mapped_column(Numeric(12, 4), nullable=False)
