"""PostgreSQL integration tests, isolated in a temporary schema.

Run with TEST_DATABASE_URL set to opt in; no existing application tables are changed.
"""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import Finding, Scan


@pytest.fixture
def connection(schema_engine):
    with schema_engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


def test_migration_matches_models(connection):
    assert set(inspect(connection).get_table_names()) == {"scans", "findings", "alembic_version"}
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    assert compare_metadata(context, Base.metadata) == []


def test_orm_roundtrip_and_database_cascade(connection):
    with Session(connection) as session:
        scan = Scan(account_ids=["123456789012"])
        scan.findings.append(
            Finding(
                check_id="AWS-S3-01",
                title="Bucket blocks public access",
                provider="aws",
                account_id="123456789012",
                region="us-east-1",
                resource_id="test-bucket",
                status="PASS",
                severity="HIGH",
                details="All public access settings enabled.",
            )
        )
        session.add(scan)
        session.flush()
        assert scan.id is not None
        assert scan.status == "RUNNING"
        assert scan.started_at.tzinfo is not None
        finding_id = scan.findings[0].id
        assert session.get(Finding, finding_id).scan_id == scan.id
        connection.execute(text("DELETE FROM scans WHERE id = :id"), {"id": scan.id})
        assert connection.scalar(text("SELECT count(*) FROM findings")) == 0


def test_account_level_permission_finding(connection):
    scan_id = connection.scalar(
        text("INSERT INTO scans (account_ids) VALUES ('[\"dev\"]') RETURNING id")
    )
    connection.execute(
        text(
            "INSERT INTO findings "
            "(scan_id, check_id, title, provider, account_id, status, severity, details) "
            "VALUES (:scan_id, 'AWS-IAM-01', 'MFA', 'aws', 'dev', "
            "'CANNOT_SCAN', 'HIGH', 'AccessDenied')"
        ),
        {"scan_id": scan_id},
    )
    assert connection.scalar(text("SELECT resource_id FROM findings")) is None


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO scans (account_ids) VALUES ('[]')",
        "INSERT INTO scans (account_ids, status) VALUES ('[\"dev\"]', 'INVALID')",
        "INSERT INTO scans (account_ids, status) VALUES ('[\"dev\"]', 'COMPLETED')",
        "INSERT INTO scans (account_ids, finished_at) VALUES ('[\"dev\"]', now())",
        "INSERT INTO findings (scan_id, check_id, title, provider, account_id, "
        "resource_id, status, severity, details) "
        "VALUES (gen_random_uuid(), 'X', 'X', 'aws', 'dev', 'resource', 'PASS', 'HIGH', 'X')",
    ],
)
def test_invalid_records_are_rejected(connection, statement):
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(text(statement))


def test_upgrade_is_repeatable_and_downgrade_works(connection):
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    assert inspect(connection).get_table_names() == ["alembic_version"]
    command.upgrade(config, "head")
    assert set(inspect(connection).get_table_names()) == {"scans", "findings", "alembic_version"}


@pytest.mark.parametrize(
    "invalid",
    [
        {"severity": "URGENT"},
        {"status": "UNKNOWN"},
        {"provider": "other"},
        {"resource_id": None},
    ],
)
def test_finding_constraints(connection, invalid):
    scan_id = connection.scalar(
        text("INSERT INTO scans (account_ids) VALUES ('[\"dev\"]') RETURNING id")
    )
    values = dict(
        scan_id=scan_id,
        check_id="AWS-S3-01",
        title="Public access",
        provider="aws",
        account_id="dev",
        resource_id="test-bucket",
        status="PASS",
        severity="HIGH",
        details="Test",
    )
    values.update(invalid)
    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(Finding.__table__.insert().values(**values))


def test_exported_sql_creates_complete_schema(connection):
    schema = f"test_export_{uuid4().hex}"
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
    # Keep the artifact's statements within the test's rollback transaction.
    script = Path("artifacts/schema.sql").read_text().replace("BEGIN;", "").replace("COMMIT;", "")
    connection.exec_driver_sql(script)
    assert set(inspect(connection).get_table_names(schema=schema)) == {
        "scans",
        "findings",
        "alembic_version",
    }
    assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
