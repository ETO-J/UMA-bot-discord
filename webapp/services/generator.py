import json
import uuid
import asyncio
import random
import shutil
import logging
import aiohttp

from config import (
    COMFYUI_URL,
    COMFYUI_OUTPUT_DIR,
    IMAGE_SAVE_PATH,
    WORKFLOW_CONFIGS,
)
from services.workflow_manager import wm

logger = logging.getLogger(__name__)


async def move_generated_image(img_name: str) -> bool:
    source_path = COMFYUI_OUTPUT_DIR / img_name
    dest_path = IMAGE_SAVE_PATH / img_name
    max_wait, interval, waited = 30, 1, 0
    while waited < max_wait:
        if source_path.exists():
            try:
                shutil.move(str(source_path), str(dest_path))
                logger.info("Image moved: %s", img_name)
                return True
            except Exception as e:
                logger.error("Failed to move image: %s", e)
                return False
        else:
            await asyncio.sleep(interval)
            waited += interval
    return False


async def generate_image(
    input_prompt: str,
    user_id: str,
    workflow_name: str = "discord_anima_v2",
    seed: int | None = None,
    sampler_name: str | None = None,
    scheduler: str | None = None,
    steps: int | None = None,
    cfg: float | None = None,
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

    client_id = str(uuid.uuid4())
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"prompt": workflow_data, "client_id": client_id}
            async with session.post(f"{COMFYUI_URL}/prompt", json=payload) as response:
                if response.status != 200:
                    logger.error("ComfyUI Error: %s", await response.text())
                    return None
                resp_json = await response.json()
                prompt_id = resp_json.get("prompt_id")

            while True:
                await asyncio.sleep(1)
                async with session.get(f"{COMFYUI_URL}/history/{prompt_id}") as history_resp:
                    if history_resp.status == 200:
                        history_data = await history_resp.json()
                        if prompt_id in history_data:
                            outputs = history_data[prompt_id].get("outputs", {})
                            for out_node in outputs.values():
                                if "images" in out_node:
                                    img_name = out_node["images"][0].get("filename")
                                    async with session.get(
                                        f"{COMFYUI_URL}/view", params={"filename": img_name}
                                    ) as img_resp:
                                        if img_resp.status == 200:
                                            image_bytes = await img_resp.read()
                                            asyncio.create_task(move_generated_image(img_name))
                                            return image_bytes
                            break
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
            payload = {"prompt": workflow_data, "client_id": client_id}
            async with session.post(f"{COMFYUI_URL}/prompt", json=payload) as response:
                if response.status != 200:
                    logger.error("ComfyUI Error: %s", await response.text())
                    return None
                resp_json = await response.json()
                prompt_id = resp_json.get("prompt_id")

            while True:
                await asyncio.sleep(1)
                async with session.get(f"{COMFYUI_URL}/history/{prompt_id}") as history_resp:
                    if history_resp.status == 200:
                        history_data = await history_resp.json()
                        if prompt_id in history_data:
                            outputs = history_data[prompt_id].get("outputs", {})
                            for out_node in outputs.values():
                                if "images" in out_node:
                                    img_name = out_node["images"][0].get("filename")
                                    async with session.get(
                                        f"{COMFYUI_URL}/view", params={"filename": img_name}
                                    ) as img_resp:
                                        if img_resp.status == 200:
                                            image_bytes = await img_resp.read()
                                            asyncio.create_task(move_generated_image(img_name))
                                            return image_bytes
                            break
    except Exception as e:
        logger.error("Multidraw exception: %s", e)
        return None
