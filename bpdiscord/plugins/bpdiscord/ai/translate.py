"""自动翻译模块 — 指定频道内日↔中互译"""
from nonebot import on_message
from nonebot.adapters.discord import Bot, MessageEvent
from nonebot_plugin_alconna import UniMessage
from nonebot.log import logger

from .client import deepseek_client
from ..config import (
    TRANSLATE_CHANNELS, DEEPSEEK_CHAT_MODEL,
    is_blacklisted, is_admin,
)


def _contains_japanese(text: str) -> bool:
    """简单启发式：含假名即判日文"""
    for ch in text:
        cp = ord(ch)
        if 0x3040 <= cp <= 0x309F:
            return True
        if 0x30A0 <= cp <= 0x30FF:
            return True
    return False


def _contains_chinese(text: str) -> bool:
    for ch in text:
        cp = ord(ch)
        if 0x4E00 <= cp <= 0x9FFF:
            return True
    return False


async def _translate(text: str) -> str | None:
    """调用 DeepSeek 检测语种并翻译"""
    prompt = (
        "你是一个翻译助手。请判断以下文本是日文还是中文："
        "如果是日文，翻译为简体中文；如果是中文，翻译为日文。"
        "只输出翻译结果，不要任何解释或前缀。\n"
        f"文本：{text}"
    )

    try:
        response = await deepseek_client.chat.completions.create(
            model=DEEPSEEK_CHAT_MODEL,
            messages=[
                {"role": "system", "content": "你是一个翻译助手，只输出译文，不要说任何多余的话。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2048,
            temperature=0.3,
        )
        result = response.choices[0].message.content.strip()
        return result if result else None
    except Exception as e:
        logger.error(f"翻译失败: {e}")
        return None


translate_handler = on_message(priority=1, block=False)


@translate_handler.handle()
async def handle_translate(bot: Bot, event: MessageEvent):
    user_id = event.get_user_id()
    channel_id = str(event.channel_id) if hasattr(event, "channel_id") else user_id
    plain_text = event.get_plaintext().strip()

    # 仅处理已启用的频道
    if not TRANSLATE_CHANNELS.get(channel_id, False):
        await translate_handler.skip()
        return

    # 跳过空消息和命令
    if not plain_text or plain_text.startswith("/"):
        await translate_handler.skip()
        return

    # 黑名单 + 管理员豁免
    if is_blacklisted(user_id):
        await translate_handler.skip()
        return

    # 快速预检：不含任何 CJK 字符则跳过
    if not _contains_japanese(plain_text) and not _contains_chinese(plain_text):
        await translate_handler.skip()
        return

    logger.info(f"翻译频道【{channel_id}】收到消息，启动翻译: {plain_text[:50]}...")

    translation = await _translate(plain_text)
    if translation and translation != plain_text:
        await UniMessage(f"🌐 翻译：{translation}").send(reply_message=True)
        logger.info(f"翻译结果: {translation[:100]}...")
    else:
        logger.info("翻译结果与原文相同或为空，跳过发送")
