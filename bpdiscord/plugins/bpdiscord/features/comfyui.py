"""ComfyUI AI 绘图模块（Discord 适配版 - 含用户设置/配额/Lora/高清/多角色）"""
import json
import uuid
import asyncio
import random
import os
import sqlite3
import aiohttp
import shutil
from pathlib import Path
from dotenv import load_dotenv

from nonebot import on_message
from nonebot.adapters.discord import Bot, MessageEvent
from nonebot_plugin_alconna import UniMessage
from nonebot.log import logger

from ..config import COMFYUI_DIR, is_admin as _is_admin, is_blacklisted

load_dotenv()

# --- ComfyUI 路径配置 ---
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8000")
COMFYUI_OUTPUT_DIR = Path(os.getenv("COMFYUI_OUTPUT_DIR", r"C:\Users\Administrator\Documents\ComfyUI\output"))
COMFYUI_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LORA_BASE_PATH = Path(os.getenv("LORA_BASE_PATH", r"C:\Users\Administrator\Documents\ComfyUI\models\loras"))
LORA_DIRS = ["char", "gif", "pose", "style"]

IMAGE_SAVE_PATH = Path(os.getenv("IMAGE_SAVE_PATH", r"D:\civitai\线上绘图"))
IMAGE_SAVE_PATH.mkdir(parents=True, exist_ok=True)

DB_DIR = COMFYUI_DIR.parent / "data" / "comfyuisetting"
DB_PATH = DB_DIR / "user_settings.db"

WORKFLOW_DIR = COMFYUI_DIR

WORKFLOW_CONFIGS = {
    "discord": {
        "model_source": ["13", 0],
        "clip_source": ["22", 0],
        "pos_node_id": "29",
        "neg_node_id": "7",
        "supports_lora": True,
        "lora_start_id": 1000,
    },
    "discord_高清": {
        "model_source": ["13", 0],
        "clip_source": ["22", 0],
        "pos_node_id": "29",
        "neg_node_id": "7",
        "supports_lora": True,
        "lora_start_id": 1000,
    },
    "multidraw": {
        "model_source": ["13", 0],
        "clip_source": ["22", 0],
        "pos_node_id": "29",
        "neg_node_id": "7",
        "supports_lora": True,
        "lora_start_id": 1000,
    },
    "discord_anima": {
        "model_source": ["64", 0],
        "clip_source": ["66", 0],
        "pos_node_id": "65",
        "neg_node_id": "68",
        "supports_lora": False,
        "lora_start_id": None,
    },
}


# ========== WorkflowManager（用户设置 + 配额 + Lora + 高清）==========
class WorkflowManager:
    def __init__(self):
        self._ensure_dir()
        self._init_db()

    def _ensure_dir(self):
        WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
        DB_DIR.mkdir(parents=True, exist_ok=True)

    def _init_db(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id TEXT PRIMARY KEY,
                    width INTEGER DEFAULT 832,
                    height INTEGER DEFAULT 1216,
                    active_loras TEXT DEFAULT '{}',
                    workflow TEXT DEFAULT 'discord',
                    negative_prompt TEXT DEFAULT 'mosaic,low quality, bad quality, worst quality'
                )
            ''')
            cursor.execute("PRAGMA table_info(user_settings)")
            existing = [col[1] for col in cursor.fetchall()]
            new_fields = {
                "limit_count": "INTEGER DEFAULT 50",
                "used_today": "INTEGER DEFAULT 0",
                "last_reset_date": "TEXT DEFAULT ''",
                "negative_prompt": "TEXT DEFAULT 'mosaic,low quality, bad quality, worst quality'",
                "is_hd_mode": "INTEGER DEFAULT 0",
                "part1": "TEXT DEFAULT '[832,608,0,0]'",
                "part2": "TEXT DEFAULT '[832,608,832,0]'",
            }
            for field, definition in new_fields.items():
                if field not in existing:
                    logger.info(f"正在升级数据库：添加列 {field}")
                    cursor.execute(f"ALTER TABLE user_settings ADD COLUMN {field} {definition}")
            cursor.execute("SELECT user_id, part1, part2 FROM user_settings")
            for row in cursor.fetchall():
                uid, p1, p2 = row
                if not p1 or p1 == "[]":
                    cursor.execute("UPDATE user_settings SET part1=? WHERE user_id=?", ('[832,608,0,0]', uid))
                if not p2 or p2 == "[]":
                    cursor.execute("UPDATE user_settings SET part2=? WHERE user_id=?", ('[832,608,832,0]', uid))
            conn.commit()
            conn.close()
            logger.info(f"数据库初始化/升级成功: {DB_PATH}")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")

    def get_user_settings(self, user_id: str):
        import datetime
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT width, height, active_loras, workflow, limit_count, used_today, last_reset_date, negative_prompt, is_hd_mode, part1, part2 FROM user_settings WHERE user_id = ?",
            (user_id,))
        row = cursor.fetchone()
        if row:
            width, height, loras_json, workflow, limit_count, used_today, last_reset_date, negative_prompt, is_hd_mode, part1, part2 = row
            if last_reset_date != today_str:
                used_today = 0
                cursor.execute("UPDATE user_settings SET used_today=0, last_reset_date=? WHERE user_id=?", (today_str, user_id))
                conn.commit()
            conn.close()
            return {
                "resolution": (width, height),
                "active_loras": json.loads(loras_json),
                "workflow": workflow,
                "limit_count": limit_count,
                "used_today": used_today,
                "negative_prompt": negative_prompt,
                "is_hd_mode": is_hd_mode,
                "part1": json.loads(part1),
                "part2": json.loads(part2),
            }
        else:
            cursor.execute("INSERT INTO user_settings (user_id, last_reset_date) VALUES (?, ?)", (user_id, today_str))
            conn.commit()
            conn.close()
            return self.get_user_settings(user_id)

    def use_quota(self, user_id: str, count: int = 1) -> bool:
        settings = self.get_user_settings(user_id)
        remaining = settings["limit_count"] - settings["used_today"]
        if remaining < count:
            return False
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE user_settings SET used_today = used_today + ? WHERE user_id=?", (count, user_id))
        conn.commit()
        conn.close()
        return True

    def refund_quota(self, user_id: str, count: int = 1):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE user_settings SET used_today = used_today - ? WHERE user_id=?", (count, user_id))
        conn.commit()
        conn.close()

    def set_user_limit(self, user_id: str, new_limit: int):
        self.get_user_settings(user_id)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE user_settings SET limit_count=? WHERE user_id=?", (new_limit, user_id))
        conn.commit()
        conn.close()

    def set_resolution(self, user_id: str, width: int, height: int):
        self.get_user_settings(user_id)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE user_settings SET width=?, height=? WHERE user_id=?", (width, height, user_id))
        conn.commit()
        conn.close()

    def set_negative_prompt(self, user_id: str, text: str):
        self.get_user_settings(user_id)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE user_settings SET negative_prompt=? WHERE user_id=?", (text, user_id))
        conn.commit()
        conn.close()

    def set_part1(self, user_id: str, part: list):
        self.get_user_settings(user_id)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE user_settings SET part1=? WHERE user_id=?", (json.dumps(part), user_id))
        conn.commit()
        conn.close()

    def set_part2(self, user_id: str, part: list):
        self.get_user_settings(user_id)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE user_settings SET part2=? WHERE user_id=?", (json.dumps(part), user_id))
        conn.commit()
        conn.close()

    def set_user_setting(self, user_id: str, key: str, value):
        self.get_user_settings(user_id)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(f"UPDATE user_settings SET {key}=? WHERE user_id=?", (value, user_id))
        conn.commit()
        conn.close()

    def load_workflow_data(self, name: str) -> dict | None:
        file_path = WORKFLOW_DIR / f"{name}.json"
        if not file_path.exists():
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载工作流文件 {name} 失败: {e}")
            return None

    def get_lora_list(self):
        lora_dict = {}
        for sub_dir in LORA_DIRS:
            path = LORA_BASE_PATH / sub_dir
            if path.exists():
                loras = [f.name for f in path.glob("**/*") if f.suffix in [".safetensors", ".ckpt"]]
                lora_dict[sub_dir] = loras
        return lora_dict

    def find_lora_path(self, name: str):
        for sub_dir in LORA_DIRS:
            path = LORA_BASE_PATH / sub_dir
            for f in path.glob("**/*"):
                if name.lower() in f.name.lower():
                    return f"{sub_dir}\\{f.name}"
        return None

    def add_lora(self, user_id: str, lora_name: str, weight: float):
        settings = self.get_user_settings(user_id)
        current_loras = settings["active_loras"]
        real_path = self.find_lora_path(lora_name)
        if real_path:
            file_name = os.path.basename(real_path)
            current_loras[file_name] = weight
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("UPDATE user_settings SET active_loras=? WHERE user_id=?", (json.dumps(current_loras), user_id))
            conn.commit()
            conn.close()
            return file_name
        return None

    def remove_lora(self, user_id: str, lora_name: str):
        settings = self.get_user_settings(user_id)
        current_loras = settings["active_loras"]
        if lora_name in current_loras:
            del current_loras[lora_name]
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("UPDATE user_settings SET active_loras=? WHERE user_id=?", (json.dumps(current_loras), user_id))
            conn.commit()
            conn.close()
            return True
        return False

    def clear_loras(self, user_id: str):
        self.get_user_settings(user_id)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE user_settings SET active_loras='{}' WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()


wm = WorkflowManager()


# ========== 图片移动 ==========
async def move_generated_image(img_name: str) -> bool:
    source_path = COMFYUI_OUTPUT_DIR / img_name
    dest_path = IMAGE_SAVE_PATH / img_name
    max_wait, interval, waited = 30, 1, 0
    while waited < max_wait:
        if source_path.exists():
            try:
                shutil.move(str(source_path), str(dest_path))
                logger.info(f"成功移动图片: {img_name}")
                return True
            except Exception as e:
                logger.error(f"移动图片失败: {e}")
                return False
        else:
            await asyncio.sleep(interval)
            waited += interval
    return False


# ========== 核心生成函数 ==========
async def generate_image(input_prompt: str, user_id: str, workflow_name: str = None) -> bytes | None:
    user_settings = wm.get_user_settings(user_id)
    is_hd_mode = user_settings.get("is_hd_mode", 0)
    if is_hd_mode == 1 and not workflow_name:
        target_name = "discord_高清"
    else:
        target_name = workflow_name or user_settings["workflow"]

    workflow_data = wm.load_workflow_data(target_name)
    if not workflow_data:
        logger.error(f"无法加载工作流: {target_name}")
        return None

    active_loras = user_settings.get("active_loras", {})
    target_width, target_height = user_settings["resolution"]
    negative_text = user_settings.get("negative_prompt", "")

    config = WORKFLOW_CONFIGS.get(target_name)
    if not config:
        config = WORKFLOW_CONFIGS["discord"]

    current_model_source = list(config["model_source"])
    current_clip_source = list(config["clip_source"])

    if config["supports_lora"] and active_loras:
        start_id = config["lora_start_id"]
        for lora_name, weight in active_loras.items():
            lora_path = wm.find_lora_path(lora_name)
            if not lora_path:
                continue
            node_id = str(start_id)
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

    for node_id, node_data in workflow_data.items():
        class_type = node_data.get("class_type")
        meta_title = node_data.get("_meta", {}).get("title", "").lower()

        if class_type == "KSampler":
            node_data["inputs"]["model"] = current_model_source
            node_data["inputs"]["positive"] = [pos_node_id, 0]
            node_data["inputs"]["negative"] = [neg_node_id, 0]
            node_data["inputs"]["seed"] = random.randint(1, 1000000000)

        if class_type == "CLIPTextEncode":
            node_data["inputs"]["clip"] = current_clip_source
            if node_id == pos_node_id or "positive" in meta_title:
                node_data["inputs"]["text"] = f"{input_prompt}, SFW"
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
                    logger.error(f"ComfyUI Error: {await response.text()}")
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
                                    async with session.get(f"{COMFYUI_URL}/view", params={"filename": img_name}) as img_resp:
                                        if img_resp.status == 200:
                                            image_bytes = await img_resp.read()
                                            asyncio.create_task(move_generated_image(img_name))
                                            return image_bytes
                            break
    except Exception as e:
        logger.error(f"绘图异常: {e}")
        return None


async def generate_multidraw_image(prompt1: str, prompt2: str, global_prompt: str, user_id: str) -> bytes | None:
    user_settings = wm.get_user_settings(user_id)
    workflow_data = wm.load_workflow_data("multidraw")
    if not workflow_data:
        logger.error("无法加载多角色工作流: multidraw")
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
        for lora_name, weight in active_loras.items():
            lora_path = wm.find_lora_path(lora_name)
            if not lora_path:
                continue
            node_id = str(start_id)
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
            node_data["inputs"]["seed"] = random.randint(1, 1000000000)

        if class_type == "CLIPTextEncode":
            node_data["inputs"]["clip"] = current_clip_source
            if meta_title == "positive-全局":
                node_data["inputs"]["text"] = f"{global_prompt}, SFW"
            elif meta_title == "positive-1":
                node_data["inputs"]["text"] = f"{prompt1}, SFW"
            elif meta_title == "positive-2":
                node_data["inputs"]["text"] = f"{prompt2}, SFW"
            elif meta_title == "negative":
                final_neg = negative_text if negative_text else "mosaic, low quality, bad quality, worst quality"
                node_data["inputs"]["text"] = final_neg

        if class_type == "ConditioningSetArea":
            if meta_title == "条件采样区域":
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
                    logger.error(f"ComfyUI Error: {await response.text()}")
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
                                    async with session.get(f"{COMFYUI_URL}/view", params={"filename": img_name}) as img_resp:
                                        if img_resp.status == 200:
                                            image_bytes = await img_resp.read()
                                            asyncio.create_task(move_generated_image(img_name))
                                            return image_bytes
                            break
    except Exception as e:
        logger.error(f"多角色绘图异常: {e}")
        return None


# ========== 命令处理 ==========
draw_handler = on_message(priority=3, block=False)


@draw_handler.handle()
async def handle_comfyui_commands(bot: Bot, event: MessageEvent):
    raw_text = event.get_plaintext().strip()
    user_id = event.get_user_id()
    is_admin = _is_admin(user_id)

    if is_blacklisted(user_id):
        return

    # 1. Draw
    if raw_text.lower().startswith(("draw", "/draw")):
        prefix_len = 5 if raw_text.startswith("/") else 4
        prompt = raw_text[prefix_len:].strip()
        if not prompt:
            await UniMessage("⚠️ 提示词不能为空。").send(reply_message=True)
            return
        user_settings = wm.get_user_settings(user_id)
        is_hd = user_settings.get("is_hd_mode", 0) == 1
        cost = 100 if is_hd else 1
        remaining = user_settings["limit_count"] - user_settings["used_today"]
        if remaining < cost:
            mode_name = "高清" if is_hd else "普通"
            await UniMessage(
                f"❌ 今日配额已耗尽（{user_settings['limit_count']}/{user_settings['used_today']}）。\n每日0:00自动重置。").send(reply_message=True)
            return
        if wm.use_quota(user_id, cost):
            new_remaining = remaining - cost
            hd_tag = " [高清模式]" if is_hd else ""
            await UniMessage(f"🎨{hd_tag} 今日剩余配额: {new_remaining} 次。\n正在生成中...").send(reply_message=True)
            image_data = await generate_image(prompt, user_id)
            if image_data:
                await UniMessage.image(raw=image_data).send(reply_message=True)
            else:
                wm.refund_quota(user_id, cost)
                await UniMessage("❌ 绘图失败，已返还配额。").send(reply_message=True)
        return

    # 3. Multidraw
    if raw_text.lower().startswith(("multidraw", "/multidraw")):
        prefix_len = 9 if raw_text.startswith("/") else 8
        content = raw_text[prefix_len:].strip()
        if not content:
            await UniMessage("⚠️ 格式：multidraw 全局提示词 AND 角色1提示词 AND 角色2提示词").send(reply_message=True)
            return
        parts = [p.strip() for p in content.split('AND')]
        if len(parts) < 3:
            await UniMessage("⚠️ 格式错误。请使用 AND 分隔三个部分").send(reply_message=True)
            return
        prompt1, prompt2, global_prompt = parts[1], parts[2], parts[0]
        user_settings = wm.get_user_settings(user_id)
        remaining = user_settings["limit_count"] - user_settings["used_today"]
        cost = 10
        if remaining < cost:
            await UniMessage(f"❌ 今日配额不足（需要{cost}次，剩余{remaining}次）。").send(reply_message=True)
            return
        if wm.use_quota(user_id, cost):
            new_remaining = remaining - cost
            await UniMessage(f"🎨 [多角色绘图] 今日剩余配额: {new_remaining} 次。\n正在生成中...").send(reply_message=True)
            image_data = await generate_multidraw_image(prompt1, prompt2, global_prompt, user_id)
            if image_data:
                await UniMessage.image(raw=image_data).send(reply_message=True)
            else:
                wm.refund_quota(user_id, cost)
                await UniMessage("❌ 多角色绘图失败，已返还配额。").send(reply_message=True)
        return

    # 4. 切换分辨率
    if raw_text.startswith(("切换分辨率", "/切换分辨率")):
        import re
        dims = re.findall(r'\d+', raw_text)
        if len(dims) >= 2:
            w, h = int(dims[0]), int(dims[1])
            wm.set_resolution(user_id, w, h)
            await UniMessage(f"✅ [个人设置] 分辨率已设定为: {w} x {h}").send(reply_message=True)
        else:
            await UniMessage("❌ 格式错误。请输入：切换分辨率 1024 1024").send(reply_message=True)
        return

    # 5. Partone / Parttwo
    if raw_text.startswith(("partone", "/设置区域1")):
        import re
        dims = re.findall(r'\d+', raw_text)
        if len(dims) >= 4:
            w, h, x, y = int(dims[0]), int(dims[1]), int(dims[2]), int(dims[3])
            wm.set_part1(user_id, [w, h, x, y])
            await UniMessage(f"✅ [个人设置] 第一区域参数已设定为: 宽={w}, 高={h}, X={x}, Y={y}").send(reply_message=True)
        else:
            await UniMessage("❌ 格式错误。请输入：partone 832 608 0 0").send(reply_message=True)
        return

    if raw_text.startswith(("parttwo", "/设置区域2")):
        import re
        dims = re.findall(r'\d+', raw_text)
        if len(dims) >= 4:
            w, h, x, y = int(dims[0]), int(dims[1]), int(dims[2]), int(dims[3])
            wm.set_part2(user_id, [w, h, x, y])
            await UniMessage(f"✅ [个人设置] 第二区域参数已设定为: 宽={w}, 高={h}, X={x}, Y={y}").send(reply_message=True)
        else:
            await UniMessage("❌ 格式错误。请输入：parttwo 832 608 832 0").send(reply_message=True)
        return

    # 6. Lora 列表
    if raw_text.lower() in ["lora列表", "/lora列表", "loralist"]:
        lora_dict = wm.get_lora_list()
        user_settings = wm.get_user_settings(user_id)
        active_loras = user_settings.get("active_loras", {})
        msg = "🗂️ **可用 Lora 资源库**\n"
        if not lora_dict:
            msg += "  (库路径为空或未找到文件)\n"
        else:
            for category, files in lora_dict.items():
                for f in files:
                    msg += f"  - `{f}`\n"
        if active_loras:
            msg += "\n✅ **[个人] 当前已挂载:**\n"
            msg += "\n".join([f"🔗 {k} (权重: {v})" for k, v in active_loras.items()])
        else:
            msg += "\n⚙️ **[个人] 当前未挂载任何 Lora**"
        await UniMessage(msg).send()
        return

    # 7. 添加 Lora
    if raw_text.startswith(("添加lora", "/添加lora")):
        import re
        content = raw_text.replace("/添加lora", "").replace("添加lora", "").strip()
        match = re.search(r'^(.*)\s+(\d+(?:\.\d+)?)$', content)
        if match:
            lora_name = match.group(1).strip()
            weight = float(match.group(2))
        else:
            lora_name = content
            weight = 0.8
        if lora_name:
            result_name = wm.add_lora(user_id, lora_name, weight)
            if result_name:
                await UniMessage(f"✅ [个人设置] 成功挂载 Lora:\n`{result_name}`\n当前权重: {weight}").send()
            else:
                await UniMessage(f"❌ 未在库中找到包含 `{lora_name}` 的 Lora 文件。").send()
        else:
            await UniMessage("❌ 请输入 Lora 名称。").send(reply_message=True)
        return

    # 8. 删除 Lora
    if raw_text.startswith(("删除lora", "/删除lora")):
        target = raw_text.replace("/删除lora", "").replace("删除lora", "").strip()
        success = wm.remove_lora(user_id, target)
        if success:
            await UniMessage(f"🗑️ [个人设置] 已移除 Lora: {target}").send()
        else:
            user_settings = wm.get_user_settings(user_id)
            current = list(user_settings["active_loras"].keys())
            await UniMessage(f"❓ 您当前未挂载: {target}\n在用列表: {current}").send()
        return

    # 9. 重置 Lora
    if raw_text.lower() in ["重置lora", "/重置lora", "resetlora"]:
        wm.clear_loras(user_id)
        await UniMessage("🧹 [个人设置] 已清空您的 Lora 注入。").send()
        return

    # 10. 切换负面
    if raw_text.startswith(("切换负面", "/切换负面提示词")):
        prefix_len = 4
        content = raw_text[prefix_len:].strip()
        if not content:
            await UniMessage("❌ 请输入您想设置的负面提示词（如：模糊，低质量）。").send(reply_message=True)
            return
        wm.set_negative_prompt(user_id, content)
        await UniMessage(f"✅ [个人设置] 负面提示词已更新。\n当前设置: `{content}`").send(reply_message=True)
        return

    # 11. 重置负面
    if raw_text.lower() in ["重置负面", "clearneg"]:
        wm.set_negative_prompt(user_id, "")
        await UniMessage("🧹 [个人设置] 负面提示词已清空。").send(reply_message=True)
        return

    # 12. 切换工作流
    if raw_text.startswith(("切换工作流", "/切换工作流")):
        content = raw_text.replace("/切换工作流", "").replace("切换工作流", "").strip().lower()
        if content in ["anima", "discord_anima"]:
            wm.set_user_setting(user_id, "workflow", "discord_anima")
            wm.set_user_setting(user_id, "is_hd_mode", 0)
            await UniMessage("✅ 已切换到 Anima 工作流 (UNet + CLIP + VAE 分离架构，不支持 Lora)。高清模式已自动关闭。").send()
        elif content in ["discord", "default", "默认"]:
            wm.set_user_setting(user_id, "workflow", "discord")
            await UniMessage("✅ 已切换到默认 Discord 工作流 (SDXL + Checkpoint)。").send()
        elif content in ["高清", "hd", "discord_高清"]:
            wm.set_user_setting(user_id, "workflow", "discord_高清")
            wm.set_user_setting(user_id, "is_hd_mode", 0)
            await UniMessage("✅ 已切换到高清工作流（图生图放大+超分管线）。高清模式已自动关闭，请使用 切换分辨率 调整尺寸。").send()
        else:
            await UniMessage("可用工作流:\n  `anima` - Anima UNet 架构 (qwen_vae + anima_baseV10)\n  `discord` / `默认` - 标准 SDXL Checkpoint\n  `高清` - 图生图高清修复").send(reply_message=True)
        return

    # 13. 高清模式
    if raw_text.startswith("高清"):
        parts = raw_text.split()
        is_hd = False
        if len(parts) > 1:
            arg = parts[1]
            if arg in ["关", "off", "0"]:
                is_hd = False
            elif arg in ["开", "on", "1"]:
                is_hd = True
            else:
                await UniMessage("用法: 高清 [开/关] 或 高清 [on/off]").send(reply_message=True)
                return
        try:
            wm.set_user_setting(user_id, "is_hd_mode", 1 if is_hd else 0)
            msg_type = "开启" if is_hd else "关闭"
            await UniMessage(f"✅ 已{msg_type}高清绘图模式。⚠此模式下每次使用消耗100每日次数。").send()
        except Exception as e:
            await UniMessage(f"❌ 设置失败: {e}").send()
        return

    # 如果没匹配任何命令，skip 让其他 handler 处理
    await draw_handler.skip()
