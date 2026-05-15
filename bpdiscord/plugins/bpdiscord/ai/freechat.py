"""统一聊天处理器 - 合并命令式对话与自由聊天（Discord 适配版）"""
import os
import random

from nonebot import on_message
from nonebot.adapters.discord import Bot, MessageEvent
from nonebot_plugin_alconna import UniMessage
from nonebot.log import logger

from .chat import chat_with_ai, adapt_response_for_user
from .memory import memory
from .search_judge import needs_search_async, search_web
from .reply_judge import should_reply_with_ai
from .vision import analyze_image, build_vision_prompt
from ..config import (
    ERROR_IMAGES_DIR, is_admin, is_channel_allowed, is_blacklisted,
    BOT_DISPLAY_NAME, PRIVATE_CHAT_ENABLED,
)
from ..utils.user_info import get_user_info

# 已知命令前缀（来自 master_control / admin / features），自由聊天跳过
KNOWN_COMMAND_PREFIXES = [
    "波旁", "/波旁","今日担当",
    "help", "/help",
    "draw", "/draw",
    "multidraw", "/multidraw",
    "高清",
    "切换分辨率", "切换负面", "重置负面","切换工作流",
    "lora列表", "添加lora", "删除lora", "重置lora",
    "修改限额",
    "partone", "parttwo",
    "人设列表", "/人设列表",
    "切换人设", "/切换人设",
    "学习", "/学习", "批量学习", "/批量学习",
    "知识列表", "/知识列表", "删除知识", "/删除知识",
    "撤回", "ban",
    "debug", "/debug", "重启", "/重启", "清除", "/清除",
    "广播", "/广播",
    "开启模拟聊天", "/开启模拟聊天", "关闭模拟聊天", "/关闭模拟聊天",
]


async def send_error_image(bot: Bot, event: MessageEvent):
    files = [f for f in os.listdir(ERROR_IMAGES_DIR) if os.path.isfile(os.path.join(ERROR_IMAGES_DIR, f))]
    if files:
        selected = random.choice(files)
        file_path = os.path.join(ERROR_IMAGES_DIR, selected)
        await UniMessage.image(raw=open(file_path, "rb").read()).send(reply_message=True)
    else:
        await UniMessage("服务暂时不可用，请稍后再试~").send(reply_message=True)


async def _do_chat_reply(bot: Bot, event: MessageEvent, prompt: str, session_id: int, user_id: str, session_type: str, user_name: str = ""):
    search_result = ""
    needs, search_query, search_reason = await needs_search_async(prompt)
    if needs:
        await UniMessage("正在搜索相关信息...").send(reply_message=True)
        logger.info(f"搜索: {search_query}, 理由: {search_reason}")
        search_result = search_web(search_query)
        logger.info(f"搜索结果: {search_result}")

    gpt_reply = await chat_with_ai(
        prompt=prompt, session_id=session_id, user_id=user_id,
        session_type=session_type, include_search_result=search_result,
        user_name=user_name,
    )

    memory.save_context(session_id, 0, gpt_reply, session_type, role='assistant', user_name=BOT_DISPLAY_NAME)

    if gpt_reply.startswith(("抱歉", "请求出错")):
        await send_error_image(bot, event)
    else:
        gpt_reply = adapt_response_for_user(gpt_reply, user_id)
        await UniMessage(gpt_reply).send(reply_message=True)


# ========== 统一聊天入口 ==========
chat_handler = on_message(priority=4, block=False)


@chat_handler.handle()
async def handle_chat(bot: Bot, event: MessageEvent):
    user_id = event.get_user_id()
    channel_id = str(event.channel_id) if hasattr(event, "channel_id") else user_id
    guild_id = str(event.guild_id) if hasattr(event, "guild_id") and event.guild_id else None

    try:
        nickname = event.author.global_name or event.author.name or '未知用户'
    except Exception:
        nickname = '未知用户'

    plain_text = event.get_plaintext().strip()
    logger.info(f"收到频道【{channel_id}】用户【{nickname}】(ID:{user_id}) 的消息: {plain_text}")

    is_private = guild_id is None
    session_id = int(channel_id) if guild_id else user_id
    session_type = 'group' if guild_id else 'private'

    # ====== 黑名单检查：消息入库但不响应 ======
    if is_blacklisted(user_id):
        logger.info(f"黑名单用户 {user_id} 的消息，仅入库不响应")
        if plain_text:
            full_prompt = plain_text + f"\n[以下是当前对话用户昵称与ID：]\n{nickname, user_id}"
            memory.save_context(session_id, user_id, full_prompt, session_type, user_name=nickname)
        return

    # ====== 分支1: 波旁 命令 — 强制 AI 对话 ======
    if plain_text.startswith(("波旁", "/波旁")):
        prefix_len = 3 if plain_text.startswith("/") else 2
        prompt = plain_text[prefix_len:].strip()
        if not prompt:
            await UniMessage("请输入你想说的话，例如：波旁 今天的天气怎么样？").send(reply_message=True)
            return

        logger.info(f"波旁命令 {session_type}用户{user_id}输入：{prompt}")
        memory.save_context(session_id, user_id, prompt, session_type, user_name=nickname)
        await _do_chat_reply(bot, event, prompt, session_id, user_id, session_type, user_name=nickname)
        return

    # ====== 跳过其他命令 ======
    first_word = plain_text.split()[0] if plain_text else ""
    for prefix in KNOWN_COMMAND_PREFIXES:
        if plain_text.startswith(prefix) or first_word == prefix:
            logger.info(f"命令消息 {plain_text}，跳过自由聊天处理")
            return

    # ====== 权限检查 ======
    admin_bypass = is_admin(user_id)

    if is_private:
        if not PRIVATE_CHAT_ENABLED:
            logger.info(f"私聊功能已全局禁用，消息仍存入数据库: user {user_id}")
            full_prompt = plain_text + f"\n[以下是当前对话用户昵称与ID：]\n{nickname, user_id}"
            memory.save_context(session_id, user_id, full_prompt, session_type, user_name=nickname)
            return
    else:
        if not is_channel_allowed(guild_id, channel_id):
            logger.info(f"群聊 {guild_id} 频道 {channel_id} 未在允许列表或已禁用，消息仍存入数据库")
            full_prompt = plain_text + f"\n[以下是当前对话用户昵称与ID：]\n{nickname, user_id}"
            memory.save_context(session_id, user_id, full_prompt, session_type, user_name=nickname)
            return

    # ====== 分支2: 自由聊天 ======
    # 检查是否包含图片
    has_image = False
    image_url = None
    if hasattr(event, 'message') and hasattr(event.message, 'attachments'):
        for attachment in event.message.attachments:
            if attachment.content_type and attachment.content_type.startswith('image/'):
                has_image = True
                image_url = attachment.url
                break

    # 检查是否 @了机器人
    special_flag = 0
    if hasattr(event, 'message') and hasattr(event.message, 'mentions'):
        if hasattr(bot, 'self_id'):
            special_flag = 1 if any(m.id == bot.self_id for m in event.message.mentions) else 0

    # --- 图片消息处理 ---
    if has_image and image_url:
        logger.info("检测到图片消息，启动视觉理解")
        image_description = analyze_image(image_url)
        full_prompt = build_vision_prompt(image_description, plain_text)
        full_prompt += f"\n[以下是当前对话用户昵称与ID：]\n{nickname, user_id}"

        memory.save_context(session_id, user_id, full_prompt, session_type, user_name=nickname)

        if special_flag == 1:
            logger.info("检测到@消息，强制回复")
            await _do_chat_reply(bot, event, full_prompt, session_id, user_id, session_type, user_name=nickname)
        else:
            should = await should_reply_with_ai(full_prompt, channel_id, nickname, user_id)
            if should:
                await _do_chat_reply(bot, event, full_prompt, session_id, user_id, session_type, user_name=nickname)
            else:
                memory.save_context(session_id, 0, "未回复", session_type, role='assistant', user_name=BOT_DISPLAY_NAME)
        return

    # 跳过空消息
    if not plain_text:
        return

    # --- 文本消息处理 ---
    full_prompt = plain_text + f"\n[以下是当前对话用户昵称与ID：]\n{nickname, user_id}"
    memory.save_context(session_id, user_id, full_prompt, session_type, user_name=nickname)

    if special_flag == 1:
        logger.info("检测到@消息，强制发言")
        await _do_chat_reply(bot, event, full_prompt, session_id, user_id, session_type, user_name=nickname)
        return

    should = await should_reply_with_ai(plain_text, channel_id, nickname, user_id)
    if should:
        logger.info("AI判断需要回复")
        await _do_chat_reply(bot, event, full_prompt, session_id, user_id, session_type, user_name=nickname)
    else:
        logger.info("AI判断不需要回复")
        memory.save_context(session_id, 0, "未回复", session_type, role='assistant', user_name=BOT_DISPLAY_NAME)
