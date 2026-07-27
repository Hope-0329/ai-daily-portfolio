"""网页 HTML 采集器（RSS/API 不可用时的备用方案）。"""

from __future__ import annotations

import asyncio
import logging
import re

import aiohttp
from bs4 import BeautifulSoup

from src.config import Settings, get_settings
from src.models import Article, Source
from src.sources.base import SourceCollector
from src.sources.utils import USER_AGENT, strip_html, url_hash, utc_now

logger = logging.getLogger(__name__)


class WebCollector(SourceCollector):
    """通过 HTML 页面提取标题与摘要。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def fetch(self, source: Source) -> list[Article]:
        """拉取网页并提取 meta 信息作为单篇文章返回。"""
        last_error: Exception | None = None
        max_attempts = self.settings.fetch_retry_count + 1
        for attempt in range(max_attempts):
            verify_ssl = attempt == 0
            try:
                html = await self._download_html(source, verify_ssl=verify_ssl)
                return self._parse_html(source, html)
            except aiohttp.ClientSSLError as exc:
                last_error = exc
                logger.warning("网页信源 %s SSL 校验失败，尝试跳过证书验证", source.id)
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    logger.warning(
                        "网页信源 %s 拉取失败（第 %s 次），%ss 后重试: %s",
                        source.id,
                        attempt + 1,
                        self.settings.fetch_retry_delay,
                        exc,
                    )
                    await asyncio.sleep(self.settings.fetch_retry_delay)
        raise RuntimeError(f"网页拉取失败: {source.id}") from last_error

    async def _download_html(self, source: Source, *, verify_ssl: bool) -> str:
        timeout_sec = source.fetch_timeout or self.settings.fetch_timeout
        timeout = aiohttp.ClientTimeout(total=timeout_sec)
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
        connector = aiohttp.TCPConnector(ssl=verify_ssl)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers, connector=connector) as session:
            async with session.get(source.url) as response:
                response.raise_for_status()
                return await response.text()

    def _parse_html(self, source: Source, html: str) -> list[Article]:
        soup = BeautifulSoup(html, "html.parser")
        title = self._extract_title(soup)
        description = self._extract_description(soup)
        if not title:
            title = source.name
        fetched_at = utc_now()
        return [
            Article(
                id=url_hash(source.url),
                title=title,
                url=source.url,
                source_id=source.id,
                source_name=source.name,
                summary_raw=description,
                fetched_at=fetched_at,
                language=source.language,
            )
        ]

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return og_title["content"].strip()
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        return ""

    @staticmethod
    def _extract_description(soup: BeautifulSoup) -> str | None:
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            return strip_html(og_desc["content"])[:1000]
        meta_desc = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
        if meta_desc and meta_desc.get("content"):
            return strip_html(meta_desc["content"])[:1000]
        return None
