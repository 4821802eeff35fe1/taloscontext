import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PostMetricSnapshot(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "post_metric_snapshots"

    publication_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    views: Mapped[int] = mapped_column(Integer, default=0)
    forwards: Mapped[int] = mapped_column(Integer, default=0)
    reactions: Mapped[int] = mapped_column(Integer, default=0)
    replies: Mapped[int] = mapped_column(Integer, default=0)
