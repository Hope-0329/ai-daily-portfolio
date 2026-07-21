"""灏戞暟娲?鈥?RSS 鏁堢巼宸ュ叿璇勬祴"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from utils.rss_fetcher import fetch_rss
from utils.interest_filter import classify_article
from .base import BaseExtractor, Article


class SspaiExtractor(BaseExtractor):
    FEED_URL = "https://sspai.com/feed"

    async def fetch(self) -> list[Article]:
        articles = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        async with httpx.AsyncClient(headers=headers) as session:
            items = await fetch_rss(session, self.FEED_URL)
            if not items:
                return articles

            for item in items[:30]:
                title = item["title"]
                summary = item["summary"]
                category, score = classify_article(title, summary)
                if score < 2.0:
                    continue

                articles.append(Article(
                    platform="sspai",
                    title=title,
                    url=item["url"],
                    summary=summary[:200],
                    author=item["author"],
                    published=item["published"],
                    category=category,
                    raw_score=score,
                    metadata={"source": "灏戞暟娲?},
                ))
        return articles
