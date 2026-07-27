"""测试备用信源 URL。"""

from __future__ import annotations

import asyncio

import aiohttp
import feedparser

from src.sources.utils import USER_AGENT

CANDIDATES = [
    ("jiqizhixin-gnews", "https://news.google.com/rss/search?q=site:jiqizhixin.com&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
    ("huxiu-gnews", "https://news.google.com/rss/search?q=site:huxiu.com+AI&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"),
    ("cohere-github", "https://github.com/cohere-ai/cohere-python/releases.atom"),
    ("cohere-docs", "https://docs.cohere.com/changelog/rss.xml"),
    ("tencent-cloud", "https://cloud.tencent.com/developer/column/1001/rss"),
    ("analytics-substack", "https://analyticsindiamag.com/feed/"),
    ("stability-github", "https://github.com/Stability-AI/generative-models/releases.atom"),
    ("arxiv-ai-api", "http://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=20"),
]


async def check(name: str, url: str, timeout: int = 45) -> None:
    headers = {"User-Agent": USER_AGENT}
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout), ssl=False) as response:
                text = await response.text()
                parsed = feedparser.parse(text)
                print(
                    f"{name}: status={response.status} entries={len(parsed.entries)} "
                    f"bytes={len(text)} bozo={parsed.bozo}"
                )
                if parsed.entries:
                    entry = parsed.entries[0]
                    print(f"  sample: {entry.get('title', '')[:70]}")
    except Exception as exc:
        print(f"{name}: FAIL {type(exc).__name__} {exc}")


async def main() -> None:
    for name, url in CANDIDATES:
        timeout = 120 if "huxiu" in name else 45
        await check(name, url, timeout=timeout)


if __name__ == "__main__":
    asyncio.run(main())
