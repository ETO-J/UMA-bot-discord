from nonebot import on_message, get_driver, require
from nonebot.adapters.discord import Bot as DiscordBot, MessageEvent
from nonebot_plugin_alconna import UniMessage
from nonebot.log import logger
import importlib
import asyncio
import time

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

_config = importlib.import_module("bpdiscord.plugins.bpdiscord.config")
ADMIN_IDS = _config.ADMIN_IDS
is_admin = _config.is_admin
ALLOWED_GUILDS_CENSOR = _config.ALLOWED_GUILDS_CENSOR
is_channel_allowed_censor = _config.is_channel_allowed_censor

_processed_users: dict[str, float] = {}


def _is_trap_channel(guild_id: str, channel_id: str) -> bool:
    return is_channel_allowed_censor(guild_id, channel_id)


def _get_trap_channel_ids() -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for guild_id, gcfg in ALLOWED_GUILDS_CENSOR.items():
        if not gcfg.get("enabled", False):
            continue
        for channel_id, enabled in gcfg.get("channels", {}).items():
            if enabled:
                result.append((guild_id, channel_id))
    return result


async def _ban_and_kick(bot: DiscordBot, guild_id: str, user_id: int) -> bool:
    try:
        await bot.create_guild_ban(
            guild_id=guild_id,
            user_id=user_id,
            delete_message_seconds=604800,
        )
        logger.info(f"[陷阱频道] 已封禁用户 {user_id}，正在清除消息记录...")
    except Exception as e:
        err_msg = str(e)
        if "50013" in err_msg or "Missing Permissions" in err_msg:
            logger.error(
                f"[陷阱频道] 封禁用户 {user_id} 失败: Discord 权限不足 (错误码 50013)。"
                f"请确保机器人在服务器 {guild_id} 中拥有「封禁成员」权限，"
                f"且机器人身份组层级高于目标用户。"
            )
        else:
            logger.error(f"[陷阱频道] 封禁用户 {user_id} 失败: {e}")
        return False

    await asyncio.sleep(0.5)

    try:
        await bot.remove_guild_ban(guild_id=guild_id, user_id=user_id)
        logger.info(f"[陷阱频道] 已解封用户 {user_id}，踢出+清除消息完成")
    except Exception as e:
        logger.warning(f"[陷阱频道] 解封用户 {user_id} 失败，尝试直接踢出: {e}")
        try:
            await bot.remove_guild_member(guild_id=guild_id, user_id=user_id)
            logger.info(f"[陷阱频道] 已踢出用户 {user_id}（用户已被封禁，使用成员移除接口）")
        except Exception as e2:
            logger.error(f"[陷阱频道] 踢出用户 {user_id} 也失败: {e2}")
            return False

    return True


message_handler = on_message(priority=5, block=False)


@message_handler.handle()
async def handle_trap_message(bot: DiscordBot, event: MessageEvent):
    user_id = event.get_user_id()
    channel_id = str(event.channel_id) if hasattr(event, "channel_id") else user_id
    guild_id = str(event.guild_id) if hasattr(event, "guild_id") else None

    if guild_id is None:
        return

    if not _is_trap_channel(guild_id, channel_id):
        return

    if is_admin(user_id):
        return

    try:
        if hasattr(event, 'author') and event.author:
            if getattr(event.author, 'bot', False):
                return
    except Exception:
        pass

    try:
        if hasattr(event, 'author'):
            nickname = event.author.global_name or event.author.name or '未知用户'
        else:
            nickname = '未知用户'
    except Exception:
        nickname = '未知用户'

    plain_text = event.get_plaintext().strip()
    logger.info(
        f"[陷阱频道] 检测到用户 {nickname}(ID:{user_id}) "
        f"在频道 {channel_id} 发送消息: {plain_text[:100]}"
    )

    user_id_int = int(user_id)

    success = await _ban_and_kick(bot, guild_id, user_id_int)
    if success:
        _processed_users[user_id] = time.time()
        await UniMessage(
            f"检测到垃圾消息发送者 <@{user_id}>，已踢出并清除消息记录。"
        ).send()
    else:
        await UniMessage(
            f"检测到垃圾消息发送者 <@{user_id}>，但处理失败，请检查机器人权限。"
        ).send()


@scheduler.scheduled_job("interval", minutes=10, id="trap_channel_periodic_scan")
async def periodic_trap_channel_scan():
    logger.info("[陷阱频道扫描] 开始定期扫描...")

    bots = get_driver().bots
    if not bots:
        logger.warning("[陷阱频道扫描] 没有可用的Bot实例")
        return

    bot = list(bots.values())[0]

    trap_channels = _get_trap_channel_ids()
    if not trap_channels:
        logger.info("[陷阱频道扫描] 没有配置陷阱频道，跳过")
        return

    now = time.time()
    users_to_process: set[int] = set()
    guild_for_user: dict[int, str] = {}

    for guild_id_str, channel_id_str in trap_channels:
        try:
            messages = await bot.get_channel_messages(
                channel_id=int(channel_id_str),
                limit=50,
            )
            for msg in messages:
                if not hasattr(msg, 'author') or not msg.author:
                    continue

                author_id_str = str(msg.author.id)

                if getattr(msg.author, 'bot', False):
                    continue
                if is_admin(author_id_str):
                    continue
                if author_id_str in _processed_users:
                    if now - _processed_users[author_id_str] < 600:
                        continue

                users_to_process.add(int(msg.author.id))
                guild_for_user[int(msg.author.id)] = guild_id_str
        except Exception as e:
            logger.error(f"[陷阱频道扫描] 获取频道 {channel_id_str} 消息失败: {e}")
            continue

    for user_id_int in users_to_process:
        gid_str = guild_for_user.get(user_id_int)
        if gid_str is None:
            continue
        logger.info(f"[陷阱频道扫描] 发现未处理的用户 {user_id_int}，执行清理...")
        success = await _ban_and_kick(bot, gid_str, user_id_int)
        if success:
            _processed_users[str(user_id_int)] = now

    for uid in list(_processed_users.keys()):
        if now - _processed_users[uid] > 3600:
            del _processed_users[uid]

    logger.info("[陷阱频道扫描] 定期扫描完成")
