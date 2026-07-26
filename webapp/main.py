import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from routers import draw, settings, lora, quota, auth
from services.task_queue import task_queue
from services.online_tracker import cleanup_loop as online_cleanup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await task_queue.load_persisted_tasks()
    async def cleanup_loop():
        while True:
            await asyncio.sleep(300)
            await task_queue.cleanup()
    cleanup_task = asyncio.create_task(cleanup_loop())
    online_cleanup_task = asyncio.create_task(online_cleanup())
    logger.info("WebUI started")
    yield
    cleanup_task.cancel()
    online_cleanup_task.cancel()


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

app.include_router(auth.router, prefix="/api")
app.include_router(draw.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(lora.router, prefix="/api")
app.include_router(quota.router, prefix="/api")

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
