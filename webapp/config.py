import os
from pathlib import Path
from dotenv import load_dotenv

THIS_DIR = Path(__file__).absolute().parent
PROJECT_ROOT = THIS_DIR.parent

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

COMFYUI_DIR = PROJECT_ROOT / "comfyui"
DATA_DIR = PROJECT_ROOT / "data"

COMFYUI_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8000")
COMFYUI_OUTPUT_DIR = Path(os.getenv("COMFYUI_OUTPUT_DIR", r"C:\Users\Administrator\Documents\ComfyUI\output"))
COMFYUI_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LORA_BASE_PATH = Path(os.getenv("LORA_BASE_PATH", r"C:\Users\Administrator\Documents\ComfyUI\models\loras"))
LORA_DIRS = ["char", "pose", "style"]
LORA_ANIMA_DIRS = ["char_anima", "pose_anima", "style_anima"]

IMAGE_SAVE_PATH = Path(os.getenv("IMAGE_SAVE_PATH", r"D:\civitai\线上绘图"))
IMAGE_SAVE_PATH.mkdir(parents=True, exist_ok=True)

DB_DIR = DATA_DIR / "comfyuisetting"
DB_PATH = DB_DIR / "user_settings.db"
TASK_IMAGE_DIR = DB_DIR / "task_images"
TASK_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
WORKFLOW_DIR = COMFYUI_DIR

VIDEO_RESOLUTIONS = {
    "480p": {"portrait": (480, 640), "square": (512, 512), "landscape": (640, 480)},
    "720p": {"portrait": (720, 1280), "square": (768, 768), "landscape": (1280, 720)},
}
VIDEO_BASE_COST = {"480p": 250, "720p": 500}
VIDEO_FPS = 16

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/callback")
DISCORD_PROXY = os.getenv("DISCORD_PROXY", "")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "1440336869144395868")

COMFYUI_DEFAULT_RESOLUTIONS = {
    "1": (832, 1216),
    "2": (1024, 1024),
    "3": (1216, 832),
}

WORKFLOW_CONFIGS = {
    "discord": {
        "model_source": ["13", 0],
        "clip_source": ["22", 0],
        "pos_node_id": "29",
        "neg_node_id": "7",
        "supports_lora": True,
        "lora_start_id": 1000,
    },
    "discord_高清": {
        "model_source": ["13", 0],
        "clip_source": ["22", 0],
        "pos_node_id": "29",
        "neg_node_id": "7",
        "supports_lora": True,
        "lora_start_id": 1000,
    },
    "multidraw": {
        "model_source": ["13", 0],
        "clip_source": ["22", 0],
        "pos_node_id": "29",
        "neg_node_id": "7",
        "supports_lora": True,
        "lora_start_id": 1000,
    },
    "discord_anima": {
        "model_source": ["64", 0],
        "clip_source": ["66", 0],
        "pos_node_id": "65",
        "neg_node_id": "68",
        "supports_lora": True,
        "lora_start_id": 1000,
        "lora_type": "LoraLoaderModelOnly",
    },
    "discord_anima_v2": {
        "model_source": ["64", 0],
        "clip_source": ["66", 0],
        "pos_node_id": None,
        "neg_node_id": "68",
        "supports_lora": True,
        "lora_start_id": 1000,
        "lora_type": "LoraLoaderModelOnly",
        "bridging_model_node": "73",
        "bridging_positive_node": "73",
        "prompt_pack_node": "72",
        "prompt_field": "base_prompt",
        "prompt_class_type": "AnimaArtistPack",
    },
    "webui_video": {
        "clip_source": ["84", 0],
        "pos_node_id": "93",
        "neg_node_id": "89",
        "supports_lora": False,
        "video_node_id": "134",
        "start_image_node_id": "97",
        "end_image_node_id": "135",
        "lora_high_node_id": "101",
        "lora_low_node_id": "102",
        "high_chain_source": ["117", 0],
        "low_chain_source": ["118", 0],
        "high_chain_target": "104",
        "low_chain_target": "103",
        "ksampler_ids": ["86", "85"],
        "video_node_class_first": "WanImageToVideo",
        "video_node_class_both": "WanFirstLastFrameToVideo",
    },
}
