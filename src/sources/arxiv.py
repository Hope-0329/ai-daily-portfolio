"""arXiv Atom API 采集（RSS 周末为空时的回退方案）。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from xml.etree import ElementTree as ET

import aiohttp

from src.config import Settings, get_settings
from src.models import Article, Source
from src.sources.utils import USER_AGENT, strip_html, url_hash, utc_now

logger = logging.getLogger(__name__)

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

ARXIV_CATEGORIES: dict[str, str] = {
    "arxiv-ai": "cs.AI",
    "arxiv-ml": "cs.LG",
    "arxiv-cl": "cs.CL",
    "arxiv-cv": "cs.CV",
}


def is_arxiv_source(source_id: str) -> bool:
    """判断是否为 arXiv 信源。"""
    return source_id in ARXIV_CATEGORIES


async def fetch_arxiv_category(
    source: Source,
    settings: Settings | None = None,
    *,
    max_results: int | None = None,
) -> list[Article]:
    """通过 arXiv Atom API 拉取指定分类的最新论文。"""
    category = ARXIV_CATEGORIES.get(source.id)
    if not category:
        return []

    cfg = settings or get_settings()
    limit = max_results if max_results is not None else cfg.arxiv_max_items
    timeout_sec = source.fetch_timeout or cfg.fetch_timeout
    query = (
        "http://export.arxiv.org/api/query?"
        f"search_query=cat:{category}&sortBy=submittedDate&sortOrder=descending"
        f"&max_results={limit}"
    )
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/atom+xml, application/xml, text/xml, */*",
    }
    timeout = aiohttp.ClientTimeout(total=timeout_sec)
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(query, ssl=False) as response:
            response.raise_for_status()
            content = await response.text()

    return await asyncio.to_thread(_parse_arxiv_atom, source, content)


def _parse_arxiv_atom(source: Source, content: str) -> list[Article]:
    """解析 arXiv Atom XML 为 Article 列表。"""
    root = ET.fromstring(content)
    fetched_at = utc_now()
    articles: list[Article] = []

    for entry in root.findall("atom:entry", ATOM_NS):
        title = _entry_text(entry, "atom:title")
        entry_id = _entry_text(entry, "atom:id")
        summary = _entry_text(entry, "atom:summary")
        published = _entry_text(entry, "atom:published")
        link = _entry_link(entry)
        url = link or entry_id
        if not title or not url:
            continue
        articles.append(
            Article(
                id=url_hash(url),
                title=strip_html(title),
                url=url,
                source_id=source.id,
                source_name=source.name,
                summary_raw=strip_html(summary)[:1000] or None,
                published_at=_parse_atom_datetime(published),
                fetched_at=fetched_at,
                language=source.language,
            )
        )
    return articles


def _entry_text(entry: ET.Element, tag: str) -> str:
    node = entry.find(tag, ATOM_NS)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _entry_link(entry: ET.Element) -> str:
    for link in entry.findall("atom:link", ATOM_NS):
        rel = link.attrib.get("rel", "alternate")
        href = link.attrib.get("href", "")
        if href and rel in {"alternate", ""}:
            return href
    return ""


def _parse_atom_datetime(value: str) -> Any:
    from src.sources.utils import parse_published_at

    return parse_published_at(value)
