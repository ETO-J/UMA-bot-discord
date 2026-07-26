import json
import uuid
import asyncio
import random
import shutil
import time
import base64
import logging
import aiohttp

from config import (
    COMFYUI_URL,
    COMFYUI_OUTPUT_DIR,
    IMAGE_SAVE_PATH,
    WORKFLOW_CONFIGS,
    VIDEO_RESOLUTIONS,
    VIDEO_FPS,
)
from services.workflow_manager import wm

logger = logging.getLogger(__name__)

_WS_TIMEOUT = 600.0
_QUEUE_CACHE_TTL = 2.0
_comfy_queue_cache: tuple[float, dict] | None = None


async def fetch_comfyui_queue() -> dict:
    """Fetch the real ComfyUI prompt queue (short TTL cache).

    Returns ``{"running": [prompt_id, ...], "pending": [prompt_id, ...]}``.
    """
    global _comfy_queue_cache
    now = time.monotonic()
    if _comfy_queue_cache is not None and now - _comfy_queue_cache[0] < _QUEUE_CACHE_TTL:
        return _comfy_queue_cache[1]
    result = {"running": [], "pending": []}
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{COMFYUI_URL}/queue") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result["running"] = [e[1] for e in data.get("queue_running", []) if len(e) > 1]
                    result["pending"] = [e[1] for e in data.get("queue_pending", []) if len(e) > 1]
    except Exception as e:
        logger.warning("Failed to fetch ComfyUI queue: %s", e)
    _comfy_queue_cache = (now, result)
    return result


async def move_generated_file(filename: str, subfolder: str = "") -> bool:
    if subfolder:
        source_path = COMFYUI_OUTPUT_DIR / subfolder / filename
        dest_dir = IMAGE_SAVE_PATH / subfolder
        dest_dir.mkdir(parents=True, exist_ok=True)
    else:
        source_path = COMFYUI_OUTPUT_DIR / filename
        dest_dir = IMAGE_SAVE_PATH
    dest_path = dest_dir / filename
    max_wait, interval, waited = 30, 1, 0
    while waited < max_wait:
        if source_path.exists():
            try:
                shutil.move(str(source_path), str(dest_path))
                logger.info("File moved: %s/%s", subfolder or ".", filename)
                return True
            except Exception as e:
                logger.error("Failed to move file: %s", e)
                return False
        else:
            await asyncio.sleep(interval)
            waited += interval
    return False


def _comfyui_ws_url(client_id: str) -> str:
    base = COMFYUI_URL.rstrip("/")
    if base.startswith("https://"):
        ws_base = "wss://" + base[len("https://"):]
    elif base.startswith("http://"):
        ws_base = "ws://" + base[len("http://"):]
    else:
        ws_base = "ws://" + base
    return f"{ws_base}/ws?clientId={client_id}"


async def _listen_ws(ws, prompt_id: str) -> dict | None:
    """Listen on the ComfyUI WebSocket for *prompt_id* completion.

    Returns a dict with ``filename``, ``subfolder``, ``type`` keys,
    or ``None`` on failure / no output.
    """
    file_info = None
    start = time.monotonic()
    try:
        while True:
            remaining = _WS_TIMEOUT - (time.monotonic() - start)
            if remaining <= 0:
                logger.error("WS timeout for prompt %s", prompt_id)
                break
            msg = await asyncio.wait_for(ws.receive(), timeout=remaining)
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                mtype = data.get("type", "")
                mdata = data.get("data", {})
                if mdata.get("prompt_id") != prompt_id:
                    continue
                if mtype == "executed":
                    output = mdata.get("output", {})
                    for key in ("images", "gifs", "videos"):
                        items = output.get(key)
                        if items:
                            file_info = {
                                "filename": items[0].get("filename"),
                                "subfolder": items[0].get("subfolder", ""),
                                "type": items[0].get("type", "output"),
                            }
                            break
                elif mtype == "executing" and mdata.get("node") is None:
                    return file_info
                elif mtype in ("execution_error", "execution_interrupted"):
                    logger.error("ComfyUI %s for prompt %s: %s", mtype, prompt_id, mdata)
                    return None
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                logger.error("WS closed/errored for prompt %s", prompt_id)
                break
    except asyncio.TimeoutError:
        logger.error("WS receive timeout for prompt %s", prompt_id)
    except Exception as e:
        logger.error("WS listen failed: %s", e)
    return file_info


async def _poll_history(session: aiohttp.ClientSession, prompt_id: str) -> dict | None:
    """Fallback: poll ComfyUI /history for completion."""
    start = time.monotonic()
    while time.monotonic() - start < _WS_TIMEOUT:
        await asyncio.sleep(1)
        try:
            async with session.get(f"{COMFYUI_URL}/history/{prompt_id}") as history_resp:
                if history_resp.status != 200:
                    continue
                history_data = await history_resp.json()
                if prompt_id in history_data:
                    outputs = history_data[prompt_id].get("outputs", {})
                    for out_node in outputs.values():
                        for key in ("images", "gifs", "videos"):
                            items = out_node.get(key)
                            if items:
                                return {
                                    "filename": items[0].get("filename"),
                                    "subfolder": items[0].get("subfolder", ""),
                                    "type": items[0].get("type", "output"),
                                }
                    return None
        except Exception as e:
            logger.error("Polling error for prompt %s: %s", prompt_id, e)
    logger.error("Polling timeout for prompt %s", prompt_id)
    return None


async def _download_output(session: aiohttp.ClientSession, file_info: dict) -> bytes | None:
    filename = file_info["filename"]
    subfolder = file_info.get("subfolder", "")
    file_type = file_info.get("type", "output")
    params = {"filename": filename}
    if subfolder:
        params["subfolder"] = subfolder
    if file_type:
        params["type"] = file_type
    try:
        async with session.get(f"{COMFYUI_URL}/view", params=params) as resp:
            if resp.status != 200:
                logger.error("Failed to download %s: HTTP %s", filename, resp.status)
                return None
            data = await resp.read()
            asyncio.create_task(move_generated_file(filename, subfolder))
            return data
    except Exception as e:
        logger.error("Download exception: %s", e)
        return None


async def _submit_and_wait(
    session: aiohttp.ClientSession,
    workflow_data: dict,
    client_id: str,
    on_prompt_submitted=None,
) -> bytes | None:
    """Submit *workflow_data* to ComfyUI and wait for the result image.

    Uses WebSocket for real-time completion detection, with automatic
    fall-back to HTTP ``/history`` polling when the WS connection fails.
    *on_prompt_submitted* (async callable) is invoked with the ComfyUI
    ``prompt_id`` right after the prompt is accepted.
    """
    payload = {"prompt": workflow_data, "client_id": client_id}
    ws_url = _comfyui_ws_url(client_id)

    ws = None
    try:
        ws = await session.ws_connect(ws_url, heartbeat=30)
    except Exception as e:
        logger.warning("WS connect failed, will use polling: %s", e)

    try:
        async with session.post(f"{COMFYUI_URL}/prompt", json=payload) as response:
            if response.status != 200:
                logger.error("ComfyUI Error: %s", await response.text())
                return None
            resp_json = await response.json()
            prompt_id = resp_json.get("prompt_id")

        if on_prompt_submitted is not None and prompt_id:
            try:
                await on_prompt_submitted(prompt_id)
            except Exception as e:
                logger.warning("on_prompt_submitted callback failed: %s", e)

        if ws is not None:
            file_info = await _listen_ws(ws, prompt_id)
            if file_info is None:
                logger.info("WS returned no output, falling back to polling for %s", prompt_id)
                file_info = await _poll_history(session, prompt_id)
        else:
            file_info = await _poll_history(session, prompt_id)
    finally:
        if ws is not None:
            await ws.close()

    if file_info:
        return await _download_output(session, file_info)
    return None


def _inject_hd_nodes(workflow_data: dict, config: dict) -> None:
    """Inject upscale + refine nodes into *workflow_data* for HD mode.

    Chain: existing VAEDecode -> ImageScaleBy -> VAEEncode -> KSampler(refine)
           -> VAEDecode -> SaveImage (redirected).

    Modifies *workflow_data* in-place.
    """
    hd_id = config["hd_start_id"]
    scale = config.get("hd_scale", 1.5)
    upscale_method = config.get("hd_upscale_method", "nearest-exact")
    hd_steps = config.get("hd_steps", 15)
    hd_cfg = config.get("hd_cfg", 5.0)
    hd_denoise = config.get("hd_denoise", 0.75)

    # Find the SaveImage node and the VAEDecode it currently references.
    save_node_id = None
    first_decode_id = None
    vae_source = None
    for nid, ndata in workflow_data.items():
        if ndata.get("class_type") == "SaveImage":
            save_node_id = nid
            images_ref = ndata.get("inputs", {}).get("images")
            if images_ref:
                first_decode_id = str(images_ref[0])
            break
    if not save_node_id or not first_decode_id:
        logger.warning("HD inject: SaveImage or first VAEDecode not found")
        return

    first_decode = workflow_data.get(first_decode_id)
    if not first_decode:
        logger.warning("HD inject: first VAEDecode node %s not found", first_decode_id)
        return

    # Reuse the VAE connection from the first VAEDecode.
    vae_source = first_decode["inputs"].get("vae")
    if not vae_source:
        logger.warning("HD inject: no VAE source on VAEDecode %s", first_decode_id)
        return

    # Find the first KSampler to replicate model / positive / negative connections.
    first_ksampler = None
    for nid, ndata in workflow_data.items():
        if ndata.get("class_type") == "KSampler":
            first_ksampler = ndata
            break
    if not first_ksampler:
        logger.warning("HD inject: no KSampler found")
        return

    model_src = first_ksampler["inputs"]["model"]
    positive_src = first_ksampler["inputs"]["positive"]
    negative_src = first_ksampler["inputs"]["negative"]

    scale_id = str(hd_id)
    encode_id = str(hd_id + 1)
    ksampler_id = str(hd_id + 2)
    decode_id = str(hd_id + 3)

    workflow_data[scale_id] = {
        "inputs": {
            "upscale_method": upscale_method,
            "scale_by": scale,
            "image": [first_decode_id, 0],
        },
        "class_type": "ImageScaleBy",
        "_meta": {"title": "HD Upscale"},
    }

    workflow_data[encode_id] = {
        "inputs": {
            "pixels": [scale_id, 0],
            "vae": list(vae_source),
        },
        "class_type": "VAEEncode",
        "_meta": {"title": "HD VAE Encode"},
    }

    workflow_data[ksampler_id] = {
        "inputs": {
            "seed": random.randint(1, 1000000000),
            "steps": hd_steps,
            "cfg": hd_cfg,
            "sampler_name": first_ksampler["inputs"].get("sampler_name", "er_sde"),
            "scheduler": first_ksampler["inputs"].get("scheduler", "simple"),
            "denoise": hd_denoise,
            "model": list(model_src),
            "positive": list(positive_src),
            "negative": list(negative_src),
            "latent_image": [encode_id, 0],
        },
        "class_type": "KSampler",
        "_meta": {"title": "HD Refine Sampler"},
    }

    workflow_data[decode_id] = {
        "inputs": {
            "samples": [ksampler_id, 0],
            "vae": list(vae_source),
        },
        "class_type": "VAEDecode",
        "_meta": {"title": "HD VAEDecode"},
    }

    # Redirect SaveImage to the final HD decode.
    workflow_data[save_node_id]["inputs"]["images"] = [decode_id, 0]
    logger.info("HD nodes injected: %s -> %s -> %s -> %s -> SaveImage(%s)",
                first_decode_id, scale_id, encode_id, ksampler_id, save_node_id)


async def generate_image(
    input_prompt: str,
    user_id: str,
    workflow_name: str = "discord_anima_v2",
    seed: int | None = None,
    sampler_name: str | None = None,
    scheduler: str | None = None,
    steps: int | None = None,
    cfg: float | None = None,
    hd_mode: bool = False,
    on_prompt_submitted=None,
) -> bytes | None:
    target_name = workflow_name or "discord_anima_v2"

    workflow_data = wm.load_workflow_data(target_name)
    if not workflow_data:
        logger.error("Cannot load workflow: %s", target_name)
        return None

    user_settings = wm.get_user_settings(user_id)
    active_loras = user_settings.get("active_loras", {})
    target_width, target_height = user_settings["resolution"]
    negative_text = user_settings.get("negative_prompt", "")
    artist_chain = user_settings.get("artist_chain", "")

    config = WORKFLOW_CONFIGS.get(target_name)
    if not config:
        config = WORKFLOW_CONFIGS["discord_anima_v2"]

    current_model_source = list(config["model_source"])
    current_clip_source = list(config["clip_source"])

    if config["supports_lora"] and active_loras:
        start_id = config["lora_start_id"]
        lora_type = config.get("lora_type", "LoraLoader")
        for lora_name, weight in active_loras.items():
            lora_path = wm.find_lora_path(lora_name, target_name)
            if not lora_path:
                continue
            node_id = str(start_id)
            if lora_type == "LoraLoaderModelOnly":
                workflow_data[node_id] = {
                    "inputs": {
                        "lora_name": lora_path,
                        "strength_model": weight,
                        "model": current_model_source,
                    },
                    "class_type": "LoraLoaderModelOnly",
                    "_meta": {"title": f"DynamicLora_{lora_name}"},
                }
                current_model_source = [node_id, 0]
            else:
                workflow_data[node_id] = {
                    "inputs": {
                        "lora_name": lora_path,
                        "strength_model": weight,
                        "strength_clip": weight,
                        "model": current_model_source,
                        "clip": current_clip_source,
                    },
                    "class_type": "LoraLoader",
                    "_meta": {"title": f"DynamicLora_{lora_name}"},
                }
                current_model_source = [node_id, 0]
                current_clip_source = [node_id, 1]
            start_id += 1

    pos_node_id = config["pos_node_id"]
    neg_node_id = config["neg_node_id"]
    bridging_model_node = config.get("bridging_model_node")
    bridging_pos_node = config.get("bridging_positive_node")
    prompt_pack_node = config.get("prompt_pack_node")

    for node_id, node_data in workflow_data.items():
        class_type = node_data.get("class_type")
        meta_title = node_data.get("_meta", {}).get("title", "").lower()

        if prompt_pack_node and node_id == prompt_pack_node:
            node_data["inputs"]["clip"] = current_clip_source
            node_data["inputs"][config.get("prompt_field", "base_prompt")] = input_prompt
            node_data["inputs"]["artist_chain"] = artist_chain

        if bridging_model_node and node_id == bridging_model_node:
            node_data["inputs"]["model"] = current_model_source

        if class_type == "KSampler":
            node_data["inputs"]["seed"] = seed if seed is not None else random.randint(1, 1000000000)
            if sampler_name:
                node_data["inputs"]["sampler_name"] = sampler_name
            if scheduler:
                node_data["inputs"]["scheduler"] = scheduler
            if steps is not None:
                node_data["inputs"]["steps"] = steps
            if cfg is not None:
                node_data["inputs"]["cfg"] = cfg
            node_data["inputs"]["negative"] = [neg_node_id, 0]
            if bridging_model_node:
                node_data["inputs"]["model"] = [bridging_model_node, 0]
                node_data["inputs"]["positive"] = [bridging_pos_node, 1]
            else:
                node_data["inputs"]["model"] = current_model_source
                node_data["inputs"]["positive"] = [pos_node_id, 0]

        if class_type == "CLIPTextEncode":
            node_data["inputs"]["clip"] = current_clip_source
            if pos_node_id and (node_id == pos_node_id or "positive" in meta_title):
                node_data["inputs"]["text"] = input_prompt
            elif node_id == neg_node_id or "negative" in meta_title:
                final_neg = negative_text if negative_text else "mosaic, low quality, bad quality, worst quality"
                node_data["inputs"]["text"] = final_neg

        if class_type == "EmptyLatentImage":
            node_data["inputs"]["width"] = target_width
            node_data["inputs"]["height"] = target_height

    if hd_mode and config.get("hd_enabled"):
        _inject_hd_nodes(workflow_data, config)

    client_id = str(uuid.uuid4())
    try:
        async with aiohttp.ClientSession() as session:
            return await _submit_and_wait(session, workflow_data, client_id, on_prompt_submitted)
    except Exception as e:
        logger.error("Draw exception: %s", e)
        return None


async def generate_multidraw_image(
    prompt1: str,
    prompt2: str,
    global_prompt: str,
    user_id: str,
    seed: int | None = None,
    sampler_name: str | None = None,
    scheduler: str | None = None,
    steps: int | None = None,
    cfg: float | None = None,
    on_prompt_submitted=None,
) -> bytes | None:
    user_settings = wm.get_user_settings(user_id)
    workflow_data = wm.load_workflow_data("multidraw")
    if not workflow_data:
        logger.error("Cannot load multidraw workflow")
        return None

    active_loras = user_settings.get("active_loras", {})
    negative_text = user_settings.get("negative_prompt", "")
    part1 = user_settings.get("part1", [832, 608, 0, 0])
    part2 = user_settings.get("part2", [832, 608, 832, 0])

    config = WORKFLOW_CONFIGS.get("multidraw", WORKFLOW_CONFIGS["discord"])
    current_model_source = list(config["model_source"])
    current_clip_source = list(config["clip_source"])

    if config["supports_lora"] and active_loras:
        start_id = config["lora_start_id"]
        lora_type = config.get("lora_type", "LoraLoader")
        for lora_name, weight in active_loras.items():
            lora_path = wm.find_lora_path(lora_name, "multidraw")
            if not lora_path:
                continue
            node_id = str(start_id)
            if lora_type == "LoraLoaderModelOnly":
                workflow_data[node_id] = {
                    "inputs": {
                        "lora_name": lora_path,
                        "strength_model": weight,
                        "model": current_model_source,
                    },
                    "class_type": "LoraLoaderModelOnly",
                    "_meta": {"title": f"DynamicLora_{lora_name}"},
                }
                current_model_source = [node_id, 0]
            else:
                workflow_data[node_id] = {
                    "inputs": {
                        "lora_name": lora_path,
                        "strength_model": weight,
                        "strength_clip": weight,
                        "model": current_model_source,
                        "clip": current_clip_source,
                    },
                    "class_type": "LoraLoader",
                    "_meta": {"title": f"DynamicLora_{lora_name}"},
                }
                current_model_source = [node_id, 0]
                current_clip_source = [node_id, 1]
            start_id += 1

    for node_id, node_data in workflow_data.items():
        class_type = node_data.get("class_type")
        meta_title = node_data.get("_meta", {}).get("title", "")

        if class_type == "KSampler":
            node_data["inputs"]["model"] = current_model_source
            node_data["inputs"]["seed"] = seed if seed is not None else random.randint(1, 1000000000)
            if sampler_name:
                node_data["inputs"]["sampler_name"] = sampler_name
            if scheduler:
                node_data["inputs"]["scheduler"] = scheduler
            if steps is not None:
                node_data["inputs"]["steps"] = steps
            if cfg is not None:
                node_data["inputs"]["cfg"] = cfg

        if class_type == "CLIPTextEncode":
            node_data["inputs"]["clip"] = current_clip_source
            if meta_title == "positive-\u5168\u5c40":
                node_data["inputs"]["text"] = f"{global_prompt}, SFW"
            elif meta_title == "positive-1":
                node_data["inputs"]["text"] = f"{prompt1}, SFW"
            elif meta_title == "positive-2":
                node_data["inputs"]["text"] = f"{prompt2}, SFW"
            elif meta_title == "negative":
                final_neg = negative_text if negative_text else "mosaic, low quality, bad quality, worst quality"
                node_data["inputs"]["text"] = final_neg

        if class_type == "ConditioningSetArea":
            if meta_title == "\u6761\u4ef6\u91c7\u6837\u533a\u57df":
                current_x = node_data["inputs"].get("x", 0)
                if current_x == 0:
                    node_data["inputs"]["width"] = part1[0]
                    node_data["inputs"]["height"] = part1[1]
                    node_data["inputs"]["x"] = part1[2]
                    node_data["inputs"]["y"] = part1[3]
                else:
                    node_data["inputs"]["width"] = part2[0]
                    node_data["inputs"]["height"] = part2[1]
                    node_data["inputs"]["x"] = part2[2]
                    node_data["inputs"]["y"] = part2[3]

        if class_type == "EmptyLatentImage":
            total_width = max(part1[0] + part1[2], part2[0] + part2[2])
            total_height = max(part1[1] + part1[3], part2[1] + part2[3])
            node_data["inputs"]["width"] = total_width
            node_data["inputs"]["height"] = total_height

    client_id = str(uuid.uuid4())
    try:
        async with aiohttp.ClientSession() as session:
            return await _submit_and_wait(session, workflow_data, client_id, on_prompt_submitted)
    except Exception as e:
        logger.error("Multidraw exception: %s", e)
        return None


async def _upload_image(session: aiohttp.ClientSession, image_b64: str) -> str | None:
    """Upload a base64-encoded image to ComfyUI and return the filename."""
    try:
        image_bytes = base64.b64decode(image_b64)
    except Exception as e:
        logger.error("Failed to decode base64 image: %s", e)
        return None
    try:
        form = aiohttp.FormData()
        form.add_field("image", image_bytes, filename="webui_upload.png", content_type="image/png")
        async with session.post(f"{COMFYUI_URL}/upload/image", data=form) as resp:
            if resp.status != 200:
                logger.error("Image upload failed: HTTP %s", resp.status)
                return None
            data = await resp.json()
            name = data.get("name")
            subfolder = data.get("subfolder", "")
            if not name:
                logger.error("Upload response missing name: %s", data)
                return None
            if subfolder:
                return f"{subfolder}/{name}"
            return name
    except Exception as e:
        logger.error("Image upload exception: %s", e)
        return None


async def generate_video(
    prompt: str,
    start_image_b64: str,
    end_image_b64: str | None,
    width: int,
    height: int,
    length: int,
    lora_enabled: bool,
    lora_strength: float,
    seed: int | None = None,
    negative_prompt: str | None = None,
    on_prompt_submitted=None,
) -> bytes | None:
    workflow_data = wm.load_workflow_data("webui_video")
    if not workflow_data:
        logger.error("Cannot load webui_video workflow")
        return None

    config = WORKFLOW_CONFIGS["webui_video"]
    video_node_id = config["video_node_id"]
    start_image_node_id = config["start_image_node_id"]
    end_image_node_id = config["end_image_node_id"]
    pos_node_id = config["pos_node_id"]
    neg_node_id = config["neg_node_id"]

    client_id = str(uuid.uuid4())
    try:
        async with aiohttp.ClientSession() as session:
            start_filename = await _upload_image(session, start_image_b64)
            if not start_filename:
                logger.error("Failed to upload start image")
                return None

            end_filename = None
            if end_image_b64:
                end_filename = await _upload_image(session, end_image_b64)
                if not end_filename:
                    logger.error("Failed to upload end image")
                    return None

            has_end_frame = end_filename is not None

            workflow_data[start_image_node_id]["inputs"]["image"] = start_filename

            if has_end_frame:
                workflow_data[end_image_node_id]["inputs"]["image"] = end_filename
            else:
                workflow_data[video_node_id]["class_type"] = config["video_node_class_first"]
                workflow_data[video_node_id]["inputs"].pop("end_image", None)
                if end_image_node_id in workflow_data:
                    del workflow_data[end_image_node_id]

            workflow_data[video_node_id]["inputs"]["width"] = width
            workflow_data[video_node_id]["inputs"]["height"] = height
            workflow_data[video_node_id]["inputs"]["length"] = length

            workflow_data[pos_node_id]["inputs"]["text"] = prompt

            if negative_prompt:
                workflow_data[neg_node_id]["inputs"]["text"] = negative_prompt

            lora_high_id = config["lora_high_node_id"]
            lora_low_id = config["lora_low_node_id"]
            high_chain_source = config["high_chain_source"]
            low_chain_source = config["low_chain_source"]
            high_chain_target = config["high_chain_target"]
            low_chain_target = config["low_chain_target"]

            if lora_enabled:
                workflow_data[lora_high_id]["inputs"]["strength_model"] = lora_strength
                workflow_data[lora_low_id]["inputs"]["strength_model"] = lora_strength
            else:
                if lora_high_id in workflow_data:
                    del workflow_data[lora_high_id]
                if lora_low_id in workflow_data:
                    del workflow_data[lora_low_id]
                workflow_data[high_chain_target]["inputs"]["model"] = list(high_chain_source)
                workflow_data[low_chain_target]["inputs"]["model"] = list(low_chain_source)

            actual_seed = seed if seed is not None else random.randint(1, 1000000000)
            for ks_id in config["ksampler_ids"]:
                workflow_data[ks_id]["inputs"]["noise_seed"] = actual_seed

            return await _submit_and_wait(session, workflow_data, client_id, on_prompt_submitted)
    except Exception as e:
        logger.error("Video generation exception: %s", e)
        return None


def _inject_flux2_reference_chain(workflow_data: dict, config: dict, ref_image_filename: str) -> None:
    """Inject a second image-reference chain into the Flux2 workflow.

    Adds: LoadImage -> ImageScaleToTotalPixels -> VAEEncode
          -> ReferenceLatent(pos) chained after existing reference_pos
          -> ReferenceLatent(neg) chained after existing reference_neg
    Rewires CFGGuider to use the new chained outputs.

    Node IDs start at ``config["ref_chain_start_id"]`` (3000).
    """
    rid = config["ref_chain_start_id"]
    vae_src = list(config["vae_source"])

    load_id = str(rid)
    scale_id = str(rid + 1)
    encode_id = str(rid + 2)
    ref_pos_id = str(rid + 3)
    ref_neg_id = str(rid + 4)

    workflow_data[load_id] = {
        "inputs": {"image": ref_image_filename},
        "class_type": "LoadImage",
        "_meta": {"title": "Ref Image"},
    }

    workflow_data[scale_id] = {
        "inputs": {
            "upscale_method": "lanczos",
            "megapixels": 1,
            "resolution_steps": 1,
            "image": [load_id, 0],
        },
        "class_type": "ImageScaleToTotalPixels",
        "_meta": {"title": "Ref Scale"},
    }

    workflow_data[encode_id] = {
        "inputs": {
            "pixels": [scale_id, 0],
            "vae": vae_src,
        },
        "class_type": "VAEEncode",
        "_meta": {"title": "Ref VAE Encode"},
    }

    # Chain: existing ref_pos -> new ref_pos
    workflow_data[ref_pos_id] = {
        "inputs": {
            "conditioning": [config["reference_pos_node_id"], 0],
            "latent": [encode_id, 0],
        },
        "class_type": "ReferenceLatent",
        "_meta": {"title": "Ref Latent (pos)"},
    }

    # Chain: existing ref_neg -> new ref_neg
    workflow_data[ref_neg_id] = {
        "inputs": {
            "conditioning": [config["reference_neg_node_id"], 0],
            "latent": [encode_id, 0],
        },
        "class_type": "ReferenceLatent",
        "_meta": {"title": "Ref Latent (neg)"},
    }

    # Rewire CFGGuider to the new chain ends
    guider_id = config["guider_node_id"]
    workflow_data[guider_id]["inputs"]["positive"] = [ref_pos_id, 0]
    workflow_data[guider_id]["inputs"]["negative"] = [ref_neg_id, 0]

    logger.info("Flux2 reference chain injected: %s..%s", load_id, ref_neg_id)


async def generate_flux2_edit_image(
    prompt: str,
    source_image_b64: str,
    reference_image_b64: str | None,
    user_id: str,
    negative_prompt: str | None = None,
    seed: int | None = None,
    steps: int | None = None,
    cfg: float | None = None,
    sampler_name: str | None = None,
    on_prompt_submitted=None,
) -> bytes | None:
    workflow_data = wm.load_workflow_data("discord_flux2_9b_edit")
    if not workflow_data:
        logger.error("Cannot load discord_flux2_9b_edit workflow")
        return None

    config = WORKFLOW_CONFIGS["discord_flux2_9b_edit"]

    client_id = str(uuid.uuid4())
    try:
        async with aiohttp.ClientSession() as session:
            # Upload source image (required)
            source_filename = await _upload_image(session, source_image_b64)
            if not source_filename:
                logger.error("Failed to upload source image")
                return None
            workflow_data[config["load_image_node_id"]]["inputs"]["image"] = source_filename

            # Upload and inject reference image (optional)
            if reference_image_b64:
                ref_filename = await _upload_image(session, reference_image_b64)
                if not ref_filename:
                    logger.error("Failed to upload reference image")
                    return None
                _inject_flux2_reference_chain(workflow_data, config, ref_filename)

            # Set prompts
            workflow_data[config["pos_node_id"]]["inputs"]["text"] = prompt
            neg_text = negative_prompt or ""
            workflow_data[config["neg_node_id"]]["inputs"]["text"] = neg_text

            # Set sampling parameters
            actual_seed = seed if seed is not None else random.randint(1, 1000000000)
            workflow_data[config["noise_node_id"]]["inputs"]["noise_seed"] = actual_seed

            if steps is not None:
                workflow_data[config["scheduler_node_id"]]["inputs"]["steps"] = steps
            if cfg is not None:
                workflow_data[config["guider_node_id"]]["inputs"]["cfg"] = cfg
            if sampler_name:
                workflow_data[config["sampler_select_node_id"]]["inputs"]["sampler_name"] = sampler_name

            return await _submit_and_wait(session, workflow_data, client_id, on_prompt_submitted)
    except Exception as e:
        logger.error("Flux2 edit generation exception: %s", e)
        return None
