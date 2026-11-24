import asyncio
import logging

from app.scanner.checks.common import Malformed, items, obj, string
from app.scanner.registry import CHECKS
from app.scanner.types import Check, Outcome, Snapshot

logger = logging.getLogger(__name__)


def finding(check: Check, account: dict, outcome: Outcome, resource=None) -> dict:
    resource = resource if isinstance(resource, dict) else {}
    identity = resource.get(check.resource_id_field)
    return dict(
        check_id=check.check_id,
        title=check.title,
        provider=check.provider,
        account_id=account["account_id"],
        region=resource.get("region") if isinstance(resource.get("region"), str) else None,
        resource_id=identity if isinstance(identity, str) and identity.strip() else None,
        status=outcome.status,
        severity=check.severity,
        details=outcome.details,
    )


async def scan_accounts(snapshot: Snapshot, account_ids: list[str], workers: int = 4) -> list[dict]:
    if workers < 1:
        raise ValueError("workers must be positive")
    semaphore = asyncio.Semaphore(workers)

    async def scan_account(account):
        # Holding the worker slot during latency limits concurrent cloud requests too.
        async with semaphore:
            await asyncio.sleep(account["simulated_latency_ms"] / 1000)
            results = []
            for check in CHECKS:
                if check.provider != account["provider"]:
                    continue
                try:
                    errors = obj(account.get("errors"), "errors")
                    if check.collection in errors:
                        outcome = Outcome(
                            "CANNOT_SCAN", f"{check.collection}: {errors[check.collection]}"
                        )
                        results.append(finding(check, account, outcome))
                        continue
                    resources = obj(account.get("resources"), "resources")
                    if check.collection not in resources:
                        continue
                    records = items(resources[check.collection], check.collection)
                except Malformed as exc:
                    logger.warning(
                        "Malformed collection for %s/%s: %s",
                        account["account_id"],
                        check.check_id,
                        exc,
                    )
                    results.append(finding(check, account, Outcome("CANNOT_SCAN", str(exc))))
                    continue
                for raw in records:
                    try:
                        resource = obj(raw, "resource")
                        string(resource.get(check.resource_id_field), check.resource_id_field)
                        outcome = check.evaluator(resource, snapshot.taken_at)
                        if not isinstance(outcome, Outcome):
                            raise TypeError("Check evaluator must return an Outcome")
                    except Malformed as exc:
                        outcome = Outcome("CANNOT_SCAN", str(exc))
                    except Exception:
                        logger.exception(
                            "Check execution failed: %s/%s", account["account_id"], check.check_id
                        )
                        outcome = Outcome("CANNOT_SCAN", "Unexpected check evaluation error.")
                    if outcome.status == "CANNOT_SCAN":
                        logger.warning(
                            "Cannot scan %s/%s: %s",
                            account["account_id"],
                            check.check_id,
                            outcome.details,
                        )
                    results.append(finding(check, account, outcome, raw))
            return results

    batches = await asyncio.gather(
        *(scan_account(a) for a in snapshot.accounts if a["account_id"] in account_ids)
    )
    return [record for batch in batches for record in batch]
