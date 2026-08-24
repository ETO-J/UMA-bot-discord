import os
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends

from schemas.requests import LoraAddRequest, LoraRemoveRequest, LoraListResponse
from services.workflow_manager import wm
from dependencies import get_current_user_id
from config import WORKFLOW_CONFIGS

router = APIRouter(tags=["lora"])

THUMB_EXTS = (".png", ".jpg", ".jpeg", ".webp")
THUMB_DIR = Path(__file__).resolve().parent.parent / "static" / "thumbnails"

# Cache of lora filename -> thumbnail URL, rebuilt when the directory changes.
_thumb_cache = {"mtime": None, "map": {}}


def _thumb_url_map() -> dict[str, str]:
    """Return {lora_filename: /thumbnails/<url-encoded actual file>}."""
    try:
        mtime = THUMB_DIR.stat().st_mtime
    except OSError:
        return {}
    if _thumb_cache["mtime"] == mtime:
        return _thumb_cache["map"]
    mapping = {}
    if THUMB_DIR.is_dir():
        with os.scandir(THUMB_DIR) as entries:
            for entry in entries:
                if entry.is_file() and entry.name.lower().endswith(THUMB_EXTS):
                    mapping[Path(entry.name).stem] = "/thumbnails/" + quote(entry.name, safe="")
    _thumb_cache["mtime"] = mtime
    _thumb_cache["map"] = mapping
    return mapping


@router.get("/lora", response_model=LoraListResponse)
async def get_lora_list(workflow: str | None = None, user_id: str = Depends(get_current_user_id)):
    settings = wm.get_user_settings(user_id)
    if workflow is None:
        workflow = settings.get("workflow", "discord_anima_v2")
    lora_dict = wm.get_lora_list(workflow)
    active = settings.get("active_loras", {})
    if workflow == "webui_video":
        label = "Video"
        fixed = set(WORKFLOW_CONFIGS.get("webui_video", {}).get("fixed_lora_names", []))
        if fixed:
            lora_dict = {
                cat: [name for name in files if name not in fixed]
                for cat, files in lora_dict.items()
            }
            lora_dict = {cat: files for cat, files in lora_dict.items() if files}
    else:
        label = "Anima" if "anima" in workflow else "SDXL"
    thumb_map = _thumb_url_map()
    thumb_urls = {
        name: thumb_map.get(name)
        for files in lora_dict.values()
        for name in files
    }
    return LoraListResponse(
        available=lora_dict,
        active=active,
        workflow_label=label,
        thumb_urls=thumb_urls,
    )


@router.post("/lora/add")
async def add_lora(req: LoraAddRequest, user_id: str = Depends(get_current_user_id)):
    result_name = wm.add_lora(user_id, req.name, req.weight, workflow=req.workflow)
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
