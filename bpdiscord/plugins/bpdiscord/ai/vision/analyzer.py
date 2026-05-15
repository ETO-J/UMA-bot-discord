"""视觉理解模块 - 豆包视觉模型"""
from volcenginesdkarkruntime import Ark
from nonebot.log import logger

from ...config import DOUBAO_API_KEY, DOUBAO_VISION_MODEL

_client = Ark(api_key=DOUBAO_API_KEY)


def analyze_image(image_url: str, prompt: str = "请非常简要地描述这张图片的内容。如有特定动漫角色，尝试准确辨别。如图片为表情包，则简要准确地描述表情以及可能表达的情绪。给出一个简洁的输出") -> str:
    """
    使用豆包视觉模型分析图片

    Args:
        image_url: 图片URL
        prompt: 分析提示词

    Returns:
        str: 图片分析结果
    """
    try:
        resp = _client.chat.completions.create(
            model=DOUBAO_VISION_MODEL,
            messages=[{
                "content": [
                    {"image_url": {"url": image_url}, "type": "image_url"},
                    {"text": prompt, "type": "text"},
                ],
                "role": "user",
            }],
        )
        result = resp.choices[0].message.content
        logger.info(f"豆包视觉分析成功: {result[:100]}...")
        return result
    except Exception as e:
        logger.error(f"豆包视觉分析失败: {e}")
        return f"图片分析失败: {e}"


def build_vision_prompt(image_description: str, user_message: str = "") -> str:
    """构建包含视觉理解的提示词"""
    base = f"【图片内容】\n{image_description}"
    if user_message:
        base += f"【用户消息】{user_message}"
    return base
