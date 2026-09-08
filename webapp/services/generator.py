import json
import uuid
import asyncio
import random
import shutil
import time
import base64
import io
import math
import logging
import mimetypes
from pathlib import Path
import aiohttp
from PIL import Image

from config import (
    COMFYUI_URL,
    COMFYUI_OUTPUT_DIR,
    IMAGE_SAVE_PATH,
    WORKFLOW_CONFIGS,
    VIDEO_RESOLUTIONS,
    VIDEO_FPS,
    VIDEO_MEGAPIXELS,
    VIDEO_ASPECT_RATIOS,
    VIDEO_ASPECT_RATIO_LABELS,
)
from services.task_queue import task_queue
from services.workflow_manager import wm
from services.media_store import temp_media_store
from services.asset_library import asset_library

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


async def _download_single(session: aiohttp.ClientSession, info: dict) -> bytes | None:
    """Download one persisted ComfyUI output file."""
    filename = info["filename"]
    subfolder = info.get("subfolder", "")
    file_type = info.get("type", "output")
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
            return await resp.read()
    except Exception as e:
        logger.error("Download exception: %s", e)
        return None


def _preferred_output_order(file_infos: list[dict], prefer_ext: str | None = None) -> list[dict]:
    if prefer_ext:
        preferred_suffixes = set(prefer_ext.split(","))
        return sorted(
            file_infos,
            key=lambda info: (
                0 if Path(info["filename"]).suffix.lower().lstrip(".") in preferred_suffixes else 1
            ),
        )
    return list(file_infos)


async def _download_all_outputs(
    session: aiohttp.ClientSession,
    file_infos: list[dict],
    prefer_ext: str | None = None,
) -> list[tuple[dict, bytes]]:
    """Download every output, then schedule moves.

    All bytes are collected before any file is moved so callers can return
    both a video and its extracted last frame.
    """
    results: list[tuple[dict, bytes]] = []
    for info in _preferred_output_order(file_infos, prefer_ext):
        data = await _download_single(session, info)
        if data is not None:
            results.append((info, data))
    for info in file_infos:
        try:
            task_queue.register_generated_file(info["filename"], info.get("subfolder", ""))
        except Exception as e:
            logger.warning("Failed to register generated file %s: %s", info["filename"], e)
        _spawn_move_task(info["filename"], info.get("subfolder", ""))
    return results


async def _download_output(session: aiohttp.ClientSession, file_infos: list[dict]) -> bytes | None:
    """Download the primary output and schedule the move of every output file."""
    if not file_infos:
        return None
    results = await _download_all_outputs(session, file_infos)
    if not results:
        return None
    return results[0][1]


async def _submit_and_wait(
    session: aiohttp.ClientSession,
    workflow_data: dict,
    client_id: str,
    on_prompt_submitted=None,
) -> bytes | None:
    """Submit and return the first persisted output (backward-compatible)."""
    results = await _submit_and_wait_outputs(
        session,
        workflow_data,
        client_id,
        on_prompt_submitted,
    )
    return results[0][1] if results else None


async def _submit_and_wait_outputs(
    session: aiohttp.ClientSession,
    workflow_data: dict,
    client_id: str,
    on_prompt_submitted=None,
    prefer_ext: str | None = None,
) -> list[tuple[dict, bytes]]:
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
                return []
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
        return await _download_all_outputs(session, file_info, prefer_ext=prefer_ext)
    return []


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
    workflow_name: str = "discord_anima_fast",
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
    target_name = workflow_name or "discord_anima_fast"

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

    if config.get("builtin_hd"):
        # discord_anima_fast already carries its own upscale+refine chain wired
        # into the SaveImage node. HD mode leaves it intact; non-HD mode bypasses
        # it so the base decode is saved directly (the refine chain is pruned as
        # it becomes unreachable from the output).
        if not hd_mode:
            save_node = config.get("builtin_save_node")
            base_decode = config.get("builtin_base_decode_node")
            if save_node and base_decode and save_node in workflow_data and base_decode in workflow_data:
                workflow_data[save_node]["inputs"]["images"] = [base_decode, 0]
                logger.info(
                    "Builtin-HD %s: HD off, straight saves base decode %s",
                    target_name,
                    base_decode,
                )
    elif hd_mode and config.get("hd_enabled"):
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


async def _upload_media_file(
    session: aiohttp.ClientSession,
    path: Path,
    content_type: str = "application/octet-stream",
) -> str | None:
    """Upload any reference media file into the ComfyUI input directory."""
    try:
        data = path.read_bytes()
        ext = path.suffix.lower() or ".bin"
        form = aiohttp.FormData()
        form.add_field(
            "image",
            data,
            filename=f"webui_{uuid.uuid4().hex}{ext}",
            content_type=content_type,
        )
        async with session.post(f"{COMFYUI_URL}/upload/image", data=form) as resp:
            if resp.status != 200:
                logger.error("Media upload failed: HTTP %s", resp.status)
                return None
            response = await resp.json()
            name = response.get("name")
            subfolder = response.get("subfolder", "")
            if not name:
                return None
            return f"{subfolder}/{name}" if subfolder else name
    except Exception as e:
        logger.error("Media upload exception: %s", e)
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


def _canvas_from_ratio(ratio_w: float, ratio_h: float, quality: str) -> tuple[int, int]:
    """Mirror ComfyUI ResolutionSelector: ratio * megapixel target, snap to 32."""
    megapixels = VIDEO_MEGAPIXELS.get(quality, VIDEO_MEGAPIXELS["480p"])
    total_pixels = megapixels * 1024 * 1024
    scale = math.sqrt(total_pixels / max(0.01, ratio_w * ratio_h))
    width = _snap_h3_dim(round(ratio_w * scale / 32.0) * 32)
    height = _snap_h3_dim(round(ratio_h * scale / 32.0) * 32)
    return width, height


def _canvas_from_image_bytes(
    image_b64: str,
    quality: str,
    fallback: tuple[int, int],
) -> tuple[int, int]:
    try:
        data = base64.b64decode(image_b64)
        with Image.open(io.BytesIO(data)) as img:
            return _canvas_from_ratio(img.width, img.height, quality)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cannot derive canvas from first frame: %s", exc)
        return fallback


def _canvas_from_image_path(
    path: Path,
    quality: str,
    fallback: tuple[int, int],
) -> tuple[int, int]:
    try:
        with Image.open(path) as img:
            return _canvas_from_ratio(img.width, img.height, quality)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cannot derive canvas from reference image: %s", exc)
        return fallback


async def generate_video(
    prompt: str,
    start_image_b64: str,
    end_image_b64: str | None,
    width: int,
    height: int,
    length: int,
    user_id: str,
    quality: str = "480p",
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
            canvas_w, canvas_h = _canvas_from_image_bytes(
                start_image_b64,
                quality,
                (_snap_h3_dim(width), _snap_h3_dim(height)),
            )
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


def _reinforce_ref2va_prompt(
    prompt: str,
    image_count: int,
    video_count: int,
    audio_count: int,
) -> str:
    labels = [f"<Picture {i + 1}>" for i in range(image_count)]
    labels += [f"<Video {i + 1}>" for i in range(video_count)]
    labels += [f"<Audio {i + 1}>" for i in range(audio_count)]
    missing = [label for label in labels if label.lower() not in (prompt or "").lower()]
    body = (prompt or "").strip()
    if not missing:
        return body
    prefix = " ".join(missing)
    return f"{prefix}\n{body}" if body else prefix


async def generate_ref2va_video(
    *,
    prompt: str,
    reference_image_uploads: list[str],
    reference_video_uploads: list[str],
    reference_audio_uploads: list[str],
    reference_image_asset_ids: list[str],
    reference_video_asset_ids: list[str],
    reference_audio_asset_ids: list[str],
    width: int,
    height: int,
    length: int,
    aspect_ratio: str | None = None,
    user_id: str,
    quality: str = "480p",
    seed: int | None = None,
    output_last_frame: bool = False,
    on_prompt_submitted=None,
) -> dict:
    """Run the provided MiniMax H3 Ref2VA workflow.

    Returns ``{"video": bytes | None, "last_frame": bytes | None}``.
    """
    reference_image_uploads = reference_image_uploads or []
    reference_video_uploads = reference_video_uploads or []
    reference_audio_uploads = reference_audio_uploads or []
    reference_image_asset_ids = reference_image_asset_ids or []
    reference_video_asset_ids = reference_video_asset_ids or []
    reference_audio_asset_ids = reference_audio_asset_ids or []

    if len(reference_image_uploads) + len(reference_image_asset_ids) > 6:
        raise ValueError("参考图最多支持 6 张")
    if len(reference_video_uploads) + len(reference_video_asset_ids) > 2:
        raise ValueError("参考视频最多支持 2 段")
    if len(reference_audio_uploads) + len(reference_audio_asset_ids) > 3:
        raise ValueError("参考音频最多支持 3 段")

    config = WORKFLOW_CONFIGS["webui_video_ref"]
    workflow_file = config["workflow_file"]
    workflow_data = wm.load_workflow_data(workflow_file)
    if not workflow_data:
        logger.error("Cannot load %s workflow", workflow_file)
        return {"video": None, "last_frame": None}

    video_node_id = config["video_node_id"]
    video_node = workflow_data.get(video_node_id)
    if not video_node:
        logger.error("Ref2VA video node %s not found", video_node_id)
        return {"video": None, "last_frame": None}

    # Resolve temporary uploads and asset-library files into local paths.
    image_paths: list[Path] = []
    video_paths: list[Path] = []
    audio_paths: list[Path] = []
    try:
        for upload_id in reference_image_uploads:
            image_paths.append(temp_media_store.get_path(upload_id, "image"))
        for upload_id in reference_video_uploads:
            video_paths.append(temp_media_store.get_path(upload_id, "video"))
        for upload_id in reference_audio_uploads:
            audio_paths.append(temp_media_store.get_path(upload_id, "audio"))
        for asset_id in reference_image_asset_ids:
            asset = asset_library.get_asset(user_id, asset_id)
            if not asset:
                raise PermissionError(f"参考图资产不存在：{asset_id}")
            image_paths.append(asset_library.get_asset_path(user_id, asset_id))
        for asset_id in reference_video_asset_ids:
            asset = asset_library.get_asset(user_id, asset_id)
            if not asset:
                raise PermissionError(f"参考视频资产不存在：{asset_id}")
            video_paths.append(asset_library.get_asset_path(user_id, asset_id))
        for asset_id in reference_audio_asset_ids:
            asset = asset_library.get_asset(user_id, asset_id)
            if not asset:
                raise PermissionError(f"参考音频资产不存在：{asset_id}")
            audio_paths.append(asset_library.get_asset_path(user_id, asset_id))
    except Exception:
        raise

    if not (image_paths or video_paths or audio_paths):
        raise ValueError("Ref2VA 至少需要一个参考素材")

    # Clean the workflow template's sample inputs and loaders.
    for key in list(video_node["inputs"].keys()):
        if key.startswith("ref_images.") or key.startswith("ref_videos.") or key.startswith("ref_audios."):
            video_node["inputs"].pop(key, None)
    for node_id, node_data in list(workflow_data.items()):
        cls = node_data.get("class_type", "")
        if cls in {"LoadImage", "VHS_LoadVideo", "LoadAudio"}:
            workflow_data.pop(node_id, None)

    workflow_data[config["prompt_node_id"]]["inputs"]["value"] = _reinforce_ref2va_prompt(
        prompt,
        len(image_paths),
        len(video_paths),
        len(audio_paths),
    )
    duration_node = workflow_data[config["duration_node_id"]]
    duration_node["inputs"]["value"] = max(1.0, round(length / 24.0, 2))
    fallback = (_snap_h3_dim(width), _snap_h3_dim(height))
    resolution_node_id = config.get("resolution_selector_node_id")
    resolution_node = workflow_data.get(resolution_node_id)
    if resolution_node and aspect_ratio in VIDEO_ASPECT_RATIOS:
        resolution_node["inputs"]["aspect_ratio"] = VIDEO_ASPECT_RATIO_LABELS[aspect_ratio]
        resolution_node["inputs"]["megapixels"] = VIDEO_MEGAPIXELS.get(
            quality, VIDEO_MEGAPIXELS["480p"]
        )
        resolution_node["inputs"]["multiple"] = 32
        video_node["inputs"]["width"] = [resolution_node_id, 0]
        video_node["inputs"]["height"] = [resolution_node_id, 1]
    elif aspect_ratio in VIDEO_ASPECT_RATIOS:
        ratio_w, ratio_h = VIDEO_ASPECT_RATIOS[aspect_ratio]
        canvas_w, canvas_h = _canvas_from_ratio(ratio_w, ratio_h, quality)
        video_node["inputs"]["width"] = canvas_w
        video_node["inputs"]["height"] = canvas_h
        if resolution_node_id in workflow_data:
            workflow_data.pop(resolution_node_id, None)
    elif image_paths:
        # Legacy fallback only for requests that do not send aspect_ratio.
        canvas_w, canvas_h = _canvas_from_image_path(image_paths[0], quality, fallback)
        video_node["inputs"]["width"] = canvas_w
        video_node["inputs"]["height"] = canvas_h
    else:
        video_node["inputs"]["width"] = fallback[0]
        video_node["inputs"]["height"] = fallback[1]
    video_node["inputs"]["ref_image_size"] = config.get("ref_image_size", "max")

    steps_node = workflow_data.get(config["steps_node_id"])
    if steps_node:
        steps_node["inputs"]["steps"] = 8
    accelerator_node = workflow_data.get(config["accelerator_lora_node_id"])
    if accelerator_node:
        accelerator_node["inputs"]["lora_name"] = (
            "gif\\minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"
        )

    if not output_last_frame:
        for node_id in (
            config["last_frame_save_node_id"],
            config["last_frame_parent_node_id"],
            config["last_frame_components_node_id"],
        ):
            workflow_data.pop(node_id, None)

    # Add the reference loaders.
    next_id = 5000
    try:
        async with aiohttp.ClientSession() as session:
            for index, path in enumerate(image_paths):
                ctype = mimetypes.guess_type(str(path))[0] or "image/png"
                filename = await _upload_media_file(session, path, ctype)
                if not filename:
                    return {"video": None, "last_frame": None}
                node_id = str(next_id)
                workflow_data[node_id] = {
                    "inputs": {"image": filename},
                    "class_type": "LoadImage",
                    "_meta": {"title": f"Ref Image {index + 1}"},
                }
                video_node["inputs"][f"ref_images.ref_image_{index}"] = [node_id, 0]
                next_id += 1

            for index, path in enumerate(video_paths):
                ctype = mimetypes.guess_type(str(path))[0] or "video/mp4"
                filename = await _upload_media_file(session, path, ctype)
                if not filename:
                    return {"video": None, "last_frame": None}
                node_id = str(next_id)
                workflow_data[node_id] = {
                    "inputs": {
                        "video": filename,
                        "force_rate": 0,
                        "custom_width": 0,
                        "custom_height": 0,
                        "frame_load_cap": 0,
                        "skip_first_frames": 0,
                        "select_every_nth": 1,
                        "format": "AnimateDiff",
                    },
                    "class_type": "VHS_LoadVideo",
                    "_meta": {"title": f"Ref Video {index + 1}"},
                }
                video_node["inputs"][f"ref_videos.ref_video_{index}"] = [node_id, 0]
                next_id += 1

            for index, path in enumerate(audio_paths):
                ctype = mimetypes.guess_type(str(path))[0] or "audio/wav"
                filename = await _upload_media_file(session, path, ctype)
                if not filename:
                    return {"video": None, "last_frame": None}
                node_id = str(next_id)
                workflow_data[node_id] = {
                    "inputs": {"audio": filename},
                    "class_type": "LoadAudio",
                    "_meta": {"title": f"Ref Audio {index + 1}"},
                }
                video_node["inputs"][f"ref_audios.ref_audio_{index}"] = [node_id, 0]
                next_id += 1

            actual_seed = seed if seed is not None else random.randint(1, 1000000000)
            workflow_data[config["seed_node_id"]]["inputs"]["noise_seed"] = actual_seed
            outputs = await _submit_and_wait_outputs(
                session,
                workflow_data,
                str(uuid.uuid4()),
                on_prompt_submitted,
                prefer_ext="mp4,webm,mkv,mov",
            )
    finally:
        # Temp uploads are intentionally retained for reuse; TTL cleanup runs
        # in the WebUI cleanup loop rather than immediately after generation.
        pass
    video_bytes = None
    last_frame_bytes = None
    for info, data in outputs:
        ext = Path(info["filename"]).suffix.lower().lstrip(".")
        if ext in {"mp4", "webm", "mkv", "mov"} and video_bytes is None:
            video_bytes = data
        elif ext in {"png", "jpg", "jpeg", "webp"} and last_frame_bytes is None:
            last_frame_bytes = data
    return {"video": video_bytes, "last_frame": last_frame_bytes}


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


def _build_birefnet_cutout_node(image_src: list, config: dict) -> dict:
    """BiRefNetRMBG node (Alpha output), mirroring the user's 抠图 workflows."""
    return {
        "inputs": {
            "image": image_src,
            "model": config["cutout_model"],
            "mask_blur": 0,
            "mask_offset": 0,
            "invert_output": False,
            "refine_foreground": False,
            "background": "Alpha",
            "background_color": "#222222",
        },
        "class_type": "BiRefNetRMBG",
        "_meta": {"title": "BiRefNet 抠图"},
    }


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
    mode: str = "edit",
    on_prompt_submitted=None,
) -> bytes | None:
    workflow_data = wm.load_workflow_data("discord_flux2_9b_edit")
    if not workflow_data:
        logger.error("Cannot load discord_flux2_9b_edit workflow")
        return None

    config = WORKFLOW_CONFIGS["discord_flux2_9b_edit"]
    cutout_id = config["cutout_node_id"]
    load_id = config["load_image_node_id"]
    save_id = config["save_node_id"]

    client_id = str(uuid.uuid4())
    try:
        async with aiohttp.ClientSession() as session:
            # Upload source image (required)
            source_filename = await _upload_image(session, source_image_b64)
            if not source_filename:
                logger.error("Failed to upload source image")
                return None
            workflow_data[load_id]["inputs"]["image"] = source_filename

            if mode == "cutout":
                # Direct cutout: skip the Flux2 edit entirely - build a minimal
                # graph (LoadImage -> BiRefNetRMBG -> SaveImage).
                minimal = {
                    load_id: {
                        "inputs": {"image": source_filename},
                        "class_type": "LoadImage",
                        "_meta": {"title": "Source Image"},
                    },
                    cutout_id: _build_birefnet_cutout_node([load_id, 0], config),
                    save_id: {
                        "inputs": {
                            "filename_prefix": config["cutout_direct_save_prefix"],
                            "images": [cutout_id, 0],
                        },
                        "class_type": "SaveImage",
                        "_meta": {"title": "Save Cutout"},
                    },
                }
                workflow_data = minimal
            else:
                # Standard Flux2 edit; optionally chain cutout after decode.
                if reference_image_b64:
                    ref_filename = await _upload_image(session, reference_image_b64)
                    if not ref_filename:
                        logger.error("Failed to upload reference image")
                        return None
                    _inject_flux2_reference_chain(workflow_data, config, ref_filename)

                workflow_data[config["pos_node_id"]]["inputs"]["text"] = prompt
                neg_text = negative_prompt or ""
                workflow_data[config["neg_node_id"]]["inputs"]["text"] = neg_text

                actual_seed = seed if seed is not None else random.randint(1, 1000000000)
                workflow_data[config["noise_node_id"]]["inputs"]["noise_seed"] = actual_seed

                if steps is not None:
                    workflow_data[config["scheduler_node_id"]]["inputs"]["steps"] = steps
                if cfg is not None:
                    workflow_data[config["guider_node_id"]]["inputs"]["cfg"] = cfg
                if sampler_name:
                    workflow_data[config["sampler_select_node_id"]]["inputs"]["sampler_name"] = sampler_name

                if mode == "edit_cutout":
                    workflow_data[cutout_id] = _build_birefnet_cutout_node(
                        [config["decode_node_id"], 0], config
                    )
                    workflow_data[save_id]["inputs"]["images"] = [cutout_id, 0]
                    workflow_data[save_id]["inputs"]["filename_prefix"] = (
                        config["cutout_edit_save_prefix"]
                    )

            return await _submit_and_wait(session, workflow_data, client_id, on_prompt_submitted)
    except Exception as e:
        logger.error("Flux2 edit generation exception: %s", e)
        return None
