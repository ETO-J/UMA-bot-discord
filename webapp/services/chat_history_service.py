"""Short-term chat history for the drawing assistant (SQLite).

Keeps the most recent N rounds of conversation per user.
One "round" = 1 user message + 1 assistant message.
"""
import sqlite3
import logging
import threading
import time

from config import DB_PATH, CHAT_MAX_ROUNDS

logger = logging.getLogger(__name__)


class ChatHistoryService:
    def __init__(self):
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
            self._conn.commit()
            logger.info("Artist chat history table ready")

    def save_message(self, user_id: str, role: str, content: str):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "INSERT INTO artist_chat_history (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                (user_id, role, content, time.time()),
            )
            self._conn.commit()

    def get_recent_messages(self, user_id: str, limit: int = None) -> list[dict]:
        """Return recent messages in chronological order.

        *limit* defaults to ``CHAT_MAX_ROUNDS * 2`` (user + assistant per round).
        """
        if limit is None:
            limit = CHAT_MAX_ROUNDS * 2
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT role, content, timestamp FROM artist_chat_history "
                "WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
                (user_id, limit),
            )
            rows = cursor.fetchall()
            # Reverse to get chronological order
            return [{"role": r["role"], "content": r["content"], "timestamp": r["timestamp"]}
                    for r in reversed(rows)]

    def clear_session(self, user_id: str):
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "DELETE FROM artist_chat_history WHERE user_id = ?",
                (user_id,),
            )
            self._conn.commit()
            logger.info("Cleared chat history for user %s", user_id)


chat_history = ChatHistoryService()
