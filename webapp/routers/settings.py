from fastapi import APIRouter, Depends

from schemas.requests import (
    ResolutionRequest,
    NegativePromptRequest,
    ArtistChainRequest,
    PartRequest,
    SettingsResponse,
)
from services.workflow_manager import wm
from dependencies import get_current_user_id

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(user_id: str = Depends(get_current_user_id)):
    s = wm.get_user_settings(user_id)
    return SettingsResponse(
        resolution=s["resolution"],
        workflow=s["workflow"],
        negative_prompt=s["negative_prompt"],
        artist_chain=s.get("artist_chain", ""),
        active_loras=s["active_loras"],
        part1=s.get("part1", [832, 608, 0, 0]),
        part2=s.get("part2", [832, 608, 832, 0]),
    )


@router.put("/settings/resolution")
async def set_resolution(req: ResolutionRequest, user_id: str = Depends(get_current_user_id)):
    wm.set_resolution(user_id, req.width, req.height)
    return {"status": "ok", "width": req.width, "height": req.height}


@router.put("/settings/negative_prompt")
async def set_negative_prompt(req: NegativePromptRequest, user_id: str = Depends(get_current_user_id)):
    wm.set_negative_prompt(user_id, req.text)
    return {"status": "ok", "negative_prompt": req.text}


@router.put("/settings/artist_chain")
async def set_artist_chain(req: ArtistChainRequest, user_id: str = Depends(get_current_user_id)):
    wm.set_artist_chain(user_id, req.text)
    return {"status": "ok", "artist_chain": req.text}


@router.put("/settings/part1")
async def set_part1(req: PartRequest, user_id: str = Depends(get_current_user_id)):
    wm.set_part1(user_id, [req.w, req.h, req.x, req.y])
    return {"status": "ok", "part1": [req.w, req.h, req.x, req.y]}


@router.put("/settings/part2")
async def set_part2(req: PartRequest, user_id: str = Depends(get_current_user_id)):
    wm.set_part2(user_id, [req.w, req.h, req.x, req.y])
    return {"status": "ok", "part2": [req.w, req.h, req.x, req.y]}
