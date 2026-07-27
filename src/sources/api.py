"""API 类型信源采集器。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from src.config import Settings, get_settings
from src.models import Article, Source
from src.sources.base import SourceCollector
from src.sources.utils import USER_AGENT, matches_ai_keywords, url_hash, utc_now

logger = logging.getLogger(__name__)

HN_BASE = "https://hacker-news.firebaseio.com/v0"
GITHUB_SEARCH = "https://api.github.com/search/repositories"


class APICollector(SourceCollector):
    """GitHub Trending、Hacker News、HuggingFace Papers 等 API 采集器。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def fetch(self, source: Source) -> list[Article]:
        """根据信源 ID 路由到对应 API 采集逻辑。"""
        if source.id == "github-trending":
            return await self._fetch_github_trending(source)
        if source.id == "hacker-news":
            return await self._fetch_hacker_news(source)
        if source.id == "huggingface-papers":
            return await self._fetch_huggingface_papers(source)
        raise ValueError(f"未支持的 API 信源: {source.id}")

    async def _fetch_github_trending(self, source: Source) -> list[Article]:
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        query = (
            "topic:artificial-intelligence+topic:machine-learning+"
            f"created:>{since}&sort=stars&order=desc&per_page=20"
        )
        url = f"{GITHUB_SEARCH}?q={query}"
        payload = await self._get_json(url, accept="application/vnd.github+json", source=source)
        items = payload.get("items") or []
        fetched_at = utc_now()
        articles: list[Article] = []
        for repo in items[:20]:
            repo_url = repo.get("html_url") or ""
            name = repo.get("full_name") or repo.get("name") or ""
            if not repo_url or not name:
                continue
            description = repo.get("description") or ""
            stars = repo.get("stargazers_count", 0)
            summary_raw = f"{description} (⭐ {stars})".strip()
            articles.append(
                Article(
                    id=url_hash(repo_url),
                    title=name,
                    url=repo_url,
                    source_id=source.id,
                    source_name=source.name,
                    summary_raw=summary_raw or None,
                    published_at=self._parse_github_datetime(repo.get("created_at")),
                    fetched_at=fetched_at,
                    language=source.language,
                )
            )
        return articles

    async def _fetch_hacker_news(self, source: Source) -> list[Article]:
        story_ids = await self._get_json(f"{HN_BASE}/topstories.json")
        if not isinstance(story_ids, list):
            return []
        top_ids = story_ids[:30]
        fetched_at = utc_now()
        articles: list[Article] = []

        async def fetch_item(story_id: int) -> Article | None:
            item = await self._get_json(f"{HN_BASE}/item/{story_id}.json")
            title = (item.get("title") or "").strip()
            url = item.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
            if not title or not matches_ai_keywords(title):
                return None
            return Article(
                id=url_hash(url),
                title=title,
                url=url,
                source_id=source.id,
                source_name=source.name,
                summary_raw=f"HN score: {item.get('score', 0)}",
                published_at=self._hn_timestamp(item.get("time")),
                fetched_at=fetched_at,
                language=source.language,
            )

        results = await asyncio.gather(*(fetch_item(story_id) for story_id in top_ids), return_exceptions=True)
        for result in results:
            if isinstance(result, Article):
                articles.append(result)
            elif isinstance(result, Exception):
                logger.debug("HN 条目拉取失败: %s", result)
        return articles

    async def _fetch_huggingface_papers(self, source: Source) -> list[Article]:
        payload = await self._get_json(source.url, source=source)
        fetched_at = utc_now()
        papers: list[Any]
        if isinstance(payload, list):
            papers = payload
        elif isinstance(payload, dict):
            papers = payload.get("papers") or payload.get("daily_papers") or []
        else:
            papers = []

        articles: list[Article] = []
        for entry in papers:
            paper = entry.get("paper", entry) if isinstance(entry, dict) else {}
            title = (paper.get("title") or entry.get("title") or "").strip()
            paper_id = paper.get("id") or entry.get("id") or title
            url = paper.get("url") or f"https://huggingface.co/papers/{paper_id}"
            if not title:
                continue
            summary_raw = paper.get("summary") or paper.get("abstract") or entry.get("summary") or ""
            articles.append(
                Article(
                    id=url_hash(url),
                    title=title,
                    url=url,
                    source_id=source.id,
                    source_name=source.name,
                    summary_raw=str(summary_raw)[:1000] or None,
                    published_at=fetched_at,
                    fetched_at=fetched_at,
                    language=source.language,
                )
            )
        return articles

    async def _get_json(
        self,
        url: str,
        *,
        accept: str = "application/json",
        source: Source | None = None,
    ) -> Any:
        last_error: Exception | None = None
        timeout_sec = (source.fetch_timeout if source else None) or self.settings.fetch_timeout
        max_attempts = self.settings.fetch_retry_count + 1
        for attempt in range(max_attempts):
            try:
                timeout = aiohttp.ClientTimeout(total=timeout_sec)
                headers = {"User-Agent": USER_AGENT, "Accept": accept}
                async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                    async with session.get(url) as response:
                        response.raise_for_status()
                        return await response.json()
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    logger.warning(
                        "API 请求失败（第 %s 次），%ss 后重试: %s",
                        attempt + 1,
                        self.settings.fetch_retry_delay,
                        url,
                    )
                    await asyncio.sleep(self.settings.fetch_retry_delay)
        raise RuntimeError(f"API 请求失败: {url}") from last_error

    @staticmethod
    def _parse_github_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _hn_timestamp(value: int | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromtimestamp(value, tz=timezone.utc)
