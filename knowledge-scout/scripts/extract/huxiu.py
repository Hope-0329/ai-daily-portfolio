"""铏庡梾 鈥?RSSHub 浠ｇ悊 + 鐩磋繛鍙岄€氶亾"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from utils.rss_fetcher import fetch_rss
from utils.interest_filter import classify_article
from .base import BaseExtractor, Article


class HuxiuExtractor(BaseExtractor):
    # 铏庡梾涓荤珯 RSS 琚樋閲屼簯 WAF 鎷︽埅锛岀敤 RSSHub 浠ｇ悊
    FEED_URLS = [
        "https://rsshub.rssforever.com/huxiu/article",  # RSSHub 浠ｇ悊
    ]

    async def fetch(self) -> list[Article]:
        articles = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        async with httpx.AsyncClient(headers=headers, timeout=30.0) as session:
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
                    metadata={"source": "铏庡梾"},
                ))
        return articles
