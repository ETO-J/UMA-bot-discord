"""Discord 频道历史抓取模块（文本 / 图片 / 全部）。"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import httpx
from nonebot import on_message
from nonebot.adapters.discord import Bot, MessageEvent
from nonebot.adapters.discord.api import (
    Attachment,
    Channel,
    MessageGet,
)
from nonebot.adapters.discord.api.types import UNSET
from nonebot.log import logger
from nonebot.rule import Rule
from nonebot_plugin_alconna import UniMessage

from ..config import GRABBING_DATA_DIR, is_admin

MODE_TEXT = "text"
MODE_IMAGE = "image"
MODE_ALL = "all"

MODE_ALIASES: dict[str, str] = {
    "文本": MODE_TEXT,
    "文字": MODE_TEXT,
    "text": MODE_TEXT,
    "图片": MODE_IMAGE,
    "图": MODE_IMAGE,
    "image": MODE_IMAGE,
    "images": MODE_IMAGE,
    "全部": MODE_ALL,
    "all": MODE_ALL,
    "everything": MODE_ALL,
}
MODE_LABELS = {
    MODE_TEXT: "文本",
    MODE_IMAGE: "图片",
    MODE_ALL: "全部",
}

# 可以直接拉取消息的 Discord 频道类型
MESSAGE_CHANNEL_TYPES = {0, 1, 3, 5, 10, 11, 12}
# 可以包含子线程的频道类型（普通文本、公告、论坛）
THREAD_PARENT_CHANNEL_TYPES = {0, 5, 15}
FORUM_CHANNEL_TYPE = 15
PAGE_SIZE = 100
FETCH_DELAY_SECONDS = 0.25

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".avif",
    ".heic",
    ".heif",
    ".tif",
    ".tiff",
    ".svg",
}

CONTENT_TYPE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/avif": ".avif",
    "image/svg+xml": ".svg",
    "application/octet-stream": ".bin",
}

DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# 同一时间只允许一个抓取任务，避免多个命令同时写同一批目录。
# 延迟创建 Lock，兼容 Python 3.9 在没有运行事件循环时导入插件。
_grabbing_lock: Optional[asyncio.Lock] = None


def _get_grabbing_lock() -> asyncio.Lock:
    global _grabbing_lock
    if _grabbing_lock is None:
        _grabbing_lock = asyncio.Lock()
    return _grabbing_lock


def _field_str(value: Any) -> str:
    """把模型中的 UNSET/None 值转成普通字符串。"""
    if value is None or value is UNSET:
        return ""
    text = str(value)
    if text == "<UNSET>" or text == "UNSET":
        return ""
    return text


def _optional_int(value: Any) -> Optional[int]:
    text = _field_str(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _safe_segment(value: Any, fallback: str = "item", max_len: int = 80) -> str:
    """生成可用于 Windows 路径的安全文件名片段。"""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value)).strip(" .")
    if not text:
        text = fallback
    if text.upper() in {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "LPT1", "LPT2"}:
        text = f"_{text}"
    return text[:max_len] or fallback


def _parse_iso_datetime(value: Any) -> Optional[dt.datetime]:
    """解析 Discord 返回的时间字符串。"""
    if value is None or value is UNSET:
        return None
    if isinstance(value, dt.datetime):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        return None


def _channel_name(channel: Channel) -> str:
    return _field_str(getattr(channel, "name", "")) or str(channel.id)


def _channel_guild_id(channel: Channel, fallback: Optional[str]) -> Optional[str]:
    guild_id = getattr(channel, "guild_id", None)
    if guild_id is None or guild_id is UNSET:
        return fallback
    return str(guild_id)


def _get_event_guild_id(event: MessageEvent) -> Optional[str]:
    value = getattr(event, "guild_id", None)
    if value is None or value is UNSET:
        return None
    text = str(value)
    if text == "<UNSET>" or text == "UNSET":
        return None
    return text


def _is_message_channel(channel: Channel) -> bool:
    return int(channel.type) in MESSAGE_CHANNEL_TYPES


def _clean_channel_id(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[#<>@!]", "", value)
    return value


def _decode_command(raw_text: str) -> tuple[Optional[str], Optional[str]]:
    """解析：抓取 模式 [频道id]。"""
    raw_text = raw_text.strip()
    if raw_text.startswith(("/抓取", "!抓取")):
        raw_text = raw_text[1:]
    if not raw_text.startswith("抓取"):
        return None, None
    rest = raw_text[len("抓取") :].strip()
    if not rest:
        return None, None
    parts = rest.split(maxsplit=1)
    mode = MODE_ALIASES.get(parts[0].lower())
    if mode is None:
        return None, None
    channel_id = None
    if len(parts) > 1:
        raw_channel_id = _clean_channel_id(parts[1])
        if raw_channel_id and raw_channel_id.isdigit():
            channel_id = raw_channel_id
        else:
            return None, None
    return mode, channel_id


def _is_grabbing_command(event: MessageEvent) -> bool:
    raw_text = event.get_plaintext().strip()
    return raw_text.startswith(("抓取", "/抓取", "!抓取"))


async def _list_active_threads(bot: Bot, guild_id: str) -> list[Channel]:
    """列出当前服务器所有活跃线程。"""
    try:
        response = await bot.list_active_guild_threads(guild_id=guild_id)
        return list(getattr(response, "threads", []) or [])
    except Exception as exc:
        logger.warning(f"获取活跃线程失败: {exc}")
        return []


async def _list_archived_threads(
    bot: Bot,
    channel_id: str,
    kind: str,
) -> list[Channel]:
    """分页获取某个父频道的归档线程。"""
    result: list[Channel] = []
    before: Optional[dt.datetime] = None
    for _ in range(10000):
        kwargs: dict[str, Any] = {"channel_id": channel_id, "limit": PAGE_SIZE}
        if before is not None:
            kwargs["before"] = before
        try:
            if kind == "public":
                response = await bot.list_public_archived_threads(**kwargs)
            else:
                try:
                    response = await bot.list_private_archived_threads(**kwargs)
                except Exception:
                    # 没有 MANAGE_THREADS 权限时，至少抓取已加入的私密线程
                    response = await bot.list_joined_private_archived_threads(
                        **kwargs
                    )
        except Exception:
            # 私密线程没有权限时直接跳过，不影响其他频道
            break
        threads = list(getattr(response, "threads", []) or [])
        result.extend(threads)
        has_more = bool(getattr(response, "has_more", False))
        if not has_more or not threads:
            break
        last_thread = threads[-1]
        metadata = getattr(last_thread, "thread_metadata", None)
        archive_timestamp = (
            getattr(metadata, "archive_timestamp", None) if metadata else None
        )
        next_before = _parse_iso_datetime(archive_timestamp)
        if next_before is None or next_before == before:
            break
        before = next_before
        await asyncio.sleep(FETCH_DELAY_SECONDS)
    return result


def _deduplicate_channels(channels: list[Channel]) -> list[Channel]:
    seen: set[str] = set()
    result: list[Channel] = []
    for channel in channels:
        channel_id = str(channel.id)
        if channel_id in seen or not _is_message_channel(channel):
            continue
        seen.add(channel_id)
        result.append(channel)
    return result


async def _resolve_channels(
    bot: Bot,
    guild_id: Optional[str],
    explicit_channel_id: Optional[str],
) -> list[Channel]:
    """解析本次抓取目标：单个频道或整个服务器的可读子频道。"""
    if explicit_channel_id:
        channel = await bot.get_channel(channel_id=explicit_channel_id)
        if int(channel.type) == FORUM_CHANNEL_TYPE:
            # 论坛父频道本身没有直接消息，抓取其帖子/线程
            threads: list[Channel] = []
            if guild_id:
                threads.extend(
                    thread
                    for thread in await _list_active_threads(bot, guild_id)
                    if _field_str(getattr(thread, "parent_id", ""))
                    == explicit_channel_id
                )
            threads.extend(
                await _list_archived_threads(bot, explicit_channel_id, "public")
            )
            threads.extend(
                await _list_archived_threads(bot, explicit_channel_id, "private")
            )
            return _deduplicate_channels(threads)
        if not _is_message_channel(channel):
            return []
        return [channel]

    if not guild_id:
        return []

    base_channels = list(await bot.get_guild_channels(guild_id=guild_id))
    channels = list(base_channels)
    channels.extend(await _list_active_threads(bot, guild_id))

    # 普通文本/公告/论坛频道里的归档线程
    for parent in base_channels:
        if int(parent.type) not in THREAD_PARENT_CHANNEL_TYPES:
            continue
        parent_id = str(parent.id)
        channels.extend(await _list_archived_threads(bot, parent_id, "public"))
        channels.extend(await _list_archived_threads(bot, parent_id, "private"))

    return _deduplicate_channels(channels)


def _is_image_attachment(attachment: Attachment) -> bool:
    content_type = _field_str(getattr(attachment, "content_type", "")).lower()
    if content_type.startswith("image/"):
        return True
    filename = _field_str(getattr(attachment, "filename", "")).lower()
    return Path(filename).suffix.lower() in IMAGE_EXTENSIONS


def _original_url(url: Any) -> str:
    """返回图片原图地址，去掉 Discord CDN 的尺寸/格式参数。"""
    url_text = _field_str(url)
    if not url_text:
        return ""
    parts = urlsplit(url_text)
    query_pairs = []
    discord_host = parts.netloc.lower() in {
        "cdn.discordapp.com",
        "media.discordapp.net",
    }
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if discord_host and key.lower() in {
            "width",
            "height",
            "format",
            "size",
            "quality",
        }:
            continue
        query_pairs.append((key, value))

    netloc = parts.netloc
    if netloc.lower() == "media.discordapp.net" and "/attachments/" in parts.path:
        netloc = "cdn.discordapp.com"
    return urlunsplit(
        (
            parts.scheme or "https",
            netloc,
            parts.path,
            urlencode(query_pairs, quote_via=quote),
            parts.fragment,
        )
    )


def _extension_from_url(url: str) -> str:
    suffix = Path(urlsplit(url).path).suffix.lower()
    if suffix and len(suffix) <= 10:
        return suffix
    return ""


def _extension_from_content_type(content_type: str) -> str:
    return CONTENT_TYPE_EXTENSIONS.get(content_type.lower(), "")


def _attachment_url(attachment: Attachment) -> str:
    return _original_url(
        getattr(attachment, "url", "") or getattr(attachment, "proxy_url", "")
    )


def _embed_image_url(embed: Any) -> str:
    image = getattr(embed, "image", None)
    if not image:
        return ""
    return _original_url(getattr(image, "url", ""))


def _embed_thumbnail_url(embed: Any) -> str:
    thumbnail = getattr(embed, "thumbnail", None)
    if not thumbnail:
        return ""
    return _original_url(getattr(thumbnail, "url", ""))


def _has_image_media(message: MessageGet) -> bool:
    for attachment in getattr(message, "attachments", []) or []:
        if _is_image_attachment(attachment):
            return True
    for embed in getattr(message, "embeds", []) or []:
        if _embed_image_url(embed):
            return True
    return False


def _should_save_message(message: MessageGet, mode: str) -> bool:
    if mode == MODE_TEXT:
        return bool(_field_str(getattr(message, "content", "")).strip())
    if mode == MODE_IMAGE:
        return _has_image_media(message)
    return True


def _attachment_info(attachment: Attachment) -> dict[str, Any]:
    return {
        "id": _field_str(getattr(attachment, "id", "")),
        "filename": _field_str(getattr(attachment, "filename", "")),
        "content_type": _field_str(getattr(attachment, "content_type", "")),
        "size": int(getattr(attachment, "size", 0) or 0),
        "url": _attachment_url(attachment),
        "proxy_url": _original_url(getattr(attachment, "proxy_url", "")),
        "width": _optional_int(getattr(attachment, "width", "")),
        "height": _optional_int(getattr(attachment, "height", "")),
        "is_image": _is_image_attachment(attachment),
        "saved_path": "",
    }


async def _download_file(
    client: httpx.AsyncClient,
    url: str,
    target_dir: Path,
    prefix: str,
    filename: str,
    content_type: str = "",
) -> Optional[Path]:
    """下载文件并按原始文件保存，已存在时跳过。"""
    if not url:
        return None
    stem = Path(filename).stem or "file"
    suffix = Path(filename).suffix
    if not suffix or len(suffix) > 10:
        suffix = (
            _extension_from_url(url)
            or _extension_from_content_type(content_type)
            or ".bin"
        )
    safe_prefix = _safe_segment(prefix, "file", max_len=50)
    safe_stem = _safe_segment(stem, "file", max_len=60)
    target = target_dir / f"{safe_prefix}_{safe_stem}{suffix}"
    if target.exists() and target.is_file() and target.stat().st_size > 0:
        return target

    target_dir.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".part")
    if temp.exists():
        temp.unlink()
    try:
        async with client.stream("GET", url, headers=DOWNLOAD_HEADERS) as response:
            response.raise_for_status()
            real_content_type = response.headers.get("content-type", "")
            if (
                not suffix
                or suffix == ".bin"
                or (
                    real_content_type.lower().startswith("image/")
                    and suffix.lower() not in IMAGE_EXTENSIONS
                )
            ):
                detected = _extension_from_content_type(real_content_type)
                if detected:
                    target = target.with_suffix(detected)
                    temp = target.with_name(target.name + ".part")
            with open(temp, "wb") as file_handle:
                async for chunk in response.aiter_bytes():
                    file_handle.write(chunk)
        temp.replace(target)
        return target
    except Exception as exc:
        logger.warning(f"下载失败 {url}: {exc}")
        if temp.exists():
            temp.unlink()
        return None


async def _build_record(
    client: httpx.AsyncClient,
    message: MessageGet,
    mode: str,
    channel_dir: Path,
) -> Optional[dict[str, Any]]:
    """构建一条可读的消息记录，并按模式抓取图片/附件。"""
    message_id = str(message.id)
    content = _field_str(getattr(message, "content", ""))
    attachments = list(getattr(message, "attachments", []) or [])
    embeds = list(getattr(message, "embeds", []) or [])
    author = getattr(message, "author", None)

    record: dict[str, Any] = {
        "message_id": message_id,
        "channel_id": str(message.channel_id),
        "author_id": _field_str(getattr(author, "id", "")) if author else "",
        "author_name": _field_str(getattr(author, "username", "")) if author else "",
        "timestamp": _field_str(getattr(message, "timestamp", "")),
        "edited_timestamp": _field_str(getattr(message, "edited_timestamp", "")),
        "message_type": _field_str(getattr(message, "type", "")),
        "pinned": bool(getattr(message, "pinned", False)),
        "content": content,
        "attachments": [],
        "embeds": [],
        "files": [],
        "download_errors": [],
        "reactions": [
            {
                "count": _optional_int(getattr(reaction, "count", "")) or 0,
                "emoji": _field_str(
                    getattr(getattr(reaction, "emoji", None), "name", "")
                ),
                "emoji_id": _field_str(
                    getattr(getattr(reaction, "emoji", None), "id", "")
                ),
            }
            for reaction in (getattr(message, "reactions", []) or [])
        ],
    }

    if mode in (MODE_IMAGE, MODE_ALL):
        for index, attachment in enumerate(attachments):
            is_image = _is_image_attachment(attachment)
            if mode == MODE_IMAGE and not is_image:
                continue
            info = _attachment_info(attachment)
            record["attachments"].append(info)
            if is_image:
                target_dir = channel_dir / "images"
            else:
                target_dir = channel_dir / "files"
            if info["url"]:
                saved = await _download_file(
                    client,
                    info["url"],
                    target_dir,
                    prefix=f"{message_id}_{index}",
                    filename=info["filename"],
                    content_type=info["content_type"],
                )
                if saved:
                    relative = saved.relative_to(channel_dir).as_posix()
                    info["saved_path"] = relative
                    record["files"].append(relative)
                else:
                    record["download_errors"].append(
                        f"附件 {info['filename']} 下载失败"
                    )

        # Discord Embed：记录完整信息；图片使用 embed.image 的原图地址，
        # 不下载 thumbnail，避免保存成缩略图/WebP 预览。
        for embed_index, embed in enumerate(embeds):
            image_url = _embed_image_url(embed)
            embed_info = {
                "title": _field_str(getattr(embed, "title", "")),
                "type": _field_str(getattr(embed, "type", "")),
                "description": _field_str(getattr(embed, "description", "")),
                "url": _field_str(getattr(embed, "url", "")),
                "image_url": image_url,
                "thumbnail_url": _embed_thumbnail_url(embed),
                "saved_path": "",
            }
            record["embeds"].append(embed_info)
            if not image_url:
                continue
            saved = await _download_file(
                client,
                image_url,
                channel_dir / "images",
                prefix=f"embed_{message_id}_{embed_index}",
                filename=Path(urlsplit(image_url).path).name
                or f"embed_{embed_index}",
                content_type="image/png",
            )
            if saved:
                relative = saved.relative_to(channel_dir).as_posix()
                embed_info["saved_path"] = relative
                record["files"].append(relative)
            else:
                record["download_errors"].append(
                    f"Embed 图片 {embed_info['title'] or embed_index} 下载失败"
                )
    elif mode == MODE_TEXT:
        # 文本模式只保存消息正文信息，不抓附件
        record["attachments"] = [
            _attachment_info(attachment) for attachment in attachments
        ]
        record["embeds"] = [
            {
                "title": _field_str(getattr(embed, "title", "")),
                "type": _field_str(getattr(embed, "type", "")),
                "description": _field_str(getattr(embed, "description", "")),
                "url": _field_str(getattr(embed, "url", "")),
                "image_url": _embed_image_url(embed),
                "thumbnail_url": _embed_thumbnail_url(embed),
            }
            for embed in embeds
        ]

    return record


async def _grab_channel(
    bot: Bot,
    client: httpx.AsyncClient,
    channel: Channel,
    mode: str,
    root: Path,
    fallback_guild_id: Optional[str],
    full_scan: bool = False,
) -> dict[str, Any]:
    """抓取单个频道的全部消息，并写入 messages.jsonl。"""
    channel_id = str(channel.id)
    guild_id = _channel_guild_id(channel, fallback_guild_id)
    guild_label = guild_id or "dm"
    if full_scan:
        # 全频道抓取：直接按频道号创建目录
        channel_dir = root / channel_id
    else:
        # 指定单频道：保留原结构（服务器/频道名/模式）
        channel_dir = (
            root
            / guild_label
            / f"{channel_id}_{_safe_segment(_channel_name(channel), 'channel')}"
            / mode
        )
    channel_dir.mkdir(parents=True, exist_ok=True)

    messages_path = channel_dir / "messages.jsonl"
    temp_path = channel_dir / ".messages.tmp"
    text_path = channel_dir / "text" / "messages.txt"
    text_temp = channel_dir / "text" / ".messages.txt.tmp"
    text_path.parent.mkdir(parents=True, exist_ok=True)
    (channel_dir / "images").mkdir(parents=True, exist_ok=True)
    (channel_dir / "files").mkdir(parents=True, exist_ok=True)
    if temp_path.exists():
        temp_path.unlink()
    if text_temp.exists():
        text_temp.unlink()

    stats: dict[str, Any] = {
        "channel_id": channel_id,
        "channel_name": _channel_name(channel),
        "channel_type": int(channel.type),
        "guild_id": guild_id,
        "mode": mode,
        "full_scan": full_scan,
        "message_count": 0,
        "media_count": 0,
        "errors": [],
    }
    before: Optional[str] = None

    try:
        with open(temp_path, "w", encoding="utf-8") as message_handle:
            with open(text_temp, "w", encoding="utf-8") as text_handle:
                while True:
                    try:
                        message_kwargs: dict[str, Any] = {
                            "channel_id": channel_id,
                            "limit": PAGE_SIZE,
                        }
                        if before is not None:
                            message_kwargs["before"] = before
                        batch = await bot.get_channel_messages(**message_kwargs)
                    except Exception as exc:
                        stats["errors"].append(f"获取消息分页失败: {exc}")
                        logger.warning(f"获取频道 {channel_id} 消息失败: {exc}")
                        break
                    if not batch:
                        break
                    for message in batch:
                        if not _should_save_message(message, mode):
                            continue
                        try:
                            record = await _build_record(
                                client, message, mode, channel_dir
                            )
                        except Exception as exc:
                            stats["errors"].append(
                                f"处理消息 {message.id} 失败: {exc}"
                            )
                            logger.warning(f"处理消息 {message.id} 失败: {exc}")
                            continue
                        if record is None:
                            continue
                        json.dump(
                            record,
                            message_handle,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        message_handle.write("\n")
                        if record.get("content"):
                            text_handle.write(
                                f"[{record.get('timestamp', '')}] "
                                f"{record.get('author_name') or '未知'}: "
                                f"{record.get('content', '')}\n"
                            )
                        stats["message_count"] += 1
                        stats["media_count"] += len(record.get("files", []))
                        stats["errors"].extend(record.get("download_errors", []))

                    oldest_id = str(batch[-1].id)
                    if before is not None and oldest_id == before:
                        break
                    before = oldest_id
                    await asyncio.sleep(FETCH_DELAY_SECONDS)
        temp_path.replace(messages_path)
        text_temp.replace(text_path)
    except Exception as exc:
        stats["errors"].append(f"抓取频道失败: {exc}")
        logger.exception(f"抓取频道 {channel_id} 失败")
        if temp_path.exists():
            temp_path.unlink()
        if text_temp.exists():
            text_temp.unlink()

    stats["status"] = "completed" if not stats["errors"] else "completed_with_errors"
    channel_json = {
        "grabbed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        **stats,
    }
    with open(channel_dir / "channel.json", "w", encoding="utf-8") as meta_handle:
        json.dump(channel_json, meta_handle, ensure_ascii=False, indent=2)
    return stats


async def _write_summary(
    results: list[dict[str, Any]],
    mode: str,
    guild_id: Optional[str],
    explicit_channel_id: Optional[str],
) -> None:
    summary = {
        "grabbed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": mode,
        "guild_id": guild_id,
        "explicit_channel_id": explicit_channel_id,
        "full_scan": explicit_channel_id is None,
        "channel_count": len(results),
        "message_count": sum(item.get("message_count", 0) for item in results),
        "media_count": sum(item.get("media_count", 0) for item in results),
        "channels": [
            {
                "channel_id": item.get("channel_id"),
                "channel_name": item.get("channel_name"),
                "status": item.get("status"),
                "message_count": item.get("message_count", 0),
                "media_count": item.get("media_count", 0),
            }
            for item in results
        ],
    }
    with open(GRABBING_DATA_DIR / "last_run.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)


grabbing_handler = on_message(
    priority=3,
    block=True,
    rule=Rule(_is_grabbing_command),
)


@grabbing_handler.handle()
async def handle_grabbing(bot: Bot, event: MessageEvent):
    user_id = event.get_user_id()
    if not is_admin(user_id):
        await UniMessage(
            "⚠️ 权限不足：抓取历史记录仅限管理员使用。"
        ).send(reply_message=True)
        return

    mode, explicit_channel_id = _decode_command(event.get_plaintext())
    if mode is None:
        await UniMessage(
            "用法：抓取 图片/文本/全部 [频道id]\n"
            "示例：抓取 全部\n"
            "示例：抓取 图片 123456789012345678"
        ).send(reply_message=True)
        return

    guild_id = _get_event_guild_id(event)
    if not explicit_channel_id and not guild_id:
        await UniMessage(
            "无法确定服务器：请填写频道id，或从服务器频道内发送命令。"
        ).send(reply_message=True)
        return

    _grabbing_lock = _get_grabbing_lock()
    if _grabbing_lock.locked():
        await UniMessage("已有抓取任务正在进行，请稍后再试。").send(
            reply_message=True
        )
        return

    await _grabbing_lock.acquire()
    try:
        try:
            channels = await _resolve_channels(bot, guild_id, explicit_channel_id)
        except Exception as exc:
            logger.exception("解析抓取频道失败")
            await UniMessage(f"解析频道失败，请检查频道id与机器人权限。错误：{exc}").send(
                reply_message=True
            )
            return

        if not channels:
            await UniMessage("没有找到可抓取的消息频道或子线程。").send(
                reply_message=True
            )
            return

        target_desc = (
            f"频道 {explicit_channel_id}"
            if explicit_channel_id
            else f"服务器 {guild_id} 的全部子频道"
        )
        await UniMessage(
            f"📦 开始抓取“{target_desc}”（模式：{MODE_LABELS.get(mode, mode)}）\n"
            f"找到 {len(channels)} 个频道/线程，历史较长时可能需要较长时间。"
        ).send(reply_message=True)

        GRABBING_DATA_DIR.mkdir(parents=True, exist_ok=True)
        results: list[dict[str, Any]] = []
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(180.0),
            follow_redirects=True,
        ) as client:
            for index, channel in enumerate(channels, start=1):
                try:
                    channel_result = await _grab_channel(
                        bot,
                        client,
                        channel,
                        mode,
                        GRABBING_DATA_DIR,
                        guild_id,
                        full_scan=explicit_channel_id is None,
                    )
                except Exception as exc:
                    logger.exception("抓取频道时发生未预期异常")
                    channel_result = {
                        "channel_id": str(channel.id),
                        "channel_name": _channel_name(channel),
                        "channel_type": int(channel.type),
                        "guild_id": _channel_guild_id(channel, guild_id),
                        "mode": mode,
                        "message_count": 0,
                        "media_count": 0,
                        "status": "failed",
                        "errors": [f"未预期异常: {exc}"],
                    }
                    await UniMessage(
                        f"⚠️ [{index}/{len(channels)}] 频道 "
                        f"{channel_result['channel_name']} 抓取失败：{exc}"
                    ).send(reply_message=True)
                results.append(channel_result)
                if channel_result.get("status") != "failed":
                    await UniMessage(
                        f"✅ [{index}/{len(channels)}] {channel_result['channel_name']} "
                        f"（消息 {channel_result['message_count']} 条，"
                        f"媒体 {channel_result['media_count']} 个）"
                    ).send(reply_message=True)

        summary_written = True
        try:
            await _write_summary(results, mode, guild_id, explicit_channel_id)
        except Exception as exc:
            summary_written = False
            logger.exception("写入抓取摘要失败")
            await UniMessage(f"⚠️ 写入 last_run.json 摘要失败：{exc}").send(
                reply_message=True
            )
        total_messages = sum(item.get("message_count", 0) for item in results)
        total_media = sum(item.get("media_count", 0) for item in results)
        error_channels = sum(
            1
            for item in results
            if item.get("status") in {"completed_with_errors", "failed"}
        )
        await UniMessage(
            f"🎉 抓取完成：{len(channels)} 个频道/线程，"
            f"{total_messages} 条消息，{total_media} 个媒体文件。\n"
            f"存储目录：{GRABBING_DATA_DIR}\n"
            + (f"生成文件：last_run.json" if summary_written else "")
            + (f"\n⚠️ {error_channels} 个频道存在部分错误，详见对应 channel.json。"
               if error_channels else "")
        ).send(reply_message=True)
    finally:
        _grabbing_lock.release()
