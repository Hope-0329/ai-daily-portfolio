"""AIHOT 公开 API 采集器。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp

from src.config import Settings, get_settings
from src.models import Article, Category, Source
from src.sources.base import SourceCollector
from src.sources.utils import url_hash, utc_now

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "aihot-skill/1.2.0 (+https://aihot.virxact.com/aihot-skill/)"

AIHOT_CATEGORY_MAP: dict[str, Category] = {
    "model": Category.AI_MODELS,
    "product": Category.AI_PRODUCTS,
    "industry": Category.INDUSTRY,
    "paper": Category.PAPER,
    "tips": Category.TIP,
    "tip": Category.TIP,
}


class AIHOTCollector(SourceCollector):
    """AIHOT 热点聚合 API 采集器。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def fetch(self, source: Source) -> list[Article]:
        """拉取 AIHOT 24h 精选；失败时仅 warning，返回空列表。"""
        try:
            return await self._fetch_items(source)
        except Exception as exc:
            logger.warning("AIHOT 采集失败（不影响其他信源）: %s", exc)
            return []

    async def _fetch_items(self, source: Source) -> list[Article]:
        payload = await self._get_json(source.url, source=source)
        items = payload.get("items") if isinstance(payload, dict) else []
        if not isinstance(items, list):
            return []

        fetched_at = utc_now()
        articles: list[Article] = []
        for entry in items:
            article = self._parse_item(entry, source, fetched_at)
            if article is not None:
                articles.append(article)
        return articles

    def _parse_item(self, entry: dict[str, Any], source: Source, fetched_at: datetime) -> Article | None:
        title = (entry.get("title") or "").strip()
        summary = (entry.get("summary") or "").strip()
        links = entry.get("links") or {}
        url = (links.get("original") or entry.get("url") or "").strip()
        if not title or not url:
            return None

        source_info = entry.get("source") or {}
        original_source_name = (source_info.get("name") or "未知信源").strip()
        category = AIHOT_CATEGORY_MAP.get(str(entry.get("category") or "").lower())
        score_raw = entry.get("score")
        try:
            score = float(score_raw) if score_raw is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(100.0, score))

        published_at = self._parse_datetime(entry.get("publishedAt")) or self._parse_datetime(
            entry.get("discoveredAt")
        )

        return Article(
            id=url_hash(url),
            title=title,
            url=url,
            source_id=source.id,
            source_name=original_source_name,
            summary=summary or None,
            summary_raw=summary or None,
            content=summary or None,
            published_at=published_at,
            fetched_at=fetched_at,
            category=category,
            score=score,
            language=source.language,
            pre_summarized=True,
            pre_classified=True,
        )

    async def _get_json(self, url: str, *, source: Source) -> Any:
        headers = {"Accept": "application/json", "User-Agent": DEFAULT_USER_AGENT}
        headers.update(source.api_headers or {})
        last_error: Exception | None = None
        timeout_sec = source.fetch_timeout or self.settings.fetch_timeout
        max_attempts = self.settings.fetch_retry_count + 1
        for attempt in range(max_attempts):
            try:
                timeout = aiohttp.ClientTimeout(total=timeout_sec)
                async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                    async with session.get(url) as response:
                        response.raise_for_status()
                        return await response.json()
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    logger.warning(
                        "AIHOT 请求失败（第 %s 次），%ss 后重试: %s",
                        attempt + 1,
                        self.settings.fetch_retry_delay,
                        url,
                    )
                    await asyncio.sleep(self.settings.fetch_retry_delay)
        raise RuntimeError(f"AIHOT API 请求失败: {url}") from last_error

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            return None
