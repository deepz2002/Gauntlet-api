from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Finding, Scan


async def get_scan(session: AsyncSession, scan_id: UUID) -> Scan | None:
    return await session.get(Scan, scan_id)


async def get_scans(session: AsyncSession) -> list[Scan]:
    return list(
        (await session.scalars(select(Scan).order_by(Scan.started_at.desc(), Scan.id.desc()))).all()
    )


async def aggregate_findings(session: AsyncSession, scan_ids: list[UUID]) -> dict:
    grouped = defaultdict(list)
    if not scan_ids:
        return grouped
    query = (
        select(Finding.scan_id, Finding.account_id, Finding.status, Finding.severity, func.count())
        .where(Finding.scan_id.in_(scan_ids))
        .group_by(Finding.scan_id, Finding.account_id, Finding.status, Finding.severity)
    )
    for scan_id, account_id, status, severity, count in await session.execute(query):
        grouped[scan_id].append((account_id, status, severity, count))
    return grouped
