"""在 HTML 中搜索内嵌 JSON 文章列表。"""

from __future__ import annotations

import asyncio
import json
import re

import aiohttp

from src.sources.utils import USER_AGENT


async def fetch(url: str) -> str:
    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60), ssl=False) as response:
            return await response.text()


def find_json_blobs(html: str, label: str) -> None:
    patterns = [
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        r'window\.__APOLLO_STATE__\s*=\s*(\{.*?\});',
        r'\"posts\":\s*(\[.*?\])',
        r'\"articles\":\s*(\[.*?\])',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, html, re.S)
        print(f"{label} pattern `{pattern[:40]}` matches={len(matches)}")
        for match in matches[:1]:
            text = match.strip()
            print("  preview:", text[:300])


async def main() -> None:
    for label, url in [
        ("cohere", "https://cohere.com/blog"),
        ("analytics", "https://analyticsindiamag.com/feed/"),
        ("huxiu", "https://www.huxiu.com/rss/0.xml"),
    ]:
        html = await fetch(url)
        print(f"\n=== {label} bytes={len(html)} ===")
        find_json_blobs(html, label)
        if "xml" in html[:100].lower() or "rss" in html[:100].lower():
            print("  looks like xml/rss header:", html[:120].replace("\n", " "))


if __name__ == "__main__":
    asyncio.run(main())
