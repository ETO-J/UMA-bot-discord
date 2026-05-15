"""管理员命令模块 - Discord 适配版（重启/清除/人设/知识库/模拟聊天/撤回/ban/修改限额）"""
import os
import sys
import asyncio

from nonebot import on_message
from nonebot.adapters.discord import Bot, MessageEvent
from nonebot_plugin_alconna import UniMessage
from nonebot.log import logger

from ..ai.memory import memory
from ..ai.persona import persona_manager
from ..ai.persona.manager import handle_persona_list, handle_switch_persona
from .. import config as _cfg
from ..config import CHAT_DB_PATH, ALLOWED_GUILDS, is_admin

# 排除 features 模块已处理的命令
FEATURE_COMMANDS = ["draw", "/draw", "multidraw", "/multidraw",
                    "高清", "切换分辨率", "切换负面", "重置负面",
                    "lora列表", "添加lora", "删除lora", "重置lora",
                    "partone", "parttwo", "help", "/help"]

admin_handler = on_message(priority=3, block=False)


@admin_handler.handle()
async def handle_admin_commands(bot: Bot, event: MessageEvent):
    raw_text = event.get_plaintext().strip()
    user_id = event.get_user_id()

    guild_id = str(event.guild_id) if hasattr(event, "guild_id") and event.guild_id else None
    channel_id = str(event.channel_id) if hasattr(event, "channel_id") else user_id

    # 跳过已由 features 处理的命令
    for cmd in FEATURE_COMMANDS:
        if raw_text.startswith(cmd) or raw_text == cmd:
            await admin_handler.skip()
            return

    # ========== DEBUG ==========
    if raw_text.lower() in ["debug", "/debug"]:
        if not is_admin(user_id):
            await UniMessage("⚠️ 权限不足，仅管理员可执行此操作").send(reply_message=True)
            return
        _cfg.DEBUG_MODE = not _cfg.DEBUG_MODE
        status = "开启" if _cfg.DEBUG_MODE else "关闭"
        await UniMessage(f"🔍 DEBUG 模式已{status}").send(reply_message=True)
        return

    # ========== 重启 ==========
    if raw_text.lower() in ["重启", "/重启"]:
        if not is_admin(user_id):
            await UniMessage("⚠️ 权限不足，仅管理员可执行此操作").send(reply_message=True)
            return
        await UniMessage("🔄 服务重启中，请稍后...").send(reply_message=True)
        logger.info(f"管理员 {user_id} 正在重启服务...")
        python = sys.executable
        os.execl(python, python, *sys.argv)
        return

    # ========== 清除 ==========
    if raw_text.lower() in ["清除", "/清除"]:
        if not is_admin(user_id):
            await UniMessage("⚠️ 权限不足，仅管理员可执行此操作").send(reply_message=True)
            return
        deleted = 0
        if os.path.exists(CHAT_DB_PATH):
            os.remove(CHAT_DB_PATH)
            deleted += 1
            logger.info(f"已删除文件: {CHAT_DB_PATH}")
        await UniMessage(f"✅ 缓存清除完成\n已删除文件：{deleted}个\n🔄 正在重新启动服务...").send()
        python = sys.executable
        os.execl(python, python, *sys.argv)
        return

    # ========== 人设列表 ==========
    if raw_text.lower() in ["人设列表", "/人设列表", "personalist"]:
        await handle_persona_list(bot, event)
        return

    # ========== 切换人设 ==========
    if raw_text.startswith(("切换人设", "/切换人设")):
        if not is_admin(user_id):
            await UniMessage("❌ 权限不足。").send(reply_message=True)
            return
        await handle_switch_persona(bot, event)
        return

    # ========== 开启/关闭模拟聊天 ==========
    if raw_text.startswith(("开启模拟聊天", "/开启模拟聊天")):
        if not guild_id:
            await UniMessage("⚠️ 此功能仅限群聊使用").send(reply_message=True)
            return
        if not is_admin(user_id):
            await UniMessage("⚠️ 权限不足，仅管理员可操作").send(reply_message=True)
            return
        if guild_id not in ALLOWED_GUILDS:
            ALLOWED_GUILDS[guild_id] = {"enabled": True, "channels": {}}
        ALLOWED_GUILDS[guild_id]["enabled"] = True
        if channel_id not in ALLOWED_GUILDS[guild_id].get("channels", {}):
            ALLOWED_GUILDS[guild_id].setdefault("channels", {})[channel_id] = True
        await UniMessage("✅ 自由聊天模式已开启").send(reply_message=True)
        return

    if raw_text.startswith(("关闭模拟聊天", "/关闭模拟聊天")):
        if not guild_id:
            await UniMessage("⚠️ 此功能仅限群聊使用").send(reply_message=True)
            return
        if not is_admin(user_id):
            await UniMessage("⚠️ 权限不足，仅管理员可操作").send(reply_message=True)
            return
        if guild_id not in ALLOWED_GUILDS:
            ALLOWED_GUILDS[guild_id] = {"enabled": False, "channels": {}}
        ALLOWED_GUILDS[guild_id]["enabled"] = False
        await UniMessage("✅ 自由聊天模式已关闭").send(reply_message=True)
        return

    # ========== 学习 ==========
    if raw_text.startswith(("学习", "/学习")):
        prefix_len = 3 if raw_text.startswith("/") else 2
        knowledge = raw_text[prefix_len:].strip()
        if not knowledge:
            await UniMessage("请输入有效知识内容，格式：学习 北京是中国的首都").send(reply_message=True)
            return
        try:
            memory.add_knowledge(knowledge)
            await UniMessage(f"新知识已掌握：{knowledge}").send(reply_message=True)
            logger.success(f"知识库更新：{knowledge}")
        except Exception as e:
            await UniMessage(f"学习失败：{e}").send(reply_message=True)
            logger.error(f"知识库更新失败: {e}")
        return

    # ========== 批量学习 ==========
    if raw_text.startswith(("批量学习", "/批量学习")):
        if not is_admin(user_id):
            await UniMessage("⚠️ 权限不足，仅管理员可批量教学").send(reply_message=True)
            return
        prefix_len = 5 if raw_text.startswith("/") else 4
        knowledge_block = raw_text[prefix_len:].strip()
        if not knowledge_block:
            await UniMessage("请输入知识内容，格式：批量学习 [知识1]\\n[知识2]\\n...").send(reply_message=True)
            return
        try:
            knowledge_items = [k.strip() for k in knowledge_block.split('\n') if k.strip()]
            if not knowledge_items:
                await UniMessage("未检测到有效的知识条目").send(reply_message=True)
                return
            success_count = 0
            for item in knowledge_items:
                try:
                    memory.add_knowledge(item)
                    success_count += 1
                except Exception as e:
                    logger.warning(f"知识添加失败: {item} - {e}")
            await UniMessage(f"✅ 批量学习完成！成功添加 {success_count}/{len(knowledge_items)} 条知识").send(reply_message=True)
            logger.success(f"管理员 {user_id} 批量添加了 {success_count} 条知识")
        except Exception as e:
            await UniMessage(f"❌ 批量学习失败: {e}").send(reply_message=True)
            logger.error(f"批量学习失败: {e}")
        return

    # ========== 知识列表 ==========
    if raw_text.startswith(("知识列表", "/知识列表")):
        if not is_admin(user_id):
            await UniMessage("⚠️ 权限不足，仅管理员可查看知识库").send(reply_message=True)
            return
        try:
            all_knowledge = memory.get_all_knowledge()
            if not all_knowledge:
                await UniMessage("📚 知识库目前为空").send(reply_message=True)
                return
            PAGE_SIZE = 10
            total_pages = (len(all_knowledge) + PAGE_SIZE - 1) // PAGE_SIZE
            page_num = 1
            args = raw_text.split()
            if len(args) > 1 and args[1].isdigit():
                page_num = max(1, min(int(args[1]), total_pages))
            start_idx = (page_num - 1) * PAGE_SIZE
            end_idx = min(start_idx + PAGE_SIZE, len(all_knowledge))
            knowledge_list = f"📖 知识库条目列表(第{page_num}/{total_pages}页):\n"
            for idx in range(start_idx, end_idx):
                content = all_knowledge[idx].page_content
                if len(content) > 100:
                    content = content[:97] + "..."
                knowledge_list += f"{idx + 1}. {content}\n"
            if total_pages > 1:
                knowledge_list += "\n使用 知识列表 [页码] 查看其他页"
            await UniMessage(knowledge_list).send(reply_message=True)
            logger.success(f"管理员 {user_id} 查看了知识库列表 (第{page_num}页)")
        except Exception as e:
            await UniMessage(f"❌ 获取知识列表失败: {e}").send(reply_message=True)
            logger.error(f"知识库列表获取失败: {e}")
        return

    # ========== 删除知识 ==========
    if raw_text.startswith(("删除知识", "/删除知识")):
        if not is_admin(user_id):
            await UniMessage("⚠️ 权限不足，仅管理员可删除知识").send(reply_message=True)
            return
        prefix_len = 5 if raw_text.startswith("/") else 4
        arg = raw_text[prefix_len:].strip()
        if not arg:
            await UniMessage("请指定要删除的知识内容或序号\n格式：删除知识 [序号] 或 删除知识 [内容片段]").send(reply_message=True)
            return
        try:
            index = int(arg)
            success = memory.delete_knowledge_by_index(index)
            if success:
                await UniMessage(f"✅ 知识条目 #{index} 已成功删除").send(reply_message=True)
                logger.success(f"管理员 {user_id} 删除了知识条目 #{index}")
            else:
                await UniMessage(f"❌ 删除失败：序号 {index} 无效").send(reply_message=True)
        except ValueError:
            success = memory.delete_knowledge_by_content(arg)
            if success:
                await UniMessage(f"✅ 包含 '{arg}' 的知识条目已删除").send(reply_message=True)
                logger.success(f"管理员 {user_id} 删除了包含'{arg}'的知识条目")
            else:
                await UniMessage(f"❌ 未找到包含 '{arg}' 的知识条目").send(reply_message=True)
        return

    # ========== 修改限额 ==========
    if raw_text.startswith(("修改限额", "/修改限额")):
        if not is_admin(user_id):
            await UniMessage("❌ 只有管理员可以执行此操作。").send(reply_message=True)
            return
        parts = raw_text.split()
        if len(parts) >= 3:
            target_uid = parts[1].replace("<@", "").replace(">", "").replace("!", "")
            new_val = int(parts[2])
            from ..features.comfyui import wm as comfy_wm
            comfy_wm.set_user_limit(target_uid, new_val)
            await UniMessage(f"✅ 已将用户 {target_uid} 的每日限额修改为 {new_val} 次。").send()
        else:
            await UniMessage("❌ 格式：修改限额 [用户ID] [次数]").send(reply_message=True)
        return

    # ========== 撤回消息 ==========
    if raw_text.startswith(("撤回", "/撤回")):
        if not is_admin(user_id):
            await UniMessage("❌ 只有管理员可以执行此操作。").send(reply_message=True)
            return
        prefix_len = 3 if raw_text.startswith("/") else 2
        message_id_param = raw_text[prefix_len:].strip()
        if not message_id_param and hasattr(event, 'reference') and event.reference:
            message_id_param = event.reference.message_id
        if not message_id_param:
            await UniMessage("请提供要删除的消息 ID，或直接回复那条消息并输入撤回。").send()
            return
        try:
            await bot.delete_message(channel_id=int(channel_id), message_id=int(message_id_param))
        except Exception as e:
            await UniMessage(f"清理失败，请检查 Discord 后台权限配置。错误: {e}").send()
        return

    # ========== Ban 用户 ==========
    if raw_text.lower().startswith(("ban", "/ban")):
        if not is_admin(user_id):
            await UniMessage("❌ 只有管理员可以执行此操作。").send(reply_message=True)
            return
        prefix_len = 4 if raw_text.startswith("/") else 3
        ban_user_id = raw_text[prefix_len:].strip()
        if not guild_id:
            await UniMessage("封禁指令只能在服务器频道内使用。").send()
            return
        if hasattr(event, 'message') and hasattr(event.message, 'mentions') and event.message.mentions:
            ban_user_id = event.message.mentions[0].id
        if not ban_user_id or not str(ban_user_id).isdigit():
            await UniMessage("请提供正确的用户 ID，或者直接 @ 那个用户并输入 ban。").send()
            return
        try:
            await bot.create_guild_ban(guild_id=guild_id, user_id=int(ban_user_id), delete_message_seconds=86400)
            await UniMessage("指令已确认。已将目标驱逐出服务器，并清除了其近期的所有痕迹。").send()
        except Exception as e:
            await UniMessage(f"封禁失败，请确保机器人的身份组层级高于该用户。错误: {e}").send()
        return

    # ========== 长期撤回（遍历频道逐条删除，不封禁不踢出）==========
    if raw_text.startswith(("长期撤回", "/长期撤回")):
        if not is_admin(user_id):
            await UniMessage("❌ 只有管理员可以执行此操作。").send(reply_message=True)
            return
        prefix_len = 5 if raw_text.startswith("/") else 4
        target_id = raw_text[prefix_len:].strip()
        if not guild_id:
            await UniMessage("此指令只能在服务器频道内使用。").send()
            return
        if hasattr(event, 'message') and hasattr(event.message, 'mentions') and event.message.mentions:
            target_id = event.message.mentions[0].id
        if not target_id or not str(target_id).isdigit():
            await UniMessage("请提供正确的用户 ID，或者直接 @ 那个用户并输入 长期撤回。").send()
            return

        #await UniMessage(f"🔍 正在扫描服务器所有频道，清理用户 {target_id} 的发言记录...").send(reply_message=True)
        target_int = int(target_id)
        deleted_total = 0
        scanned_channels = 0

        try:
            channels = await bot.get_guild_channels(guild_id=int(guild_id))
            for channel in channels:
                ctype = int(channel.type) if hasattr(channel, 'type') else -1
                if ctype not in (0, 5):
                    continue
                scanned_channels += 1
                try:
                    messages = await bot.get_channel_messages(
                        channel_id=int(channel.id), limit=1000
                    )
                    for msg in messages:
                        if hasattr(msg, 'author') and int(msg.author.id) == target_int:
                            try:
                                await bot.delete_message(
                                    channel_id=int(channel.id), message_id=int(msg.id)
                                )
                                deleted_total += 1
                                await asyncio.sleep(0.3)
                            except Exception:
                                pass
                except Exception:
                    continue
                await asyncio.sleep(0.5)

            '''await UniMessage(
                f"✅ 扫描完成：{scanned_channels} 个频道，共清除 {deleted_total} 条消息。\n"
                f"（仅覆盖每个频道最近100条消息，可多次执行以覆盖更多）"
            ).send()
            '''
            logger.success(f"管理员 {user_id} 执行长期撤回: {target_id}，共清除 {deleted_total} 条")
        except Exception as e:
            await UniMessage(f"❌ 操作失败: {e}").send()
        return

    # 未匹配任何命令
    await admin_handler.skip()
