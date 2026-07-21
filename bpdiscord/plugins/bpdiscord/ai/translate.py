"""自动翻译模块 — 指定频道内中/英/日三语互译"""
from nonebot import on_message
from nonebot.adapters.discord import Bot, MessageEvent
from nonebot_plugin_alconna import UniMessage
from nonebot.log import logger

from .client import deepseek_client
from ..config import (
    TRANSLATE_CHANNELS, DEEPSEEK_CHAT_MODEL,
    is_blacklisted, is_admin,
)

LANG_EMOJI = {
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
}


def _has_text_content(text: str) -> bool:
    """检查是否包含任何中/英/日文字符"""
    for ch in text:
        cp = ord(ch)
        if 0x3040 <= cp <= 0x309F:   # 平假名
            return True
        if 0x30A0 <= cp <= 0x30FF:   # 片假名
            return True
        if 0x4E00 <= cp <= 0x9FFF:   # CJK 汉字
            return True
        if 0x0041 <= cp <= 0x005A:   # A-Z
            return True
        if 0x0061 <= cp <= 0x007A:   # a-z
            return True
    return False


async def _translate(text: str) -> dict | None:
    """调用 DeepSeek 检测语种并翻译为另外两种语言"""
    prompt = (
        "你是一个翻译助手。请先判断以下文本的语言（只能是 zh / en / ja 之一），"
        "然后将其翻译为另外两种语言。\n"
        "严格按以下格式输出，每行一条，不要任何解释或多余内容：\n"
        "source: <zh|en|ja>\n"
        "<目标语言标识>: <译文>\n"
        "<另一个目标语言标识>: <译文>\n\n"
        f"文本：{text}"
    )

    try:
        response = await deepseek_client.chat.completions.create(
            model=DEEPSEEK_CHAT_MODEL,
            messages=[
                {"role": "system", "content": "你是一个翻译助手，严格按指定格式输出，不要说任何多余的话。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2048,
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        result = {}
        for line in raw.split("\n"):
            line = line.strip()
            if not line:
                continue
            if ":" in line:
                key, _, val = line.partition(":")
                key, val = key.strip(), val.strip()
                if key == "source":
                    result["source"] = val
                elif key in LANG_EMOJI:
                    result[key] = val
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

    # 快速预检：不含任何中/英/日文字符则跳过
    if not _has_text_content(plain_text):
        await translate_handler.skip()
        return

    logger.info(f"翻译频道【{channel_id}】收到消息，启动翻译: {plain_text[:50]}...")

    result = await _translate(plain_text)
    if result and "source" in result:
        source = result["source"]
        source_name = LANG_EMOJI.get(source, source)
        lines = [f"🌐 翻译（{source_name} → 其余语言）"]
        for lang, label in LANG_EMOJI.items():
            if lang != source and lang in result:
                lines.append(f"**{label}**: {result[lang]}")
        if len(lines) > 1:
            await UniMessage("\n".join(lines)).send(reply_message=True)
            logger.info(f"翻译结果: {result}")
    else:
        logger.info("翻译解析失败或为空，跳过发送")
