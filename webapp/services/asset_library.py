"""Local asset library with per-user storage quotas.

Assets are stored under ``ASSET_LIBRARY_ROOT`` with blob-level SHA-256
deduplication. SQLite keeps ownership, folders, tags, published snapshots, and
a small FTS index. The asset root is intentionally never exposed directly to
the browser; all downloads go through the API.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from pathlib import Path

from config import (
    ASSET_BLOB_DIR,
    ASSET_DB_PATH,
    ASSET_LIBRARY_DISABLED_LIMIT,
    ASSET_LIBRARY_LARGE_BYTES,
    ASSET_LIBRARY_LARGE_LIMIT,
    ASSET_LIBRARY_MEDIUM_BYTES,
    ASSET_LIBRARY_MEDIUM_LIMIT,
    ASSET_LIBRARY_ROOT,
    ASSET_MAX_AUDIO_BYTES,
    ASSET_MAX_IMAGE_BYTES,
    ASSET_MAX_VIDEO_BYTES,
    ASSET_THUMB_DIR,
)
from services.workflow_manager import wm

logger = logging.getLogger(__name__)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".gif", ".avi"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}


def _infer_kind(filename: str, content_type: str = "") -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".gif":
        return "video"
    if ext in IMAGE_EXTS or content_type.startswith("image/"):
        return "image"
    if ext in VIDEO_EXTS or content_type.startswith("video/"):
        return "video"
    if ext in AUDIO_EXTS or content_type.startswith("audio/"):
        return "audio"
    raise ValueError(f"Unsupported media type: {filename}")


def _ffprobe_meta(path: Path) -> dict:
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    try:
        out = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "stream=width,height,duration:format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if out.returncode != 0:
            return {}
        data = json.loads(out.stdout or "{}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("ffprobe failed for %s: %s", path, exc)
        return {}
    streams = data.get("streams") or []
    width = height = None
    duration = None
    for stream in streams:
        if stream.get("codec_type") == "video":
            width = stream.get("width")
            height = stream.get("height")
            duration = _safe_float(stream.get("duration"))
            break
    if duration is None:
        duration = _safe_float(data.get("format", {}).get("duration"))
    return {"width": width, "height": height, "duration": duration}


def _safe_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class AssetLibraryUnavailable(RuntimeError):
    """Raised when the asset-library root/database cannot be initialized."""


class AssetLibrary:
    def __init__(self):
        self._lock = threading.RLock()
        self._conn = None
        self.available = False
        try:
            ASSET_LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)
            ASSET_BLOB_DIR.mkdir(parents=True, exist_ok=True)
            ASSET_THUMB_DIR.mkdir(parents=True, exist_ok=True)
            ASSET_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(ASSET_DB_PATH), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._init_db()
            self.available = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Asset library unavailable; continuing in degraded mode: %s", exc)

    def _migrate_blobs_per_user(self, cur):
        """One-time migration: asset_blobs sha256 -> (user_id, sha256), files
        moved from <root>/blobs|thumbs into <root>/<user_id>/blobs|thumbs."""
        logger.info("Migrating asset_blobs to per-user storage layout ...")
        cur.execute("ALTER TABLE asset_blobs RENAME TO asset_blobs_old")
        cur.execute(
            """
            CREATE TABLE asset_blobs (
                user_id TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                rel_path TEXT NOT NULL,
                thumb_rel_path TEXT,
                mime_type TEXT NOT NULL,
                size INTEGER NOT NULL,
                width INTEGER,
                height INTEGER,
                duration REAL,
                created_at REAL NOT NULL,
                PRIMARY KEY (user_id, sha256)
            )
            """
        )
        rows = cur.execute("SELECT * FROM asset_blobs_old").fetchall()
        migrated = dropped = 0
        for row in rows:
            sha = row["sha256"]
            users = {
                u[0]
                for u in cur.execute(
                    "SELECT owner_id FROM assets WHERE blob_sha256=? "
                    "UNION SELECT publisher_id FROM published_assets WHERE blob_sha256=?",
                    (sha, sha),
                ).fetchall()
            }
            if not users:
                dropped += 1  # no asset/ published row references it anymore
                continue
            old_path = ASSET_LIBRARY_ROOT / row["rel_path"]
            old_thumb = (
                ASSET_LIBRARY_ROOT / row["thumb_rel_path"] if row["thumb_rel_path"] else None
            )
            blob_name = Path(row["rel_path"]).name
            thumb_name = Path(row["thumb_rel_path"]).name if row["thumb_rel_path"] else None
            for uid in users:
                new_rel = f"{uid}/blobs/{blob_name}"
                new_thumb_rel = f"{uid}/thumbs/{thumb_name}" if thumb_name else None
                dest = ASSET_LIBRARY_ROOT / new_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                if old_path.exists():
                    try:
                        shutil.copy2(old_path, dest)
                    except OSError as exc:  # noqa: BLE001
                        logger.warning("Blob migration copy failed %s: %s", old_path, exc)
                if old_thumb and old_thumb.exists() and new_thumb_rel:
                    tdest = ASSET_LIBRARY_ROOT / new_thumb_rel
                    tdest.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(old_thumb, tdest)
                    except OSError as exc:  # noqa: BLE001
                        logger.warning("Thumb migration copy failed %s: %s", old_thumb, exc)
                cur.execute(
                    """
                    INSERT INTO asset_blobs (
                        user_id, sha256, rel_path, thumb_rel_path, mime_type,
                        size, width, height, duration, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uid, sha, new_rel, new_thumb_rel, row["mime_type"],
                        row["size"], row["width"], row["height"], row["duration"],
                        row["created_at"],
                    ),
                )
                migrated += 1
        cur.execute("DROP TABLE asset_blobs_old")
        self._conn.commit()
        logger.info("asset_blobs migration done: rows=%d orphans dropped=%d", migrated, dropped)

    def _require_available(self):
        if not self.available or self._conn is None:
            raise AssetLibraryUnavailable("资产库不可用：存储目录或数据库初始化失败")

    def _init_db(self):
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS asset_folders (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    parent_id TEXT,
                    is_root INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                )
                """
            )
            folder_cols = [col[1] for col in cur.execute("PRAGMA table_info(asset_folders)").fetchall()]
            if "is_root" not in folder_cols:
                cur.execute("ALTER TABLE asset_folders ADD COLUMN is_root INTEGER NOT NULL DEFAULT 0")
            blob_cols = [col[1] for col in cur.execute("PRAGMA table_info(asset_blobs)").fetchall()]
            if blob_cols and "user_id" not in blob_cols:
                self._migrate_blobs_per_user(cur)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS asset_blobs (
                    user_id TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    rel_path TEXT NOT NULL,
                    thumb_rel_path TEXT,
                    mime_type TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    duration REAL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (user_id, sha256)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]',
                    folder_id TEXT,
                    visibility TEXT NOT NULL DEFAULT 'private',
                    blob_sha256 TEXT NOT NULL,
                    subject_key TEXT,
                    subject_aliases TEXT NOT NULL DEFAULT '',
                    subject_role TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    FOREIGN KEY(folder_id) REFERENCES asset_folders(id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS published_assets (
                    published_id TEXT PRIMARY KEY,
                    source_asset_id TEXT NOT NULL,
                    publisher_id TEXT NOT NULL,
                    blob_sha256 TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '[]',
                    subject_key TEXT,
                    subject_aliases TEXT NOT NULL DEFAULT '',
                    subject_role TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS asset_likes (
                    published_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (published_id, user_id)
                )
                """
            )
            asset_cols = [col[1] for col in cur.execute("PRAGMA table_info(assets)").fetchall()]
            if "subject_aliases" not in asset_cols:
                cur.execute("ALTER TABLE assets ADD COLUMN subject_aliases TEXT NOT NULL DEFAULT ''")
            published_cols = [
                col[1] for col in cur.execute("PRAGMA table_info(published_assets)").fetchall()
            ]
            if "kind" not in published_cols:
                cur.execute("ALTER TABLE published_assets ADD COLUMN kind TEXT NOT NULL DEFAULT 'image'")
            if "subject_aliases" not in published_cols:
                cur.execute(
                    "ALTER TABLE published_assets ADD COLUMN subject_aliases TEXT NOT NULL DEFAULT ''"
                )
            if "publisher_name" not in published_cols:
                cur.execute(
                    "ALTER TABLE published_assets ADD COLUMN publisher_name TEXT NOT NULL DEFAULT ''"
                )
            if "discord_message_id" not in published_cols:
                cur.execute("ALTER TABLE published_assets ADD COLUMN discord_message_id TEXT")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_asset_likes_pub ON asset_likes(published_id)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_assets_owner ON assets(owner_id, created_at DESC)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_assets_folder ON assets(folder_id)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_published_publisher "
                "ON published_assets(publisher_id, created_at DESC)"
            )
            try:
                cur.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS assets_fts USING fts5(
                        asset_id UNINDEXED,
                        title,
                        description,
                        tags,
                        subject_key,
                        subject_aliases
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS assets_fts_insert
                    AFTER INSERT ON assets BEGIN
                        INSERT INTO assets_fts(
                            asset_id, title, description, tags, subject_key, subject_aliases
                        ) VALUES (
                            new.asset_id, new.title, new.description, new.tags,
                            new.subject_key, new.subject_key || ' ' || new.subject_aliases
                        );
                    END
                    """
                )
                cur.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS assets_fts_update
                    AFTER UPDATE ON assets BEGIN
                        UPDATE assets_fts SET
                            title=new.title,
                            description=new.description,
                            tags=new.tags,
                            subject_key=new.subject_key,
                            subject_aliases=new.subject_key || ' ' || new.subject_aliases
                        WHERE asset_id=new.asset_id;
                    END
                    """
                )
                cur.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS assets_fts_delete
                    AFTER DELETE ON assets BEGIN
                        DELETE FROM assets_fts WHERE asset_id=old.asset_id;
                    END
                    """
                )
            except sqlite3.OperationalError as exc:
                logger.warning("SQLite FTS5 unavailable; falling back to LIKE search: %s", exc)
            self._conn.commit()

    def _ensure_user_root_locked(self, user_id: str) -> str:
        row = self._conn.cursor().execute(
            "SELECT id FROM asset_folders WHERE owner_id=? AND is_root=1 LIMIT 1",
            (user_id,),
        ).fetchone()
        if row:
            return row["id"]
        root_id = str(uuid.uuid4())
        self._conn.cursor().execute(
            "INSERT INTO asset_folders (id, owner_id, name, parent_id, is_root, created_at) "
            "VALUES (?, ?, ?, NULL, 1, ?)",
            (root_id, user_id, "根目录", time.time()),
        )
        self._conn.cursor().execute(
            "UPDATE assets SET folder_id=? WHERE owner_id=? AND folder_id IS NULL",
            (root_id, user_id),
        )
        self._conn.commit()
        return root_id

    def get_root_folder(self, user_id: str) -> dict:
        self._require_available()
        with self._lock:
            root_id = self._ensure_user_root_locked(user_id)
            row = self._conn.cursor().execute(
                "SELECT * FROM asset_folders WHERE id=?", (root_id,)
            ).fetchone()
            return self._folder_to_dict(row)

    def _folder_to_dict(self, row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "parent_id": row["parent_id"],
            "is_root": bool(row["is_root"]),
            "asset_count": 0,
        }

    def storage_quota(self, user_id: str) -> tuple[int, int, bool]:
        """Return (limit_bytes, used_bytes, enabled) for a user."""
        if not self.available or self._conn is None:
            return 0, 0, False
        with self._lock:
            self._ensure_user_root_locked(user_id)
        settings = wm.get_user_settings(user_id)
        limit_count = int(settings.get("limit_count", 0))
        if limit_count < ASSET_LIBRARY_DISABLED_LIMIT:
            return 0, 0, False
        if limit_count < ASSET_LIBRARY_LARGE_LIMIT:
            limit = ASSET_LIBRARY_MEDIUM_BYTES
        else:
            limit = ASSET_LIBRARY_LARGE_BYTES
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT COALESCE(SUM(size), 0) AS used FROM (
                    SELECT b.size AS size
                    FROM asset_blobs b
                    JOIN assets a ON a.blob_sha256=b.sha256 AND b.user_id=a.owner_id
                    WHERE a.owner_id=?
                    UNION
                    SELECT b.size AS size
                    FROM asset_blobs b
                    JOIN published_assets p ON p.blob_sha256=b.sha256 AND b.user_id=p.publisher_id
                    WHERE p.publisher_id=?
                )
                """,
                (user_id, user_id),
            )
            used = int(cur.fetchone()["used"])
        return limit, used, True

    def ensure_can_store(self, user_id: str, size: int) -> tuple[int, int, bool]:
        self._require_available()
        limit, used, enabled = self.storage_quota(user_id)
        if not enabled:
            raise PermissionError("资产库存储未开通：当前用户无资产库使用权限")
        if used + size > limit:
            raise PermissionError(
                f"资产库空间不足：已使用 {used}/{limit} 字节，本次需要 {size} 字节"
            )
        return limit, used, enabled

    def upload(
        self,
        user_id: str,
        filename: str,
        content_type: str,
        data: bytes,
        title: str = "",
        description: str = "",
        tags: list[str] | None = None,
        folder_id: str | None = None,
        subject_key: str | None = None,
        subject_aliases: str = "",
        subject_role: str | None = None,
    ) -> dict:
        self._require_available()
        kind = _infer_kind(filename, content_type)
        size = len(data)
        max_size = {
            "image": ASSET_MAX_IMAGE_BYTES,
            "video": ASSET_MAX_VIDEO_BYTES,
            "audio": ASSET_MAX_AUDIO_BYTES,
        }[kind]
        if size <= 0:
            raise ValueError("文件为空")
        if size > max_size:
            raise ValueError(f"{kind} 文件超过单文件限制：{size} > {max_size}")
        self.ensure_can_store(user_id, size)
        with self._lock:
            root_id = self._ensure_user_root_locked(user_id)
        if not folder_id or folder_id == "__root__":
            folder_id = root_id
        if folder_id:
            self._assert_folder_owner(user_id, folder_id)

        sha256 = hashlib.sha256(data).hexdigest()
        suffix = Path(filename).suffix.lower() or ".bin"
        user_dir = ASSET_LIBRARY_ROOT / str(user_id)
        blob_path = user_dir / "blobs" / f"{sha256}{suffix}"
        if not blob_path.exists():
            blob_path.parent.mkdir(parents=True, exist_ok=True)
            blob_path.write_bytes(data)

        meta = self._probe_media(blob_path, kind)
        thumb_rel = self._make_thumbnail(blob_path, kind, sha256, user_id)

        try:
            with self._lock:
                cur = self._conn.cursor()
                cur.execute(
                    """
                    INSERT INTO asset_blobs (
                        user_id, sha256, rel_path, thumb_rel_path, mime_type, size,
                        width, height, duration, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, sha256) DO UPDATE SET
                        mime_type=excluded.mime_type,
                        width=COALESCE(excluded.width, asset_blobs.width),
                        height=COALESCE(excluded.height, asset_blobs.height),
                        duration=COALESCE(excluded.duration, asset_blobs.duration)
                    """,
                    (
                        user_id,
                        sha256,
                        str(blob_path.relative_to(ASSET_LIBRARY_ROOT)).replace("\\", "/"),
                        thumb_rel,
                        content_type or "application/octet-stream",
                        size,
                        meta.get("width"),
                        meta.get("height"),
                        meta.get("duration"),
                        time.time(),
                    ),
                )
                asset_id = str(uuid.uuid4())
                now = time.time()
                cur.execute(
                    """
                    INSERT INTO assets (
                        asset_id, owner_id, kind, title, description, tags,
                        folder_id, visibility, blob_sha256, subject_key,
                        subject_aliases, subject_role, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'private', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asset_id,
                        user_id,
                        kind,
                        title or Path(filename).stem,
                        description or "",
                        json.dumps(tags or [], ensure_ascii=False),
                        folder_id,
                        sha256,
                        subject_key,
                        subject_aliases,
                        subject_role,
                        now,
                        now,
                    ),
                )
                self._conn.commit()
                row = self._row_to_asset(self._conn.cursor().execute(
                    "SELECT * FROM assets WHERE asset_id=?", (asset_id,)
                ).fetchone())
        except Exception:
            with self._lock:
                self._conn.rollback()
                self._maybe_remove_blob(user_id, sha256)
            raise
        return row

    def _probe_media(self, path: Path, kind: str) -> dict:
        if kind == "image":
            try:
                from PIL import Image

                with Image.open(path) as img:
                    return {"width": img.width, "height": img.height}
            except Exception as exc:  # noqa: BLE001
                logger.warning("Image metadata failed for %s: %s", path, exc)
                return {}
        return _ffprobe_meta(path)

    def _make_thumbnail(self, path: Path, kind: str, sha256: str, user_id: str) -> str | None:
        out = ASSET_LIBRARY_ROOT / str(user_id) / "thumbs" / f"{sha256}.webp"
        if out.exists():
            return str(out.relative_to(ASSET_LIBRARY_ROOT)).replace("\\", "/")
        try:
            if kind == "image":
                from PIL import Image

                with Image.open(path) as img:
                    img.thumbnail((512, 512))
                    out.parent.mkdir(parents=True, exist_ok=True)
                    img.convert("RGB").save(out, "WEBP", quality=82)
            elif kind == "video":
                out.parent.mkdir(parents=True, exist_ok=True)
                ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
                subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-ss",
                        "0",
                        "-i",
                        str(path),
                        "-frames:v",
                        "1",
                        "-vf",
                        "scale=512:-2",
                        str(out),
                    ],
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
                if not out.exists():
                    return None
            else:
                return None
            return str(out.relative_to(ASSET_LIBRARY_ROOT)).replace("\\", "/")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Thumbnail failed for %s: %s", path, exc)
            return None

    def _assert_folder_owner(self, user_id: str, folder_id: str):
        with self._lock:
            row = self._conn.cursor().execute(
                "SELECT id FROM asset_folders WHERE id=? AND owner_id=?",
                (folder_id, user_id),
            ).fetchone()
        if not row:
            raise PermissionError("文件夹不存在或不属于当前用户")

    def create_folder(self, user_id: str, name: str, parent_id: str | None = None):
        self._require_available()
        with self._lock:
            self._ensure_user_root_locked(user_id)
        if parent_id:
            self._assert_folder_owner(user_id, parent_id)
        folder_id = str(uuid.uuid4())
        with self._lock:
            self._conn.cursor().execute(
                "INSERT INTO asset_folders (id, owner_id, name, parent_id, is_root, created_at) "
                "VALUES (?, ?, ?, ?, 0, ?)",
                (folder_id, user_id, name.strip(), parent_id, time.time()),
            )
            self._conn.commit()
        return self.list_folders(user_id, folder_id)[0]

    def list_folders(self, user_id: str, folder_id: str | None = None):
        self._require_available()
        with self._lock:
            self._ensure_user_root_locked(user_id)
            sql = (
                "SELECT f.*, "
                "(SELECT COUNT(*) FROM assets a WHERE a.folder_id=f.id AND a.owner_id=?) "
                "AS asset_count "
                "FROM asset_folders f WHERE f.owner_id=?"
            )
            args: list = [user_id, user_id]
            if folder_id:
                sql += " AND f.id=?"
                args.append(folder_id)
            sql += " ORDER BY f.name"
            rows = self._conn.cursor().execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    def _collect_folder_ids_locked(self, folder_id: str, max_depth: int = 32) -> list[str]:
        ids: list[str] = [folder_id]
        frontier = [folder_id]
        for _ in range(max_depth):
            if not frontier:
                break
            placeholders = ",".join("?" for _ in frontier)
            rows = self._conn.cursor().execute(
                f"SELECT id FROM asset_folders WHERE parent_id IN ({placeholders})",
                frontier,
            ).fetchall()
            children = [row["id"] for row in rows]
            if not children:
                break
            ids.extend(children)
            frontier = children
        return ids

    def folder_stats(self, user_id: str, folder_id: str) -> dict | None:
        self._require_available()
        with self._lock:
            self._assert_folder_owner(user_id, folder_id)
            ids = self._collect_folder_ids_locked(folder_id)
            if not ids:
                return None
            placeholders = ",".join("?" for _ in ids)
            asset_count = self._conn.cursor().execute(
                f"SELECT COUNT(*) FROM assets WHERE folder_id IN ({placeholders})",
                ids,
            ).fetchone()[0]
            return {
                "asset_count": int(asset_count),
                "folder_count": len(ids) - 1,
                "total_items": int(asset_count) + len(ids) - 1,
            }

    def delete_folder(
        self,
        user_id: str,
        folder_id: str,
        confirm: bool = False,
    ) -> dict | None:
        self._require_available()
        with self._lock:
            self._assert_folder_owner(user_id, folder_id)
            root_row = self._conn.cursor().execute(
                "SELECT is_root FROM asset_folders WHERE id=? AND owner_id=?",
                (folder_id, user_id),
            ).fetchone()
            if root_row and root_row["is_root"]:
                raise PermissionError("根目录不可删除")
            ids = self._collect_folder_ids_locked(folder_id)
            if not ids:
                return None
            placeholders = ",".join("?" for _ in ids)
            cur = self._conn.cursor()
            asset_rows = cur.execute(
                f"SELECT asset_id, blob_sha256 FROM assets WHERE folder_id IN ({placeholders})",
                ids,
            ).fetchall()
            asset_count = len(asset_rows)
            if asset_count and not confirm:
                return {
                    "ok": False,
                    "needs_confirmation": True,
                    "asset_count": asset_count,
                    "folder_count": len(ids) - 1,
                }

            asset_ids = [row["asset_id"] for row in asset_rows]
            blob_hashes = [row["blob_sha256"] for row in asset_rows]
            if asset_ids:
                asset_placeholders = ",".join("?" for _ in asset_ids)
                cur.execute(f"DELETE FROM assets WHERE asset_id IN ({asset_placeholders})", asset_ids)
            cur.execute(
                f"DELETE FROM asset_folders WHERE id IN ({placeholders})",
                ids,
            )
            self._conn.commit()
            for sha256 in blob_hashes:
                self._maybe_remove_blob(user_id, sha256)
            self._conn.commit()
            return {
                "ok": True,
                "needs_confirmation": False,
                "asset_count": asset_count,
                "folder_count": len(ids) - 1,
            }

    def save_published_to_private(
        self,
        user_id: str,
        published_id: str,
        folder_id: str | None = None,
    ) -> dict:
        self._require_available()
        with self._lock:
            pub = self._conn.cursor().execute(
                "SELECT * FROM published_assets WHERE published_id=?",
                (published_id,),
            ).fetchone()
            if not pub:
                raise PermissionError("公开素材不存在或不可访问")
            blob = self._conn.cursor().execute(
                "SELECT * FROM asset_blobs WHERE sha256=? AND user_id=?",
                (pub["blob_sha256"], pub["publisher_id"]),
            ).fetchone()
            if not blob:
                blob = self._conn.cursor().execute(
                    "SELECT * FROM asset_blobs WHERE sha256=?", (pub["blob_sha256"],)
                ).fetchone()
            if not blob:
                raise PermissionError("公开素材文件缺失")
            size = blob["size"]
        limit, used, enabled = self.storage_quota(user_id)
        if not enabled:
            raise PermissionError("当前用户无资产库存储权限")
        if used + size > limit:
            raise PermissionError(f"资产库空间不足：需要 {size} 字节，剩余 {limit - used} 字节")
        with self._lock:
            if not folder_id or folder_id == "__root__":
                folder_id = self._ensure_user_root_locked(user_id)
            else:
                self._assert_folder_owner(user_id, folder_id)
            # Per-user storage: give the saving user their own blob entry (and a
            # file copy of the published snapshot).
            own = self._conn.cursor().execute(
                "SELECT * FROM asset_blobs WHERE sha256=? AND user_id=?",
                (pub["blob_sha256"], user_id),
            ).fetchone()
            if not own:
                sha = pub["blob_sha256"]
                suffix = Path(blob["rel_path"]).suffix.lower() or ".bin"
                new_rel = f"{user_id}/blobs/{sha}{suffix}"
                src = (ASSET_LIBRARY_ROOT / blob["rel_path"]).resolve()
                self._ensure_under_root(src)
                dest = ASSET_LIBRARY_ROOT / new_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                new_thumb_rel = None
                if src.exists():
                    try:
                        shutil.copy2(src, dest)
                    except OSError as exc:  # noqa: BLE001
                        logger.warning("Save published file copy failed %s: %s", src, exc)
                if blob["thumb_rel_path"]:
                    tsrc = (ASSET_LIBRARY_ROOT / blob["thumb_rel_path"]).resolve()
                    self._ensure_under_root(tsrc)
                    tname = Path(blob["thumb_rel_path"]).name
                    new_thumb_rel = f"{user_id}/thumbs/{tname}"
                    tdest = ASSET_LIBRARY_ROOT / new_thumb_rel
                    if tsrc.exists():
                        tdest.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            shutil.copy2(tsrc, tdest)
                        except OSError:  # noqa: BLE001
                            pass
                self._conn.cursor().execute(
                    """
                    INSERT INTO asset_blobs (
                        user_id, sha256, rel_path, thumb_rel_path, mime_type, size,
                        width, height, duration, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id, sha, new_rel, new_thumb_rel, blob["mime_type"],
                        blob["size"], blob["width"], blob["height"], blob["duration"],
                        time.time(),
                    ),
                )
            asset_id = str(uuid.uuid4())
            now = time.time()
            self._conn.cursor().execute(
                """
                INSERT INTO assets (
                    asset_id, owner_id, kind, title, description, tags,
                    folder_id, visibility, blob_sha256, subject_key,
                    subject_aliases, subject_role, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'private', ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    user_id,
                    pub["kind"],
                    pub["title"],
                    pub["description"],
                    pub["tags"],
                    folder_id,
                    pub["blob_sha256"],
                    pub["subject_key"],
                    pub["subject_aliases"],
                    pub["subject_role"],
                    now,
                    now,
                ),
            )
            self._conn.commit()
            row = self._row_to_asset(self._conn.cursor().execute(
                "SELECT * FROM assets WHERE asset_id=?", (asset_id,)
            ).fetchone())
        return row

    def list_assets(
        self,
        user_id: str,
        kind: str | None = None,
        folder_id: str | None = None,
        query: str = "",
        shared: bool = False,
    ):
        self._require_available()
        with self._lock:
            if shared:
                sql = "SELECT * FROM published_assets WHERE 1=1"
                args: list = []
            else:
                root_id = self._ensure_user_root_locked(user_id)
                if folder_id == "__root__":
                    sql = (
                        "SELECT * FROM assets WHERE owner_id=? "
                        "AND (folder_id IS NULL OR folder_id=?)"
                    )
                    args = [user_id, root_id]
                else:
                    if folder_id:
                        self._assert_folder_owner(user_id, folder_id)
                    sql = "SELECT * FROM assets WHERE owner_id=?"
                    args = [user_id]
                    if folder_id:
                        sql += " AND folder_id=?"
                        args.append(folder_id)
            if kind:
                sql += " AND kind=?"
                args.append(kind)
            if query:
                ids = self._fts_ids(query, user_id, shared)
                key = "published_id" if shared else "asset_id"
                if not ids:
                    return []
                placeholders = ",".join("?" for _ in ids)
                sql += f" AND {key} IN ({placeholders})"
                args.extend(ids)
            sql += " ORDER BY created_at DESC"
            rows = self._conn.cursor().execute(sql, args).fetchall()
            like_stats: dict[str, tuple[int, bool]] = {}
            if shared:
                like_stats = self._like_stats([r["published_id"] for r in rows], user_id)
        if shared:
            return [
                self._row_to_published_asset(r, viewer_id=user_id, like_stats=like_stats)
                for r in rows
            ]
        return [self._row_to_asset(self._fetch_asset(r["asset_id"], user_id)) for r in rows]

    def _fts_ids(self, query: str, user_id: str, shared: bool) -> list[str]:
        terms = [t for t in re.findall(r"[\w\u4e00-\u9fff]+", query) if t]
        if not terms:
            return []
        match = " AND ".join(f'"{t.replace(chr(34), chr(34) * 2)}"' for t in terms)
        like = f"%{query}%"
        with self._lock:
            if shared:
                rows = self._conn.cursor().execute(
                    """
                    SELECT published_id AS id FROM published_assets
                    WHERE title LIKE ? OR description LIKE ? OR tags LIKE ?
                    OR subject_key LIKE ? OR subject_aliases LIKE ?
                    """,
                    (like, like, like, like, like),
                ).fetchall()
                return [r["id"] for r in rows]
            try:
                rows = self._conn.cursor().execute(
                    "SELECT asset_id FROM assets_fts WHERE assets_fts MATCH ? "
                    "ORDER BY rank LIMIT 200",
                    (match,),
                ).fetchall()
                ids = [r["asset_id"] for r in rows]
            except sqlite3.OperationalError:
                ids = []
            if not ids:
                rows = self._conn.cursor().execute(
                    """
                    SELECT asset_id FROM assets
                    WHERE owner_id=? AND (
                        title LIKE ? OR description LIKE ? OR tags LIKE ? OR
                        subject_key LIKE ? OR subject_aliases LIKE ?
                    )
                    """,
                    (user_id, like, like, like, like, like),
                ).fetchall()
                ids = [r["asset_id"] for r in rows]
        return ids

    def get_asset(self, user_id: str, asset_id: str) -> dict | None:
        self._require_available()
        with self._lock:
            row = self._conn.cursor().execute(
                "SELECT * FROM assets WHERE asset_id=? AND owner_id=?",
                (asset_id, user_id),
            ).fetchone()
        return self._row_to_asset(row) if row else None

    def get_asset_path(self, user_id: str, asset_id: str) -> Path:
        self._require_available()
        with self._lock:
            row = self._conn.cursor().execute(
                """
                SELECT b.rel_path AS rel_path
                FROM assets a
                JOIN asset_blobs b ON b.sha256=a.blob_sha256 AND b.user_id=a.owner_id
                WHERE a.asset_id=? AND a.owner_id=?
                """,
                (asset_id, user_id),
            ).fetchone()
        if not row:
            raise PermissionError("资产不存在或不可访问")
        path = (ASSET_LIBRARY_ROOT / row["rel_path"]).resolve()
        self._ensure_under_root(path)
        return path

    def get_asset_thumbnail_path(self, user_id: str, asset_id: str) -> Path | None:
        self._require_available()
        with self._lock:
            row = self._conn.cursor().execute(
                """
                SELECT b.thumb_rel_path AS thumb_rel_path
                FROM assets a
                JOIN asset_blobs b ON b.sha256=a.blob_sha256 AND b.user_id=a.owner_id
                WHERE a.asset_id=? AND a.owner_id=?
                """,
                (asset_id, user_id),
            ).fetchone()
        return self._resolve_optional_root(row["thumb_rel_path"]) if row else None

    def get_published_path(self, published_id: str) -> Path:
        self._require_available()
        with self._lock:
            row = self._conn.cursor().execute(
                """
                SELECT b.rel_path AS rel_path
                FROM published_assets p
                JOIN asset_blobs b ON b.sha256=p.blob_sha256 AND b.user_id=p.publisher_id
                WHERE p.published_id=?
                """,
                (published_id,),
            ).fetchone()
        if not row:
            raise PermissionError("精选资产不存在")
        path = (ASSET_LIBRARY_ROOT / row["rel_path"]).resolve()
        self._ensure_under_root(path)
        return path

    def get_published_thumbnail_path(self, published_id: str) -> Path | None:
        self._require_available()
        with self._lock:
            row = self._conn.cursor().execute(
                """
                SELECT b.thumb_rel_path AS thumb_rel_path
                FROM published_assets p
                JOIN asset_blobs b ON b.sha256=p.blob_sha256 AND b.user_id=p.publisher_id
                WHERE p.published_id=?
                """,
                (published_id,),
            ).fetchone()
        return self._resolve_optional_root(row["thumb_rel_path"]) if row else None

    def update_asset(
        self,
        user_id: str,
        asset_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        folder_id: str | None = None,
        subject_key: str | None = None,
        subject_aliases: str | None = None,
        subject_role: str | None = None,
    ) -> dict:
        self._require_available()
        if not self.get_asset(user_id, asset_id):
            raise PermissionError("资产不存在或不可访问")
        if folder_id:
            self._assert_folder_owner(user_id, folder_id)
        with self._lock:
            current = self._conn.cursor().execute(
                "SELECT * FROM assets WHERE asset_id=?", (asset_id,)
            ).fetchone()
            updates = {
                "title": title if title is not None else current["title"],
                "description": description if description is not None else current["description"],
                "tags": json.dumps(tags if tags is not None else json.loads(current["tags"] or "[]"), ensure_ascii=False),
                "folder_id": folder_id if folder_id is not None else current["folder_id"],
                "subject_key": subject_key if subject_key is not None else current["subject_key"],
                "subject_aliases": subject_aliases if subject_aliases is not None else current["subject_aliases"],
                "subject_role": subject_role if subject_role is not None else current["subject_role"],
            }
            self._conn.cursor().execute(
                """
                UPDATE assets SET title=?, description=?, tags=?, folder_id=?,
                    subject_key=?, subject_aliases=?, subject_role=?, updated_at=?
                WHERE asset_id=?
                """,
                (
                    updates["title"], updates["description"], updates["tags"],
                    updates["folder_id"], updates["subject_key"],
                    updates["subject_aliases"],
                    updates["subject_role"], time.time(), asset_id,
                ),
            )
            self._conn.commit()
        return self.get_asset(user_id, asset_id)

    def delete_asset(self, user_id: str, asset_id: str) -> bool:
        self._require_available()
        asset = self.get_asset(user_id, asset_id)
        if not asset:
            return False
        with self._lock:
            row = self._conn.cursor().execute(
                "SELECT blob_sha256 FROM assets WHERE asset_id=?", (asset_id,)
            ).fetchone()
            self._conn.cursor().execute(
                "DELETE FROM assets WHERE asset_id=?", (asset_id,)
            )
            self._maybe_remove_blob(user_id, row["blob_sha256"])
            self._conn.commit()
        return True

    def publish(self, user_id: str, asset_id: str, publisher_name: str = "") -> dict:
        self._require_available()
        asset = self.get_asset(user_id, asset_id)
        if not asset:
            raise PermissionError("资产不存在或不可访问")
        with self._lock:
            existing = self._conn.cursor().execute(
                "SELECT * FROM published_assets WHERE source_asset_id=? AND publisher_id=?",
                (asset_id, user_id),
            ).fetchone()
            if existing:
                if publisher_name and not existing["publisher_name"]:
                    self._conn.cursor().execute(
                        "UPDATE published_assets SET publisher_name=? WHERE published_id=?",
                        (publisher_name[:64], existing["published_id"]),
                    )
                    self._conn.commit()
                    existing = self._conn.cursor().execute(
                        "SELECT * FROM published_assets WHERE published_id=?",
                        (existing["published_id"],),
                    ).fetchone()
                return self._row_to_published_asset(existing, viewer_id=user_id)
            published_id = str(uuid.uuid4())
            blob_row = self._conn.cursor().execute(
                "SELECT blob_sha256 FROM assets WHERE asset_id=?", (asset_id,)
            ).fetchone()
            tags_json = json.dumps(asset["tags"], ensure_ascii=False)
            metadata = {
                "title": asset["title"],
                "description": asset["description"],
                "tags": tags_json,
                "subject_key": asset["subject_key"],
                "subject_aliases": asset.get("subject_aliases", ""),
                "subject_role": asset["subject_role"],
            }
            self._conn.cursor().execute(
                """
                INSERT INTO published_assets (
                    published_id, source_asset_id, publisher_id, blob_sha256,
                    kind, title, description, tags, subject_key, subject_aliases, subject_role,
                    metadata_json, publisher_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    published_id, asset_id, user_id, blob_row["blob_sha256"],
                    asset["kind"], asset["title"], asset["description"], tags_json,
                    asset["subject_key"], asset.get("subject_aliases", ""),
                    asset["subject_role"],
                    json.dumps(metadata, ensure_ascii=False),
                    publisher_name[:64],
                    time.time(),
                ),
            )
            self._conn.commit()
            row = self._conn.cursor().execute(
                "SELECT * FROM published_assets WHERE published_id=?", (published_id,)
            ).fetchone()
        return self._row_to_published_asset(row, viewer_id=user_id)

    def unpublish(self, user_id: str, published_id: str) -> bool:
        self._require_available()
        with self._lock:
            row = self._conn.cursor().execute(
                "SELECT * FROM published_assets WHERE published_id=? AND publisher_id=?",
                (published_id, user_id),
            ).fetchone()
            if not row:
                return False
            self._conn.cursor().execute(
                "DELETE FROM published_assets WHERE published_id=?", (published_id,)
            )
            self._conn.cursor().execute(
                "DELETE FROM asset_likes WHERE published_id=?", (published_id,)
            )
            self._maybe_remove_blob(user_id, row["blob_sha256"])
            self._conn.commit()
        return True

    def unpublish_by_source(self, user_id: str, asset_id: str) -> bool:
        self._require_available()
        with self._lock:
            row = self._conn.cursor().execute(
                "SELECT * FROM published_assets WHERE source_asset_id=? AND publisher_id=?",
                (asset_id, user_id),
            ).fetchone()
            if not row:
                return False
            self._conn.cursor().execute(
                "DELETE FROM published_assets WHERE published_id=?", (row["published_id"],)
            )
            self._conn.cursor().execute(
                "DELETE FROM asset_likes WHERE published_id=?", (row["published_id"],)
            )
            self._maybe_remove_blob(user_id, row["blob_sha256"])
            self._conn.commit()
        return True

    # ---- Public feed / likes ----

    def get_published_for_source(self, user_id: str, asset_id: str) -> dict | None:
        """Return the publisher's own published snapshot for an asset."""
        self._require_available()
        with self._lock:
            row = self._conn.cursor().execute(
                "SELECT * FROM published_assets WHERE source_asset_id=? AND publisher_id=? "
                "ORDER BY created_at DESC LIMIT 1",
                (asset_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def get_published(self, published_id: str) -> dict | None:
        self._require_available()
        with self._lock:
            row = self._conn.cursor().execute(
                "SELECT * FROM published_assets WHERE published_id=?", (published_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_published_item(self, published_id: str, viewer_id: str | None = None) -> dict | None:
        """Full public item dict (with like stats) for one published id."""
        self._require_available()
        with self._lock:
            row = self._conn.cursor().execute(
                "SELECT * FROM published_assets WHERE published_id=?", (published_id,)
            ).fetchone()
        return self._row_to_published_asset(row, viewer_id=viewer_id) if row else None

    # ---- Admin public-library management ----

    def admin_upload_public(
        self,
        user_id: str,
        filename: str,
        content_type: str,
        data: bytes,
        title: str = "",
        description: str = "",
        tags: list[str] | None = None,
        subject_key: str | None = None,
        subject_aliases: str = "",
        subject_role: str | None = None,
    ) -> dict:
        """Admin-only: upload a file directly into the public library."""
        self._require_available()
        kind = _infer_kind(filename, content_type)
        size = len(data)
        max_size = {
            "image": ASSET_MAX_IMAGE_BYTES,
            "video": ASSET_MAX_VIDEO_BYTES,
            "audio": ASSET_MAX_AUDIO_BYTES,
        }[kind]
        if size <= 0:
            raise ValueError("文件为空")
        if size > max_size:
            raise ValueError(f"{kind} 文件超过单文件限制：{size} > {max_size}")
        sha256 = hashlib.sha256(data).hexdigest()
        suffix = Path(filename).suffix.lower() or ".bin"
        user_dir = ASSET_LIBRARY_ROOT / str(user_id)
        blob_path = user_dir / "blobs" / f"{sha256}{suffix}"
        if not blob_path.exists():
            blob_path.parent.mkdir(parents=True, exist_ok=True)
            blob_path.write_bytes(data)
        meta = self._probe_media(blob_path, kind)
        thumb_rel = self._make_thumbnail(blob_path, kind, sha256, user_id)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO asset_blobs (
                    user_id, sha256, rel_path, thumb_rel_path, mime_type, size,
                    width, height, duration, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, sha256) DO UPDATE SET
                    mime_type=excluded.mime_type,
                    width=COALESCE(excluded.width, asset_blobs.width),
                    height=COALESCE(excluded.height, asset_blobs.height),
                    duration=COALESCE(excluded.duration, asset_blobs.duration)
                """,
                (
                    user_id, sha256,
                    str(blob_path.relative_to(ASSET_LIBRARY_ROOT)).replace("\\", "/"),
                    thumb_rel, content_type or "application/octet-stream", size,
                    meta.get("width"), meta.get("height"), meta.get("duration"),
                    time.time(),
                ),
            )
            published_id = str(uuid.uuid4())
            tags_json = json.dumps(tags or [], ensure_ascii=False)
            now = time.time()
            metadata = {
                "title": title, "description": description, "tags": tags_json,
                "subject_key": subject_key, "subject_aliases": subject_aliases,
                "subject_role": subject_role,
            }
            cur.execute(
                """
                INSERT INTO published_assets (
                    published_id, source_asset_id, publisher_id, blob_sha256,
                    kind, title, description, tags, subject_key, subject_aliases, subject_role,
                    metadata_json, publisher_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    published_id, "", user_id, sha256,
                    kind, title or Path(filename).stem, description or "", tags_json,
                    subject_key, subject_aliases, subject_role,
                    json.dumps(metadata, ensure_ascii=False), "", now,
                ),
            )
            self._conn.commit()
            row = self._conn.cursor().execute(
                "SELECT * FROM published_assets WHERE published_id=?", (published_id,)
            ).fetchone()
        return self._row_to_published_asset(row, viewer_id=user_id)

    def admin_update_published(
        self,
        published_id: str,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> dict | None:
        """Admin-only: update a public library item's metadata."""
        self._require_available()
        with self._lock:
            row = self._conn.cursor().execute(
                "SELECT * FROM published_assets WHERE published_id=?", (published_id,)
            ).fetchone()
            if not row:
                return None
            new_title = title if title is not None else row["title"]
            new_desc = description if description is not None else row["description"]
            new_tags = json.dumps(tags, ensure_ascii=False) if tags is not None else row["tags"]
            self._conn.cursor().execute(
                "UPDATE published_assets SET title=?, description=?, tags=? WHERE published_id=?",
                (new_title, new_desc, new_tags, published_id),
            )
            self._conn.commit()
            row = self._conn.cursor().execute(
                "SELECT * FROM published_assets WHERE published_id=?", (published_id,)
            ).fetchone()
        return self._row_to_published_asset(row, viewer_id=None)

    def admin_remove_published(self, published_id: str) -> bool:
        """Admin-only: remove any public library item (and its likes)."""
        self._require_available()
        with self._lock:
            row = self._conn.cursor().execute(
                "SELECT * FROM published_assets WHERE published_id=?", (published_id,)
            ).fetchone()
            if not row:
                return False
            self._conn.cursor().execute(
                "DELETE FROM published_assets WHERE published_id=?", (published_id,)
            )
            self._conn.cursor().execute(
                "DELETE FROM asset_likes WHERE published_id=?", (published_id,)
            )
            self._maybe_remove_blob(row["publisher_id"], row["blob_sha256"])
            self._conn.commit()
        return True

    def set_discord_message_id(self, published_id: str, message_id: str | None) -> None:
        self._require_available()
        with self._lock:
            self._conn.cursor().execute(
                "UPDATE published_assets SET discord_message_id=? WHERE published_id=?",
                (message_id, published_id),
            )
            self._conn.commit()

    def set_publisher_name(self, published_id: str, name: str) -> None:
        self._require_available()
        with self._lock:
            self._conn.cursor().execute(
                "UPDATE published_assets SET publisher_name=? WHERE published_id=? "
                "AND publisher_name=''",
                (name[:64], published_id),
            )
            self._conn.commit()

    def set_like(self, published_id: str, user_id: str, liked: bool) -> dict | None:
        """Add or remove the current user's like. Returns (like_count, liked)."""
        self._require_available()
        with self._lock:
            exists = self._conn.cursor().execute(
                "SELECT 1 FROM published_assets WHERE published_id=?", (published_id,)
            ).fetchone()
            if not exists:
                return None
            if liked:
                self._conn.cursor().execute(
                    "INSERT OR IGNORE INTO asset_likes (published_id, user_id, created_at) "
                    "VALUES (?, ?, ?)",
                    (published_id, user_id, time.time()),
                )
            else:
                self._conn.cursor().execute(
                    "DELETE FROM asset_likes WHERE published_id=? AND user_id=?",
                    (published_id, user_id),
                )
            count = self._conn.cursor().execute(
                "SELECT COUNT(*) FROM asset_likes WHERE published_id=?", (published_id,)
            ).fetchone()[0]
            mine = self._conn.cursor().execute(
                "SELECT 1 FROM asset_likes WHERE published_id=? AND user_id=?",
                (published_id, user_id),
            ).fetchone() is not None
            self._conn.commit()
        return {"like_count": count, "liked": mine}

    def _like_stats(self, published_ids: list[str], viewer_id: str | None) -> dict[str, tuple[int, bool]]:
        """Bulk like counts + viewer's likes for a set of published ids."""
        stats: dict[str, tuple[int, bool]] = {}
        if not published_ids:
            return stats
        placeholders = ",".join("?" for _ in published_ids)
        with self._lock:
            rows = self._conn.cursor().execute(
                f"SELECT published_id, COUNT(*) AS c FROM asset_likes "
                f"WHERE published_id IN ({placeholders}) GROUP BY published_id",
                published_ids,
            ).fetchall()
            counts = {r["published_id"]: r["c"] for r in rows}
            mine: set[str] = set()
            if viewer_id:
                rows = self._conn.cursor().execute(
                    f"SELECT published_id FROM asset_likes "
                    f"WHERE published_id IN ({placeholders}) AND user_id=?",
                    [*published_ids, viewer_id],
                ).fetchall()
                mine = {r["published_id"] for r in rows}
        for pid in published_ids:
            stats[pid] = (counts.get(pid, 0), pid in mine)
        return stats

    def _maybe_remove_blob(self, user_id: str, sha256: str):
        cur = self._conn.cursor()
        count = cur.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM assets WHERE owner_id=? AND blob_sha256=?) +
              (SELECT COUNT(*) FROM published_assets WHERE publisher_id=? AND blob_sha256=?)
            """,
            (user_id, sha256, user_id, sha256),
        ).fetchone()[0]
        if count:
            return
        row = cur.execute(
            "SELECT rel_path, thumb_rel_path FROM asset_blobs WHERE user_id=? AND sha256=?",
            (user_id, sha256),
        ).fetchone()
        if row:
            path = (ASSET_LIBRARY_ROOT / row["rel_path"]).resolve()
            self._ensure_under_root(path)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            if row["thumb_rel_path"]:
                thumb = (ASSET_LIBRARY_ROOT / row["thumb_rel_path"]).resolve()
                self._ensure_under_root(thumb)
                try:
                    thumb.unlink(missing_ok=True)
                except OSError:
                    pass
            cur.execute(
                "DELETE FROM asset_blobs WHERE user_id=? AND sha256=?",
                (user_id, sha256),
            )

    def _row_to_asset(self, row) -> dict:
        if not row:
            return {}
        blob = self._conn.cursor().execute(
            "SELECT * FROM asset_blobs WHERE user_id=? AND sha256=?",
            (row["owner_id"], row["blob_sha256"]),
        ).fetchone()
        tags = json.loads(row["tags"] or "[]")
        return {
            "id": row["asset_id"],
            "kind": row["kind"],
            "title": row["title"],
            "description": row["description"],
            "tags": tags,
            "folder_id": row["folder_id"],
            "visibility": row["visibility"],
            "mime_type": blob["mime_type"],
            "size_bytes": blob["size"],
            "width": blob["width"],
            "height": blob["height"],
            "duration": blob["duration"],
            "subject_key": row["subject_key"],
            "subject_aliases": row["subject_aliases"],
            "subject_role": row["subject_role"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "file_url": f"/api/assets/{row['asset_id']}/file",
            "thumbnail_url": (
                f"/api/assets/{row['asset_id']}/thumbnail" if blob["thumb_rel_path"] else None
            ),
            "published_id": self._published_id_for(row["asset_id"]),
        }

    def _row_to_published_asset(self, row, viewer_id: str | None = None,
                                like_stats: dict[str, tuple[int, bool]] | None = None) -> dict:
        if not row:
            return {}
        blob = self._conn.cursor().execute(
            "SELECT * FROM asset_blobs WHERE sha256=? AND user_id=?",
            (row["blob_sha256"], row["publisher_id"]),
        ).fetchone()
        if like_stats is None:
            try:
                like_stats = self._like_stats([row["published_id"]], viewer_id)
            except Exception:  # noqa: BLE001 - stats must never break listing
                like_stats = {row["published_id"]: (0, False)}
        like_count, liked_by_me = like_stats.get(row["published_id"], (0, False))
        return {
            "id": row["published_id"],
            "kind": row["kind"],
            "title": row["title"],
            "description": row["description"],
            "tags": json.loads(row["tags"] or "[]"),
            "folder_id": None,
            "visibility": "shared",
            "mime_type": blob["mime_type"],
            "size_bytes": blob["size"],
            "width": blob["width"],
            "height": blob["height"],
            "duration": blob["duration"],
            "subject_key": row["subject_key"],
            "subject_role": row["subject_role"],
            "created_at": row["created_at"],
            "updated_at": row["created_at"],
            "file_url": f"/api/assets/public/{row['published_id']}/file",
            "thumbnail_url": (
                f"/api/assets/public/{row['published_id']}/thumbnail"
                if blob["thumb_rel_path"] else None
            ),
            "published_id": row["published_id"],
            "publisher_id": row["publisher_id"],
            "publisher_name": row["publisher_name"] or "",
            "discord_message_id": row["discord_message_id"],
            "like_count": like_count,
            "liked_by_me": liked_by_me,
        }

    def _published_id_for(self, asset_id: str) -> str | None:
        row = self._conn.cursor().execute(
            "SELECT published_id FROM published_assets WHERE source_asset_id=? LIMIT 1",
            (asset_id,),
        ).fetchone()
        return row["published_id"] if row else None

    def _fetch_asset(self, asset_id: str, user_id: str):
        return self._conn.cursor().execute(
            "SELECT * FROM assets WHERE asset_id=? AND owner_id=?", (asset_id, user_id)
        ).fetchone()

    def _resolve_optional_root(self, rel: str | None) -> Path | None:
        if not rel:
            return None
        path = (ASSET_LIBRARY_ROOT / rel).resolve()
        self._ensure_under_root(path)
        return path

    @staticmethod
    def _ensure_under_root(path: Path):
        root = ASSET_LIBRARY_ROOT.resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise PermissionError("非法资产路径") from exc


asset_library = AssetLibrary()
