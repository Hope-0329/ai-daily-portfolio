"""RSS 通用抓取 + 解析工具"""
import aiohttp
import xml.etree.ElementTree as ET
from typing import Optional

FEED_TIMEOUT = 15


async def fetch_rss(session: aiohttp.ClientSession, url: str) -> Optional[list[dict]]:
    """抓取 RSS feed，返回条目列表"""
    try:
        async with session.get(url, timeout=FEED_TIMEOUT, ssl=False) as resp:
            if resp.status != 200:
                return None
            xml_text = await resp.text()
    except Exception:
        return None

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    items = []
    # 兼容 RSS 2.0 和 Atom
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.iter("item"):
        items.append(_parse_rss_item(entry))
    for entry in root.findall("atom:entry", ns):
        items.append(_parse_atom_item(entry, ns))
    return items if items else None


def _parse_rss_item(item) -> dict:
    return {
        "title": (item.findtext("title") or "").strip(),
        "url": (item.findtext("link") or "").strip(),
        "summary": _strip_html((item.findtext("description") or "").strip()),
        "author": (item.findtext("author") or "").strip(),
        "published": (item.findtext("pubDate") or "").strip(),
    }


def _parse_atom_item(entry, ns) -> dict:
    title = entry.findtext("atom:title", "", ns).strip()
    url = ""
    for link in entry.findall("atom:link", ns):
        href = link.get("href", "")
        if href:
            url = href
            break
    summary = entry.findtext("atom:summary", "", ns).strip()
    author_elem = entry.find("atom:author", ns)
    author = ""
    if author_elem is not None:
        author = (author_elem.findtext("atom:name", "", ns) or "").strip()
    published = (entry.findtext("atom:published", "", ns) or
                 entry.findtext("atom:updated", "", ns) or "").strip()
    return {
        "title": title,
        "url": url,
        "summary": _strip_html(summary),
        "author": author,
        "published": published,
    }


def _strip_html(text: str) -> str:
    """清理 HTML 标签"""
    import re
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    return " ".join(text.split())[:500]
