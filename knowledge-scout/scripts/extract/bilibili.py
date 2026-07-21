"""B站 — 搜索 + 热门，用兴趣分类筛选"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.env_reader import get_env
from utils.interest_filter import is_quality_article, classify_article
import re
import aiohttp
from .base import BaseExtractor, Article

# 搜索关键词 — 偏行业分析/工具评测/创作方向
SEARCH_KEYWORDS = [
    "AI行业分析", "AI工具推荐", "AI商业化",
    "AI视频生成", "AI短剧", "AIGC创作",
    "大模型应用", "DeepSeek", "ChatGPT",
    "AI Agent", "效率工具", "自动化工作流",
]


class BilibiliExtractor(BaseExtractor):
    SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"

    async def fetch(self) -> list[Article]:
        sessdata = get_env("BILIBILI_SESSDATA", "")
        cookies = {"SESSDATA": sessdata} if sessdata else {}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com",
        }

        articles = []
        async with aiohttp.ClientSession(cookies=cookies, headers=headers) as session:
            for keyword in SEARCH_KEYWORDS:
                params = {
                    "keyword": keyword,
                    "search_type": "video",
                    "order": "pubdate",
                    "page": 1,
                }
                try:
                    async with session.get(self.SEARCH_URL, params=params, timeout=10) as resp:
                        data = await resp.json()
                    for v in data.get("data", {}).get("result", [])[:10]:
                        article = self._parse_video(v)
                        if article:
                            articles.append(article)
                except Exception:
                    continue

        return articles

    def _parse_video(self, v: dict) -> Article | None:
        title = v.get("title", "").replace('<em class="keyword">', '').replace('</em>', '')
        if not title:
            return None

        desc = v.get("desc", "") or v.get("description", "")

        # 兴趣筛选
        if not is_quality_article(title, desc):
            return None

        category, score = classify_article(title, desc)

        stat = v.get("stat", {}) or v
        play = stat.get("view", 0)
        favorite = stat.get("favorite", 0)
        danmaku = stat.get("danmaku", 0)

        author = v.get("owner", {}).get("name", "") or v.get("author", "")
        bvid = v.get("bvid", "")
        pubdate = v.get("pubdate", 0)

        # 综合评分：兴趣匹配 + 热度
        popularity = play * 0.01 + favorite * 0.5 + danmaku * 0.3
        final_score = score * 2 + popularity

        return Article(
            platform="bilibili",
            title=title,
            url=f"https://www.bilibili.com/video/{bvid}" if bvid else "",
            summary=desc[:200],
            author=author,
            published=str(pubdate),
            category=category,
            raw_score=final_score,
            metadata={"plays": play, "favorites": favorite, "danmaku": danmaku},
        )
