"""bopang 统一插件 - 所有模块入口"""
from . import ai          # 注册 /波旁 + 自由聊天
from . import features    # 注册 娱乐性功能命令（涩图/draw/ezdraw/今日担当/识图）
from . import admin       # 注册 管理员命令
from . import help        # 注册 /help

from nonebot.log import logger
logger.info("bopang 统一插件加载完成")