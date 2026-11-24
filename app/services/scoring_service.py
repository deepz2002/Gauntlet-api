from collections import defaultdict


def posture_score(passed: int, failed: int) -> float | None:
    # Unevaluable findings never enter the denominator; no evaluated findings means N/A.
    return round(100 * passed / (passed + failed), 1) if passed + failed else None


def summarize(rows: list, account_ids: list[str]) -> dict:
    counts = dict(PASS=0, FAIL=0, CANNOT_SCAN=0)
    severities = dict(CRITICAL=0, HIGH=0, MEDIUM=0, LOW=0)
    accounts = defaultdict(lambda: dict(PASS=0, FAIL=0, CANNOT_SCAN=0))
    for account_id, status, severity, count in rows:
        counts[status] += count
        accounts[account_id][status] += count
        if status == "FAIL":
            severities[severity] += count
    return dict(
        score=posture_score(counts["PASS"], counts["FAIL"]),
        counts=counts,
        fail_counts_by_severity=severities,
        account_scores={
            key: posture_score(accounts[key]["PASS"], accounts[key]["FAIL"]) for key in account_ids
        },
    )
