"""HuggingFace Papers — 社区热门 AI 论文"""

import sys, asyncio, requests
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.interest_filter import classify_article
from .base import BaseExtractor, Article


class HuggingFaceExtractor(BaseExtractor):
    PAPERS_URL = "https://huggingface.co/api/papers"

    async def fetch(self) -> list[Article]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fetch_sync)

    def _fetch_sync(self) -> list[Article]:
        articles = []
        try:
            r = requests.get(self.PAPERS_URL, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "application/json",
            }, timeout=12)
            r.raise_for_status()
            raw = r.json()
        except Exception:
            return articles

        # 处理响应格式: list 或 dict
        if isinstance(raw, list):
            papers = raw
        elif isinstance(raw, dict):
            papers = raw.get("papers", raw.get("data", raw.get("results", [])))
        else:
            return articles

        for paper in papers[:30]:
            if not isinstance(paper, dict):
                continue
            title = paper.get("title", "")
            paper_id = paper.get("id", "")
            url = f"https://huggingface.co/papers/{paper_id}" if paper_id else ""
            summary = paper.get("summary", "")
            authors = paper.get("authors", [])
            if isinstance(authors, list):
                authors_str = ", ".join(str(a)[:30] for a in authors[:3])
            else:
                authors_str = str(authors)[:50]

            full_summary = f"{authors_str}: {summary[:180]}" if authors_str else summary[:200]

            category, score = classify_article(title, full_summary)
            if score < 1.5:
                category = "AI技术"
                score = 3.0

            articles.append(Article(
                platform="huggingface",
                title=title[:120],
                url=url,
                summary=full_summary[:200],
                author=authors_str[:50],
                category=category,
                raw_score=score,
                metadata={
                    "source": "HuggingFace Papers",
                    "upvotes": paper.get("upvotes", 0),
                },
            ))
        return articles
