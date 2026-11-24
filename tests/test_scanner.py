import asyncio
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from app.scanner import engine
from app.scanner.inventory import InventoryError, load_inventory
from app.services.scoring_service import posture_score, summarize

INVENTORY = Path("data/inventory.json")


def test_assignment_snapshot_results(monkeypatch):
    snapshot = load_inventory(INVENTORY)
    original_sleep = asyncio.sleep

    async def no_latency(seconds):
        await original_sleep(0)

    monkeypatch.setattr(engine.asyncio, "sleep", no_latency)
    rows = asyncio.run(engine.scan_accounts(snapshot, [a["account_id"] for a in snapshot.accounts]))
    assert len(rows) == 49
    assert Counter(row["status"] for row in rows) == {"PASS": 27, "FAIL": 17, "CANNOT_SCAN": 5}
    permission_rows = [
        r for r in rows if r["account_id"] == "210987654321" and r["resource_id"] is None
    ]
    assert len(permission_rows) == 3
    assert any("AccessDenied" in r["details"] for r in permission_rows)
    assert any("UnauthorizedOperation" in r["details"] for r in permission_rows)
    assert posture_score(27, 17) == 61.4


@pytest.mark.parametrize("workers", [1, 2, 4])
def test_worker_limit_and_latency(monkeypatch, workers):
    snapshot = load_inventory(INVENTORY)
    active, peak, latencies = 0, 0, []
    original_sleep = asyncio.sleep

    async def observed_sleep(seconds):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        latencies.append(seconds)
        await original_sleep(0.001)
        active -= 1

    monkeypatch.setattr(engine.asyncio, "sleep", observed_sleep)
    asyncio.run(
        engine.scan_accounts(snapshot, [a["account_id"] for a in snapshot.accounts], workers)
    )
    assert peak == workers
    assert sorted(latencies) == [1, 1.5, 2.5, 3]


def test_missing_collections_and_malformed_resource(monkeypatch):
    snapshot = load_inventory(INVENTORY)
    account = dict(
        snapshot.accounts[0],
        simulated_latency_ms=0,
        resources={"s3_buckets": [None, {"name": "bad"}]},
    )
    rows = asyncio.run(
        engine.scan_accounts(replace(snapshot, accounts=[account]), [account["account_id"]])
    )
    assert len(rows) == 2
    assert all(r["status"] == "CANNOT_SCAN" for r in rows)


def test_unexpected_check_error_is_isolated(monkeypatch):
    snapshot = load_inventory(INVENTORY)
    account = dict(snapshot.accounts[0], simulated_latency_ms=0)
    original = engine.CHECKS[0]

    def broken(*args):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(engine, "CHECKS", (replace(original, evaluator=broken), *engine.CHECKS[1:]))
    rows = asyncio.run(
        engine.scan_accounts(replace(snapshot, accounts=[account]), [account["account_id"]])
    )
    assert len(rows) == 24
    assert all(r["status"] == "CANNOT_SCAN" for r in rows if r["check_id"] == "AWS-S3-01")
    assert any(r["status"] == "PASS" for r in rows)


def test_inventory_error(tmp_path):
    with pytest.raises(InventoryError):
        load_inventory(tmp_path / "missing.json")


def test_invalid_check_return_is_isolated(monkeypatch):
    snapshot = load_inventory(INVENTORY)
    account = dict(snapshot.accounts[0], simulated_latency_ms=0)
    monkeypatch.setattr(
        engine, "CHECKS", (replace(engine.CHECKS[0], evaluator=lambda *args: None),)
    )
    rows = asyncio.run(
        engine.scan_accounts(replace(snapshot, accounts=[account]), [account["account_id"]])
    )
    assert len(rows) == 3
    assert all(row["status"] == "CANNOT_SCAN" for row in rows)


def test_scoring_excludes_cannot_scan_and_does_not_average_accounts():
    result = summarize(
        [("a", "PASS", "LOW", 1), ("b", "FAIL", "HIGH", 9), ("a", "CANNOT_SCAN", "HIGH", 5)],
        ["a", "b", "c"],
    )
    assert result["score"] == 10
    assert result["account_scores"] == {"a": 100, "b": 0, "c": None}
    assert result["counts"]["CANNOT_SCAN"] == 5
    assert posture_score(0, 0) is None
