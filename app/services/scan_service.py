import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models import Finding, Scan
from app.repositories.scan_repository import aggregate_findings
from app.scanner.engine import scan_accounts
from app.scanner.inventory import load_inventory
from app.schemas.scan import ScanResponse
from app.services.scoring_service import summarize

logger = logging.getLogger(__name__)


async def recover_interrupted_scans(factory: async_sessionmaker[AsyncSession]) -> None:
    """With one API process, leftover RUNNING rows belong to interrupted jobs."""
    async with factory.begin() as session:
        await session.execute(
            update(Scan)
            .where(Scan.status == "RUNNING")
            .values(
                status="FAILED",
                finished_at=datetime.now(UTC),
                error_message=(
                    "API restarted before this background scan finished. Start a new scan."
                ),
            )
        )


async def create_scan(session: AsyncSession, selected_ids: list[str] | None) -> Scan:
    snapshot = await asyncio.to_thread(load_inventory, get_settings().inventory_path)
    available = [account["account_id"] for account in snapshot.accounts]
    account_ids = selected_ids if selected_ids is not None else available
    unknown = set(account_ids) - set(available)
    if unknown:
        raise ValueError("Unknown account IDs: " + ", ".join(sorted(unknown)))
    scan = Scan(account_ids=account_ids)
    session.add(scan)
    await session.commit()
    await session.refresh(scan)
    return scan


async def describe_scans(session: AsyncSession, scans: list[Scan]) -> list[ScanResponse]:
    aggregates = await aggregate_findings(session, [scan.id for scan in scans])
    return [
        ScanResponse(
            id=scan.id,
            status=scan.status,
            account_ids=scan.account_ids,
            started_at=scan.started_at,
            finished_at=scan.finished_at,
            error_message=scan.error_message,
            **summarize(aggregates[scan.id], scan.account_ids),
        )
        for scan in scans
    ]


async def execute_scan(scan_id: UUID, factory: async_sessionmaker[AsyncSession]) -> None:
    # A background job owns its sessions; it never reuses a closed request session.
    try:
        async with factory() as session:
            scan = await session.get(Scan, scan_id)
            if scan is None or scan.status != "RUNNING":
                return
            account_ids = list(scan.account_ids)
        snapshot = await asyncio.to_thread(load_inventory, get_settings().inventory_path)
        if set(account_ids) - {a["account_id"] for a in snapshot.accounts}:
            raise ValueError("Selected accounts disappeared from the inventory")
        records = await scan_accounts(snapshot, account_ids, get_settings().scan_worker_limit)
        async with factory.begin() as session:
            scan = await session.get(Scan, scan_id)
            if scan is None or scan.status != "RUNNING":
                return
            session.add_all(Finding(scan_id=scan_id, **record) for record in records)
            scan.status = "COMPLETED"
            scan.finished_at = datetime.now(UTC)
            # This transaction commits the findings and terminal state together.
    except Exception:
        logger.exception("Scan failed: %s", scan_id)
        try:
            async with factory.begin() as session:
                scan = await session.get(Scan, scan_id)
                if scan is not None and scan.status == "RUNNING":
                    scan.status = "FAILED"
                    scan.finished_at = datetime.now(UTC)
                    scan.error_message = (
                        "Scan failed while reading inventory or persisting results. "
                        "Check server logs."
                    )
        except Exception:
            logger.exception("Could not persist failed state for scan %s", scan_id)
