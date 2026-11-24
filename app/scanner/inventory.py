import json
from pathlib import Path

from app.scanner.checks.common import Malformed, items, obj, string, timestamp
from app.scanner.types import Snapshot


class InventoryError(ValueError):
    pass


def load_inventory(path: Path) -> Snapshot:
    try:
        data = obj(json.loads(path.read_text(encoding="utf-8")), "inventory")
        taken_at = timestamp(data.get("snapshot_taken_at"), "snapshot_taken_at")
        accounts = items(data.get("accounts"), "accounts")
        if not accounts:
            raise Malformed("Inventory contains no accounts")
        seen = set()
        for raw in accounts:
            account = obj(raw, "account")
            account_id = string(account.get("account_id"), "account_id")
            if account_id.casefold() in seen:
                raise Malformed("Duplicate account ID")
            seen.add(account_id.casefold())
            if account.get("provider") not in ("aws", "azure", "gcp"):
                raise Malformed("Unsupported provider")
            latency = account.get("simulated_latency_ms")
            if type(latency) is not int or latency < 0:
                raise Malformed("simulated_latency_ms must be a nonnegative integer")
        return Snapshot(taken_at, accounts)
    except (OSError, ValueError, TypeError) as exc:
        raise InventoryError(
            "Inventory could not be read or is invalid; check INVENTORY_PATH."
        ) from exc
