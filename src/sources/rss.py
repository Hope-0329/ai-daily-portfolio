"""RSS/Atom/JSON Feed 通用采集器。"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp
import feedparser

from src.config import Settings, get_settings
from src.models import Article, Source
from src.sources.arxiv import fetch_arxiv_category, is_arxiv_source
from src.sources.base import SourceCollector
from src.sources.utils import (
    USER_AGENT,
    parse_published_at,
    strip_html,
    url_hash,
    utc_now,
)

logger = logging.getLogger(__name__)

# 429 限流时额外等待秒数（独立于通用重试间隔）
RATE_LIMIT_RETRY_DELAY = 5


class RSSCollector(SourceCollector):
    """RSS 通用采集器。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def fetch(self, source: Source) -> list[Article]:
        """拉取 RSS/Atom/JSON Feed 并转为 Article 列表。"""
        last_error: Exception | None = None
        max_attempts = self.settings.fetch_retry_count + 1
        for attempt in range(max_attempts):
            verify_ssl = attempt == 0
            try:
                content = await self._download_feed(source, verify_ssl=verify_ssl)
                articles = await self._parse_feed(source, content)
                if not articles and is_arxiv_source(source.id):
                    logger.info("信源 %s RSS 为空，回退 arXiv Atom API", source.id)
                    articles = await fetch_arxiv_category(source, self.settings)
                return articles
            except aiohttp.ClientSSLError as exc:
                last_error = exc
                logger.warning("信源 %s SSL 校验失败，尝试跳过证书验证", source.id)
            except aiohttp.ClientResponseError as exc:
                last_error = exc
                if exc.status == 429 and attempt < max_attempts - 1:
                    logger.warning(
                        "信源 %s 触发 429 限流（第 %s 次），%ss 后重试",
                        source.id,
                        attempt + 1,
                        RATE_LIMIT_RETRY_DELAY,
                    )
                    await asyncio.sleep(RATE_LIMIT_RETRY_DELAY)
                    continue
                if attempt < max_attempts - 1:
                    logger.warning(
                        "信源 %s HTTP %s（第 %s 次），%ss 后重试: %s",
                        source.id,
                        exc.status,
                        attempt + 1,
                        self.settings.fetch_retry_delay,
                        exc,
                    )
                    await asyncio.sleep(self.settings.fetch_retry_delay)
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    logger.warning(
                        "信源 %s 拉取失败（第 %s 次），%ss 后重试: %s",
                        source.id,
                        attempt + 1,
                        self.settings.fetch_retry_delay,
                        exc,
                    )
                    await asyncio.sleep(self.settings.fetch_retry_delay)
        raise RuntimeError(f"RSS 拉取失败: {source.id}") from last_error

    async def _download_feed(self, source: Source, *, verify_ssl: bool) -> str:
        timeout_sec = source.fetch_timeout or self.settings.fetch_timeout
        timeout = aiohttp.ClientTimeout(total=timeout_sec)
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/json, */*",
        }
        if source.id == "huxiu-ai":
            headers["Referer"] = "https://www.huxiu.com/"
        ssl_modes = [verify_ssl]
        if verify_ssl:
            ssl_modes.append(False)

        last_error: Exception | None = None
        for ssl_flag in ssl_modes:
            connector = aiohttp.TCPConnector(ssl=ssl_flag)
            try:
                async with aiohttp.ClientSession(timeout=timeout, headers=headers, connector=connector) as session:
                    async with session.get(source.url) as response:
                        if response.status == 429:
                            raise aiohttp.ClientResponseError(
                                response.request_info,
                                response.history,
                                status=429,
                                message="Too Many Requests",
                                headers=response.headers,
                            )
                        response.raise_for_status()
                        return await response.text()
            except aiohttp.ClientSSLError as exc:
                last_error = exc
                if ssl_flag:
                    logger.warning("信源 %s SSL 校验失败，尝试跳过证书验证", source.id)
                continue
            except Exception:
                raise

        raise last_error or RuntimeError(f"RSS 下载失败: {source.id}")

    async def _parse_feed(self, source: Source, content: str) -> list[Article]:
        stripped = content.lstrip()
        if stripped.startswith("{"):
            return self._parse_json_feed(source, json.loads(content))
        parsed = await asyncio.to_thread(feedparser.parse, content)
        return self._entries_to_articles(source, parsed.entries)

    def _parse_json_feed(self, source: Source, payload: dict[str, Any]) -> list[Article]:
        items = payload.get("items") or payload.get("entries") or []
        articles: list[Article] = []
        fetched_at = utc_now()
        for item in items:
            url = item.get("url") or item.get("id") or ""
            title = (item.get("title") or "").strip()
            if not url or not title:
                continue
            summary_raw = item.get("summary") or item.get("content_text") or item.get("content_html") or ""
            if isinstance(summary_raw, dict):
                summary_raw = summary_raw.get("value", "")
            articles.append(
                Article(
                    id=url_hash(url),
                    title=title,
                    url=url,
                    source_id=source.id,
                    source_name=source.name,
                    summary_raw=strip_html(str(summary_raw))[:1000] or None,
                    published_at=parse_published_at(item.get("date_published") or item.get("date_modified")),
                    fetched_at=fetched_at,
                    language=source.language,
                )
            )
        return articles

    def _entries_to_articles(self, source: Source, entries: list[Any]) -> list[Article]:
        articles: list[Article] = []
        fetched_at = utc_now()
        max_entries = self.settings.arxiv_max_items if source.id.startswith("arxiv-") else None
        iterable = entries[:max_entries] if max_entries else entries
        for entry in iterable:
            url = self._entry_url(entry)
            title = (getattr(entry, "title", "") or "").strip()
            if not url or not title:
                continue
            summary_raw = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
            published_raw = (
                getattr(entry, "published", None)
                or getattr(entry, "updated", None)
                or getattr(entry, "created", None)
            )
            articles.append(
                Article(
                    id=url_hash(url),
                    title=title,
                    url=url,
                    source_id=source.id,
                    source_name=source.name,
                    summary_raw=strip_html(str(summary_raw))[:1000] or None,
                    published_at=parse_published_at(str(published_raw) if published_raw else None),
                    fetched_at=fetched_at,
                    language=source.language,
                )
            )
        return articles

    @staticmethod
    def _entry_url(entry: Any) -> str:
        link = getattr(entry, "link", "") or ""
        if link:
            return link.strip()
        links = getattr(entry, "links", None) or []
        for item in links:
            href = item.get("href") if isinstance(item, dict) else getattr(item, "href", "")
            if href:
                return href.strip()
        return ""
