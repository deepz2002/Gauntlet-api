"""Create scan history and findings.

Revision ID: 0001
Revises: None
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scans",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("status", sa.String(16), server_default="RUNNING", nullable=False),
        sa.Column("account_ids", postgresql.JSONB(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('RUNNING', 'COMPLETED', 'FAILED')", name="ck_scans_status"),
        sa.CheckConstraint(
            "jsonb_typeof(account_ids) = 'array' AND jsonb_array_length(account_ids) > 0",
            name="ck_scans_account_ids",
        ),
        sa.CheckConstraint(
            "(status = 'RUNNING' AND finished_at IS NULL) OR "
            "(status IN ('COMPLETED', 'FAILED') AND finished_at IS NOT NULL)",
            name="ck_scans_lifecycle",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at", name="ck_scans_timestamps"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_scans"),
    )
    op.create_index("ix_scans_started_at", "scans", ["started_at"])
    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("check_id", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("resource_id", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.CheckConstraint("status IN ('PASS', 'FAIL', 'CANNOT_SCAN')", name="ck_findings_status"),
        sa.CheckConstraint(
            "severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')", name="ck_findings_severity"
        ),
        sa.CheckConstraint("provider IN ('aws', 'azure', 'gcp')", name="ck_findings_provider"),
        sa.CheckConstraint(
            "resource_id IS NOT NULL OR status = 'CANNOT_SCAN'", name="ck_findings_resource_id"
        ),
        sa.ForeignKeyConstraint(
            ["scan_id"], ["scans.id"], name="fk_findings_scan_id_scans", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_findings"),
    )
    op.create_index(
        "ix_findings_scan_status_severity", "findings", ["scan_id", "status", "severity"]
    )
    op.create_index("ix_findings_scan_provider", "findings", ["scan_id", "provider"])
    op.create_index("ix_findings_scan_account", "findings", ["scan_id", "account_id"])
    op.create_index("ix_findings_scan_check", "findings", ["scan_id", "check_id"])


def downgrade() -> None:
    op.drop_table("findings")
    op.drop_table("scans")
