from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.scan import Scan


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint("status IN ('PASS', 'FAIL', 'CANNOT_SCAN')", name="ck_findings_status"),
        CheckConstraint(
            "severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')", name="ck_findings_severity"
        ),
        CheckConstraint("provider IN ('aws', 'azure', 'gcp')", name="ck_findings_provider"),
        CheckConstraint(
            "resource_id IS NOT NULL OR status = 'CANNOT_SCAN'",
            name="ck_findings_resource_id",
        ),
        Index("ix_findings_scan_status_severity", "scan_id", "status", "severity"),
        Index("ix_findings_scan_provider", "scan_id", "provider"),
        Index("ix_findings_scan_account", "scan_id", "account_id"),
        Index("ix_findings_scan_check", "scan_id", "check_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    scan_id: Mapped[UUID] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"))
    check_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(16))
    account_id: Mapped[str] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text)
    resource_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(16))
    details: Mapped[str] = mapped_column(Text)
    scan: Mapped["Scan"] = relationship(back_populates="findings")
