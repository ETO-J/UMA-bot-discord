"""Publish/delete public-asset announcements on Discord.

Uses the same bot token (DiscordToken in .env) as the NoneBot2 process, so
messages are posted and silently removed ("no-trace 撤回") through the bot
account without depending on the bot process being online at that moment.
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from pathlib import Path

import httpx

from config import (
    ASSET_DISCORD_MAX_UPLOAD_MB,
    ASSET_PUBLISH_CHANNEL_ID,
    DISCORD_API_BASE,
    DISCORD_BOT_TOKEN,
    DISCORD_PROXY,
)

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15.0
MAX_RETRIES = 2

_username_cache: dict[str, str] = {}


class DiscordPublishError(Exception):
    """Raised when the Discord API rejects a feed operation."""


def feed_enabled() -> bool:
    """True when a bot token and an announcement channel are configured."""
    return bool(DISCORD_BOT_TOKEN and ASSET_PUBLISH_CHANNEL_ID)


def _client_kwargs():
    kwargs = {"timeout": REQUEST_TIMEOUT}
    if DISCORD_PROXY:
        kwargs["proxy"] = DISCORD_PROXY
    return kwargs


def _auth_headers() -> dict:
    return {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}


def _attachment_candidates(file_path: Path | None, thumb_path: Path | None) -> list[tuple[Path, str]]:
    """Pick the best attachment for the feed message (file first, then thumb)."""
    cap = ASSET_DISCORD_MAX_UPLOAD_MB * 1024 * 1024
    candidates: list[tuple[Path, str]] = []
    if file_path and file_path.is_file() and file_path.stat().st_size <= cap:
        candidates.append((file_path, "file"))
    if thumb_path and thumb_path.is_file() and thumb_path.stat().st_size <= cap:
        candidates.append((thumb_path, "thumbnail"))
    return candidates


def _kind_label(kind: str) -> str:
    return {"image": "图片", "video": "视频", "audio": "音频"}.get(kind, kind)


def _build_content(*, title: str, description: str, publisher_name: str, kind: str, tags: list[str]) -> str:
    lines = ["📢 **公共素材库 · 新发布**", ""]
    lines.append(f"**{title or '(未命名素材)'}**")
    lines.append(f"上传者：{publisher_name or '未知用户'}")
    lines.append(f"类型：{_kind_label(kind)}")
    desc = (description or "").strip().replace("\n", " ")
    if desc:
        lines.append("")
        lines.append(desc[:400])
    clean_tags = [t.strip().strip("#") for t in (tags or []) if t and t.strip()]
    if clean_tags:
        lines.append("")
        lines.append(" ".join(f"`#{t}`" for t in clean_tags[:12]))
    return "\n".join(lines)


async def _post_message(content: str, filename: str | None, data: bytes | None, mime: str | None) -> str:
    headers = _auth_headers()
    files = None
    if filename and data is not None:
        files = {"file": (filename, data, mime or "application/octet-stream")}
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(**_client_kwargs()) as client:
                resp = await client.post(
                    f"{DISCORD_API_BASE}/channels/{ASSET_PUBLISH_CHANNEL_ID}/messages",
                    headers=headers,
                    data={"content": content},
                    files=files,
                )
                if resp.status_code == 429:
                    retry_after = float(resp.json().get("retry_after", 1.0))
                    await asyncio.sleep(min(retry_after, 5.0))
                    continue
                if resp.status_code >= 300:
                    raise DiscordPublishError(
                        f"Discord post failed (HTTP {resp.status_code}): {resp.text[:300]}"
                    )
                return str(resp.json()["id"])
        except DiscordPublishError:
            raise
        except Exception as exc:  # noqa: BLE001 - network/parse errors
            last_error = exc
            logger.warning(
                "Discord publish attempt %s/%s failed: %s",
                attempt + 1,
                MAX_RETRIES + 1,
                exc,
            )
            if attempt < MAX_RETRIES:
                await asyncio.sleep(1.0 * (attempt + 1))
    raise DiscordPublishError(f"Discord publish failed after retries: {last_error}")


async def post_publish_message(
    *,
    title: str,
    description: str,
    publisher_name: str,
    kind: str,
    tags: list[str],
    file_path: Path | None = None,
    thumb_path: Path | None = None,
) -> str | None:
    """Announce a new public asset. Returns the Discord message id (None when disabled)."""
    if not feed_enabled():
        logger.info("Discord feed sync disabled (no token/channel configured)")
        return None
    content = _build_content(
        title=title, description=description, publisher_name=publisher_name,
        kind=kind, tags=tags,
    )
    filename = data = mime = None
    for path, which in _attachment_candidates(file_path, thumb_path):
        try:
            data = path.read_bytes()
            mime = {
                "file": None,  # let Discord sniff the real type
                "thumbnail": "image/webp",
            }.get(which, None)
            filename = path.name
            break
        except OSError as exc:
            logger.warning("Feed attachment unreadable (%s): %s", path, exc)
    message_id = await _post_message(content, filename, data, mime)
    logger.info("Public asset announcement posted to channel %s (message %s)", ASSET_PUBLISH_CHANNEL_ID, message_id)
    return message_id


async def delete_publish_message(message_id: str) -> bool:
    """Silently delete an announcement. 404 counts as already-gone success."""
    if not feed_enabled() or not message_id:
        return False
    headers = _auth_headers()
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(**_client_kwargs()) as client:
                resp = await client.delete(
                    f"{DISCORD_API_BASE}/channels/{ASSET_PUBLISH_CHANNEL_ID}/messages/{message_id}",
                    headers=headers,
                )
                if resp.status_code == 429:
                    retry_after = float(resp.json().get("retry_after", 1.0))
                    await asyncio.sleep(min(retry_after, 5.0))
                    continue
                if resp.status_code in (200, 204, 404):
                    return True
                last_error = DiscordPublishError(
                    f"Discord delete failed (HTTP {resp.status_code}): {resp.text[:300]}"
                )
                logger.warning("Discord delete attempt %s/%s failed: %s", attempt + 1, MAX_RETRIES + 1, last_error)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("Discord delete attempt %s/%s failed: %s", attempt + 1, MAX_RETRIES + 1, exc)
        if attempt < MAX_RETRIES:
            await asyncio.sleep(1.0 * (attempt + 1))
    logger.error("Discord announcement delete failed after retries: %s", last_error)
    return False


async def resolve_username(user_id: str) -> str | None:
    """Resolve a Discord user id to a username (used to backfill legacy rows)."""
    if not DISCORD_BOT_TOKEN or not user_id or user_id == "local_user":
        return None
    if user_id in _username_cache:
        return _username_cache[user_id]
    try:
        async with httpx.AsyncClient(**_client_kwargs()) as client:
            resp = await client.get(f"{DISCORD_API_BASE}/users/{user_id}", headers=_auth_headers())
            if resp.status_code == 200:
                name = resp.json().get("username") or resp.json().get("global_name")
                if name:
                    _username_cache[user_id] = str(name)
                    return str(name)
    except Exception:  # noqa: BLE001
        logger.debug("resolve_username(%s) failed:\n%s", user_id, traceback.format_exc())
    return None
