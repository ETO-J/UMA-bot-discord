import asyncio
import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response

from schemas.requests import DrawRequest, MultidrawRequest, VideoRequest, TaskResponse
from services.workflow_manager import wm
from services.generator import generate_image, generate_multidraw_image, generate_video
from services.task_queue import task_queue
from dependencies import get_current_user_id
from config import VIDEO_RESOLUTIONS, VIDEO_BASE_COST, VIDEO_FPS

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


def _video_cost(quality: str, duration: int) -> int:
    return int(VIDEO_BASE_COST[quality] * duration * 0.2)


@router.post("/video/async", response_model=TaskResponse)
async def video_async(req: VideoRequest, user_id: str = Depends(get_current_user_id)):
    cost = _video_cost(req.quality, req.duration)
    user_settings = wm.get_user_settings(user_id)
    remaining = user_settings["limit_count"] - user_settings["used_today"]
    if remaining < cost:
        raise HTTPException(status_code=429, detail=f"Quota exhausted: need {cost}, have {remaining}")
    if not wm.use_quota(user_id, cost):
        raise HTTPException(status_code=429, detail="Quota check failed")

    res_set = VIDEO_RESOLUTIONS.get(req.quality, VIDEO_RESOLUTIONS["480p"])
    width, height = res_set.get(req.orientation, res_set["portrait"])
    length = req.duration * VIDEO_FPS + 1

    task = await task_queue.create_task(
        user_id=user_id, prompt=req.prompt,
        seed=req.seed, output_type="video",
    )

    async def process():
        await task_queue.update_task(task.task_id, status="processing")
        try:
            result = await generate_video(
                prompt=req.prompt,
                start_image_b64=req.start_image,
                end_image_b64=req.end_image,
                width=width, height=height, length=length,
                lora_enabled=req.lora_enabled,
                lora_strength=req.lora_strength,
                seed=req.seed,
                negative_prompt=req.negative_prompt,
            )
            if result:
                await task_queue.update_task(task.task_id, status="completed", image_bytes=result)
            else:
                wm.refund_quota(user_id, cost)
                await task_queue.update_task(task.task_id, status="failed", error="Video generation returned no data")
        except Exception as e:
            wm.refund_quota(user_id, cost)
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
        has_image=(t.image_bytes is not None) or (t.image_filename is not None),
        prompt1=t.prompt1, prompt2=t.prompt2, global_prompt=t.global_prompt,
        seed=t.seed, sampler_name=t.sampler_name,
        scheduler=t.scheduler, steps=t.steps, cfg=t.cfg,
        output_type=t.output_type,
    )


@router.get("/task/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str):
    task = await task_queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_response(task)


@router.get("/task/{task_id}/image")
async def get_task_image(task_id: str):
    image_bytes = await task_queue.get_image_bytes(task_id)
    if image_bytes is None:
        raise HTTPException(status_code=404, detail="Image not ready or task not found")
    return Response(content=image_bytes, media_type="image/png")


@router.get("/task/{task_id}/video")
async def get_task_video(task_id: str):
    video_bytes = await task_queue.get_image_bytes(task_id)
    if video_bytes is None:
        raise HTTPException(status_code=404, detail="Video not ready or task not found")
    return Response(content=video_bytes, media_type="video/mp4")


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(user_id: str = Depends(get_current_user_id)):
    tasks = await task_queue.get_user_tasks(user_id)
    return [_task_to_response(t) for t in tasks]
