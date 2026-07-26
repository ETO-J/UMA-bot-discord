import asyncio
import uuid
import time
import sqlite3
import threading
import logging
from dataclasses import dataclass

from config import DB_PATH, TASK_IMAGE_DIR

logger = logging.getLogger(__name__)

_TASK_COLUMNS = (
    "task_id, status, created_at, prompt, workflow, prompt1, prompt2, "
    "global_prompt, user_id, image_filename, error, seed, "
    "sampler_name, scheduler, steps, cfg, output_type"
)
_LOAD_LIMIT = 500


@dataclass
class Task:
    task_id: str
    status: str
    created_at: float
    prompt: str
    workflow: str | None = None
    prompt1: str | None = None
    prompt2: str | None = None
    global_prompt: str | None = None
    user_id: str = "local_user"
    image_bytes: bytes | None = None
    image_filename: str | None = None
    error: str | None = None
    seed: int | None = None
    sampler_name: str | None = None
    scheduler: str | None = None
    steps: int | None = None
    cfg: float | None = None
    output_type: str = "image"
    comfyui_prompt_id: str | None = None


class TaskQueue:
    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._lock = asyncio.Lock()
        self._db_lock = threading.RLock()
        self._conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self.cleanup_age = 3600
        self._completed_durations: list[float] = []
        self._processing_started: dict[str, float] = {}
        self._comfyui_run_started: dict[str, float] = {}
        self._init_db()

    def _init_db(self):
        with self._db_lock:
            cursor = self._conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    prompt TEXT DEFAULT '',
                    workflow TEXT,
                    prompt1 TEXT,
                    prompt2 TEXT,
                    global_prompt TEXT,
                    user_id TEXT DEFAULT 'local_user',
                    image_filename TEXT,
                    error TEXT,
                    seed INTEGER,
                    sampler_name TEXT,
                    scheduler TEXT,
                    steps INTEGER,
                    cfg REAL,
                    output_type TEXT DEFAULT 'image'
                )
            """)
            cursor.execute("PRAGMA table_info(tasks)")
            existing_cols = [col[1] for col in cursor.fetchall()]
            if "output_type" not in existing_cols:
                cursor.execute("ALTER TABLE tasks ADD COLUMN output_type TEXT DEFAULT 'image'")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id, created_at DESC)"
            )
            self._conn.commit()

    @staticmethod
    def _row_to_task(row) -> Task:
        return Task(
            task_id=row["task_id"],
            status=row["status"],
            created_at=row["created_at"],
            prompt=row["prompt"] or "",
            workflow=row["workflow"],
            prompt1=row["prompt1"],
            prompt2=row["prompt2"],
            global_prompt=row["global_prompt"],
            user_id=row["user_id"],
            image_filename=row["image_filename"],
            error=row["error"],
            seed=row["seed"],
            sampler_name=row["sampler_name"],
            scheduler=row["scheduler"],
            steps=row["steps"],
            cfg=row["cfg"],
            output_type=row["output_type"] or "image",
        )

    def _persist_task(self, task: Task):
        with self._db_lock:
            cursor = self._conn.cursor()
            cursor.execute(
                f"INSERT OR REPLACE INTO tasks ({_TASK_COLUMNS}) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    task.task_id, task.status, task.created_at, task.prompt,
                    task.workflow, task.prompt1, task.prompt2, task.global_prompt,
                    task.user_id, task.image_filename, task.error, task.seed,
                    task.sampler_name, task.scheduler, task.steps, task.cfg,
                    task.output_type,
                ),
            )
            self._conn.commit()

    def _delete_from_db(self, task_id: str):
        with self._db_lock:
            cursor = self._conn.cursor()
            cursor.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
            self._conn.commit()

    def _save_image_to_disk(self, task: Task):
        if not task.image_bytes:
            return
        path = TASK_IMAGE_DIR / f"{task.task_id}.png"
        try:
            path.write_bytes(task.image_bytes)
            task.image_filename = path.name
        except Exception as e:
            logger.error("Failed to persist task image %s: %s", task.task_id, e)

    def _read_image_from_disk(self, task_id: str) -> bytes | None:
        path = TASK_IMAGE_DIR / f"{task_id}.png"
        if path.exists():
            try:
                return path.read_bytes()
            except Exception as e:
                logger.error("Failed to read task image %s: %s", task_id, e)
        return None

    def _delete_image_from_disk(self, task_id: str):
        path = TASK_IMAGE_DIR / f"{task_id}.png"
        if path.exists():
            try:
                path.unlink()
            except Exception as e:
                logger.warning("Failed to delete task image %s: %s", task_id, e)

    async def load_persisted_tasks(self):
        """Load tasks from DB on startup. Mark incomplete tasks as failed."""
        with self._db_lock:
            cursor = self._conn.cursor()
            cursor.execute(
                f"SELECT {_TASK_COLUMNS} FROM tasks ORDER BY created_at DESC LIMIT ?",
                (_LOAD_LIMIT,),
            )
            rows = cursor.fetchall()
        loaded = 0
        async with self._lock:
            for row in rows:
                task = self._row_to_task(row)
                if task.status in ("queued", "processing"):
                    task.status = "failed"
                    task.error = task.error or "Server restarted"
                    self._persist_task(task)
                self._tasks[task.task_id] = task
                loaded += 1
        logger.info("Loaded %d persisted tasks", loaded)

    async def create_task(
        self,
        user_id: str,
        prompt: str = "",
        workflow: str | None = None,
        prompt1: str | None = None,
        prompt2: str | None = None,
        global_prompt: str | None = None,
        seed: int | None = None,
        sampler_name: str | None = None,
        scheduler: str | None = None,
        steps: int | None = None,
        cfg: float | None = None,
        output_type: str = "image",
    ) -> Task:
        task = Task(
            task_id=str(uuid.uuid4())[:8],
            status="queued",
            created_at=time.time(),
            prompt=prompt,
            workflow=workflow,
            prompt1=prompt1,
            prompt2=prompt2,
            global_prompt=global_prompt,
            user_id=user_id,
            seed=seed,
            sampler_name=sampler_name,
            scheduler=scheduler,
            steps=steps,
            cfg=cfg,
            output_type=output_type,
        )
        async with self._lock:
            self._tasks[task.task_id] = task
        self._persist_task(task)
        return task

    async def get_task(self, task_id: str) -> Task | None:
        async with self._lock:
            if task_id in self._tasks:
                return self._tasks[task_id]
        with self._db_lock:
            cursor = self._conn.cursor()
            cursor.execute(
                f"SELECT {_TASK_COLUMNS} FROM tasks WHERE task_id=?",
                (task_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        task = self._row_to_task(row)
        async with self._lock:
            self._tasks.setdefault(task_id, task)
        return task

    async def update_task(self, task_id: str, **kwargs):
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            for key, value in kwargs.items():
                setattr(task, key, value)
            new_status = kwargs.get("status")
            if new_status == "processing" and task_id not in self._processing_started:
                self._processing_started[task_id] = time.time()
            if new_status in ("completed", "failed") and task_id in self._processing_started:
                duration = time.time() - self._processing_started.pop(task_id)
                if new_status == "completed":
                    self._completed_durations.append(duration)
                    if len(self._completed_durations) > 20:
                        self._completed_durations = self._completed_durations[-20:]
            if new_status in ("completed", "failed") and task.comfyui_prompt_id:
                self._comfyui_run_started.pop(task.comfyui_prompt_id, None)
            if new_status == "completed" and task.image_bytes:
                self._save_image_to_disk(task)
            self._persist_task(task)

    async def get_image_bytes(self, task_id: str) -> bytes | None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task:
                if task.status != "completed":
                    return None
                if task.image_bytes:
                    return task.image_bytes
        return self._read_image_from_disk(task_id)

    async def cleanup(self):
        now = time.time()
        to_remove = []
        async with self._lock:
            to_remove = [
                tid
                for tid, t in self._tasks.items()
                if t.status in ("completed", "failed") and (now - t.created_at) > self.cleanup_age
            ]
            for tid in to_remove:
                del self._tasks[tid]
        for tid in to_remove:
            self._delete_from_db(tid)
            self._delete_image_from_disk(tid)
        if to_remove:
            logger.info("Cleaned up %d old tasks", len(to_remove))

    async def get_all_tasks(self) -> list[Task]:
        async with self._lock:
            return list(self._tasks.values())

    async def get_user_tasks(self, user_id: str) -> list[Task]:
        async with self._lock:
            mem_tasks = [t for t in self._tasks.values() if t.user_id == user_id]
        if mem_tasks:
            return mem_tasks
        with self._db_lock:
            cursor = self._conn.cursor()
            cursor.execute(
                f"SELECT {_TASK_COLUMNS} FROM tasks WHERE user_id=? ORDER BY created_at DESC LIMIT 100",
                (user_id,),
            )
            rows = cursor.fetchall()
        tasks = []
        async with self._lock:
            for row in rows:
                task = self._row_to_task(row)
                self._tasks.setdefault(task.task_id, task)
                tasks.append(task)
        return tasks

    @property
    def _avg_processing_time(self) -> float | None:
        if not self._completed_durations:
            return None
        return sum(self._completed_durations) / len(self._completed_durations)

    async def get_queue_info(self, task_id: str) -> dict:
        """Return real queue position / ETA based on the ComfyUI prompt queue.

        The webapp forwards every task to ComfyUI immediately, so the real
        waiting happens inside ComfyUI's own queue.  We locate the task's
        ``comfyui_prompt_id`` in ``/queue`` to find its true position.
        """
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.status not in ("queued", "processing"):
                return {}
            pid = task.comfyui_prompt_id
            output_type = task.output_type
            created_at = task.created_at
            started = self._processing_started.get(task_id)
            ahead_fallback = len([
                t for t in self._tasks.values()
                if t.status in ("queued", "processing")
                and t.created_at < created_at and t.task_id != task_id
            ])
            active_total = len([
                t for t in self._tasks.values() if t.status in ("queued", "processing")
            ])

        # Lazy import to avoid any import-order issues at module load time.
        from services.generator import fetch_comfyui_queue
        queue = await fetch_comfyui_queue()
        running, pending = queue["running"], queue["pending"]
        comfy_total = len(running) + len(pending)

        avg = self._avg_processing_time
        if avg is None:
            avg = 300.0 if output_type == "video" else 60.0

        elapsed = round(time.time() - started, 1) if started else None

        if pid and pid in running:
            run_started = self._comfyui_run_started.setdefault(pid, time.time())
            exec_elapsed = time.time() - run_started
            remaining = max(0.0, avg - exec_elapsed)
            return {
                "queue_position": 0,
                "queue_total": max(comfy_total, 1),
                "estimated_seconds": round(remaining, 1),
                "elapsed_seconds": elapsed,
                "is_running": True,
            }
        if pid and pid in pending:
            ahead = len(running) + pending.index(pid)
            return {
                "queue_position": ahead,
                "queue_total": max(comfy_total, ahead + 1),
                "estimated_seconds": round(ahead * avg, 1),
                "elapsed_seconds": elapsed,
                "is_running": False,
            }

        # Fallback: prompt not submitted to ComfyUI yet (workflow prep /
        # image upload) or ComfyUI unreachable — estimate from webapp tasks.
        if ahead_fallback == 0:
            remaining = max(0.0, avg - (elapsed or 0))
            return {
                "queue_position": 0,
                "queue_total": max(active_total, comfy_total, 1),
                "estimated_seconds": round(remaining, 1),
                "elapsed_seconds": elapsed,
                "is_running": True,
            }
        return {
            "queue_position": ahead_fallback,
            "queue_total": max(active_total, comfy_total, ahead_fallback + 1),
            "estimated_seconds": round(ahead_fallback * avg, 1),
            "elapsed_seconds": elapsed,
            "is_running": False,
        }


task_queue = TaskQueue()
