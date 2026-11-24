from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.scanner.types import FindingStatus, Provider, Severity


class StartScan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_ids: list[str] | None = Field(default=None, min_length=1)

    @field_validator("account_ids")
    @classmethod
    def validate_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            if any(not item.strip() for item in value):
                raise ValueError("Account IDs cannot be blank")
            return list(dict.fromkeys(value))
        return value


class ScanResponse(BaseModel):
    id: UUID
    status: str
    account_ids: list[str]
    started_at: datetime
    finished_at: datetime | None
    error_message: str | None
    score: float | None
    counts: dict[str, int]
    fail_counts_by_severity: dict[str, int]
    account_scores: dict[str, float | None]


class FindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    scan_id: UUID
    check_id: str
    title: str
    provider: Provider
    account_id: str
    region: str | None
    resource_id: str | None
    status: FindingStatus
    severity: Severity
    details: str


class FindingsPage(BaseModel):
    items: list[FindingResponse]
    total: int
    page: int
    page_size: int


class CheckResponse(BaseModel):
    check_id: str
    title: str
    provider: Provider
    severity: Severity
    collection: str
    resource_id_field: str
