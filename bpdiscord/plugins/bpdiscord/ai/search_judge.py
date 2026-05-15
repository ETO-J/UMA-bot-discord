"""联网搜索判断模块"""
import json
from typing import Tuple

from nonebot.log import logger

from .client import deepseek_client
from .. import config as _cfg
from ..config import BING_API_KEY, BING_SEARCH_URL, DEEPSEEK_CHAT_MODEL

import requests


def needs_search(prompt: str, context: str = None) -> Tuple[bool, str, str]:
    """
    使用 AI 模型智能判断是否需要进行网络搜索

    Returns:
        (needs_search, search_query, reason)
    """
    # 清理 prompt，移除元数据标记
    clean_prompt = prompt.split("[以下是当前对话用户昵称与ID：]")[0].strip()

    judge_prompt = f"""你是一个搜索意图判断助手。请分析用户的问题，判断是否需要进行网络搜索。

判断标准：
1. 时效性内容：天气、新闻、股票、实时事件等需要最新信息的问题
2. 动态信息：价格、状态、位置等可能变化的信息
3. 特定查询：需要查询具体网页、链接、文档等
4. 事实核查：需要验证最新事实或数据
5. 超出知识库：明显超出AI训练数据范围的问题
6. 用户明确提出需要网络搜索的情况

不需要搜索的情况：
1. 常识性问题：历史、科学原理、编程知识等
2. 创作类：写作、翻译、代码生成等
3. 个人观点：询问意见、建议、分析等
4. 已知信息：AI训练数据中包含的稳定知识
5. 日常对话：问候、闲聊、情感表达等

用户问题：{clean_prompt}

{f"上下文信息：{context}" if context else ""}

请以JSON格式返回判断结果：
{{
    "needs_search": true/false,
    "reason": "判断理由",
    "search_query": "提取的搜索关键词（如果需要搜索）"
}}

只返回JSON，不要其他内容。"""

    try:
        import asyncio
        # 同步接口用于兼容旧调用方式
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if loop and loop.is_running():
            # 在异步上下文中，使用回退方案
            return _fallback_needs_search(prompt)

        import openai
        sync_client = openai.OpenAI(api_key=BING_API_KEY, base_url="https://api.deepseek.com")
        response = sync_client.chat.completions.create(
            model=DEEPSEEK_CHAT_MODEL,
            messages=[
                {"role": "system", "content": "你是一个专业的搜索意图判断助手，只输出JSON。"},
                {"role": "user", "content": judge_prompt},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        result_text = response.choices[0].message.content.strip()

        try:
            result = json.loads(result_text)
            needs_search_flag = result.get("needs_search", False)
            reason = result.get("reason", "")
            search_query = result.get("search_query", prompt)
            logger.info(f"搜索判断: needs={needs_search_flag}, query={search_query}, reason={reason}")
            return needs_search_flag, search_query, reason
        except json.JSONDecodeError:
            return _fallback_needs_search(prompt)

    except Exception as e:
        logger.error(f"AI搜索判断失败: {e}")
        return _fallback_needs_search(prompt)


async def needs_search_async(prompt: str, context: str = None) -> Tuple[bool, str, str]:
    """异步版本的搜索判断"""
    clean_prompt = prompt.split("[以下是当前对话用户昵称与ID：]")[0].strip()

    judge_prompt = f"""你是一个搜索意图判断助手。请分析用户的问题，判断是否需要进行网络搜索。

判断标准：
1. 时效性内容：天气、新闻、股票、实时事件等
2. 动态信息：价格、状态、位置等
3. 特定查询、事实核查、超出知识库
6. 用户明确提出需要搜索

不需要搜索：常识问题、创作类、个人观点、日常对话

用户问题：{clean_prompt}
{f"上下文信息：{context}" if context else ""}

返回JSON：{{"needs_search": true/false, "reason": "理由", "search_query": "关键词"}}
只返回JSON。"""

    try:
        if _cfg.DEBUG_MODE:
            logger.info("=" * 60)
            logger.info("🔍 [DEBUG] DeepSeek 搜索判断最终输入")
            logger.info(judge_prompt)
            logger.info("=" * 60)

        response = await deepseek_client.chat.completions.create(
            model=DEEPSEEK_CHAT_MODEL,
            messages=[
                {"role": "system", "content": "你是一个专业的搜索意图判断助手，只输出JSON。"},
                {"role": "user", "content": judge_prompt},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        result_text = response.choices[0].message.content.strip()
        result = json.loads(result_text)
        return (
            result.get("needs_search", False),
            result.get("search_query", prompt),
            result.get("reason", ""),
        )
    except Exception as e:
        logger.error(f"异步搜索判断失败: {e}")
        return _fallback_needs_search(prompt)


def _fallback_needs_search(prompt: str) -> Tuple[bool, str, str]:
    """回退的关键词匹配"""
    keywords = [
        "search", "look up", "find", "google", "what is",
        "搜索", "百度一下", "联网搜索", "查一查", "搜一查", "查询一下",
        "天气", "新闻", "股票", "汇率", "实时", "最新", "今天", "现在",
    ]
    needs = any(kw in prompt.lower() for kw in keywords)
    return needs, prompt, "关键词匹配" if needs else "未匹配到搜索关键词"


def search_web(query: str) -> str:
    """执行网络搜索"""
    payload = {"query": query, "summary": False, "count": 3}
    headers = {
        "Authorization": f"Bearer {BING_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(BING_SEARCH_URL, headers=headers, json=payload)
        response.raise_for_status()
        search_results = response.json()

        target_data = search_results.get("webPages")
        if not target_data and "data" in search_results:
            target_data = search_results.get("data").get("webPages")

        if target_data and "value" in target_data and target_data["value"]:
            return target_data["value"][0].get("snippet", "未找到相关摘要。")
        return "未找到相关信息。"
    except Exception as e:
        logger.error(f"搜索出错: {e}")
        return f"搜索出错：{e}"
