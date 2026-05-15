"""统一 AI 客户端"""
import httpx
from openai import AsyncOpenAI

from ..config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, OLLAMA_HOST

# DeepSeek 客户端（主力对话）
deepseek_client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
    http_client=httpx.AsyncClient(trust_env=False),
)

# Ollama 本地客户端（辅助判断）
ollama_client = AsyncOpenAI(
    api_key="ollama",
    base_url=OLLAMA_HOST,
    http_client=httpx.AsyncClient(trust_env=False),
)
