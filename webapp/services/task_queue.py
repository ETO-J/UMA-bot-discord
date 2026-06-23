import asyncio
import uuid
import time
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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


class TaskQueue:
    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._lock = asyncio.Lock()
        self.cleanup_age = 3600

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
        )
        async with self._lock:
            self._tasks[task.task_id] = task
        return task

    async def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    async def update_task(self, task_id: str, **kwargs):
        async with self._lock:
            if task_id in self._tasks:
                for key, value in kwargs.items():
                    setattr(self._tasks[task_id], key, value)

    async def cleanup(self):
        now = time.time()
        async with self._lock:
            to_remove = [
                tid
                for tid, t in self._tasks.items()
                if t.status in ("completed", "failed") and (now - t.created_at) > self.cleanup_age
            ]
            for tid in to_remove:
                del self._tasks[tid]
            if to_remove:
                logger.info("Cleaned up %d old tasks", len(to_remove))

    async def get_all_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    async def get_user_tasks(self, user_id: str) -> list[Task]:
        return [t for t in self._tasks.values() if t.user_id == user_id]


task_queue = TaskQueue()
