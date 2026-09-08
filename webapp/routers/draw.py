import asyncio
import math
import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response, FileResponse

from schemas.requests import DrawRequest, DiffDrawRequest, MultidrawRequest, VideoRequest, Flux2EditRequest, TaskResponse
from services.workflow_manager import wm
from services.generator import (
    generate_image,
    generate_multidraw_image,
    generate_video,
    generate_ref2va_video,
    generate_flux2_edit_image,
)
from services.task_queue import task_queue
from dependencies import get_current_user_id
from config import (
    VIDEO_RESOLUTIONS,
    VIDEO_PER_SECOND_COST,
    VIDEO_LONG_DURATION_START,
    VIDEO_LONG_DURATION_MULT,
    VIDEO_FPS,
    REF2VA_COST_MULTIPLIER,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["draw"])

DEFAULT_WORKFLOW = "discord_anima_fast"
DIFF_WORKFLOW = "discord_差分"
HD_COST = 10

# Strong references for fire-and-forget generation tasks so the event loop never
# garbage-collects (and silently cancels) a long-running video generation.
_bg_tasks: set[asyncio.Task] = set()


def _spawn_bg(coro):
    """Schedule a background task while keeping a strong reference."""
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)

    def _done(t: asyncio.Task):
        _bg_tasks.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error("Background generation task crashed: %s", exc)

    task.add_done_callback(_done)
    return task


@router.post("/draw", response_class=Response)
async def draw_sync(req: DrawRequest, user_id: str = Depends(get_current_user_id)):
    user_settings = wm.get_user_settings(user_id)
    cost = HD_COST if req.hd_mode else 1
    remaining = user_settings["limit_count"] - user_settings["used_today"]
    if remaining < cost:
        raise HTTPException(status_code=429, detail=f"Quota exhausted: {user_settings['used_today']}/{user_settings['limit_count']}")
    if not wm.use_quota(user_id, cost):
        raise HTTPException(status_code=429, detail="Quota check failed")

    try:
        image_bytes = await generate_image(
            req.prompt, user_id, DEFAULT_WORKFLOW,
            seed=req.seed, sampler_name=req.sampler_name,
            scheduler=req.scheduler, steps=req.steps, cfg=req.cfg,
            hd_mode=req.hd_mode,
        )
        if image_bytes:
            return Response(content=image_bytes, media_type="image/png")
        else:
            wm.refund_quota(user_id, cost)
            raise HTTPException(status_code=500, detail="Image generation failed")
    except HTTPException:
        raise
    except Exception as e:
        wm.refund_quota(user_id, cost)
        logger.error("Draw failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/draw/async", response_model=TaskResponse)
async def draw_async(req: DrawRequest, user_id: str = Depends(get_current_user_id)):
    user_settings = wm.get_user_settings(user_id)
    cost = HD_COST if req.hd_mode else 1
    remaining = user_settings["limit_count"] - user_settings["used_today"]
    if remaining < cost:
        raise HTTPException(status_code=429, detail=f"Quota exhausted: need {cost}, have {remaining}")
    if not wm.use_quota(user_id, cost):
        raise HTTPException(status_code=429, detail="Quota check failed")

    task = await task_queue.create_task(
        user_id=user_id, prompt=req.prompt,
        seed=req.seed, sampler_name=req.sampler_name,
        scheduler=req.scheduler, steps=req.steps, cfg=req.cfg,
    )

    async def process():
        await task_queue.update_task(task.task_id, status="processing")
        async def _on_submit(pid: str):
            await task_queue.update_task(task.task_id, comfyui_prompt_id=pid)
        try:
            result = await generate_image(
                req.prompt, user_id, DEFAULT_WORKFLOW,
                seed=req.seed, sampler_name=req.sampler_name,
                scheduler=req.scheduler, steps=req.steps, cfg=req.cfg,
                hd_mode=req.hd_mode,
                on_prompt_submitted=_on_submit,
            )
            if result:
                await task_queue.update_task(task.task_id, status="completed", image_bytes=result)
            else:
                wm.refund_quota(user_id, cost)
                await task_queue.update_task(task.task_id, status="failed", error="Generation returned no data")
        except Exception as e:
            wm.refund_quota(user_id, cost)
            await task_queue.update_task(task.task_id, status="failed", error=str(e))

    _spawn_bg(process())
    return await _task_to_response_with_queue(task)


@router.post("/draw/diff/async", response_model=TaskResponse)
async def draw_diff_async(req: DiffDrawRequest, user_id: str = Depends(get_current_user_id)):
    user_settings = wm.get_user_settings(user_id)
    cost = HD_COST if req.hd_mode else 1
    remaining = user_settings["limit_count"] - user_settings["used_today"]
    if remaining < cost:
        raise HTTPException(status_code=429, detail=f"Quota exhausted: need {cost}, have {remaining}")
    if not wm.use_quota(user_id, cost):
        raise HTTPException(status_code=429, detail="Quota check failed")

    task = await task_queue.create_task(
        user_id=user_id, prompt=req.prompt,
        seed=req.seed, sampler_name=req.sampler_name,
        scheduler=req.scheduler, steps=req.steps, cfg=req.cfg,
    )

    async def process():
        await task_queue.update_task(task.task_id, status="processing")
        async def _on_submit(pid: str):
            await task_queue.update_task(task.task_id, comfyui_prompt_id=pid)
        try:
            result = await generate_image(
                req.prompt, user_id, DIFF_WORKFLOW,
                seed=req.seed, sampler_name=req.sampler_name,
                scheduler=req.scheduler, steps=req.steps, cfg=req.cfg,
                hd_mode=req.hd_mode,
                denoise=req.denoise,
                source_image_b64=req.image,
                on_prompt_submitted=_on_submit,
            )
            if result:
                await task_queue.update_task(task.task_id, status="completed", image_bytes=result)
            else:
                wm.refund_quota(user_id, cost)
                await task_queue.update_task(task.task_id, status="failed", error="Diff generation returned no data")
        except Exception as e:
            wm.refund_quota(user_id, cost)
            await task_queue.update_task(task.task_id, status="failed", error=str(e))

    _spawn_bg(process())
    return await _task_to_response_with_queue(task)


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
        async def _on_submit(pid: str):
            await task_queue.update_task(task.task_id, comfyui_prompt_id=pid)
        try:
            result = await generate_multidraw_image(
                req.prompt1, req.prompt2, req.global_prompt, user_id,
                seed=req.seed, sampler_name=req.sampler_name,
                scheduler=req.scheduler, steps=req.steps, cfg=req.cfg,
                on_prompt_submitted=_on_submit,
            )
            if result:
                await task_queue.update_task(task.task_id, status="completed", image_bytes=result)
            else:
                wm.refund_quota(user_id, 10)
                await task_queue.update_task(task.task_id, status="failed", error="Generation returned no data")
        except Exception as e:
            wm.refund_quota(user_id, 10)
            await task_queue.update_task(task.task_id, status="failed", error=str(e))

    _spawn_bg(process())
    return await _task_to_response_with_queue(task)


def _video_cost(quality: str, duration: int) -> int:
    rate = VIDEO_PER_SECOND_COST.get(quality, VIDEO_PER_SECOND_COST["480p"])
    if duration >= VIDEO_LONG_DURATION_START:
        rate *= VIDEO_LONG_DURATION_MULT
    return rate * duration


@router.post("/video/async", response_model=TaskResponse)
async def video_async(req: VideoRequest, user_id: str = Depends(get_current_user_id)):
    base_cost = _video_cost(req.quality, req.duration)
    cost = (
        math.ceil(base_cost * REF2VA_COST_MULTIPLIER)
        if req.video_mode == "ref2va"
        else base_cost
    )
    user_settings = wm.get_user_settings(user_id)
    remaining = user_settings["limit_count"] - user_settings["used_today"]
    if remaining < cost:
        raise HTTPException(status_code=429, detail=f"Quota exhausted: need {cost}, have {remaining}")
    if not wm.use_quota(user_id, cost):
        raise HTTPException(status_code=429, detail="Quota check failed")

    res_set = VIDEO_RESOLUTIONS.get(req.quality, VIDEO_RESOLUTIONS["480p"])
    width, height = res_set.get(req.orientation, res_set["portrait"])
    length = req.duration * VIDEO_FPS + 1

    reference_ids = {
        "image_uploads": req.reference_image_uploads or [],
        "video_uploads": req.reference_video_uploads or [],
        "audio_uploads": req.reference_audio_uploads or [],
        "image_assets": req.reference_image_asset_ids or [],
        "video_assets": req.reference_video_asset_ids or [],
        "audio_assets": req.reference_audio_asset_ids or [],
    }
    task = await task_queue.create_task(
        user_id=user_id, prompt=req.prompt,
        seed=req.seed, output_type="video",
        workflow="webui_video_ref" if req.video_mode == "ref2va" else "webui_video",
        video_mode=req.video_mode,
        reference_ids=reference_ids,
        params={
            "quality": req.quality,
            "duration": req.duration,
            "orientation": req.orientation,
            "aspect_ratio": req.aspect_ratio,
            "output_last_frame": req.output_last_frame,
            "start_image": bool(req.start_image),
            "end_image": bool(req.end_image),
        },
    )

    async def process():
        await task_queue.update_task(task.task_id, status="processing")
        async def _on_submit(pid: str):
            await task_queue.update_task(task.task_id, comfyui_prompt_id=pid)
        try:
            if req.video_mode == "fl2va":
                if not req.start_image:
                    raise ValueError("FL2VA 模式必须提供首帧")
                result = await generate_video(
                    prompt=req.prompt,
                    start_image_b64=req.start_image,
                    end_image_b64=req.end_image,
                    width=width, height=height, length=length,
                    quality=req.quality,
                    user_id=user_id,
                    seed=req.seed,
                    on_prompt_submitted=_on_submit,
                )
                video_bytes = result
                last_frame_bytes = None
            else:
                reference_image_uploads = req.reference_image_uploads or []
                reference_video_uploads = req.reference_video_uploads or []
                reference_audio_uploads = req.reference_audio_uploads or []
                if not (
                    reference_image_uploads
                    or reference_video_uploads
                    or reference_audio_uploads
                    or req.reference_image_asset_ids
                    or req.reference_video_asset_ids
                    or req.reference_audio_asset_ids
                ):
                    raise ValueError("Ref2VA 至少需要一个参考素材")
                ref_result = await generate_ref2va_video(
                    prompt=req.prompt,
                    reference_image_uploads=reference_image_uploads,
                    reference_video_uploads=reference_video_uploads,
                    reference_audio_uploads=reference_audio_uploads,
                    reference_image_asset_ids=req.reference_image_asset_ids or [],
                    reference_video_asset_ids=req.reference_video_asset_ids or [],
                    reference_audio_asset_ids=req.reference_audio_asset_ids or [],
                    width=width,
                    height=height,
                    quality=req.quality,
                    aspect_ratio=req.aspect_ratio,
                    length=length,
                    user_id=user_id,
                    seed=req.seed,
                    output_last_frame=req.output_last_frame,
                    on_prompt_submitted=_on_submit,
                )
                video_bytes = ref_result.get("video")
                last_frame_bytes = ref_result.get("last_frame")

            if video_bytes:
                await task_queue.update_task(
                    task.task_id,
                    status="completed",
                    image_bytes=video_bytes,
                    last_frame_bytes=last_frame_bytes,
                )
            else:
                wm.refund_quota(user_id, cost)
                await task_queue.update_task(task.task_id, status="failed", error="Video generation returned no data")
        except Exception as e:
            wm.refund_quota(user_id, cost)
            await task_queue.update_task(task.task_id, status="failed", error=str(e))

    _spawn_bg(process())
    return await _task_to_response_with_queue(task)


FLUX2_EDIT_COST = 20
FLUX2_EDIT_CUTOUT_COST = 20
FLUX2_CUTOUT_COST = 1


def _flux2_cost(mode: str) -> int:
    if mode == "cutout":
        return FLUX2_CUTOUT_COST
    if mode == "edit_cutout":
        return FLUX2_EDIT_CUTOUT_COST
    return FLUX2_EDIT_COST


@router.post("/flux2_edit/async", response_model=TaskResponse)
async def flux2_edit_async(req: Flux2EditRequest, user_id: str = Depends(get_current_user_id)):
    cost = _flux2_cost(req.mode)
    user_settings = wm.get_user_settings(user_id)
    remaining = user_settings["limit_count"] - user_settings["used_today"]
    if remaining < cost:
        raise HTTPException(status_code=429, detail=f"Quota exhausted: need {cost}, have {remaining}")
    if not wm.use_quota(user_id, cost):
        raise HTTPException(status_code=429, detail="Quota check failed")

    task = await task_queue.create_task(
        user_id=user_id, prompt=req.prompt,
        seed=req.seed, sampler_name=req.sampler_name,
        steps=req.steps, cfg=req.cfg,
    )

    async def process():
        await task_queue.update_task(task.task_id, status="processing")
        async def _on_submit(pid: str):
            await task_queue.update_task(task.task_id, comfyui_prompt_id=pid)
        try:
            result = await generate_flux2_edit_image(
                prompt=req.prompt,
                source_image_b64=req.source_image,
                reference_image_b64=req.reference_image,
                user_id=user_id,
                negative_prompt=req.negative_prompt,
                seed=req.seed,
                steps=req.steps,
                cfg=req.cfg,
                sampler_name=req.sampler_name,
                mode=req.mode,
                on_prompt_submitted=_on_submit,
            )
            if result:
                await task_queue.update_task(task.task_id, status="completed", image_bytes=result)
            else:
                wm.refund_quota(user_id, cost)
                await task_queue.update_task(task.task_id, status="failed", error="Flux2 edit generation returned no data")
        except Exception as e:
            wm.refund_quota(user_id, cost)
            await task_queue.update_task(task.task_id, status="failed", error=str(e))

    _spawn_bg(process())
    return await _task_to_response_with_queue(task)


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
        has_last_frame=t.has_last_frame,
        video_mode=t.video_mode,
        reference_ids=t.reference_ids,
        params=t.params,
    )


async def _task_to_response_with_queue(t) -> TaskResponse:
    resp = _task_to_response(t)
    if t.status in ("queued", "processing"):
        info = await task_queue.get_queue_info(t.task_id)
        resp.queue_position = info.get("queue_position")
        resp.queue_total = info.get("queue_total")
        resp.estimated_seconds = info.get("estimated_seconds")
        resp.elapsed_seconds = info.get("elapsed_seconds")
        resp.is_running = info.get("is_running")
    return resp


@router.get("/task/{task_id}", response_model=TaskResponse)
async def get_task_status(task_id: str):
    task = await task_queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return await _task_to_response_with_queue(task)


@router.get("/task/{task_id}/image")
async def get_task_image(task_id: str):
    path = await task_queue.get_saved_file_path(task_id)
    if path is not None:
        return FileResponse(path, media_type="image/png")
    image_bytes = await task_queue.get_image_bytes(task_id)
    if image_bytes is None:
        raise HTTPException(status_code=404, detail="Image not ready or task not found")
    return Response(content=image_bytes, media_type="image/png")


@router.get("/task/{task_id}/video")
async def get_task_video(task_id: str):
    path = await task_queue.get_saved_file_path(task_id)
    if path is not None:
        return FileResponse(path, media_type="video/mp4")
    video_bytes = await task_queue.get_image_bytes(task_id)
    if video_bytes is None:
        raise HTTPException(status_code=404, detail="Video not ready or task not found")
    return Response(content=video_bytes, media_type="video/mp4")


@router.get("/task/{task_id}/last-frame")
async def get_task_last_frame(task_id: str):
    path = await task_queue.get_saved_last_frame_path(task_id)
    if path is not None:
        return FileResponse(path, media_type="image/png")
    last_frame_bytes = await task_queue.get_last_frame_bytes(task_id)
    if last_frame_bytes is None:
        raise HTTPException(status_code=404, detail="尾帧不存在或任务未完成")
    return Response(content=last_frame_bytes, media_type="image/png")


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(user_id: str = Depends(get_current_user_id)):
    tasks = await task_queue.get_user_tasks(user_id)
    return [_task_to_response(t) for t in tasks]
