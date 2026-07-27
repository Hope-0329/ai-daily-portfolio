"""深入探测 __NEXT_DATA__ 与内嵌 API。"""

from __future__ import annotations

import asyncio
import json
import re

import aiohttp
from bs4 import BeautifulSoup

from src.sources.utils import USER_AGENT


async def fetch(url: str) -> str:
    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60), ssl=False) as response:
            return await response.text()


def walk(obj, path="", depth=0, max_depth=4):
    if depth > max_depth:
        return
    if isinstance(obj, dict):
        for key, value in obj.items():
            new_path = f"{path}.{key}" if path else key
            if key in {"title", "name", "slug", "url", "link", "articles", "posts", "items", "list", "nodes", "news"}:
                preview = str(value)[:120]
                print(f"  {new_path}: {preview}")
            if isinstance(value, (dict, list)) and depth < max_depth:
                walk(value, new_path, depth + 1, max_depth)
    elif isinstance(obj, list) and obj and depth < max_depth:
        walk(obj[0], f"{path}[0]", depth + 1, max_depth)


async def inspect(name: str, url: str) -> None:
    html = await fetch(url)
    print(f"\n=== {name} === bytes={len(html)}")
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if script and script.string:
        data = json.loads(script.string)
        walk(data)
    else:
        apis = re.findall(r"https?://[^\"'\\s]+(?:api|feed|rss)[^\"'\\s]*", html, re.I)
        print("  api-like urls:", apis[:10])
        scripts = re.findall(r"/api/[^\"'\\s]+", html)
        print("  /api paths:", scripts[:10])


async def main() -> None:
    await inspect("jiqizhixin-home", "https://www.jiqizhixin.com/")
    await inspect("tencent-news", "https://ai.tencent.com/ailab/zh/news")
    await inspect("cohere-blog", "https://cohere.com/blog")


if __name__ == "__main__":
    asyncio.run(main())
