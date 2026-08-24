"""ComfyUI / WebUI 后端在线状态监测插件（Discord 适配版）

- 快速轮询实时感知后端开机/关机事件，状态变化时向指定频道发送通知；
- 每 10 分钟执行一次定时复核，状态未变化时不发送任何消息；
- 用本地状态文件记住上一次状态，避免机器人重启时重复播报。
"""

import asyncio
import json
import os
from typing import Optional

import aiohttp
from nonebot import get_driver, require
from nonebot.adapters.discord import Bot
from nonebot.adapters.discord.api import Embed
from nonebot.adapters.discord.message import MessageSegment
from nonebot.log import logger

from ..config import DATA_DIR

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

# === 可调参数 ===
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8000").rstrip("/")
HEALTH_PATH = "/api/auth/me"  # 无鉴权也返回 JSON 200，能避开 nginx 维护页面的误判
STATUS_CHANNEL_ID = 1540743228523815063

QUICK_POLL_SECONDS = int(os.getenv("COMFYUI_STATUS_POLL_SECONDS", "10"))
PERIODIC_CHECK_MINUTES = int(os.getenv("COMFYUI_STATUS_CHECK_MINUTES", "10"))

STATE_FILE = DATA_DIR / "comfyui_status.json"

_OPENED_TEXT = "webui在线状态：opened"
_CLOSED_TEXT = "webui在线状态：closed"
_OPENED_JA = "WebUI 起動中"
_CLOSED_JA = "WebUI 停止中"
_OPENED_EN = "WebUI online"
_CLOSED_EN = "WebUI offline"

# Discord embed 颜色：绿 = opened，红 = closed
_GREEN_COLOR = 0x2ECC71
_RED_COLOR = 0xE74C3C

_session: Optional[aiohttp.ClientSession] = None
_check_lock = asyncio.Lock()
_last_status: Optional[bool] = None


def _load_state() -> Optional[bool]:
    """从本地状态文件读取上一次后端状态；文件不存在时返回 None。"""
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            value = data.get("opened")
            if isinstance(value, bool):
                return value
    except Exception as exc:
        logger.warning(f"读取 ComfyUI 状态文件失败: {exc}")
    return None


def _save_state(opened: bool) -> None:
    """持久化当前后端状态。"""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps({"opened": opened}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning(f"写入 ComfyUI 状态文件失败: {exc}")


async def _get_session() -> aiohttp.ClientSession:
    """惰性创建可复用的 HTTP 会话，避免每次探测都新建连接。"""
    global _session
    if _session is None or _session.closed:
        timeout = aiohttp.ClientTimeout(total=5)
        _session = aiohttp.ClientSession(timeout=timeout)
    return _session


@get_driver().on_shutdown
async def _close_session() -> None:
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


async def _is_backend_opened() -> bool:
    """探测后端是否在线。

    /api/auth/me 返回 JSON 200（新版本）或 401/403/404（旧版本/需鉴权）
    都说明后端进程本身在响应；nginx 维护页会让 API 路径返回 HTML 200，
    此时视为 closed，避免把维护页误判为后端在线。
    """
    session = await _get_session()
    try:
        async with session.get(
            f"{COMFYUI_URL}{HEALTH_PATH}", allow_redirects=False
        ) as resp:
            content_type = resp.headers.get("Content-Type", "").lower()
            if resp.status in (401, 403, 404):
                return True
            if resp.status >= 500:
                return False
            if resp.status == 200:
                return "application/json" in content_type
            return False
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
        logger.debug(f"ComfyUI 后端探测失败: {exc}")
        return False


async def _send_status(opened: bool) -> bool:
    """向指定频道发送绿色 opened / 红色 closed 通知；成功返回 True。"""
    bots = get_driver().bots
    if not bots:
        logger.warning("没有可用的 Discord Bot，跳过 ComfyUI 状态通知")
        return False

    text = _OPENED_TEXT if opened else _CLOSED_TEXT
    ja_text = _OPENED_JA if opened else _CLOSED_JA
    en_text = _OPENED_EN if opened else _CLOSED_EN
    color = _GREEN_COLOR if opened else _RED_COLOR
    light = "🟢" if opened else "🔴"
    description = "\n".join(
        [
            f"{light} {text}",
            f"日本語：{ja_text}",
            f"English: {en_text}",
        ]
    )
    embed = Embed(
        title="WebUI 在线状态",
        description=description,
        color=color,
    )
    bot: Bot = next(iter(bots.values()))
    try:
        await bot.send_to(
            channel_id=STATUS_CHANNEL_ID,
            message=MessageSegment.embed(embed),
        )
        logger.info(f"已发送 ComfyUI 状态通知: {text}")
        return True
    except Exception as exc:
        logger.error(f"发送 ComfyUI 状态通知失败: {exc}")
        return False


async def _monitor_once(send_if_unknown: bool = True) -> None:
    """执行一次状态探测；仅在状态发生变化（或首次未知）时发送通知。"""
    global _last_status
    async with _check_lock:
        opened = await _is_backend_opened()

        if _last_status is None:
            if send_if_unknown:
                if await _send_status(opened):
                    _last_status = opened
                    _save_state(opened)
            return

        if opened != _last_status:
            if await _send_status(opened):
                _last_status = opened
                _save_state(opened)


@scheduler.scheduled_job(
    "interval",
    seconds=QUICK_POLL_SECONDS,
    id="comfyui_status_quick_poll",
)
async def _quick_status_poll() -> None:
    """近实时探测：感知后端开机/关机事件。"""
    await _monitor_once()


@scheduler.scheduled_job(
    "interval",
    minutes=PERIODIC_CHECK_MINUTES,
    id="comfyui_status_periodic_check",
)
async def _periodic_status_check() -> None:
    """每 10 分钟复核；状态未变化时不发送消息。"""
    await _monitor_once()


@get_driver().on_bot_connect
async def _on_bot_connect(_bot: Bot) -> None:
    """机器人连接成功后先确认一次状态；补发停机期间发生的状态变化。"""
    await asyncio.sleep(2)
    await _monitor_once()


_last_status = _load_state()
