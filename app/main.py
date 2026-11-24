import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.checks import router as checks_router
from app.api.health import router as health_router
from app.api.scans import router as scans_router
from app.core.config import get_settings
from app.db.session import check_database, close_database, session_factory
from app.services.scan_service import recover_interrupted_scans

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        try:
            await check_database()
        except Exception:
            # Avoid exposing DATABASE_URL or driver messages containing credentials.
            logger.error("PostgreSQL is unavailable. Check DATABASE_URL and database health.")
            raise RuntimeError("Database startup check failed") from None
        app.state.session_factory = session_factory
        await recover_interrupted_scans(session_factory)
        yield
    finally:
        await close_database()


app = FastAPI(
    title="Mini Gauntlet API",
    description="Inventory-based multi-cloud security scans, findings and posture scores.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(health_router, prefix="/api")

app.include_router(checks_router, prefix="/api")
app.include_router(scans_router, prefix="/api")
