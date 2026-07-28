"""AIHOT 采集器单元测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.models import Category, Source, SourceType
from src.sources.aihot import AIHOTCollector

SAMPLE_PAYLOAD = {
    "items": [
        {
            "title": "OpenAI 发布 GPT-5",
            "summary": "OpenAI 推出新一代大模型，推理能力显著提升。",
            "category": "model",
            "score": 92,
            "source": {"name": "OpenAI Blog"},
            "links": {
                "original": "https://openai.com/blog/gpt-5",
                "aihot": "https://aihot.virxact.com/item/abc",
            },
            "publishedAt": "2026-07-26T08:00:00Z",
        },
        {
            "title": "Copilot 企业版更新",
            "summary": "微软为企业用户推出新 API 能力。",
            "category": "product",
            "score": 80,
            "source": {"name": "Microsoft Blog"},
            "links": {"original": "https://microsoft.com/copilot-update"},
            "discoveredAt": "2026-07-26T09:00:00+00:00",
        },
    ],
    "cursor": None,
}

AIHOT_SOURCE = Source(
    id="aihot",
    name="AIHOT",
    name_display="AIHOT",
    url="https://aihot.virxact.com/api/v1/items?mode=selected&window=24h",
    type=SourceType.API,
    tier=1,
    language="zh",
)


@pytest.mark.asyncio
async def test_aihot_collector_maps_fields() -> None:
    collector = AIHOTCollector()
    with patch.object(collector, "_get_json", new=AsyncMock(return_value=SAMPLE_PAYLOAD)):
        articles = await collector.fetch(AIHOT_SOURCE)

    assert len(articles) == 2
    first = articles[0]
    assert first.title == "OpenAI 发布 GPT-5"
    assert first.summary == "OpenAI 推出新一代大模型，推理能力显著提升。"
    assert first.url == "https://openai.com/blog/gpt-5"
    assert first.category == Category.AI_MODELS
    assert first.score == 92.0
    assert first.source_id == "aihot"
    assert first.source_name == "OpenAI Blog"
    assert first.pre_summarized is True
    assert first.pre_classified is True
    assert first.content == first.summary
    assert first.published_at == datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)

    second = articles[1]
    assert second.category == Category.AI_PRODUCTS
    assert second.published_at == datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_aihot_collector_returns_empty_on_failure() -> None:
    collector = AIHOTCollector()
    with patch.object(collector, "_get_json", new=AsyncMock(side_effect=RuntimeError("503"))):
        articles = await collector.fetch(AIHOT_SOURCE)
    assert articles == []
