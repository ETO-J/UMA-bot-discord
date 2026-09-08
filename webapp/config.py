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
LORA_VIDEO_DIRS = ["gif"]
# Workflows that run on the Anima model family should load anima LoRAs.
# Kept as an explicit set because the diff workflow name ("discord_差分") does
# not contain the literal "anima" substring.
ANIMA_WORKFLOWS = {
    "discord_anima",
    "discord_anima_v2",
    "discord_anima_new",
    "discord_anima_fast",
    "discord_anima_高清",
    "discord_差分",
}

IMAGE_SAVE_PATH = Path(os.getenv("IMAGE_SAVE_PATH", r"D:\civitai\线上绘图"))
IMAGE_SAVE_PATH.mkdir(parents=True, exist_ok=True)

DB_DIR = DATA_DIR / "comfyuisetting"
DB_PATH = DB_DIR / "user_settings.db"
TASK_IMAGE_DIR = DB_DIR / "task_images"
TASK_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
WORKFLOW_DIR = COMFYUI_DIR

# --- Asset library / media storage ---
ASSET_LIBRARY_ROOT = Path(os.getenv("ASSET_LIBRARY_ROOT", r"D:\civitai\数字资产库"))
ASSET_DB_PATH = DATA_DIR / "assets" / "assets.db"
ASSET_THUMB_DIR = ASSET_LIBRARY_ROOT / "thumbs"
ASSET_BLOB_DIR = ASSET_LIBRARY_ROOT / "blobs"

# Direct Ref2VA upload cache (not counted as asset-library storage).
VIDEO_UPLOAD_DIR = DATA_DIR / "video_uploads"
VIDEO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Per-user asset-library quotas are derived from limit_count.
# limit_count < 1000 -> disabled; 1000..39999 -> 100 MB; >= 40000 -> 1 GB.
ASSET_LIBRARY_DISABLED_LIMIT = 1000
ASSET_LIBRARY_MEDIUM_LIMIT = 1000
ASSET_LIBRARY_MEDIUM_BYTES = 100 * 1024 * 1024
ASSET_LIBRARY_LARGE_LIMIT = 40000
ASSET_LIBRARY_LARGE_BYTES = 1024 * 1024 * 1024
# Single upload caps; full quota still governs total storage.
ASSET_MAX_IMAGE_BYTES = 30 * 1024 * 1024
ASSET_MAX_VIDEO_BYTES = 200 * 1024 * 1024
ASSET_MAX_AUDIO_BYTES = 50 * 1024 * 1024

# Ref2VA generation pricing.
REF2VA_COST_MULTIPLIER = 1.5

VIDEO_RESOLUTIONS = {
    "480p": {"portrait": (480, 640), "square": (512, 512), "landscape": (640, 480)},
    # MiniMax H3's video latent is width/16 x height/16, and patchify_video
    # needs both to be even, so every dimension must be a multiple of 32.
    # True 720 (720//16 = 45, odd) makes patchify throw, so use a 1280x736
    # canvas instead (both are multiples of 32; latent 80x46 is even).
    "720p": {"portrait": (736, 1280), "square": (736, 736), "landscape": (1280, 736)},
}
# Ref2VA/FL2VA canvas uses input aspect ratio + megapixel coefficient:
# 480p -> 0.4 MP, 720p -> 0.8 MP.
VIDEO_MEGAPIXELS = {"480p": 0.4, "720p": 0.8}
# Manual Ref2VA aspect ratios matching ComfyUI ResolutionSelector.
VIDEO_ASPECT_RATIOS = {
    "1:1": (1, 1),
    "2:3": (2, 3),
    "3:2": (3, 2),
    "4:3": (4, 3),
    "3:4": (3, 4),
    "16:9": (16, 9),
    "9:16": (9, 16),
}
VIDEO_ASPECT_RATIO_LABELS = {
    "1:1": "1:1 (Square)",
    "2:3": "2:3 (Portrait Photo)",
    "3:2": "3:2 (Photo)",
    "4:3": "4:3 (Standard)",
    "3:4": "3:4 (Portrait Standard)",
    "16:9": "16:9 (Widescreen)",
    "9:16": "9:16 (Portrait Widescreen)",
}
# Per-second quota for 1-10s video.  720p is 4x the 480p rate; durations
# 11-15s double the per-second rate (e.g. 480p 11-15s = 100/s, 720p =
# 200/s, 720p 11-15s = 400/s).
VIDEO_PER_SECOND_COST = {"480p": 50, "720p": 200}
VIDEO_LONG_DURATION_START = 11
VIDEO_LONG_DURATION_MULT = 2
VIDEO_FPS = 24

# === AI 绘画助手 ===
AISSETTING_DIR = DATA_DIR / "aisetting"
ARTIST_SKILLS_DIR = AISSETTING_DIR / "skills"
ARTIST_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
DEEPSEEK_CHAT_MODEL = "deepseek-v4-flash-vision-exp"
CHAT_MAX_ROUNDS = 20
CHAT_MAX_TOKENS = 4096
CHAT_TEMPERATURE = 0.8
# Dynamic input-token billing (mirrors DeepSeek vision image rules).
# Any single chat message is capped at CHAT_MAX_COST quota points.
CHAT_MAX_COST = 100
# Max reference images per chat message.
CHAT_MAX_IMAGES = 5
# DeepSeek vision: an image is converted to input tokens by its (post-resize)
# dimensions and is capped at 384 tokens/image.
CHAT_IMAGE_MAX_TOKEN = 384
# Pixel->token scale so a ~800x800 equivalent image maps to roughly 384 tokens:
# 800*800 / 1667 ~= 384. Lower-res images cost proportionally fewer tokens.
CHAT_IMAGE_TOKEN_PX = 1667
# DeepSeek call retry policy: up to 3 attempts, 10s between retries.
DEEPSEEK_MAX_RETRIES = 3
DEEPSEEK_RETRY_DELAY_SECONDS = 10

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/callback")
DISCORD_PROXY = os.getenv("DISCORD_PROXY", "")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "1440336869144395868")

# --- Public asset library -> Discord channel sync ---
# The bot token (DiscordToken) is shared with the NoneBot2 process, so the
# webapp posts/deletes messages using the same bot account.
DISCORD_BOT_TOKEN = os.getenv("DiscordToken", "")
DISCORD_API_BASE = os.getenv("DISCORD_API_BASE", "https://discord.com/api/v10")
# Guild + channel that receives publish announcements; empty string disables.
ASSET_PUBLISH_GUILD_ID = os.getenv("ASSET_PUBLISH_GUILD_ID", "1525712372306677991")
ASSET_PUBLISH_CHANNEL_ID = os.getenv("ASSET_PUBLISH_CHANNEL_ID", "1546739758871609386")
# Max attachment size for the feed message; larger media degrades to
# thumbnail-only (or text-only) messages instead of failing.
ASSET_DISCORD_MAX_UPLOAD_MB = int(os.getenv("ASSET_DISCORD_MAX_UPLOAD_MB", "10"))

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
        "hd_enabled": True,
        "hd_start_id": 2000,
        "hd_scale": 1.5,
        "hd_upscale_method": "nearest-exact",
        "hd_steps": 15,
        "hd_cfg": 5.0,
        "hd_denoise": 0.75,
    },
    "discord_anima_fast": {
        "model_source": ["75", 0],
        "clip_source": ["75", 1],
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
        # The workflow is text-to-image driven through the fixed turbo LoRA
        # (node 75). User-selectable anima LoRAs are stacked after it (model
        # only), so the turbo accelerator + its CLIP half stay untouched.
        "hd_enabled": True,
        # Unlike anima_v2/diff, this workflow ships its own upscale+refine
        # chain (nodes 82/83/85/88) wired into the SaveImage node. Let the HD
        # toggle switch it on/off instead of injecting another chain.
        "builtin_hd": True,
        "builtin_save_node": "86",
        "builtin_base_decode_node": "84",
        "hd_scale": 1.5,
        "hd_upscale_method": "nearest-exact",
        "hd_steps": 8,
        "hd_cfg": 1.0,
        "hd_denoise": 0.75,
    },
    "discord_差分": {
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
        "hd_enabled": True,
        "hd_start_id": 2000,
        "hd_scale": 1.5,
        "hd_upscale_method": "nearest-exact",
        "hd_steps": 15,
        "hd_cfg": 5.0,
        "hd_denoise": 0.75,
        # img2img (diff) nodes: uploaded image is loaded here and VAE-encoded
        # into the same latent the KSampler consumes.
        "load_image_node_id": "78",
        "vae_encode_node_id": "79",
        "is_anima": True,
    },
    "webui_video": {
        "supports_lora": True,
        "workflow_file": "webui-minimaxh3-fl2va",
        "video_node_id": "132",
        "start_image_node_id": "114",
        "end_image_node_id": "140",
        "seed_node_id": "130",
        "prompt_field": "prompt",
        "lora_start_id": 4000,
        "lora_type": "LoraLoader",
        # Fixed pipeline LoRA (16-step CFG-distill), always applied; it is
        # excluded from the user-selectable list but stays as the chain tail.
        "base_lora_node_id": "139",
        "fixed_lora_names": [
            "lightx2v_T2V_14B_cfg_step_distill_v2_lora_rank64_bf16_.safetensors"
        ],
        # Injection anchors: user LoRAs are chained between these sources and
        # the fixed base LoRA (node 139).
        "model_source": ["137", 0],
        "clip_source": ["129", 0],
    },
    "webui_video_ref": {
        # Ref2VA uses the provided workflow with a fixed accelerator LoRA and
        # fixed 8-step schedule; dynamic user LoRAs are intentionally disabled.
        "supports_lora": False,
        "workflow_file": "webui-minimax-h3-r2v",
        "video_node_id": "136",
        "prompt_node_id": "138",
        "duration_node_id": "132",
        "seed_node_id": "129",
        "resolution_selector_node_id": "115",
        "steps_node_id": "124",
        "accelerator_lora_node_id": "149",
        "ref_image_size": "match",
        "last_frame_save_node_id": "148",
        "last_frame_parent_node_id": "147",
        "last_frame_components_node_id": "146",
    },
    "discord_flux2_9b_edit": {
        "supports_lora": False,
        "supports_reference": True,
        "pos_node_id": "75:74",
        "neg_node_id": "75:67",
        "guider_node_id": "75:63",
        "sampler_advanced_node_id": "75:64",
        "scheduler_node_id": "75:62",
        "noise_node_id": "75:73",
        "sampler_select_node_id": "75:61",
        "latent_node_id": "75:66",
        "decode_node_id": "75:65",
        "save_node_id": "9",
        "load_image_node_id": "76",
        "scale_image_node_id": "75:80",
        "size_node_id": "75:100",
        "vae_encode_node_id": "75:123",
        "reference_pos_node_id": "75:124",
        "reference_neg_node_id": "75:122",
        "vae_source": ["75:72", 0],
        "ref_chain_start_id": 3000,
        "flux2_edit_cost": 20,
        # BiRefNet cutout (merged from comfyui/user/default/workflows/flux2_自动扣图.json)
        "cutout_node_id": "2100",
        "cutout_model": "BiRefNet-general",
        "cutout_edit_save_prefix": "Flux2-Klein-9b_cutout",
        "cutout_direct_save_prefix": "Flux2_cutout",
        "flux2_edit_cutout_cost": 20,
        "flux2_cutout_cost": 1,
    },
}
