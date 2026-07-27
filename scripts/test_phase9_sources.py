"""Phase 9 目标信源连通性探测。"""

from __future__ import annotations

import asyncio

import aiohttp
import feedparser

from src.sources.utils import USER_AGENT

TARGETS = [
    ("jiqizhixin", "https://www.jiqizhixin.com/rss"),
    ("huxiu-ai", "https://www.huxiu.com/rss/0.xml"),
    ("arxiv-ai", "https://export.arxiv.org/rss/cs.AI"),
    ("arxiv-ml", "https://export.arxiv.org/rss/cs.LG"),
    ("arxiv-cl", "https://export.arxiv.org/rss/cs.CL"),
    ("arxiv-cv", "https://export.arxiv.org/rss/cs.CV"),
    ("tencent-ai-lab", "https://ai.tencent.com/ailab/zh/feed/"),
    ("stability-ai", "https://stability.ai/news/rss.xml"),
    ("cohere", "https://cohere.com/blog/rss.xml"),
    ("analytics-india", "https://analyticsindiamag.com/feed/"),
]


async def probe(source_id: str, url: str) -> None:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    }
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=45), ssl=False) as response:
                text = await response.text()
                parsed = feedparser.parse(text)
                is_html = text.lstrip().lower().startswith("<!doctype") or text.lstrip().lower().startswith("<html")
                print(
                    f"{source_id}: status={response.status} entries={len(parsed.entries)} "
                    f"bytes={len(text)} html={is_html}"
                )
    except Exception as exc:
        print(f"{source_id}: FAIL {type(exc).__name__} {exc}")


async def main() -> None:
    for source_id, url in TARGETS:
        await probe(source_id, url)


if __name__ == "__main__":
    asyncio.run(main())
