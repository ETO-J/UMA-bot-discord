"""Pixiv 搜图模块"""
import os
import random
import time
from pathlib import Path

from nonebot.plugin.on import on_message
from pixivpy3 import AppPixivAPI
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment
from nonebot.log import logger

from ..config import PIXIV_REFRESH_TOKEN, PIXIV_IMAGES_DIR

api = AppPixivAPI()


def _authenticate():
    """认证 Pixiv API"""
    try:
        api.auth(refresh_token=PIXIV_REFRESH_TOKEN)
    except Exception as e:
        logger.error(f"Pixiv身份验证失败: {e}")


def _download_random_pixiv_images(query: str, num_images: int = 1, retries: int = 3, retry_delay: int = 5) -> list[str]:
    """从 Pixiv 搜索并下载图片"""
    PIXIV_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    attempt = 0
    while attempt < retries:
        try:
            _authenticate()
            json_result = api.search_illust(query, search_target="partial_match_for_tags")
            all_illusts = json_result.illusts
            if not all_illusts:
                return []

            selected = random.sample(all_illusts, min(num_images, len(all_illusts)))
            paths = []
            for illust in selected:
                image_url = illust.image_urls.large
                image_id = illust.id
                try:
                    api.download(image_url, path=str(PIXIV_IMAGES_DIR), name=f"{image_id}.jpg")
                    paths.append(str(PIXIV_IMAGES_DIR / f"{image_id}.jpg"))
                except Exception as e:
                    logger.warning(f"下载失败: {image_url}, 错误: {e}")
            return paths
        except Exception as e:
            logger.error(f"搜索失败: {e}, 尝试重新连接...")
            _authenticate()
        attempt += 1
        time.sleep(retry_delay)
    return []


# 中日文 Tag 映射
TRANSLATION_MAP = {
    "特别周": "スペシャルウィーク", "无声铃鹿": "サイレンススズカ",
    "目白多伯": "メジロドーベル", "东海帝皇": "トウカイテイオー",
    "东海帝王": "トウカイテイオー", "丸善斯基": "マルゼンスキー",
    "富士奇迹": "フジキセキ", "小栗帽": "オグリキャップ",
    "黄金船": "ゴールドシップ", "伏特加": "ウオッカ",
    "大和赤骥": "ダイワスカーレット", "大树快车": "タイキシャトル",
    "草上飞": "グラスワンダー", "目白麦昆": "メジロマックイーン",
    "神鹰": "エルコンドルパサー", "好歌剧": "テイエムオペラオー",
    "成田白仁": "ナリタブライアン", "鲁道夫象征": "シンボリルドルフ",
    "气槽": "エアグルーヴ", "爱丽数码": "アグネスデジタル",
    "青云天空": "セイウンスカイ", "星云天空": "セイウンスカイ",
    "玉藻十字": "タマモクロス", "美妙姿势": "ファインモーション",
    "琵琶晨光": "ビワハヤヒデ", "摩耶重炮": "マヤノトップガン",
    "曼城茶座": "マンハッタンカフェ", "美浦波旁": "ミホノブルボン",
    "米浴": "ライスシャワー", "艾尼斯风神": "アイネスフウジン",
    "爱丽速子": "アグネスタキオン", "爱慕织姬": "アドマイヤベガ",
    "稻荷一": "イナリワン", "胜利奖券": "ウイニングチケット",
    "空中神宫": "エアシャカール", "荣进闪耀": "エイシンフラッシュ",
    "真机伶": "カレンチャン", "黄金城": "ゴールドシチー",
    "樱花进王": "サクラバクシンオー", "东商变革": "スイープトウショウ",
    "超级小海湾": "スーパークリーク", "醒目飞鹰": "スマートファルコン",
    "东瀛佐敦": "トーセンジョーダン", "成田大进": "ナリタタイシン",
    "西野花": "ニシノフラワー", "春乌拉拉": "ハルウララ",
    "待兼福来": "マチカネフクキタ", "千明代表": "ミスターシービー",
    "名将怒涛": "メイショウドトウ", "优秀素质": "ナイスネイチャ",
    "帝王光辉": "キングヘイロー", "待兼诗歌剧": "マチカネタンホイザ",
    "目白善信": "メジロパーマー", "大拓太阳神": "ダイタクヘリオス",
    "里见光钻": "サトノダイヤモンド", "北部玄驹": "キタサンブラック",
    "目白阿尔丹": "メジロアルダン", "目白光明": "メジロブライト",
    "樱花桂冠": "サクラローレル", "成田白": "ナリタトップロード",
    "也文摄辉": "ヤマニンゼファー", "创升": "トランセンド",
    "北方飞翔": "ノースフライト", "谷水琴蕾": "タニノギムレット",
    "第一红宝石": "ダイイチルビー", "目白高峰": "メジロラモーヌ",
    "真弓快车": "アストンマーチャン", "里见皇冠": "サトノクラウン",
    "高尚骏逸": "シュヴァルグラン", "强击": "ヴィブロス",
    "森林宝穴": "ジャングルポケット", "创世驹": "クロノジェネシス",
    "杏目": "アーモンドアイ", "贵妇人": "ジェンティルドンナ",
    "黄金巨匠": "オルフェーヴル", "迷人景致": "ブエナビスタ",
    "唯独爱你": "ラヴズオンリーユー", "杜兰达尔": "デュランダル",
    "双涡轮": "ツインターボ", "谋勇兼备": "デアリングタクト",
    "极峰": "ヴィルシーナ", "秋川弥生": "秋川やよい",
    "光辉致意": "ライトハロー", "机伶金花": "カレンブーケドー",
    "速度象征": "スピードシンボリ", "黄金旅程": "ステイゴールド",
    "情人们": "バレンタイン", "女仆": "メイド", "和服": "着物",
}


def _convert_chinese_to_japanese(text: str) -> str:
    """将中文关键词转换为日文"""
    keywords = text.strip().split()
    converted = [TRANSLATION_MAP.get(kw, kw) for kw in keywords]
    return " ".join(converted)


# 注册命令
pixiv_cmd = on_command("涩图", priority=4, block=True)


@pixiv_cmd.handle()
async def handle_pixiv(bot: Bot, event: GroupMessageEvent, ):
    keyword = event.get_message().extract_plain_text().strip()
    # 移除命令前缀
    if keyword.startswith("/涩图"):
        keyword = keyword[3:].strip()

    if not keyword:
        await pixiv_cmd.finish("请提供关键词，例如：/涩图 特别周")
        return

    converted = _convert_chinese_to_japanese(keyword)
    logger.info(f"Pixiv搜索: {keyword} -> {converted}")

    image_paths = _download_random_pixiv_images(query=converted, num_images=1)
    if not image_paths:
        _authenticate()
        await pixiv_cmd.finish("未找到相关图片，请尝试其他关键词~")

    for image_path in image_paths:
        file_uri = f"file:///{os.path.abspath(image_path).replace(chr(92), '/')}"
        await bot.send(event, MessageSegment.image(file_uri))
        try:
            os.remove(image_path)
        except Exception as e:
            logger.warning(f"删除临时文件失败: {e}")


# 初始认证
_authenticate()
