"""探测更多 RSSHub 镜像与虎嗅路由。"""

from __future__ import annotations

import asyncio
from urllib.parse import quote

import aiohttp
import feedparser

from src.sources.utils import USER_AGENT

CANDIDATES = [
    "https://rsshub.rssforever.com/huxiu/article/0",
    "https://rsshub.umzzz.com/huxiu/article/0",
    "https://rsshub.bestblogs.dev/huxiu/article/0",
    "https://hub.slarker.me/huxiu/article/0",
    "https://rsshub.rssforever.com/huxiu/tag/" + quote("人工智能"),
    "https://rsshub.umzzz.com/huxiu/tag/" + quote("人工智能"),
    "https://rsshub.rssforever.com/wechat/mp/msgalbum/MP_WXS_2390420754962411520",
    "https://rsshub.rssforever.com/jiqizhixin",
]


async def check(url: str) -> None:
    try:
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30), ssl=False) as response:
                text = await response.text()
                parsed = feedparser.parse(text)
                print(f"{response.status} entries={len(parsed.entries)} {url}")
                if parsed.entries:
                    print(f"  -> {parsed.entries[0].title[:70]}")
    except Exception as exc:
        print(f"FAIL {url} {type(exc).__name__}")


async def main() -> None:
    for url in CANDIDATES:
        await check(url)


if __name__ == "__main__":
    asyncio.run(main())
