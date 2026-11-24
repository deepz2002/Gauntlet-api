import asyncio
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.main as main_module
from app.core.config import get_settings
from app.db.session import get_session
from app.scanner.inventory import load_inventory
from app.services import scan_service


@pytest.fixture
def client(schema_engine, tmp_path, monkeypatch):
    with schema_engine.begin() as connection:
        connection.execute(text("TRUNCATE findings, scans"))
        schema = connection.scalar(text("SELECT current_schema()"))
    engine = create_async_engine(
        schema_engine.url, poolclass=NullPool, connect_args={"options": f"-csearch_path={schema}"}
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session_override():
        async with factory() as session:
            yield session

    original = json.loads(get_settings().inventory_path.read_text())
    for account in original["accounts"]:
        account["simulated_latency_ms"] = 0
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps(original))
    monkeypatch.setenv("INVENTORY_PATH", str(inventory))
    get_settings.cache_clear()
    monkeypatch.setattr(main_module, "check_database", AsyncMock())
    monkeypatch.setattr(main_module, "close_database", AsyncMock())
    monkeypatch.setattr(main_module, "session_factory", factory)
    main_module.app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(main_module.app) as test_client:
            yield test_client
    finally:
        main_module.app.dependency_overrides.clear()
        get_settings.cache_clear()


def start(client, body=None):
    response = (
        client.post("/api/scans", json=body) if body is not None else client.post("/api/scans")
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "RUNNING"
    return response.json()["id"]


def test_catalog_and_complete_scan_contract(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    checks = client.get("/api/checks").json()
    assert len(checks) == 10
    scan_id = start(client)
    result = client.get(f"/api/scans/{scan_id}").json()
    assert result["status"] == "COMPLETED"
    assert result["counts"] == dict(PASS=27, FAIL=17, CANNOT_SCAN=5)
    assert result["score"] == 61.4
    assert result["fail_counts_by_severity"] == dict(CRITICAL=7, HIGH=7, MEDIUM=2, LOW=1)
    assert len(result["account_scores"]) == 4
    assert result["account_scores"]["123456789012"] == 60.9
    assert result["account_scores"]["210987654321"] == 66.7
    assert result["account_scores"]["8f14e45f-ceea-4e7a-9d3b-2f6c1a0b7d21"] == 57.1
    assert result["account_scores"]["example-corp-gcp"] == 63.6
    assert result["finished_at"] >= result["started_at"]
    history = client.get("/api/scans").json()
    assert history[0]["id"] == scan_id
    assert history[0]["counts"] == result["counts"]


def test_selection_and_newest_first(client):
    first = start(client, {"account_ids": ["example-corp-gcp"]})
    second = start(client, {"account_ids": ["123456789012", "123456789012"]})
    rows = client.get("/api/scans").json()
    assert [row["id"] for row in rows] == [second, first]
    result = client.get(f"/api/scans/{first}").json()
    assert result["account_ids"] == ["example-corp-gcp"]
    assert result["counts"] == dict(PASS=7, FAIL=4, CANNOT_SCAN=0)
    assert client.get(f"/api/scans/{second}").json()["account_ids"] == ["123456789012"]


def test_filters_are_combined_case_insensitive_and_paginated(client):
    scan_id = start(client)
    url = f"/api/scans/{scan_id}/findings"
    response = client.get(
        url,
        params=dict(
            status="fAiL",
            severity="hIgH",
            provider="AwS",
            account_id="123456789012",
            check_id="aws-s3-01",
            page_size=1,
        ),
    ).json()
    assert response["total"] == 1
    assert response["items"][0]["resource_id"] == "example-corp-public-downloads"
    assert client.get(url, params=dict(account_id="EXAMPLE-CORP-GCP")).json()["total"] == 11
    assert client.get(url, params=dict(status="not-a-status")).json()["total"] == 0
    first = client.get(url, params=dict(page=1, page_size=7)).json()
    second = client.get(url, params=dict(page=2, page_size=7)).json()
    assert first["total"] == second["total"] == 49
    assert len(first["items"]) == len(second["items"]) == 7
    assert not ({r["id"] for r in first["items"]} & {r["id"] for r in second["items"]})
    all_rows = client.get(url, params={"page_size": 100}).json()["items"]
    statuses = {"FAIL": 0, "CANNOT_SCAN": 1, "PASS": 2}
    severities = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

    def key(row):
        return (
            statuses[row["status"]],
            severities[row["severity"]],
            row["check_id"],
            row["resource_id"] or "",
            row["id"],
        )

    assert all_rows == sorted(all_rows, key=key)
    assert client.get(url, params=dict(page=99)).json()["items"] == []
    assert len(client.get("/api/scans").json()) == 1  # Reading findings never starts another scan.


@pytest.mark.parametrize(
    "body",
    [
        {"account_ids": []},
        {"account_ids": ["unknown"]},
        {"account_ids": [""]},
        {"account_ids": [123]},
        {"unexpected": True},
    ],
)
def test_invalid_account_selection(client, body):
    assert client.post("/api/scans", json=body).status_code == 422
    assert client.get("/api/scans").json() == []


@pytest.mark.parametrize(
    "params", [{"page": 0}, {"page_size": 0}, {"page_size": 101}, {"page": "bad"}]
)
def test_invalid_pagination(client, params):
    scan_id = start(client, {"account_ids": ["example-corp-gcp"]})
    assert client.get(f"/api/scans/{scan_id}/findings", params=params).status_code == 422


def test_missing_scan_returns_404(client):
    for suffix in ("", "/findings"):
        assert client.get(f"/api/scans/{uuid4()}{suffix}").status_code == 404
    assert client.get("/api/scans/not-a-uuid").status_code == 422


def test_background_inventory_failure_marks_failed(client, monkeypatch):
    def unavailable(path):
        raise OSError("unreadable snapshot")

    monkeypatch.setattr(scan_service, "load_inventory", unavailable)
    # Validation reads a valid snapshot, then the background task loses access to it.
    original_create = scan_service.create_scan

    async def create_then_break(session, ids):
        monkeypatch.setattr(scan_service, "load_inventory", load_inventory)
        scan = await original_create(session, ids)
        monkeypatch.setattr(scan_service, "load_inventory", unavailable)
        return scan

    monkeypatch.setattr(scan_service, "create_scan", create_then_break)
    scan_id = start(client)
    result = client.get(f"/api/scans/{scan_id}").json()
    assert result["status"] == "FAILED"
    assert result["error_message"]
    assert client.get(f"/api/scans/{scan_id}/findings").json()["total"] == 0


def test_missing_inventory_before_validation_returns_503(client, monkeypatch):
    monkeypatch.setenv("INVENTORY_PATH", "/does/not/exist.json")
    get_settings.cache_clear()
    assert client.post("/api/scans").status_code == 503


def test_empty_inventory_resources_return_null_scores(client):
    path = get_settings().inventory_path
    inventory = json.loads(path.read_text())
    for account in inventory["accounts"]:
        account["resources"] = {}
        account["errors"] = {}
    path.write_text(json.dumps(inventory))
    scan_id = start(client)
    result = client.get(f"/api/scans/{scan_id}").json()
    assert result["status"] == "COMPLETED"
    assert result["score"] is None
    assert all(score is None for score in result["account_scores"].values())
    page = client.get(f"/api/scans/{scan_id}/findings").json()
    assert page == {"items": [], "total": 0, "page": 1, "page_size": 25}


def test_persistence_failure_rolls_back_findings_and_marks_failed(client, monkeypatch):
    monkeypatch.setattr(
        scan_service,
        "scan_accounts",
        AsyncMock(
            return_value=[
                dict(
                    check_id="test",
                    title="test",
                    provider="invalid",
                    account_id="test",
                    resource_id="test",
                    status="PASS",
                    severity="HIGH",
                    details="test",
                )
            ]
        ),
    )
    scan_id = start(client)
    result = client.get(f"/api/scans/{scan_id}").json()
    assert result["status"] == "FAILED"
    assert client.get(f"/api/scans/{scan_id}/findings").json()["total"] == 0


def test_restart_recovery_marks_interrupted_scan_failed(client, schema_engine):
    with schema_engine.begin() as connection:
        scan_id = connection.scalar(
            text("INSERT INTO scans (account_ids) VALUES ('[\"example-corp-gcp\"]') RETURNING id")
        )
    asyncio.run(scan_service.recover_interrupted_scans(client.app.state.session_factory))
    result = client.get(f"/api/scans/{scan_id}").json()
    assert result["status"] == "FAILED"
    assert "restarted" in result["error_message"]
