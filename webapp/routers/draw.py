import asyncio
import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response

from schemas.requests import DrawRequest, MultidrawRequest, TaskResponse
from services.workflow_manager import wm
from services.generator import generate_image, generate_multidraw_image
from services.task_queue import task_queue
from dependencies import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(tags=["draw"])

DEFAULT_WORKFLOW = "discord_anima_v2"


@router.post("/draw", response_class=Response)
async def draw_sync(req: DrawRequest, user_id: str = Depends(get_current_user_id)):
    user_settings = wm.get_user_settings(user_id)
    remaining = user_settings["limit_count"] - user_settings["used_today"]
    if remaining < 1:
        raise HTTPException(status_code=429, detail=f"Quota exhausted: {user_settings['used_today']}/{user_settings['limit_count']}")
    if not wm.use_quota(user_id, 1):
        raise HTTPException(status_code=429, detail="Quota check failed")

    try:
        image_bytes = await generate_image(
            req.prompt, user_id, DEFAULT_WORKFLOW,
            seed=req.seed, sampler_name=req.sampler_name,
            scheduler=req.scheduler, steps=req.steps, cfg=req.cfg,
        )
        if image_bytes:
            return Response(content=image_bytes, media_type="image/png")
        else:
            wm.refund_quota(user_id, 1)
            raise HTTPException(status_code=500, detail="Image generation failed")
    except HTTPException:
        raise
    except Exception as e:
        wm.refund_quota(user_id, 1)
        logger.error("Draw failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/draw/async", response_model=TaskResponse)
async def draw_async(req: DrawRequest, user_id: str = Depends(get_current_user_id)):
    user_settings = wm.get_user_settings(user_id)
    remaining = user_settings["limit_count"] - user_settings["used_today"]
    if remaining < 1:
        raise HTTPException(status_code=429, detail=f"Quota exhausted: {user_settings['used_today']}/{user_settings['limit_count']}")
    if not wm.use_quota(user_id, 1):
        raise HTTPException(status_code=429, detail="Quota check failed")

    task = await task_queue.create_task(
        user_id=user_id, prompt=req.prompt,
        seed=req.seed, sampler_name=req.sampler_name,
        scheduler=req.scheduler, steps=req.steps, cfg=req.cfg,
    )

    async def process():
        await task_queue.update_task(task.task_id, status="processing")
        try:
            result = await generate_image(
                req.prompt, user_id, DEFAULT_WORKFLOW,
                seed=req.seed, sampler_name=req.sampler_name,
                scheduler=req.scheduler, steps=req.steps, cfg=req.cfg,
            )
            if result:
                await task_queue.update_task(task.task_id, status="completed", image_bytes=result)
            else:
                wm.refund_quota(user_id, 1)
                await task_queue.update_task(task.task_id, status="failed", error="Generation returned no data")
        except Exception as e:
            wm.refund_quota(user_id, 1)
            await task_queue.update_task(task.task_id, status="failed", error=str(e))

    asyncio.create_task(process())
    return _task_to_response(task)


@router.post("/multidraw", response_class=Response)
async def multidraw_sync(req: MultidrawRequest, user_id: str = Depends(get_current_user_id)):
    user_settings = wm.get_user_settings(user_id)
    remaining = user_settings["limit_count"] - user_settings["used_today"]
    if remaining < 10:
        raise HTTPException(status_code=429, detail=f"Quota exhausted: {user_settings['used_today']}/{user_settings['limit_count']}")
    if not wm.use_quota(user_id, 10):
        raise HTTPException(status_code=429, detail="Quota check failed")

    try:
        image_bytes = await generate_multidraw_image(
            req.prompt1, req.prompt2, req.global_prompt, user_id,
            seed=req.seed, sampler_name=req.sampler_name,
            scheduler=req.scheduler, steps=req.steps, cfg=req.cfg,
        )
        if image_bytes:
            return Response(content=image_bytes, media_type="image/png")
        else:
            wm.refund_quota(user_id, 10)
            raise HTTPException(status_code=500, detail="Multidraw generation failed")
    except HTTPException:
        raise
    except Exception as e:
        wm.refund_quota(user_id, 10)
        logger.error("Multidraw failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/multidraw/async", response_model=TaskResponse)
async def multidraw_async(req: MultidrawRequest, user_id: str = Depends(get_current_user_id)):
    user_settings = wm.get_user_settings(user_id)
    remaining = user_settings["limit_count"] - user_settings["used_today"]
    if remaining < 10:
        raise HTTPException(status_code=429, detail=f"Quota exhausted: {user_settings['used_today']}/{user_settings['limit_count']}")
    if not wm.use_quota(user_id, 10):
        raise HTTPException(status_code=429, detail="Quota check failed")

    task = await task_queue.create_task(
        user_id=user_id, prompt1=req.prompt1, prompt2=req.prompt2, global_prompt=req.global_prompt,
        seed=req.seed, sampler_name=req.sampler_name,
        scheduler=req.scheduler, steps=req.steps, cfg=req.cfg,
    )

    async def process():
        await task_queue.update_task(task.task_id, status="processing")
        try:
            result = await generate_multidraw_image(
                req.prompt1, req.prompt2, req.global_prompt, user_id,
                seed=req.seed, sampler_name=req.sampler_name,
                scheduler=req.scheduler, steps=req.steps, cfg=req.cfg,
            )
            if result:
                await task_queue.update_task(task.task_id, status="completed", image_bytes=result)
            else:
                wm.refund_quota(user_id, 10)
                await task_queue.update_task(task.task_id, status="failed", error="Generation returned no data")
        except Exception as e:
            wm.refund_quota(user_id, 10)
            await task_queue.update_task(task.task_id, status="failed", error=str(e))

    asyncio.create_task(process())
    return _task_to_response(task)


def _task_to_response(t) -> TaskResponse:
    if t.prompt:
        p = t.prompt
    elif t.global_prompt:
        p = f"[Multidraw] {t.global_prompt} | {t.prompt1} | {t.prompt2}"
    else:
        p = ""
    return TaskResponse(
        task_id=t.task_id, status=t.status, prompt=p,
        created_at=t.created_at, error=t.error,
        has_image=t.image_bytes is not None,
        prompt1=t.prompt1, prompt2=t.prompt2, global_prompt=t.global_prompt,
        seed=t.seed, sampler_name=t.sampler_name,
        scheduler=t.scheduler, steps=t.steps, cfg=t.cfg,
    )


@router.get("/task/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str):
    task = await task_queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_response(task)


@router.get("/task/{task_id}/image")
async def get_task_image(task_id: str):
    task = await task_queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "completed" or not task.image_bytes:
        raise HTTPException(status_code=404, detail="Image not ready or task failed")
    return Response(content=task.image_bytes, media_type="image/png")


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(user_id: str = Depends(get_current_user_id)):
    tasks = await task_queue.get_user_tasks(user_id)
    return [_task_to_response(t) for t in tasks]
