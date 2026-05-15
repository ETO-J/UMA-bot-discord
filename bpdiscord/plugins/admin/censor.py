from nonebot import on_message
from nonebot.adapters.discord import Bot as DiscordBot, MessageEvent
from nonebot_plugin_alconna import UniMessage
from nonebot.log import logger
from openai import AsyncOpenAI
import os
import importlib
import httpx
from dotenv import load_dotenv
import time

current_time = time.time()

load_dotenv()
API_KEY = os.getenv("AICHATKEY1")

# 从统一配置中心导入权限配置（与 bpdiscord 插件共享同一模块实例）
_config = importlib.import_module("bpdiscord.plugins.bpdiscord.config")
ADMIN_IDS = _config.ADMIN_IDS
is_admin = _config.is_admin
ALLOWED_GUILDS_CENSOR = _config.ALLOWED_GUILDS_CENSOR
is_channel_allowed_censor = _config.is_channel_allowed_censor
PRIVATE_CHAT_ENABLED = _config.PRIVATE_CHAT_ENABLED
CENSOR_ADMIN_BYPASS = _config.CENSOR_ADMIN_BYPASS

# 本地ollama地址
ollama_host = "http://127.0.0.1:11434/v1"
http_client = httpx.AsyncClient(trust_env=False)


async def should_reply_with_ai(message: str, channel_id: str, nickname: str, user_id: str) -> bool:
    try:
        judge_prompt = f"""你是一个专业的社区安全助手。请判断以下 Discord 消息是否为垃圾广告、诈骗、非法引流或骚扰内容。
【用户信息】
- 用户昵称：{nickname}
- 消息内容：{message}

【判断标准】
1. 是否包含诱导点击链接（尤其是缩写链接）。
2. 是否包含免费领取、兼职代刷、非法代充、色情消息等典型诈骗语义。
3. 是否为无意义的刷屏或大量重复符号。
4. 消息是否与正常的频道交流严重脱节。

【回复格式】
请只回复一个数字：1（是垃圾信息）或 0（是正常信息）。不要输出任何其他内容。"""

        client = AsyncOpenAI(api_key=API_KEY, base_url=ollama_host, http_client=http_client)
        response = await client.chat.completions.create(
            model="glm-4.7-flash:latest",
            messages=[
                {"role": "system", "content": "你是一个智能回复判断助手，只输出0或1。"},
                {"role": "user", "content": judge_prompt}
            ],
            max_tokens=1024,
            temperature=0.1,
        )

        result = response.choices[0].message.content.strip()
        should_reply = result == "1"
        logger.info(f"AI判断prompt：{judge_prompt} ")
        return should_reply

    except Exception as e:
        logger.error(f"AI审核出错: {str(e)}")


user_message_records = {}

message_handler = on_message(priority=5, block=False)


@message_handler.handle()
async def handle_message(bot: DiscordBot, event: MessageEvent):
    user_id = event.get_user_id()
    channel_id = str(event.channel_id) if hasattr(event, "channel_id") else user_id
    guild_id = str(event.guild_id) if hasattr(event, "guild_id") else None

    try:
        if hasattr(event, 'author'):
            nickname = event.author.global_name or event.author.name or '未知用户'
        else:
            nickname = '未知用户'
    except Exception as e:
        logger.error(f"获取用户信息失败: {str(e)}")
        nickname = "未知用户"

    message = event.get_message()
    current_time = time.time()
    plain_text = event.get_plaintext().strip()
    logger.info(f"收到频道【{channel_id}】中用户【{nickname}】(ID:{user_id}) 的消息: {plain_text}")

    # ==================== 权限检查 ====================
    admin_bypass = CENSOR_ADMIN_BYPASS and is_admin(user_id)
    is_private = guild_id is None

    if is_private:
        if not PRIVATE_CHAT_ENABLED:
            logger.info(f"私聊垃圾检测已全局禁用，忽略来自用户 {user_id} 的消息")
            return
    else:
        if not is_channel_allowed_censor(guild_id, channel_id) and not admin_bypass:
            logger.info(f"群聊 {guild_id} 或频道 {channel_id} 未在垃圾检测允许列表中，忽略消息")
            return

    # ==================== 命令消息过滤 ====================
    DISCORD_EXACT_COMMANDS = [
        "波旁",
        "人设列表",
        "切换人设",
        "draw",
        "高清",
        "切换分辨率",
        "切换负面",
        "重置负面",
        "lora列表",
        "添加lora",
        "删除lora",
        "重置lora",
        "管理员模式",
    ]
    first_word = plain_text.split()[0] if plain_text else ""
    if plain_text.startswith(("波旁")) or first_word in DISCORD_EXACT_COMMANDS:
        logger.info(f"命令消息 {plain_text}，跳过处理")
        return

    # ==================== 垃圾消息检测 ====================
    if user_id not in user_message_records:
        user_message_records[user_id] = []

    user_message_records[user_id].append((current_time, channel_id, guild_id))

    user_message_records[user_id] = [
        record for record in user_message_records[user_id]
        if current_time - record[0] < 10
    ]

    recent_channels = set()
    for record in user_message_records[user_id]:
        if current_time - record[0] < 6:
            recent_channels.add(record[1])

    condition1 = len(recent_channels) >= 3
    if condition1:
        logger.info(f"用户 {user_id} 在6s内发送消息到 {len(recent_channels)} 个不同频道")

    condition2 = 'http' or 'discord' in plain_text.lower()
    if condition2:
        logger.info(f"用户 {user_id} 的消息包含链接: {plain_text[:50]}...")

    if condition1 and condition2:
        logger.info(f"触发垃圾消息检测，用户 {user_id} 同时满足多频道和链接条件，启动AI审核")
        is_spam = True
        if is_spam:
            try:
                await bot.create_guild_ban(
                    guild_id=guild_id,
                    user_id=int(user_id),
                    delete_message_seconds=86400
                )
                await UniMessage(f"指令已确认。已将目标驱逐出服务器，并清除了其近期的所有痕迹。").send()
            except Exception as e:
                await UniMessage(f"封禁失败，请确保机器人的身份组层级高于该用户。错误: {e}").send()
            await UniMessage(f"已触发AI审核机制，成功进行诈骗分子{user_id}杀灭（DEBUG）").send()
            return
        else:
            await UniMessage(f"已触发AI审核机制，{user_id}的消息审核结果无异常").send()
