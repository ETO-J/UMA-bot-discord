import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routers import assets, draw, settings, lora, quota, auth, chat
from services.task_queue import task_queue
from services.online_tracker import cleanup_loop as online_cleanup
from services.generator import sweep_leftover_outputs
from services.media_store import temp_media_store
from services.comfyui_watchdog import start_comfyui_watchdog, get_status
from services.asset_library import AssetLibraryUnavailable

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await task_queue.load_persisted_tasks()
    await asyncio.to_thread(temp_media_store.cleanup_old)
    # Self-heal: move leftover bot/webui images left in the ComfyUI output dir
    # (e.g. after a transient WinError 32). Only bot/webui prefixes are matched,
    # so manually generated local ComfyUI outputs are never touched.
    startup_sweep_task = asyncio.create_task(sweep_leftover_outputs())

    async def cleanup_loop():
        while True:
            await asyncio.sleep(300)
            await task_queue.cleanup()
            await sweep_leftover_outputs()
            await asyncio.to_thread(temp_media_store.cleanup_old)
    cleanup_task = asyncio.create_task(cleanup_loop())
    online_cleanup_task = asyncio.create_task(online_cleanup())
    # ComfyUI 进程守护：随 webui 启动，负责 ComfyUI 崩溃时自动拉起
    comfyui_watchdog_task = asyncio.create_task(start_comfyui_watchdog())
    logger.info("WebUI started")
    yield
    startup_sweep_task.cancel()
    cleanup_task.cancel()
    online_cleanup_task.cancel()
    comfyui_watchdog_task.cancel()


app = FastAPI(title="ComfyUI WebUI", lifespan=lifespan)


@app.middleware("http")
async def no_cache_html(request, call_next):
    """Force revalidation of HTML pages so versioned asset URLs (e.g.
    /js/app.js?v=15) always reach the browser after a deploy.
    JS/CSS stay long-cached via nginx 'immutable' + ?v= bumping."""
    response = await call_next(request)
    if "text/html" in response.headers.get("content-type", ""):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*\.trycloudflare\.com|https?://localhost:\d+|https?://127\.0\.0\.1:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AssetLibraryUnavailable)
async def asset_library_unavailable_handler(request, exc: AssetLibraryUnavailable):
    return JSONResponse(status_code=503, content={"detail": str(exc)})

app.include_router(auth.router, prefix="/api")
app.include_router(draw.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(lora.router, prefix="/api")
app.include_router(quota.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(assets.router, prefix="/api")


@app.get("/api/comfyui-watchdog")
async def comfyui_watchdog_status():
    """ComfyUI 守护状态（供运维/监控查看）。"""
    return get_status()

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
