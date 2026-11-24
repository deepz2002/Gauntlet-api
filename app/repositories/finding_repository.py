from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Finding


async def get_findings(
    session: AsyncSession, scan_id: UUID, filters: dict[str, str | None], page: int, page_size: int
) -> tuple[list[Finding], int]:
    conditions = [Finding.scan_id == scan_id]
    for field, value in filters.items():
        if value is not None:
            conditions.append(func.lower(getattr(Finding, field)) == value.lower())
    total = await session.scalar(select(func.count()).select_from(Finding).where(*conditions))
    # Explicit ranks implement the assignment order; UUID breaks otherwise identical ties.
    query = (
        select(Finding)
        .where(*conditions)
        .order_by(
            case({"FAIL": 0, "CANNOT_SCAN": 1, "PASS": 2}, value=Finding.status, else_=3),
            case(
                {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}, value=Finding.severity, else_=4
            ),
            Finding.check_id,
            Finding.resource_id.asc().nullsfirst(),
            Finding.id,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list((await session.scalars(query)).all()), total or 0
