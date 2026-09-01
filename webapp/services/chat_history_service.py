"""Short-term chat history for the drawing assistant (SQLite + image cache).

Keeps the most recent N rounds of conversation per user.
One "round" = 1 user message + 1 assistant message.
Messages may be text or an image (base64 data URL); images are cached on
disk under AISSETTING_DIR/chat_images so the DB stays small, then re-encoded
to a data URL when rebuilding the multimodal context for the vision model.
"""
import base64
import re
import sqlite3
import logging
import threading
import time
import uuid
import json
from pathlib import Path

from config import AISSETTING_DIR, DB_PATH, CHAT_MAX_ROUNDS

logger = logging.getLogger(__name__)

CHAT_IMAGE_DIR = AISSETTING_DIR / "chat_images"


class ChatHistoryService:
    def __init__(self):
        self.image_dir = CHAT_IMAGE_DIR
        self.image_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._init_db()

    def _init_db(self):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS artist_chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_artist_chat_user
                ON artist_chat_history(user_id, timestamp)
            """)
            # Column upgrade (idempotent) for image messages.
            cursor.execute("PRAGMA table_info(artist_chat_history)")
            existing = {row["name"] for row in cursor.fetchall()}
            if "content_type" not in existing:
                cursor.execute(
                    "ALTER TABLE artist_chat_history ADD COLUMN content_type TEXT NOT NULL DEFAULT 'text'"
                )
            if "image_path" not in existing:
                cursor.execute(
                    "ALTER TABLE artist_chat_history ADD COLUMN image_path TEXT"
                )
            if "image_paths" not in existing:
                cursor.execute(
                    "ALTER TABLE artist_chat_history ADD COLUMN image_paths TEXT"
                )
            self._conn.commit()
            logger.info("Artist chat history table ready (multi-image supported)")

    @staticmethod
    def _safe_user_id(user_id: str) -> str:
        return re.sub(r"[^A-Za-z0-9_-]", "_", user_id or "unknown")

    @staticmethod
    def _split_data_url(data: str | None) -> tuple[str | None, str]:
        """Return (mime, payload) from a base64 string or a data URL."""
        if not data:
            return None, ""
        if data.startswith("data:"):
            header, sep, payload = data.partition(",")
            if not sep:
                return None, ""
            mime = None
            for candidate in ("image/jpeg", "image/jpg", "image/png", "image/webp"):
                if candidate in header:
                    mime = candidate
                    break
            return mime, payload
        return None, data

    def save_image(self, user_id: str, image_b64: str) -> str | None:
        """Persist an image to disk and return its filesystem path."""
        mime, payload = self._split_data_url(image_b64)
        if not payload:
            return None
        try:
            data_bytes = base64.b64decode(payload)
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to decode chat image for %s: %s", user_id, e)
            return None
        ext = "png" if (mime and "png" in mime) else "jpg"
        user_dir = self.image_dir / self._safe_user_id(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}.{ext}"
        path = user_dir / filename
        try:
            path.write_bytes(data_bytes)
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to write chat image %s: %s", path, e)
            return None
        return str(path)

    def save_images(self, user_id: str, images: list[str]) -> list[str]:
        """Persist several images and return the list of file paths."""
        paths: list[str] = []
        for image_b64 in images or []:
            path = self.save_image(user_id, image_b64)
            if path:
                paths.append(path)
        return paths

    def load_image_data_url(self, image_path: str | None) -> str | None:
        """Re-encode a cached image file back to a data URL for the model."""
        if not image_path:
            return None
        path = Path(image_path)
        if not path.exists():
            return None
        try:
            raw = path.read_bytes()
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to read chat image %s: %s", path, e)
            return None
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"

    def load_images_data_urls(self, image_paths: list[str] | None) -> list[str]:
        """Re-encode a list of cached images back to data URLs."""
        urls: list[str] = []
        for image_path in image_paths or []:
            url = self.load_image_data_url(image_path)
            if url:
                urls.append(url)
        return urls

    def save_message(
        self,
        user_id: str,
        role: str,
        content: str,
        content_type: str = "text",
        image_path: str | None = None,
        image_paths: list[str] | None = None,
    ):
        with self._lock:
            cursor = self._conn.cursor()
            paths_json = json.dumps(image_paths) if image_paths else None
            first_path = image_paths[0] if image_paths else image_path
            cursor.execute(
                "INSERT INTO artist_chat_history "
                "(user_id, role, content, content_type, image_path, image_paths, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    role,
                    content,
                    content_type or "text",
                    first_path,
                    paths_json,
                    time.time(),
                ),
            )
            self._conn.commit()

    def get_recent_messages(self, user_id: str, limit: int = None) -> list[dict]:
        """Return recent messages in chronological order.

        *limit* defaults to ``CHAT_MAX_ROUNDS * 2`` (user + assistant per round).
        Each dict includes role/content/timestamp/content_type/image_path.
        """
        if limit is None:
            limit = CHAT_MAX_ROUNDS * 2
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT role, content, content_type, image_path, image_paths, timestamp "
                "FROM artist_chat_history WHERE user_id = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (user_id, limit),
            )
            rows = cursor.fetchall()
            result: list[dict] = []
            for r in reversed(rows):
                paths: list[str] = []
                if r["image_paths"]:
                    try:
                        paths = json.loads(r["image_paths"])
                    except Exception:  # noqa: BLE001
                        paths = []
                if not paths and r["image_path"]:
                    paths = [r["image_path"]]
                result.append({
                    "role": r["role"],
                    "content": r["content"],
                    "content_type": r["content_type"] or "text",
                    "image_path": r["image_path"],
                    "image_paths": paths,
                    "timestamp": r["timestamp"],
                })
            return result

    def clear_session(self, user_id: str):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "DELETE FROM artist_chat_history WHERE user_id = ?",
                (user_id,),
            )
            self._conn.commit()
            # Best-effort removal of the user's cached images.
            user_dir = self.image_dir / self._safe_user_id(user_id)
            try:
                if user_dir.exists():
                    for f in user_dir.iterdir():
                        if f.is_file():
                            f.unlink(missing_ok=True)
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to clear chat images for %s: %s", user_id, e)
            logger.info("Cleared chat history for user %s", user_id)


chat_history = ChatHistoryService()
