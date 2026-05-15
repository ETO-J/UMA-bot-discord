"""帮助信息 - Discord 适配版"""
from nonebot import on_message
from nonebot.adapters.discord import Bot, MessageEvent
from nonebot_plugin_alconna import UniMessage

help_handler = on_message(priority=2, block=False)

HELP_TEXT = """【使用指南 | Command Guide】
💬 波旁 [内容] - 与波旁对话（含记忆+联网搜索）
🎭 今日担当 [角色] - 每日随机角色邂逅，可指定角色
🎨 draw [提示词] - AI绘图
🎨🎨 multidraw [全局 AND 角色1 AND 角色2] - 多角色绘图
🎨 高清 [开/关] - 高清绘图模式
🖼️  切换分辨率 [宽] [高] - 修改绘图尺寸
🖼️  切换工作流 discord/anima - 修改绘图原始模型。discord为IL，anima为anima-v1-base,两者lora不通用
🖼️  partone / parttwo - 多人绘图区块设置
🖼️  切换负面 / 重置负面 - 负面提示词管理
🔹 lora列表 / 添加lora / 删除lora / 重置lora - Lora管理
🎭 人设列表 / 切换人设 [名称] - 查看与切换人设
📚 学习 [知识] - 教机器人新知识
⚙️  批量学习 / 知识列表 / 删除知识 - 知识库管理(管理员)
⚙️  开启模拟聊天 / 关闭模拟聊天 - 自由对话模式(管理员)
⚙️  修改限额 [用户ID] [次数] - 修改绘图配额(管理员)
⚙️  撤回 [消息ID] - 删除消息(管理员)
⚙️  ban [用户ID] - 封禁用户(管理员)
⚙️  debug / 重启 / 清除 - 管理员专用"""


@help_handler.handle()
async def handle_help(bot: Bot, event: MessageEvent):
    raw_text = event.get_plaintext().strip().lower()
    if raw_text in ["help", "/help"]:
        await UniMessage(HELP_TEXT).send(reply_message=True)
    else:
        await help_handler.skip()
