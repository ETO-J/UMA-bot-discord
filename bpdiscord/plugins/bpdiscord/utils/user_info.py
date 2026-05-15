"""统一用户信息获取（Discord 适配版）"""
from nonebot.adapters.discord import Bot, MessageEvent
from nonebot.log import logger


async def get_user_info(bot: Bot, event: MessageEvent) -> dict:
    """
    获取用户信息（昵称、user_id、session_id、session_type）

    Returns:
        dict: {
            "nickname": str,
            "user_id": str,
            "session_id": int,   # 群聊=channel_id, 私聊=user_id
            "session_type": str,  # "group" | "private"
            "guild_id": str | None,
            "channel_id": str,
        }
    """
    user_id = event.get_user_id()
    channel_id = str(event.channel_id) if hasattr(event, "channel_id") else user_id
    guild_id = str(event.guild_id) if hasattr(event, "guild_id") and event.guild_id else None

    if guild_id:
        session_id = int(channel_id)
        session_type = "group"
    else:
        session_id = user_id
        session_type = "private"

    try:
        if hasattr(event, 'author'):
            nickname = event.author.global_name or event.author.name or '未知用户'
        else:
            nickname = '未知用户'
    except Exception as e:
        logger.error(f"获取用户信息失败: {e}")
        nickname = "未知用户"

    return {
        "nickname": nickname,
        "user_id": user_id,
        "session_id": session_id,
        "session_type": session_type,
        "guild_id": guild_id,
        "channel_id": channel_id,
    }
