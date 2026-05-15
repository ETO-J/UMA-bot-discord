"""定时消息模块 - 定时向群聊发送早安/晚安问候"""
import asyncio
from nonebot import get_driver
from nonebot_plugin_apscheduler import scheduler
from nonebot.adapters.onebot.v11 import Bot
from nonebot.log import logger

from ..config import (
    SCHEDULED_MESSAGE_GROUPS,
    SCHEDULED_GOOD_MORNING_HOUR,
    SCHEDULED_GOOD_MORNING_MINUTE,
    SCHEDULED_GOOD_NIGHT_HOUR,
    SCHEDULED_GOOD_NIGHT_MINUTE,
    DEEPSEEK_CHAT_MODEL,
    CHAT_MAX_TOKENS,
    CHAT_TEMPERATURE,
)
from ..ai.client import deepseek_client
from ..ai.persona import persona_manager


async def generate_ai_message(bot: Bot, group_id: int, prompt: str, retries: int = 3):
    """调用 AI 生成问候消息并发送到群聊，带重试机制"""
    persona_prompt = persona_manager.get_current_prompt()
    messages = [
        {"role": "system", "content": persona_prompt},
        {"role": "user", "content": prompt},
    ]

    for attempt in range(retries):
        try:
            response = await deepseek_client.chat.completions.create(
                model=DEEPSEEK_CHAT_MODEL,
                messages=messages,
                max_tokens=CHAT_MAX_TOKENS,
                temperature=CHAT_TEMPERATURE,
            )
            ai_message = response.choices[0].message.content.strip()
            await bot.send_group_msg(group_id=group_id, message=ai_message)
            return
        except Exception as e:
            logger.error(f"AI 消息生成失败 (尝试 {attempt + 1}/{retries})：{e}")
            if attempt < retries - 1:
                await asyncio.sleep(2)
            else:
                await bot.send_group_msg(group_id=group_id, message="出错了，大家早安/晚安！")


async def send_to_all_groups(bot: Bot, prompt: str):
    """向所有配置的群聊发送消息"""
    if not bot:
        logger.warning("Bot 实例不可用，跳过定时消息")
        return
    for group_id in SCHEDULED_MESSAGE_GROUPS:
        try:
            await generate_ai_message(bot, group_id, prompt)
        except Exception as e:
            logger.error(f"向群 {group_id} 发送消息失败: {e}")


@scheduler.scheduled_job("cron", hour=SCHEDULED_GOOD_MORNING_HOUR, minute=SCHEDULED_GOOD_MORNING_MINUTE, misfire_grace_time=5)
async def send_good_morning():
    bot: Bot = get_driver().bots.get(list(get_driver().bots.keys())[0])
    await send_to_all_groups(bot, "生成一条早安问候语，说早安，语气亲切友好。")


@scheduler.scheduled_job("cron", hour=SCHEDULED_GOOD_NIGHT_HOUR, minute=SCHEDULED_GOOD_NIGHT_MINUTE, misfire_grace_time=5)
async def send_good_night():
    bot: Bot = get_driver().bots.get(list(get_driver().bots.keys())[0])
    await send_to_all_groups(bot, "生成一条晚安问候语，说晚安，语气亲切友好。")
