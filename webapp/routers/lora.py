from fastapi import APIRouter, Depends

from schemas.requests import LoraAddRequest, LoraRemoveRequest, LoraListResponse
from services.workflow_manager import wm
from dependencies import get_current_user_id

router = APIRouter(tags=["lora"])


@router.get("/lora", response_model=LoraListResponse)
async def get_lora_list(user_id: str = Depends(get_current_user_id)):
    settings = wm.get_user_settings(user_id)
    workflow = settings.get("workflow", "discord_anima_v2")
    lora_dict = wm.get_lora_list(workflow)
    active = settings.get("active_loras", {})
    label = "Anima" if "anima" in workflow else "SDXL"
    return LoraListResponse(available=lora_dict, active=active, workflow_label=label)


@router.post("/lora/add")
async def add_lora(req: LoraAddRequest, user_id: str = Depends(get_current_user_id)):
    result_name = wm.add_lora(user_id, req.name, req.weight)
    if result_name:
        return {"status": "ok", "name": result_name, "weight": req.weight}
    return {"status": "error", "detail": f"Lora not found: {req.name}"}


@router.delete("/lora/remove")
async def remove_lora(req: LoraRemoveRequest, user_id: str = Depends(get_current_user_id)):
    success = wm.remove_lora(user_id, req.name)
    if success:
        return {"status": "ok", "name": req.name}
    settings = wm.get_user_settings(user_id)
    return {"status": "error", "detail": f"Lora not active: {req.name}", "active": list(settings["active_loras"].keys())}


@router.post("/lora/reset")
async def reset_lora(user_id: str = Depends(get_current_user_id)):
    wm.clear_loras(user_id)
    return {"status": "ok"}
