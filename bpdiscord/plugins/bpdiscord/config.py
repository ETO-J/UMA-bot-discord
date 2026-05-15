"""统一配置中心 - 所有配置项集中管理（Discord 适配版）"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# === 项目路径 ===
PROJECT_ROOT = Path(__file__).absolute().parent.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
IMAGES_DIR = PROJECT_ROOT / "images"
PIXIV_IMAGES_DIR = PROJECT_ROOT / "pixiv_images"
COMFYUI_DIR = PROJECT_ROOT / "comfyui"
AISSETTING_DIR = DATA_DIR / "aisetting"
ERROR_IMAGES_DIR = IMAGES_DIR / "errors"

for d in [DATA_DIR, IMAGES_DIR, PIXIV_IMAGES_DIR, ERROR_IMAGES_DIR, AISSETTING_DIR, COMFYUI_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# === 管理员（Discord 字符串 ID）===
ADMIN_IDS: list[str] = ["1440336869144395868"]

def is_admin(user_id: str) -> bool:
    return user_id in ADMIN_IDS

# === 用户黑名单（这些用户的消息仍存入数据库，但不会触发任何指令或自由聊天）===
USER_BLACKLIST: list[str] = [
"1459193006069514243",
"1268587693630160906",
"1268247382823403611",

                             ]

def is_blacklisted(user_id: str) -> bool:
    """管理员不受黑名单限制"""
    return (not is_admin(user_id)) and (user_id in USER_BLACKLIST)

# === 调试模式 ===
DEBUG_MODE: bool = True

# === AI 模型配置 ===
DEEPSEEK_API_KEY = os.getenv("AICHATKEY1", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_CHAT_MODEL = "deepseek-v4-flash"
DEEPSEEK_REASONER_MODEL = "deepseek-v4-pro"

OLLAMA_HOST = "http://127.0.0.1:11434/v1"
OLLAMA_MODEL = "glm-4.7-flash:latest"

DOUBAO_API_KEY = os.getenv("VIRSIONKEY1", "")
DOUBAO_VISION_MODEL = "doubao-seed-1-6-vision-250815"

# === 搜索 ===
BING_API_KEY = os.getenv("BINGSEARCHKEY1", "")
BING_SEARCH_URL = "https://api.bocha.cn/v1/web-search"

# === Pixiv ===
PIXIV_REFRESH_TOKEN = os.getenv("PIXIV_REFRESH_TOKEN")

# === SauceNAO ===
SAUCENAO_API_KEY = os.getenv("SAUCENAO_API_KEY")
SAUCENAO_MIN_SIMILARITY = 60

# === Discord 权限配置 ===
# 自由聊天 allowlist — 控制机器人自主回复的服务器/频道
ALLOWED_GUILDS: dict = {
    "1452668545040126056": {  # bot测试
        "enabled": True,
        "channels": {
            "1452668545895895207": True,
        },
    },
    "1441768620777799690": {  # sek
        "enabled": False,
        "channels": {
            "1441804588662653080": True,
            "1464639865068064957": True,
        },
    },
    "1491483530893725856": {  # 橡皮擦
        "enabled": True,
        "channels": {
            "1441804588662653080": True,
            "1464639865068064957": True,
            "1499077054589698149": False,
            "1492075545108680734": False,
            "1492075008195825825": False,
            "1492075329714524160": False,
            "1500157414325096559": False,
            "1492076915182403594": False,
            "1492076766842458183": False,
        },
    },
}

# censor allowlist — 控制垃圾消息扫描的服务器/频道（独立于自由聊天）
ALLOWED_GUILDS_CENSOR: dict = {
    "1452668545040126056": {  # bot测试
        "enabled": True,
        "channels": {
            "1452668545895895207": True,
            "1487642657114161253": True,
            "1487642691872358420": True,
        },
    },
    "1441768620777799690": {  # sek
        "enabled": True,
        "channels": {
            "1441804588662653080": True,
            "1464639865068064957": True,
            "1443636121463427072": True,
            "1443633950990929951": True,
            "1464990711014363227": True,
            "1465016246088237188": True,
            "1477719857654009866": True,
        },
    },
    "1491483530893725856": {  # 橡皮擦
        "enabled": True,
        "channels": {
            "1492064164263362560": True,
            "1492065926730743939": True,
            "1492066093311856752": True,
            "1492075545108680734": True,
            "1492075008195825825": True,
            "1492075329714524160": True,
            "1500157414325096559": True,
            "1499077054589698149": True,
        },
    },
}

PRIVATE_CHAT_ENABLED: bool = True

# 垃圾检测：管理员是否跳过频道限制
CENSOR_ADMIN_BYPASS: bool = False


def is_channel_allowed(guild_id: str, channel_id: str) -> bool:
    """检查频道是否允许自由聊天"""
    if guild_id not in ALLOWED_GUILDS:
        return False
    gcfg = ALLOWED_GUILDS[guild_id]
    if not gcfg.get("enabled", False):
        return False
    channels = gcfg.get("channels", {})
    if not channels:
        return True
    return channels.get(channel_id, False)


def is_channel_allowed_censor(guild_id: str, channel_id: str) -> bool:
    """检查频道是否允许垃圾检测"""
    if guild_id not in ALLOWED_GUILDS_CENSOR:
        return False
    gcfg = ALLOWED_GUILDS_CENSOR[guild_id]
    if not gcfg.get("enabled", False):
        return False
    channels = gcfg.get("channels", {})
    if not channels:
        return True
    return channels.get(channel_id, False)


# === 机器人标识 ===
BOT_DISPLAY_NAME = "美浦波旁"

# === 记忆系统 ===
CHAT_DB_PATH = DATA_DIR / "chat_history.db"
KNOWLEDGE_DB_PATH = DATA_DIR / "knowledge_db"
MODEL_CACHE_PATH = DATA_DIR / "model_cache"
MODEL_CACHE_PATH.mkdir(parents=True, exist_ok=True)
EMBEDDING_MODEL_NAME = "GanymedeNil/text2vec-base-chinese"

# === 疲劳因子 ===
FATIGUE_HALF_LIFE = 240
FATIGUE_THRESHOLD_K = 3.0
FATIGUE_STEEPNESS_N = 4.0
FATIGUE_OBSERVATION_WINDOW = 900
FATIGUE_FALLBACK_THRESHOLD = 0.5

# === 定时消息 ===
SCHEDULED_MESSAGE_GROUPS: list[int] = []
SCHEDULED_GOOD_MORNING_HOUR = 7
SCHEDULED_GOOD_MORNING_MINUTE = 30
SCHEDULED_GOOD_NIGHT_HOUR = 23
SCHEDULED_GOOD_NIGHT_MINUTE = 0

# === 对话参数 ===
CHAT_HISTORY_LIMIT = 15
KNOWLEDGE_SEARCH_K = 3
KNOWLEDGE_SCORE_THRESHOLD = 0.3
CHAT_MAX_TOKENS = 8192
CHAT_TEMPERATURE = 1.0

# === ComfyUI ===
COMFYUI_DEFAULT_RESOLUTIONS = {
    "1": (832, 1216),
    "2": (1024, 1024),
    "3": (1216, 832),
}

# === 国内 HuggingFace 镜像 ===
HF_MIRRORS = [
    "https://hf-mirror.com",
    "https://hf-mirror.cos.accelerate.myqcloud.com",
    "https://hub.yzuu.cf",
]
