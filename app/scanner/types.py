from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

FindingStatus = Literal["PASS", "FAIL", "CANNOT_SCAN"]
Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
Provider = Literal["aws", "azure", "gcp"]


@dataclass(frozen=True)
class Outcome:
    status: FindingStatus
    details: str


@dataclass(frozen=True)
class Check:
    check_id: str
    title: str
    provider: Provider
    severity: Severity
    collection: str
    resource_id_field: str
    evaluator: Callable[[dict, datetime], Outcome]


@dataclass(frozen=True)
class Snapshot:
    taken_at: datetime
    accounts: list[dict]
