"""读懂AI时代 — 中文 AI 新闻聚合"""

import sys, asyncio, requests, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.interest_filter import classify_article
from .base import BaseExtractor, Article


class ReadAITimeExtractor(BaseExtractor):
    HOME_URL = "https://www.readaitime.com/"

    async def fetch(self) -> list[Article]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fetch_sync)

    def _fetch_sync(self) -> list[Article]:
        articles = []
        try:
            r = requests.get(self.HOME_URL, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            }, timeout=12)
            r.raise_for_status()
            html = r.text
        except Exception:
            return articles

        # 解析 <article> 中的文章卡片
        # 结构: <article class="digest-item"> <a href="/news/..."><h3 class="item-title">标题</h3> <p class="item-summary">摘要</p>
        articles_match = re.findall(
            r'<article\s+class="[^"]*digest-item[^"]*"[^>]*>\s*<a\s+href="(/news/[^"]+)"[^>]*>.*?<h3\s+class="item-title"[^>]*>(.*?)</h3>\s*</header>\s*<p\s+class="item-summary"[^>]*>(.*?)</p>', 
            html,
            re.DOTALL,
        )
        
        if not articles_match:
            # Fallback: just extract h3 titles + preceding href
            titles_blocks = re.findall(
                r'<a\s+href="(/news/[^"]+)"[^>]*>.*?<h3\s+class="item-title"[^>]*>(.*?)</h3>',
                html, re.DOTALL
            )
            for link, title in titles_blocks[:20]:
                title = re.sub(r'<[^>]+>', '', title).strip()
                if len(title) < 5:
                    continue
                category, score = classify_article(title, "")
                if score < 1.5:
                    continue
                articles.append(Article(
                    platform="readaitime",
                    title=title[:120],
                    url=f"https://www.readaitime.com{link}",
                    summary="",
                    category=category,
                    raw_score=score,
                    metadata={"source": "读懂AI时代"},
                ))
        else:
            for link, title, summary in articles_match[:20]:
                title = re.sub(r'<[^>]+>', '', title).strip()
                summary = re.sub(r'<[^>]+>', '', summary).strip()
                if len(title) < 5:
                    continue
                category, score = classify_article(title, summary)
                if score < 1.5:
                    continue
                articles.append(Article(
                    platform="readaitime",
                    title=title[:120],
                    url=f"https://www.readaitime.com{link}",
                    summary=summary[:200],
                    category=category,
                    raw_score=score,
                    metadata={"source": "读懂AI时代"},
                ))

        return articles
