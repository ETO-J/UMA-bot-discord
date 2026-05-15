"""聊天记录存储 - SQLite"""
import sqlite3
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from nonebot.log import logger

from ...config import CHAT_DB_PATH

# 北京时间
BEIJING_TZ = timezone(timedelta(hours=8))


def get_beijing_time() -> str:
    """获取当前北京时间字符串"""
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


class ChatHistoryMemory:
    def __init__(self):
        self.db_path = CHAT_DB_PATH
        self._init_db()

    def _init_db(self):
        """初始化数据库，确保表结构正确"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    user_id INTEGER,
                    user_name TEXT DEFAULT '',
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    content TEXT,
                    session_type TEXT DEFAULT 'group',
                    role TEXT DEFAULT 'user'
                )
            """)
            # 兼容旧数据库：添加缺失的列
            try:
                conn.execute("ALTER TABLE chat_history ADD COLUMN session_type TEXT DEFAULT 'group'")
            except sqlite3.OperationalError:
                pass
            conn.execute("UPDATE chat_history SET session_type = 'group' WHERE session_type IS NULL")
            # 迁移：添加 role 列，区分 user/assistant
            try:
                conn.execute("ALTER TABLE chat_history ADD COLUMN role TEXT DEFAULT 'user'")
            except sqlite3.OperationalError:
                pass
            conn.execute("UPDATE chat_history SET role = 'assistant' WHERE user_id = 'assistant'")
            conn.execute("UPDATE chat_history SET role = 'user' WHERE role IS NULL OR role = ''")
            # 迁移：添加 user_name 列
            try:
                conn.execute("ALTER TABLE chat_history ADD COLUMN user_name TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            # 创建索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_group ON chat_history (group_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user ON chat_history (user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_type ON chat_history (session_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_role ON chat_history (role)")

    def save_message(self, session_id: int, user_id: int, content: str, session_type: str = "group", role: str = "user", user_name: str = ""):
        """保存单条聊天记录"""
        beijing_time = get_beijing_time()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO chat_history (group_id, user_id, user_name, content, session_type, timestamp, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, user_id, user_name, content, session_type, beijing_time, role),
            )
            logger.info(f"Saved message: session_id={session_id}, user={user_id}, type={session_type}, time={beijing_time}")

    def get_recent_chat(self, session_id: int, session_type: str = "group", limit: int = 10, exclude_user_ids: Optional[List[str]] = None) -> List[Dict]:
        """获取最近N条对话历史（含AI回复，按时间正序），可排除指定用户"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT user_id, user_name, content, role FROM chat_history "
                "WHERE group_id = ? AND session_type = ? "
                "ORDER BY id DESC LIMIT ?",
                (session_id, session_type, limit * 2),
            )
            rows = cursor.fetchall()
            rows.reverse()
            exclude = set(exclude_user_ids) if exclude_user_ids else set()
            return [
                {"user": row[0], "user_name": row[1], "content": row[2], "role": row[3]}
                for row in rows
                if str(row[0]) not in exclude
            ]

    def get_private_recent_chat(self, user_id: int, limit: int = 10, exclude_user_ids: Optional[List[str]] = None) -> List[Dict]:
        """获取私聊最近N条对话历史（含AI回复，按时间正序），可排除指定用户"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT user_id, user_name, content, role FROM chat_history "
                "WHERE user_id = ? AND session_type = 'private' "
                "ORDER BY id DESC LIMIT ?",
                (user_id, limit * 2),
            )
            rows = cursor.fetchall()
            rows.reverse()
            exclude = set(exclude_user_ids) if exclude_user_ids else set()
            return [
                {"user": row[0], "user_name": row[1], "content": row[2], "role": row[3]}
                for row in rows
                if str(row[0]) not in exclude
            ]

    def get_ai_timestamps(self, group_id: int, limit: int = 20, time_window_seconds: int = 600) -> List[float]:
        """获取AI在指定群组内最近一段时间的发言时间戳"""
        time_threshold = datetime.now(BEIJING_TZ) - timedelta(seconds=time_window_seconds)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT strftime('%s', timestamp)
                FROM chat_history
                WHERE group_id = ?
                  AND role = 'assistant'
                  AND content != '未回复'
                  AND timestamp > ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (group_id, time_threshold, limit),
            )
            return [float(row[0]) for row in cursor.fetchall() if row[0] is not None]
