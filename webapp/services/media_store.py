"""Temporary media uploads for Ref2VA generation.

These files are not part of the user asset library and do not consume the
asset storage quota. They are written under ``data/video_uploads`` and should
be cleaned up after a generation attempt.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

from config import (
    ASSET_MAX_AUDIO_BYTES,
    ASSET_MAX_IMAGE_BYTES,
    ASSET_MAX_VIDEO_BYTES,
    VIDEO_UPLOAD_DIR,
)

logger = logging.getLogger(__name__)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".gif", ".avi"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}


def infer_kind(filename: str, content_type: str = "") -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".gif":
        return "video"
    if ext in IMAGE_EXTS or content_type.startswith("image/"):
        return "image"
    if ext in VIDEO_EXTS or content_type.startswith("video/"):
        return "video"
    if ext in AUDIO_EXTS or content_type.startswith("audio/"):
        return "audio"
    raise ValueError(f"不支持的参考素材类型：{filename}")


class TempMediaStore:
    def __init__(self):
        VIDEO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    def save(self, filename: str, content_type: str, data: bytes) -> dict:
        kind = infer_kind(filename, content_type)
        max_size = {
            "image": ASSET_MAX_IMAGE_BYTES,
            "video": ASSET_MAX_VIDEO_BYTES,
            "audio": ASSET_MAX_AUDIO_BYTES,
        }[kind]
        if len(data) <= 0:
            raise ValueError("文件为空")
        if len(data) > max_size:
            raise ValueError(f"参考素材超过单文件限制：{len(data)} > {max_size}")
        upload_id = str(uuid.uuid4())
        ext = Path(filename).suffix.lower() or ".bin"
        target = VIDEO_UPLOAD_DIR / f"{upload_id}{ext}"
        target.write_bytes(data)
        manifest = VIDEO_UPLOAD_DIR / f"{upload_id}.json"
        manifest.write_text(
            json.dumps(
                {
                    "id": upload_id,
                    "kind": kind,
                    "filename": filename,
                    "content_type": content_type,
                    "size": len(data),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return {"id": upload_id, "kind": kind, "size_bytes": len(data)}

    def get_path(self, upload_id: str, expected_kind: str) -> Path:
        manifest = VIDEO_UPLOAD_DIR / f"{upload_id}.json"
        if not manifest.exists():
            raise FileNotFoundError(f"临时素材不存在：{upload_id}")
        try:
            meta = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise FileNotFoundError(f"临时素材元数据损坏：{upload_id}") from exc
        if meta.get("kind") != expected_kind:
            raise ValueError(
                f"素材类型不匹配：期望 {expected_kind}，实际 {meta.get('kind')}"
            )
        path = VIDEO_UPLOAD_DIR / f"{upload_id}{Path(meta.get('filename', '')).suffix.lower() or '.bin'}"
        if not path.exists():
            raise FileNotFoundError(f"临时素材文件不存在：{upload_id}")
        return path.resolve()

    def delete(self, upload_ids: list[str]):
        for upload_id in upload_ids or []:
            manifest = VIDEO_UPLOAD_DIR / f"{upload_id}.json"
            if not manifest.exists():
                continue
            try:
                meta = json.loads(manifest.read_text(encoding="utf-8"))
                ext = Path(meta.get("filename", "")).suffix.lower() or ".bin"
                path = VIDEO_UPLOAD_DIR / f"{upload_id}{ext}"
                path.unlink(missing_ok=True)
                manifest.unlink(missing_ok=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to clean temp upload %s: %s", upload_id, exc)

    def cleanup_old(self, age_seconds: int = 24 * 60 * 60) -> int:
        removed = 0
        now = time.time()
        for manifest in VIDEO_UPLOAD_DIR.glob("*.json"):
            try:
                if now - manifest.stat().st_mtime < age_seconds:
                    continue
                meta = json.loads(manifest.read_text(encoding="utf-8"))
                ext = Path(meta.get("filename", "")).suffix.lower() or ".bin"
                (VIDEO_UPLOAD_DIR / f"{meta.get('id')}{ext}").unlink(missing_ok=True)
                manifest.unlink(missing_ok=True)
                removed += 1
            except Exception:  # noqa: BLE001
                continue
        if removed:
            logger.info("Cleaned %d expired temp video uploads", removed)
        return removed


temp_media_store = TempMediaStore()
