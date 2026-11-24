"""Exercise the actual Compose stack, without third-party Python dependencies."""

import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

BASE = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def request(path: str, body: dict | None = None) -> tuple[int, object]:
    req = Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def main() -> None:
    with urlopen(BASE + "/docs", timeout=10) as response:
        assert response.status == 200
    assert request("/api/health") == (200, {"status": "ok"})
    status, catalog = request("/api/checks")
    assert status == 200 and len(catalog) == 10
    started = time.monotonic()
    status, scan = request("/api/scans", {})
    assert status == 202 and scan["status"] == "RUNNING", scan
    assert time.monotonic() - started < 2.5, "POST waited for the background scan"
    scan_id = scan["id"]
    while scan["status"] == "RUNNING" and time.monotonic() - started < 20:
        time.sleep(0.5)
        status, scan = request(f"/api/scans/{scan_id}")
        assert status == 200
    assert scan["status"] == "COMPLETED", scan
    assert scan["counts"] == {"PASS": 27, "FAIL": 17, "CANNOT_SCAN": 5}, scan
    assert scan["score"] == 61.4, scan
    status, history = request("/api/scans")
    assert status == 200 and any(row["id"] == scan_id for row in history)
    status, page = request(
        f"/api/scans/{scan_id}/findings?status=fail&severity=critical&page_size=2"
    )
    assert status == 200 and page["total"] == 7 and len(page["items"]) == 2
    assert request(f"/api/scans/{uuid4()}")[0] == 404
    assert request("/api/scans", {"account_ids": []})[0] == 422
    print(f"Compose smoke passed: scan {scan_id}, 49 findings, score 61.4; all six APIs verified.")


if __name__ == "__main__":
    main()
