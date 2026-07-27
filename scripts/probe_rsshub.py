"""探测 RSSHub 路由可用性。"""

from __future__ import annotations

import asyncio

import aiohttp
import feedparser

from src.sources.utils import USER_AGENT

BASES = [
    "https://rsshub.app",
    "https://rsshub.rssforever.com",
    "https://rsshub.umzzz.com",
]

ROUTES = [
    ("jiqizhixin", "/jiqizhixin"),
    ("jiqizhixin-alt", "/jiqizhixin/rss"),
    ("huxiu-tag", "/huxiu/tag/人工智能"),
    ("huxiu-article", "/huxiu/article/0"),
    ("tencent", "/tencent/ai-lab"),
    ("cohere", "/cohere/blog"),
    ("microsoft", "/microsoft/ai"),
]


async def check(base: str, route: str) -> None:
    url = base + route
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=25), ssl=False) as response:
                text = await response.text()
                parsed = feedparser.parse(text)
                print(
                    f"OK {url} status={response.status} entries={len(parsed.entries)} bytes={len(text)}"
                )
                if parsed.entries:
                    print(f"   sample: {parsed.entries[0].title[:60]}")
    except Exception as exc:
        print(f"FAIL {url} {type(exc).__name__}")


async def main() -> None:
    for name, route in ROUTES:
        print(f"\n=== {name} ===")
        for base in BASES:
            await check(base, route)


if __name__ == "__main__":
    asyncio.run(main())
