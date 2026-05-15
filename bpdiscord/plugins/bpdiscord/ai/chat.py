"""核心对话逻辑 - 上下文构建 + AI 调用"""
from datetime import datetime

from nonebot.log import logger

from .client import deepseek_client
from .memory import memory
from .persona import persona_manager
from .. import config as _cfg
from ..config import (
    DEEPSEEK_REASONER_MODEL,
    CHAT_MAX_TOKENS,
    CHAT_TEMPERATURE,
    ADMIN_IDS,
)


def build_context_prompt(session_id: int, original_prompt: str, session_type: str = "group", user_name: str = "") -> str:
    """构建包含记忆上下文的 prompt"""
    context = memory.get_context(session_id, original_prompt, session_type)
    current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")

    history_lines = []
    for msg in context["history"]:
        if msg.get("role") == "assistant" and msg.get("content") == "未回复":
            continue
        speaker = "我" if msg.get("role") == "assistant" else msg.get("user_name", msg["user"])
        history_lines.append(f"[历史消息] {speaker}: {msg['content']}")
    history_context = "\n".join(history_lines) if history_lines else ""

    knowledge_context = (
        f"[相关知识]\n当前时间：{current_time}\n{context['knowledge']}"
        if context["knowledge"]
        else f"[相关知识]\n当前时间：{current_time}"
    )

    current_speaker = user_name if user_name else "用户"
    return f"""
{knowledge_context}

{history_context}
当前对话：
{current_speaker}：{original_prompt}
你："""


async def chat_with_ai(
    prompt: str,
    session_id: int,
    user_id: int,
    session_type: str = "group",
    model: str = DEEPSEEK_REASONER_MODEL,
    include_search_result: str = "",
    user_name: str = "",
) -> str:
    full_prompt = build_context_prompt(session_id, prompt, session_type, user_name)
    if include_search_result:
        full_prompt += f"\n[网络搜索结果]\n{include_search_result}"

    logger.info(f"AI Chat prompt: {full_prompt[:200]}...")

    messages = [
        {"role": "system", "content": persona_manager.get_current_prompt()},
        {"role": "user", "content": full_prompt},
    ]

    if _cfg.DEBUG_MODE:
        logger.info("=" * 60)
        logger.info("🔍 [DEBUG] DeepSeek API 最终输入")
        for i, msg in enumerate(messages):
            logger.info(f"--- message[{i}] role={msg['role']} ---")
            logger.info(msg["content"])
        logger.info("=" * 60)
        logger.info(messages)

    try:
        response = await deepseek_client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=CHAT_MAX_TOKENS,
            temperature=CHAT_TEMPERATURE,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"请求出错：{e}"


def adapt_response_for_user(response: str, user_id: str) -> str:
    """根据用户ID适配回复中的称呼（Discord Master ID）"""
    if user_id == ADMIN_IDS[0]:
        response = response.replace("Master", "教练").replace("教练", "Master")
    return response
