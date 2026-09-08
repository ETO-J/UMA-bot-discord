from fastapi import APIRouter, Depends

from auth import is_admin_user
from schemas.requests import QuotaResponse
from services.asset_library import asset_library
from services.workflow_manager import wm
from dependencies import get_current_user_id

router = APIRouter(tags=["quota"])


@router.get("/quota", response_model=QuotaResponse)
async def get_quota(user_id: str = Depends(get_current_user_id)):
    s = wm.get_user_settings(user_id)
    asset_limit, asset_used, asset_enabled = asset_library.storage_quota(user_id)
    return QuotaResponse(
        limit=s["limit_count"],
        used=s["used_today"],
        remaining=s["limit_count"] - s["used_today"],
        asset_limit_bytes=asset_limit,
        asset_used_bytes=asset_used,
        asset_remaining_bytes=max(0, asset_limit - asset_used),
        asset_enabled=asset_enabled,
        is_admin=is_admin_user(user_id),
    )
