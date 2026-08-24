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
from services.task_queue import task_queue
from services.workflow_manager import wm

logger = logging.getLogger(__name__)

_WS_TIMEOUT = 1800.0
_QUEUE_CACHE_TTL = 2.0
_comfy_queue_cache: tuple[float, dict] | None = None

# --- Output move / sweep tuning ---
_MOVE_RETRY_SECONDS = 30.0
_MOVE_RETRY_INTERVAL = 1.0
_SWEEP_MIN_AGE_SECONDS = 60.0

# Strong references for fire-and-forget move tasks so the event loop never
# garbage-collects them mid-flight.
_move_tasks: set[asyncio.Task] = set()


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
    """Move a generated file out of the ComfyUI output dir, retrying on failure.

    Windows often briefly locks a freshly written file (antivirus scan,
    Explorer preview, the just-finished HTTP response), which raises
    WinError 32.  This function retries for ``_MOVE_RETRY_SECONDS`` instead of
    giving up after the first error.

    It is also safe when two services (webapp + Discord bot) race on the same
    file:
    - source missing + destination present  -> already moved, success
    - destination present + source present  -> the destination is overwritten
      with the freshly generated source (ComfyUI may reuse counter names after
      the previous file was moved away)
    """
    if subfolder:
        source_path = COMFYUI_OUTPUT_DIR / subfolder / filename
        dest_dir = IMAGE_SAVE_PATH / subfolder
        dest_dir.mkdir(parents=True, exist_ok=True)
    else:
        source_path = COMFYUI_OUTPUT_DIR / filename
        dest_dir = IMAGE_SAVE_PATH
    dest_path = dest_dir / filename

    deadline = time.monotonic() + _MOVE_RETRY_SECONDS
    last_error: Exception | None = None
    copied = False
    while time.monotonic() < deadline:
        if not source_path.exists():
            if dest_path.exists():
                # Another process (or a previous attempt) already moved it.
                _mark_moved(filename, subfolder)
                return True
            await asyncio.sleep(_MOVE_RETRY_INTERVAL)
            continue

        try:
            if dest_path.exists():
                # Destination collision: the fresh source must win, so copy
                # over the stale destination, then remove the source.
                if not copied:
                    await asyncio.to_thread(shutil.copy2, str(source_path), str(dest_path))
                    copied = True
                await asyncio.to_thread(source_path.unlink)
                logger.info("File moved (replaced existing): %s/%s", subfolder or ".", filename)
                _mark_moved(filename, subfolder)
                return True
            await asyncio.to_thread(shutil.move, str(source_path), str(dest_path))
            logger.info("File moved: %s/%s", subfolder or ".", filename)
            _mark_moved(filename, subfolder)
            return True
        except FileNotFoundError:
            # Lost the race: someone else moved/removed the source between
            # exists() and the move.  Only a success if the dest now exists.
            if dest_path.exists():
                _mark_moved(filename, subfolder)
                return True
            last_error = None
        except OSError as e:
            last_error = e
        except Exception as e:
            last_error = e
        await asyncio.sleep(_MOVE_RETRY_INTERVAL)

    logger.error(
        "Failed to move file %s after %.0fs%s: %s",
        filename,
        _MOVE_RETRY_SECONDS,
        f" (subfolder={subfolder})" if subfolder else "",
        last_error or "file never appeared",
    )
    return False


def _mark_moved(filename: str, subfolder: str = "") -> None:
    """Drop the registry entry once a generated file is safely archived."""
    try:
        task_queue.unregister_generated_file(filename, subfolder)
    except Exception as e:
        logger.warning("Failed to unregister moved file %s: %s", filename, e)


def _log_move_task_result(task: asyncio.Task) -> None:
    """Done-callback: surface crashes of the fire-and-forget move tasks."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Move task crashed: %s", exc)


def _spawn_move_task(filename: str, subfolder: str = "") -> None:
    """Fire-and-forget the output move while keeping a strong reference."""
    task = asyncio.create_task(move_generated_file(filename, subfolder))
    _move_tasks.add(task)
    task.add_done_callback(_move_tasks.discard)
    task.add_done_callback(_log_move_task_result)


async def sweep_leftover_outputs(min_age: float = _SWEEP_MIN_AGE_SECONDS) -> int:
    """Self-heal: move leftover files that the webapp/bot actually generated.

    Uses the ``generated_files`` registry (populated when each generation's
    outputs are handled) instead of filename prefixes, so videos or images
    produced by manually run local ComfyUI workflows — even ones sharing the
    same prefix — are never touched.  Files younger than *min_age* seconds
    are skipped so the move never races with ComfyUI writing/serving them.
    Returns the number of files moved.
    """
    try:
        registered = task_queue.get_generated_files()
    except Exception as e:
        logger.warning("Sweep: cannot read generated_files registry: %s", e)
        return 0
    if not registered:
        return 0
    by_subfolder: dict[str, list[str]] = {}
    for filename, subfolder in registered:
        by_subfolder.setdefault(subfolder or "", []).append(filename)
    moved = 0
    for subfolder, names in by_subfolder.items():
        base_dir = COMFYUI_OUTPUT_DIR / subfolder
        if not base_dir.is_dir():
            continue
        for filename in names:
            entry = base_dir / filename
            try:
                if not entry.is_file():
                    continue
                if time.time() - entry.stat().st_mtime < min_age:
                    continue
            except OSError:
                continue
            if await move_generated_file(filename, subfolder):
                moved += 1
    if moved:
        logger.info("Sweep: moved %d leftover file(s) from ComfyUI output", moved)
    return moved


def _comfyui_ws_url(client_id: str) -> str:
    base = COMFYUI_URL.rstrip("/")
    if base.startswith("https://"):
        ws_base = "wss://" + base[len("https://"):]
    elif base.startswith("http://"):
        ws_base = "ws://" + base[len("http://"):]
    else:
        ws_base = "ws://" + base
    return f"{ws_base}/ws?clientId={client_id}"


def _collect_outputs(output: dict, container: list[dict]) -> None:
    """Append every persisted output file from a ComfyUI output dict.

    Only files with ``type == "output"`` (SaveImage / SaveVideo) are kept;
    temp previews (PreviewImage) are skipped because they live in ComfyUI's
    temp dir and are not ours to move.  Duplicate (filename, subfolder)
    pairs are dropped.
    """
    if not isinstance(output, dict):
        return
    for key in ("images", "gifs", "videos"):
        for item in output.get(key) or []:
            if not isinstance(item, dict):
                continue
            if item.get("type", "output") != "output":
                continue
            filename = item.get("filename")
            if not filename:
                continue
            subfolder = item.get("subfolder", "") or ""
            if any(f["filename"] == filename and f["subfolder"] == subfolder for f in container):
                continue
            container.append(
                {"filename": filename, "subfolder": subfolder, "type": "output"}
            )


async def _listen_ws(ws, prompt_id: str) -> list[dict] | None:
    """Listen on the ComfyUI WebSocket for *prompt_id* completion.

    Returns a list of output file dicts (``filename`` / ``subfolder`` /
    ``type``) covering every persisted output node of the prompt, or
    ``None`` on failure / no output.  ``None`` is also returned when the
    connection drops or the time budget is exhausted before the prompt
    finishes, so the caller can fall back to HTTP ``/history`` polling.
    Previews (type "temp") are excluded.
    """
    file_infos: list[dict] = []
    completed = False
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
                    _collect_outputs(mdata.get("output", {}), file_infos)
                elif mtype == "executing" and mdata.get("node") is None:
                    completed = True
                    break
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
    return file_infos if completed else None


async def _poll_history(session: aiohttp.ClientSession, prompt_id: str) -> list[dict] | None:
    """Fallback: poll ComfyUI /history for completion.

    Returns a list of output file dicts (same shape as ``_listen_ws``), or
    ``None`` on failure / no output.
    """
    start = time.monotonic()
    while time.monotonic() - start < _WS_TIMEOUT:
        await asyncio.sleep(1)
        try:
            async with session.get(f"{COMFYUI_URL}/history/{prompt_id}") as history_resp:
                if history_resp.status != 200:
                    continue
                history_data = await history_resp.json()
                if prompt_id in history_data:
                    file_infos: list[dict] = []
                    outputs = history_data[prompt_id].get("outputs", {})
                    for out_node in outputs.values():
                        _collect_outputs(out_node, file_infos)
                    return file_infos
        except Exception as e:
            logger.error("Polling error for prompt %s: %s", prompt_id, e)
    logger.error("Polling timeout for prompt %s", prompt_id)
    return None


async def _download_output(session: aiohttp.ClientSession, file_infos: list[dict]) -> bytes | None:
    """Download the primary output and schedule the move of every output file.

    The first persisted output is returned to the caller; *all* persisted
    outputs (e.g. batch generations) are moved out of the ComfyUI output dir
    so nothing accumulates there.  Previews are already filtered out by
    ``_collect_outputs``.
    """
    if not file_infos:
        return None
    primary = file_infos[0]
    filename = primary["filename"]
    subfolder = primary.get("subfolder", "")
    file_type = primary.get("type", "output")
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
    except Exception as e:
        logger.error("Download exception: %s", e)
        return None
    for info in file_infos:
        try:
            task_queue.register_generated_file(info["filename"], info.get("subfolder", ""))
        except Exception as e:
            logger.warning("Failed to register generated file %s: %s", info["filename"], e)
        _spawn_move_task(info["filename"], info.get("subfolder", ""))
    return data


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
            if not file_info:
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
    denoise: float | None = None,
    source_image_b64: str | None = None,
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
            if denoise is not None:
                node_data["inputs"]["denoise"] = denoise
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
            if source_image_b64:
                # img2img / diff: upload the base image and point the workflow's
                # LoadImage node at it before encoding into the latent.
                filename = await _upload_image(session, source_image_b64)
                if not filename:
                    logger.error("Failed to upload diff source image")
                    return None
                load_node = config.get("load_image_node_id")
                if load_node and load_node in workflow_data:
                    workflow_data[load_node]["inputs"]["image"] = filename
                else:
                    logger.warning(
                        "Load image node %s not found for workflow %s",
                        load_node,
                        target_name,
                    )
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
        # Unique filename: concurrent uploads (video start/end frames, Flux2
        # source/reference images) must never overwrite each other, or a queued
        # task would load another user's image.
        form.add_field(
            "image",
            image_bytes,
            filename=f"webui_{uuid.uuid4().hex}.png",
            content_type="image/png",
        )
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


def _align_h3_frames(length: int) -> int:
    """Snap a frame count up to MiniMax H3's 17k+5 grid (124 = ~5s)."""
    n = max(5, int(length))
    while n % 17 != 5:
        n += 1
    return n


def _snap_h3_dim(value: int) -> int:
    """Snap a canvas dimension to the nearest multiple of 32 (H3 latent pad)."""
    return max(32, round(int(value) / 32.0) * 32)


async def generate_video(
    prompt: str,
    start_image_b64: str,
    end_image_b64: str | None,
    width: int,
    height: int,
    length: int,
    user_id: str,
    seed: int | None = None,
    on_prompt_submitted=None,
) -> bytes | None:
    config = WORKFLOW_CONFIGS["webui_video"]
    workflow_name = config.get("workflow_file", "webui_video")
    workflow_data = wm.load_workflow_data(workflow_name)
    if not workflow_data:
        logger.error("Cannot load %s workflow", workflow_name)
        return None

    video_node_id = config["video_node_id"]
    start_image_node_id = config["start_image_node_id"]
    end_image_node_id = config["end_image_node_id"]
    seed_node_id = config["seed_node_id"]
    prompt_field = config.get("prompt_field", "prompt")

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

            workflow_data[start_image_node_id]["inputs"]["image"] = start_filename

            if end_filename:
                workflow_data[end_image_node_id]["inputs"]["image"] = end_filename
            else:
                workflow_data[video_node_id]["inputs"].pop("last_frame", None)
                if end_image_node_id in workflow_data:
                    del workflow_data[end_image_node_id]

            node_inputs = workflow_data[video_node_id]["inputs"]
            node_inputs[prompt_field] = prompt
            # MiniMax H3's latent is width/16 x height/16 and patchify_video
            # needs both to be even, i.e. width/height must be multiples of 32.
            # Guard against any non-32-multiple dimension reaching ComfyUI.
            canvas_w = _snap_h3_dim(width)
            canvas_h = _snap_h3_dim(height)
            if (canvas_w, canvas_h) != (width, height):
                logger.info("H3 canvas snapped %sx%s -> %sx%s", width, height, canvas_w, canvas_h)
            node_inputs["width"] = canvas_w
            node_inputs["height"] = canvas_h
            node_inputs["length"] = _align_h3_frames(length)

            active_loras = wm.get_user_settings(user_id).get("active_loras", {})
            base_lora_id = config.get("base_lora_node_id")
            if base_lora_id and active_loras:
                model_source = list(config["model_source"])
                clip_source = list(config["clip_source"])
                start_id = config["lora_start_id"]
                injected = 0
                for lora_name, weight in active_loras.items():
                    lora_path = wm.find_lora_path(lora_name, "webui_video")
                    if not lora_path:
                        continue
                    node_id = str(start_id)
                    workflow_data[node_id] = {
                        "inputs": {
                            "lora_name": lora_path,
                            "strength_model": weight,
                            "strength_clip": weight,
                            "model": model_source,
                            "clip": clip_source,
                        },
                        "class_type": "LoraLoader",
                        "_meta": {"title": f"DynamicLora_{lora_name}"},
                    }
                    model_source = [node_id, 0]
                    clip_source = [node_id, 1]
                    start_id += 1
                    injected += 1
                if injected:
                    workflow_data[base_lora_id]["inputs"]["model"] = model_source
                    workflow_data[base_lora_id]["inputs"]["clip"] = clip_source
                    logger.info(
                        "Injected %d video LoRA(s) before base node %s", injected, base_lora_id
                    )

            actual_seed = seed if seed is not None else random.randint(1, 1000000000)
            workflow_data[seed_node_id]["inputs"]["noise_seed"] = actual_seed

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
