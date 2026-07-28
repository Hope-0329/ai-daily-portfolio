"""信源层单元与集成测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.models import Source, SourceType
from src.sources.api import APICollector
from src.sources.registry import SourceRegistry, load_sources
from src.sources.rss import RSSCollector

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = PROJECT_ROOT / "data" / "sources.yaml"
REMOVED_BROKEN_SOURCE_IDS = frozenset({"microsoft-ai", "jiqizhixin", "tencent-ai-lab"})


def test_registry_loads_all_sources() -> None:
    registry = SourceRegistry(SOURCES_PATH)
    all_sources = registry.get_all_sources()
    enabled = registry.get_enabled_sources()
    assert len(all_sources) == len(enabled)
    assert len(load_sources(SOURCES_PATH)) == len(enabled)
    assert all(source.enabled for source in enabled)


def test_broken_sources_removed_from_yaml() -> None:
    registry = SourceRegistry(SOURCES_PATH)
    source_ids = {source.id for source in registry.get_all_sources()}
    assert REMOVED_BROKEN_SOURCE_IDS.isdisjoint(source_ids)


def test_aihot_source_is_registered() -> None:
    registry = SourceRegistry(SOURCES_PATH)
    aihot = next(source for source in registry.get_enabled_sources() if source.id == "aihot")
    assert aihot.type == SourceType.API
    assert "aihot.virxact.com" in aihot.url
    assert aihot.api_headers.get("User-Agent", "").startswith("aihot-skill/")


def test_registry_respects_min_tier() -> None:
    registry = SourceRegistry(SOURCES_PATH)
    tier1_sources = registry.get_enabled_sources(min_tier=1)
    assert len(tier1_sources) == sum(1 for s in registry.get_enabled_sources() if s.tier == 1)
    assert all(source.tier == 1 for source in tier1_sources)


def test_registry_finds_qbitai_source() -> None:
    registry = SourceRegistry(SOURCES_PATH)
    qbitai = next(source for source in registry.get_enabled_sources() if source.id == "qbitai")
    assert qbitai.type == SourceType.RSS
    assert qbitai.url == "https://www.qbitai.com/feed"


def test_huxiu_uses_rsshub_mirror() -> None:
    registry = SourceRegistry(SOURCES_PATH)
    huxiu = next(source for source in registry.get_enabled_sources() if source.id == "huxiu-ai")
    assert huxiu.type == SourceType.RSSHUB
    assert "rsshub" in huxiu.url
    assert huxiu.fetch_timeout == 45


@pytest.mark.asyncio
async def test_rss_collector_fetches_qbitai() -> None:
    registry = SourceRegistry(SOURCES_PATH)
    qbitai = next(source for source in registry.get_enabled_sources() if source.id == "qbitai")
    collector = RSSCollector()
    articles = await collector.fetch(qbitai)
    assert len(articles) > 0
    assert all(article.url for article in articles)
    assert all(article.title for article in articles)
    assert all(article.source_id == "qbitai" for article in articles)


@pytest.mark.asyncio
async def test_api_collector_fetches_github_trending() -> None:
    source = Source(
        id="github-trending",
        name="GitHub Trending",
        name_display="GitHub Trending",
        url="https://api.github.com/search/repositories?q=topic:artificial-intelligence+created:>7d&sort=stars&order=desc",
        type=SourceType.API,
        tier=1,
        language="en",
    )
    collector = APICollector()
    articles = await collector.fetch(source)
    assert isinstance(articles, list)
    assert len(articles) > 0
    assert all(article.url.startswith("https://github.com/") for article in articles)


@pytest.mark.asyncio
async def test_rss_collector_retries_on_429(monkeypatch) -> None:
    """429 限流时应等待后重试，而非立即失败。"""
    from unittest.mock import AsyncMock

    import aiohttp

    from src.config import Settings
    from src.sources.rss import RATE_LIMIT_RETRY_DELAY, RSSCollector

    source = Source(
        id="import-ai",
        name="Import AI",
        name_display="Import AI",
        url="https://example.com/feed",
        type=SourceType.RSS,
        tier=2,
        language="en",
    )
    settings = Settings(fetch_retry_count=1)
    collector = RSSCollector(settings=settings)

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr("src.sources.rss.asyncio.sleep", fake_sleep)

    call_count = 0

    async def fake_download(_source: Source, *, verify_ssl: bool) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise aiohttp.ClientResponseError(
                request_info=AsyncMock(),
                history=(),
                status=429,
                message="Too Many Requests",
            )
        return "<?xml version='1.0'?><rss><channel><item><title>Test</title><link>https://example.com/a</link></item></channel></rss>"

    monkeypatch.setattr(collector, "_download_feed", fake_download)

    articles = await collector.fetch(source)
    assert len(articles) == 1
    assert call_count == 2
    assert RATE_LIMIT_RETRY_DELAY in sleep_calls
