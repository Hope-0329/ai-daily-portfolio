"""AIHOT URL 去重测试。"""

from __future__ import annotations

from datetime import datetime, timezone

from src.filter.dedup import dedupe_aihot_by_url, normalize_url
from src.models import Article

NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)


def _article(
    article_id: str,
    url: str,
    *,
    source_id: str = "qbitai",
    source_name: str = "量子位",
    score: float = 70.0,
) -> Article:
    return Article(
        id=article_id,
        title=f"标题 {article_id}",
        url=url,
        source_id=source_id,
        source_name=source_name,
        fetched_at=NOW,
        score=score,
    )


def test_normalize_url_strips_www_and_trailing_slash() -> None:
    assert normalize_url("HTTPS://WWW.Example.com/path/") == "https://example.com/path"


def test_dedup_keeps_self_collected_when_urls_match() -> None:
    self_article = _article("self", "https://example.com/news/gpt5", score=85.0)
    aihot_article = _article(
        "aihot",
        "https://www.example.com/news/gpt5/",
        source_id="aihot",
        source_name="OpenAI Blog",
        score=92.0,
    )
    result = dedupe_aihot_by_url([aihot_article, self_article])
    assert len(result) == 1
    assert result[0].source_id == "qbitai"
    assert result[0].score == 85.0


def test_dedup_keeps_both_when_urls_differ() -> None:
    a = _article("a1", "https://example.com/a")
    b = _article("b1", "https://example.com/b", source_id="aihot", source_name="TechCrunch")
    result = dedupe_aihot_by_url([a, b])
    assert len(result) == 2
