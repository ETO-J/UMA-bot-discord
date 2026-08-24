"""DeepSeek API client for the drawing assistant."""
import os
import httpx
from openai import AsyncOpenAI

deepseek_client = AsyncOpenAI(
    api_key=os.getenv("AICHATKEY1"),
    base_url="https://api.deepseek.com",
    http_client=httpx.AsyncClient(trust_env=False),
)
