from fastapi import APIRouter, Depends

from schemas.requests import QuotaResponse
from services.workflow_manager import wm
from dependencies import get_current_user_id

router = APIRouter(tags=["quota"])


@router.get("/quota", response_model=QuotaResponse)
async def get_quota(user_id: str = Depends(get_current_user_id)):
    s = wm.get_user_settings(user_id)
    return QuotaResponse(
        limit=s["limit_count"],
        used=s["used_today"],
        remaining=s["limit_count"] - s["used_today"],
    )
