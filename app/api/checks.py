from fastapi import APIRouter

from app.scanner.registry import CHECKS
from app.schemas.scan import CheckResponse

router = APIRouter(tags=["Checks"])


@router.get("/checks", response_model=list[CheckResponse])
async def checks() -> list[CheckResponse]:
    return [
        CheckResponse(**{key: getattr(check, key) for key in CheckResponse.model_fields})
        for check in CHECKS
    ]
