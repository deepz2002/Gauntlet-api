from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.repositories import finding_repository, scan_repository
from app.scanner.inventory import InventoryError
from app.schemas.scan import FindingsPage, ScanResponse, StartScan
from app.services import scan_service

router = APIRouter(tags=["Scans"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/scans", response_model=ScanResponse, status_code=202)
async def start_scan(
    request: Request, background: BackgroundTasks, session: Session, body: StartScan | None = None
) -> ScanResponse:
    try:
        scan = await scan_service.create_scan(session, body.account_ids if body else None)
    except InventoryError as exc:
        raise HTTPException(503, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    background.add_task(scan_service.execute_scan, scan.id, request.app.state.session_factory)
    return (await scan_service.describe_scans(session, [scan]))[0]


@router.get("/scans", response_model=list[ScanResponse])
async def list_scans(session: Session) -> list[ScanResponse]:
    return await scan_service.describe_scans(session, await scan_repository.get_scans(session))


@router.get("/scans/{scan_id}", response_model=ScanResponse)
async def scan_details(scan_id: UUID, session: Session) -> ScanResponse:
    scan = await scan_repository.get_scan(session, scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found")
    return (await scan_service.describe_scans(session, [scan]))[0]


@router.get("/scans/{scan_id}/findings", response_model=FindingsPage)
async def findings(
    scan_id: UUID,
    session: Session,
    status: str | None = None,
    severity: str | None = None,
    provider: str | None = None,
    account_id: str | None = None,
    check_id: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> FindingsPage:
    if await scan_repository.get_scan(session, scan_id) is None:
        raise HTTPException(404, "Scan not found")
    rows, total = await finding_repository.get_findings(
        session,
        scan_id,
        dict(
            status=status,
            severity=severity,
            provider=provider,
            account_id=account_id,
            check_id=check_id,
        ),
        page,
        page_size,
    )
    return FindingsPage(items=rows, total=total, page=page, page_size=page_size)
