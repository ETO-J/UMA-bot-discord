import json
import os
import sqlite3
import logging
import threading
from pathlib import Path

from config import (
    COMFYUI_DIR,
    DB_DIR,
    DB_PATH,
    WORKFLOW_DIR,
    LORA_BASE_PATH,
    LORA_DIRS,
    LORA_ANIMA_DIRS,
)

logger = logging.getLogger(__name__)


class WorkflowManager:
    def __init__(self):
        self._ensure_dir()
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._init_db()

    def _ensure_dir(self):
        WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
        DB_DIR.mkdir(parents=True, exist_ok=True)

    def _init_db(self):
        try:
            with self._lock:
                cursor = self._conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_settings (
                        user_id TEXT PRIMARY KEY,
                        width INTEGER DEFAULT 832,
                        height INTEGER DEFAULT 1216,
                        active_loras TEXT DEFAULT '{}',
                        workflow TEXT DEFAULT 'discord_anima_v2',
                        negative_prompt TEXT DEFAULT 'mosaic,low quality, bad quality, worst quality'
                    )
                """)
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
                    "artist_chain": "TEXT DEFAULT ''",
                }
                for field, definition in new_fields.items():
                    if field not in existing:
                        logger.info("DB upgrade: adding column %s", field)
                        cursor.execute(f"ALTER TABLE user_settings ADD COLUMN {field} {definition}")
                cursor.execute("SELECT user_id, part1, part2 FROM user_settings")
                for row in cursor.fetchall():
                    uid, p1, p2 = row["user_id"], row["part1"], row["part2"]
                    if not p1 or p1 == "[]":
                        cursor.execute("UPDATE user_settings SET part1=? WHERE user_id=?", ("[832,608,0,0]", uid))
                    if not p2 or p2 == "[]":
                        cursor.execute("UPDATE user_settings SET part2=? WHERE user_id=?", ("[832,608,832,0]", uid))
                cursor.execute("UPDATE user_settings SET workflow='discord_anima_v2' WHERE workflow='uma'")
                self._conn.commit()
            logger.info("DB init/upgrade success: %s", DB_PATH)
        except Exception as e:
            logger.error("DB init failed: %s", e)

    @staticmethod
    def _row_to_settings(row) -> dict:
        return {
            "resolution": (row["width"], row["height"]),
            "active_loras": json.loads(row["active_loras"]),
            "workflow": row["workflow"],
            "limit_count": row["limit_count"],
            "used_today": row["used_today"],
            "negative_prompt": row["negative_prompt"] or "",
            "is_hd_mode": bool(row["is_hd_mode"]),
            "part1": json.loads(row["part1"]) if isinstance(row["part1"], str) else row["part1"],
            "part2": json.loads(row["part2"]) if isinstance(row["part2"], str) else row["part2"],
            "artist_chain": row["artist_chain"] or "",
        }

    def get_user_settings(self, user_id: str):
        import datetime
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT width, height, active_loras, workflow, limit_count, used_today, last_reset_date, "
                "negative_prompt, is_hd_mode, part1, part2, artist_chain FROM user_settings WHERE user_id = ?",
                (user_id,),
            )
            row = cursor.fetchone()
            if row:
                if row["last_reset_date"] != today_str:
                    cursor.execute(
                        "UPDATE user_settings SET used_today=0, last_reset_date=? WHERE user_id=?",
                        (today_str, user_id),
                    )
                    self._conn.commit()
                    settings = dict(row)
                    settings["used_today"] = 0
                    return self._row_to_settings(settings)
                return self._row_to_settings(row)
            else:
                cursor.execute(
                    "INSERT INTO user_settings (user_id, last_reset_date, workflow) VALUES (?, ?, 'discord_anima_v2')",
                    (user_id, today_str),
                )
                self._conn.commit()
                cursor.execute(
                    "SELECT width, height, active_loras, workflow, limit_count, used_today, last_reset_date, "
                    "negative_prompt, is_hd_mode, part1, part2, artist_chain FROM user_settings WHERE user_id = ?",
                    (user_id,),
                )
                row = cursor.fetchone()
                return self._row_to_settings(row)

    def use_quota(self, user_id: str, count: int = 1) -> bool:
        with self._lock:
            settings = self.get_user_settings(user_id)
            remaining = settings["limit_count"] - settings["used_today"]
            if remaining < count:
                return False
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE user_settings SET used_today = used_today + ? WHERE user_id=?",
                (count, user_id),
            )
            self._conn.commit()
            return True

    def refund_quota(self, user_id: str, count: int = 1):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE user_settings SET used_today = MAX(0, used_today - ?) WHERE user_id=?",
                (count, user_id),
            )
            self._conn.commit()

    def set_user_limit(self, user_id: str, new_limit: int):
        with self._lock:
            self.get_user_settings(user_id)
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE user_settings SET limit_count=? WHERE user_id=?",
                (new_limit, user_id),
            )
            self._conn.commit()

    def set_resolution(self, user_id: str, width: int, height: int):
        with self._lock:
            self.get_user_settings(user_id)
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE user_settings SET width=?, height=? WHERE user_id=?",
                (width, height, user_id),
            )
            self._conn.commit()

    def set_negative_prompt(self, user_id: str, text: str):
        with self._lock:
            self.get_user_settings(user_id)
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE user_settings SET negative_prompt=? WHERE user_id=?",
                (text, user_id),
            )
            self._conn.commit()

    def set_artist_chain(self, user_id: str, text: str):
        with self._lock:
            self.get_user_settings(user_id)
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE user_settings SET artist_chain=? WHERE user_id=?",
                (text, user_id),
            )
            self._conn.commit()

    def set_hd_mode(self, user_id: str, enabled: bool):
        with self._lock:
            self.get_user_settings(user_id)
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE user_settings SET is_hd_mode=? WHERE user_id=?",
                (1 if enabled else 0, user_id),
            )
            self._conn.commit()

    def set_part1(self, user_id: str, part: list):
        with self._lock:
            self.get_user_settings(user_id)
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE user_settings SET part1=? WHERE user_id=?",
                (json.dumps(part), user_id),
            )
            self._conn.commit()

    def set_part2(self, user_id: str, part: list):
        with self._lock:
            self.get_user_settings(user_id)
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE user_settings SET part2=? WHERE user_id=?",
                (json.dumps(part), user_id),
            )
            self._conn.commit()

    def set_user_setting(self, user_id: str, key: str, value):
        with self._lock:
            self.get_user_settings(user_id)
            cursor = self._conn.cursor()
            cursor.execute(
                f"UPDATE user_settings SET {key}=? WHERE user_id=?",
                (value, user_id),
            )
            self._conn.commit()

    def load_workflow_data(self, name: str) -> dict | None:
        file_path = WORKFLOW_DIR / f"{name}.json"
        if not file_path.exists():
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load workflow %s: %s", name, e)
            return None

    def _get_lora_dirs(self, workflow: str = None) -> list:
        if workflow and "anima" in workflow:
            return LORA_ANIMA_DIRS
        return LORA_DIRS

    def get_lora_list(self, workflow: str = None):
        dirs = self._get_lora_dirs(workflow)
        lora_dict = {}
        for sub_dir in dirs:
            path = LORA_BASE_PATH / sub_dir
            if path.exists():
                loras = [f.name for f in path.glob("**/*") if f.suffix in [".safetensors", ".ckpt"]]
                lora_dict[sub_dir] = loras
        return lora_dict

    def find_lora_path(self, name: str, workflow: str = None):
        dirs = self._get_lora_dirs(workflow)
        for sub_dir in dirs:
            path = LORA_BASE_PATH / sub_dir
            for f in path.glob("**/*"):
                if name.lower() in f.name.lower():
                    return f"{sub_dir}\\{f.name}"
        return None

    def add_lora(self, user_id: str, lora_name: str, weight: float):
        with self._lock:
            settings = self.get_user_settings(user_id)
            workflow = settings.get("workflow", "discord_anima_v2")
            current_loras = settings["active_loras"]
            real_path = self.find_lora_path(lora_name, workflow)
            if real_path:
                file_name = os.path.basename(real_path)
                current_loras[file_name] = weight
                cursor = self._conn.cursor()
                cursor.execute(
                    "UPDATE user_settings SET active_loras=? WHERE user_id=?",
                    (json.dumps(current_loras), user_id),
                )
                self._conn.commit()
                return file_name
            return None

    def remove_lora(self, user_id: str, lora_name: str):
        with self._lock:
            settings = self.get_user_settings(user_id)
            current_loras = settings["active_loras"]
            if lora_name in current_loras:
                del current_loras[lora_name]
                cursor = self._conn.cursor()
                cursor.execute(
                    "UPDATE user_settings SET active_loras=? WHERE user_id=?",
                    (json.dumps(current_loras), user_id),
                )
                self._conn.commit()
                return True
            return False

    def clear_loras(self, user_id: str):
        with self._lock:
            self.get_user_settings(user_id)
            cursor = self._conn.cursor()
            cursor.execute(
                "UPDATE user_settings SET active_loras='{}' WHERE user_id=?",
                (user_id,),
            )
            self._conn.commit()


wm = WorkflowManager()
