"""RSS 抓取与评分 —— 对接 knowledge-scout V3 管道"""
import asyncio
import sys
import time
from pathlib import Path

# 注入 knowledge-scout 路径（兼容本地和云部署）
# 本地: knowledge-scout 在 ai-daily-mcp 的兄弟目录
# 云端: knowledge-scout 在 ai-daily-mcp 内作为子目录
SCOUT_ROOT = Path(__file__).resolve().parent.parent.parent / "knowledge-scout"
if not SCOUT_ROOT.exists():
    SCOUT_ROOT = Path(__file__).resolve().parent.parent / "knowledge-scout"
if SCOUT_ROOT.exists():
    sys.path.insert(0, str(SCOUT_ROOT))

from scripts.extract.kr36 import Kr36Extractor
from scripts.extract.huxiu import HuxiuExtractor
from scripts.extract.qbitai import QbitaiExtractor
from scripts.extract.sspai import SspaiExtractor
from scripts.extract.ifanr import IfanrExtractor
from scripts.extract.zhihu import ZhihuExtractor
from scripts.extract.github_trending import GithubTrendingExtractor
from scripts.extract.huggingface import HuggingFaceExtractor
from scripts.extract.readaitime import ReadAITimeExtractor
from scripts.content_fetcher import fetch_full_article
from scripts.interpreter import score_article_depth

# ── 信源注册表 ──
EXTRACTORS = {
    "36kr": Kr36Extractor(),
    "huxiu": HuxiuExtractor(),
    "qbitai": QbitaiExtractor(),
    "sspai": SspaiExtractor(),
    "ifanr": IfanrExtractor(),
    "zhihu": ZhihuExtractor(),
    "github": GithubTrendingExtractor(),
    "huggingface": HuggingFaceExtractor(),
    "readaitime": ReadAITimeExtractor(),
}

SOURCE_NAMES = {
    "36kr": "36氪", "huxiu": "虎嗅", "qbitai": "量子位",
    "sspai": "少数派", "ifanr": "爱范儿", "zhihu": "知乎",
    "github": "GitHub Trending", "huggingface": "HuggingFace",
    "readaitime": "读懂AI时代",
}


async def fetch_articles(sources: list[str] = None, count: int = 15):
    """
    从指定信源抓取文章，预评分后返回。

    Args:
        sources: 信源 key 列表，如 ["36kr", "huxiu"]。不传则全部。
        count:  返回条数（按评分排序取 Top N）

    Returns:
        dict: {"articles": [...], "stats": {...}, "total": int}
    """
    if sources is None:
        sources = list(EXTRACTORS.keys())

    all_articles = []
    stats = {}

    for key in sources:
        ext = EXTRACTORS.get(key)
        if ext is None:
            continue
        name = SOURCE_NAMES.get(key, key)
        try:
            articles = await asyncio.wait_for(ext.fetch(), timeout=15)
            for art in articles:
                title = getattr(art, "title", "")
                url = getattr(art, "url", "")
                summary = getattr(art, "summary", "") or getattr(art, "content", "")
                content = getattr(art, "content", "") or summary

                # 预评分
                score = score_article_depth(content, title, name, url)

                all_articles.append({
                    "title": title,
                    "source": name,
                    "url": url,
                    "summary": summary[:300],
                    "content": content[:2000],
                    "score": score,
                    "level": "深度" if score >= 4 else ("中度" if score >= 2 else "浅层"),
                })
            stats[name] = f"{len(articles)} 条"
        except asyncio.TimeoutError:
            stats[name] = "超时"
        except Exception as e:
            stats[name] = f"错误: {e}"

    # 按评分排序
    all_articles.sort(key=lambda a: a["score"], reverse=True)
    top = all_articles[:count]

    return {
        "articles": top,
        "stats": stats,
        "total": len(all_articles),
        "deep_count": sum(1 for a in all_articles if a["score"] >= 4),
        "medium_count": sum(1 for a in all_articles if 2 <= a["score"] < 4),
    }


async def fetch_full_article_safe(url: str, source: str = "", retries: int = 2):
    """
    抓取单篇文章全文（带重试）。

    Returns:
        str | None: 全文文本，失败返回 None
    """
    for i in range(retries):
        try:
            text = fetch_full_article(url, source)
            if text and len(text) > 200:
                return text
        except Exception:
            if i < retries - 1:
                time.sleep(0.5)
    return None
