"""DeepSeek API client for the drawing assistant."""
import os
import httpx
from openai import AsyncOpenAI

# Read timeout is generous for vision+reasoning outputs; connect/pool keep
# retries snappy so the 10s backoff in chat_assistant dominates the wait.
_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)

deepseek_client = AsyncOpenAI(
    api_key=os.getenv("AICHATKEY1"),
    base_url="https://api.deepseek.com",
    http_client=httpx.AsyncClient(trust_env=False, timeout=_HTTP_TIMEOUT),
    timeout=_HTTP_TIMEOUT,
)
