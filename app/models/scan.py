from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.finding import Finding


class Scan(Base):
    __tablename__ = "scans"
    __table_args__ = (
        CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED')", name="ck_scans_status"),
        CheckConstraint(
            "jsonb_typeof(account_ids) = 'array' AND jsonb_array_length(account_ids) > 0",
            name="ck_scans_account_ids",
        ),
        CheckConstraint(
            "(status = 'RUNNING' AND finished_at IS NULL) OR "
            "(status IN ('COMPLETED', 'FAILED') AND finished_at IS NOT NULL)",
            name="ck_scans_lifecycle",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at", name="ck_scans_timestamps"
        ),
        Index("ix_scans_started_at", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    status: Mapped[str] = mapped_column(String(16), server_default="RUNNING")
    account_ids: Mapped[list[str]] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan", passive_deletes=True
    )
