"""虎嗅 — RSSHub 代理 + 直连双通道"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import aiohttp
from utils.rss_fetcher import fetch_rss
from utils.interest_filter import classify_article
from .base import BaseExtractor, Article


class HuxiuExtractor(BaseExtractor):
    # 虎嗅主站 RSS 被阿里云 WAF 拦截，用 RSSHub 代理
    FEED_URLS = [
        "https://rsshub.rssforever.com/huxiu/article",  # RSSHub 代理
    ]

    async def fetch(self) -> list[Article]:
        articles = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as session:
            items = None
            for feed_url in self.FEED_URLS:
                try:
                    items = await fetch_rss(session, feed_url)
                    if items:
                        break
                except Exception:
                    continue

            if not items:
                return articles

            for item in items[:50]:
                title = item["title"]
                summary = item["summary"]
                category, score = classify_article(title, summary)
                if score < 2.0:
                    continue

                articles.append(Article(
                    platform="huxiu",
                    title=title,
                    url=item["url"],
                    summary=summary[:200],
                    author=item["author"],
                    published=item["published"],
                    category=category,
                    raw_score=score,
                    metadata={"source": "虎嗅"},
                ))
        return articles
