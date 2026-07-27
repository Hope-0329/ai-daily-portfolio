"""探测 HTML 页面是否可抓取文章列表。"""

from __future__ import annotations

import asyncio
import json
import re

import aiohttp
from bs4 import BeautifulSoup

from src.sources.utils import USER_AGENT


async def fetch(url: str, *, timeout: int = 60) -> tuple[int, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout), ssl=False) as response:
            return response.status, await response.text()


def probe_jiqizhixin(html: str) -> None:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if script and script.string:
        data = json.loads(script.string)
        props = data.get("props", {}).get("pageProps", {})
        articles = props.get("articles") or props.get("articleList") or []
        print("  __NEXT_DATA__ articles:", len(articles))
        if articles:
            print("  sample:", articles[0].get("title"), articles[0].get("slug") or articles[0].get("url"))
    links = soup.select('a[href*="/articles/"]')
    print("  article links:", len(links))
    if links:
        print("  sample link:", links[0].get("href"), links[0].get_text(strip=True)[:50])


def probe_next_data(name: str, html: str) -> None:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        print(f"  {name}: no __NEXT_DATA__")
        return
    data = json.loads(script.string)
    text = json.dumps(data, ensure_ascii=False)[:2000]
    print(f"  {name}: __NEXT_DATA__ keys={list(data.keys())}")
    for key in ("title", "slug", "url", "posts", "articles", "items", "nodes"):
        if key in text:
            print(f"    contains `{key}` in payload preview")


def probe_generic(name: str, html: str, selector: str) -> None:
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(selector)
    print(f"  {name} selector `{selector}` -> {len(items)}")
    if items:
        item = items[0]
        link = item.find("a")
        print("  sample:", (link.get("href") if link else None), item.get_text(strip=True)[:60])
    probe_next_data(name, html)


async def main() -> None:
    targets = [
        ("jiqizhixin", "https://www.jiqizhixin.com/", probe_jiqizhixin),
        ("huxiu-rss", "https://www.huxiu.com/rss/0.xml", None),
        ("cohere", "https://cohere.com/blog", lambda h: probe_generic("cohere", h, "article a, h2 a, h3 a")),
        ("stability", "https://stability.ai/news", lambda h: probe_generic("stability", h, "a[href*='/news/']")),
        ("analytics", "https://analyticsindiamag.com/category/artificial-intelligence/", lambda h: probe_generic("analytics", h, "h2.entry-title a, h3.entry-title a")),
        ("tencent", "https://ai.tencent.com/ailab/zh/news", lambda h: probe_generic("tencent", h, "a[href*='/news/']")),
    ]
    for name, url, parser in targets:
        try:
            status, html = await fetch(url, timeout=90 if name == "huxiu-rss" else 60)
            print(f"{name}: status={status} bytes={len(html)}")
            if name == "huxiu-rss":
                import feedparser

                parsed = feedparser.parse(html)
                print("  feed entries:", len(parsed.entries))
            elif parser:
                parser(html)
        except Exception as exc:
            print(f"{name}: FAIL {type(exc).__name__} {exc}")


if __name__ == "__main__":
    asyncio.run(main())
