"""SauceNAO 图片识别模块"""
import requests

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.typing import T_State
from nonebot.log import logger

from ..config import SAUCENAO_API_KEY, SAUCENAO_MIN_SIMILARITY

SAUCENAO_API_URL = "https://saucenao.com/search.php?"

image_search_cmd = on_command("识图", priority=4, block=True)


@image_search_cmd.handle()
async def handle_first(bot: Bot, event: GroupMessageEvent, state: T_State):
    await bot.send(event, "请发送要识别的图片，我会帮你查找来源~")


@image_search_cmd.got("image", prompt="请直接发送要识别的图片")
async def handle_image_input(bot: Bot, event: GroupMessageEvent, state: T_State):
    images = [seg.data["url"] for seg in event.message if seg.type == "image"]
    if not images:
        await image_search_cmd.reject("请发送有效的图片~")

    for image_url in images:
        result = await _query_saucenao(image_url)
        if result:
            msg = _format_result(result)
        else:
            msg = "未能找到相关信息，可能图片不在数据库中~"
        await bot.send(event, msg)


async def _query_saucenao(image_url: str) -> dict | None:
    """调用 SauceNAO API 查询图片信息"""
    params = {
        "output_type": 2,
        "api_key": SAUCENAO_API_KEY,
        "url": image_url,
    }
    try:
        response = requests.get(SAUCENAO_API_URL, params=params, timeout=10)
        response.raise_for_status()
        result = response.json()
        if result["header"]["status"] == 0 and result.get("results"):
            for item in result["results"]:
                if float(item["header"]["similarity"]) >= SAUCENAO_MIN_SIMILARITY:
                    return item
        return None
    except Exception as e:
        logger.error(f"SauceNAO API 调用失败: {e}")
        return None


def _format_result(result: dict) -> str:
    """格式化 SauceNAO 返回结果"""
    similarity = result["header"]["similarity"]
    title = result["data"].get("title", "未知标题")
    author = result["data"].get("member_name", "未知作者")
    source_url = result["data"].get("ext_urls", ["无来源"])[0]
    return (
        f"识别结果：\n"
        f"相似度：{similarity}%\n"
        f"标题：{title}\n"
        f"作者：{author}\n"
        f"来源链接：{source_url}"
    )
