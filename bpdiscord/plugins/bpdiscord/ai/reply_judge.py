"""自由聊天回复判断模块（含疲劳因子）"""
import time
import math

from nonebot.log import logger
from openai import AsyncOpenAI
import httpx

from .client import ollama_client
from .memory import memory
from .. import config as _cfg
from ..config import (
    OLLAMA_MODEL,
    DEEPSEEK_API_KEY,
    DEEPSEEK_CHAT_MODEL,
    DEEPSEEK_BASE_URL,
    FATIGUE_HALF_LIFE,
    FATIGUE_THRESHOLD_K,
    FATIGUE_STEEPNESS_N,
    FATIGUE_OBSERVATION_WINDOW,
    FATIGUE_FALLBACK_THRESHOLD,
)


def calculate_fatigue_T(group_id: int) -> float:
    """
    计算疲劳衰减因子 T (0.0 ~ 1.0)
    T = 1.0 表示精力充沛，T -> 0.0 表示极度疲劳
    """
    try:
        timestamps = memory.chat_history.get_ai_timestamps(
            group_id=group_id,
            limit=10,
            time_window_seconds=FATIGUE_OBSERVATION_WINDOW,
        )
        if not timestamps:
            return 1.0

        current_time = time.time()
        tau = FATIGUE_HALF_LIFE / 0.6931

        heat = 0.0
        for ts in timestamps:
            delta_t = max(0, current_time - ts)
            if delta_t <= FATIGUE_OBSERVATION_WINDOW:
                heat += math.exp(-delta_t / tau)

        if heat < 0.01:
            return 1.0

        term = (heat / FATIGUE_THRESHOLD_K) ** FATIGUE_STEEPNESS_N
        t_score = 1.0 / (1.0 + term)
        logger.debug(f"[疲劳计算] 群{group_id} | 热度:{heat:.2f} | T值:{t_score:.2f}")
        return t_score
    except Exception as e:
        logger.error(f"计算疲劳因子T失败: {e}")
        return 1.0


async def should_reply_with_ai(
    message: str, group_id: int, nickname: str, user_id: int
) -> bool:
    """
    使用次级 AI 模型判断是否需要回复

    Args:
        message: 用户消息内容
        group_id: 群组ID
        nickname: 用户昵称
        user_id: 用户ID

    Returns:
        True=需要回复, False=不需要
    """
    try:
        T = calculate_fatigue_T(group_id)
        context = memory.get_context(group_id, message, session_type="group")

        history_text = ""
        if context["history"]:
            lines = []
            for msg in context["history"][-10:]:
                if msg.get("role") == "assistant" and msg.get("content") == "未回复":
                    continue
                speaker = "我" if msg.get("role") == "assistant" else msg.get("user_name", msg["user"])
                lines.append(f"[历史消息] {speaker}: {msg['content']}")
            history_text = "\n".join(lines) if lines else "（暂无历史消息）"
        else:
            history_text = "（暂无历史消息）"

        if T > 0.8:
            fatigue_desc = "精力充沛，可以积极参与对话"
        elif T > 0.5:
            fatigue_desc = "状态正常，适度参与"
        elif T > 0.3:
            fatigue_desc = "有些疲劳，只回复重要的消息"
        else:
            fatigue_desc = "非常疲劳，除非必要否则倾向沉默"

        judge_prompt = f"""你是一个智能回复判断助手。请根据以下信息判断美浦波旁（我）是否需要回复这条消息。你只能输出0或1。1代表回复，0代表不回复。
【当前对话信息】
- 用户昵称：{nickname}
- 用户ID：{user_id}
- 群组ID：{group_id}
- 用户消息：{message}
- 疲劳状态（T={T:.2f}）：{fatigue_desc}
【最近群聊历史消息】
{history_text}

【判断标准】
1. 参考疲劳状态决定回复意愿：精力充沛时积极互动，疲劳时只回应直接提问、呼唤或与你强相关的消息
2. 优先回复与你(美浦波旁，简称波旁，或赛马娘同学)相关的消息，如你熟悉的同学：米浴，优秀素质，创世驹，目白阿尔丹等人
3. 对于普通闲聊，根据疲劳状态和消息内容综合判断。可以解答单条消息，但最好不要插入正在进行的话题
4. 如果历史消息显示话题与你（美浦波旁）相关，即使疲劳也应考虑回复
5. 若知识库显示检索到相关消息，则高概率回复。

请只回复一个数字：1（需要回复）或0（不需要回复）"""

        if _cfg.DEBUG_MODE:
            logger.info("=" * 60)
            logger.info("🔍 [DEBUG] Ollama 回复判断最终输入")
            logger.info(judge_prompt)
            logger.info("=" * 60)

        response = await ollama_client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": "你是一个智能回复判断助手，只输出0或1。"},
                {"role": "user", "content": judge_prompt},
            ],
            max_tokens=1024,
            temperature=0.1,
        )

        result = response.choices[0].message.content.strip()
        should_reply = result == "1"
        logger.info(f"AI判断结果：{result} (消息: {message[:20]}...), T值: {T:.2f}")
        return should_reply

    except Exception as e:
        logger.error(f"AI判断是否回复时出错: {e}")
        T = calculate_fatigue_T(group_id)
        return T > FATIGUE_FALLBACK_THRESHOLD
