"""端到端流程测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.models import Article, Category
from src.scheduler.jobs import daily_job, flatten_results

NOW = datetime(2026, 7, 26, 7, 0, tzinfo=timezone.utc)


def make_article(article_id: str, title: str, *, score: float = 85.0) -> Article:
    return Article(
        id=article_id,
        title=title,
        url=f"https://example.com/{article_id}",
        source_id="qbitai",
        source_name="量子位",
        summary_raw="摘要内容",
        content="正文 " * 200,
        published_at=NOW,
        fetched_at=NOW,
        language="zh",
        score=score,
        category=Category.AI_MODELS,
    )


MOCK_MARKDOWN = """# AI 日报 2026-07-26（周日）

## 📌 今日 TOP 3
| # | 事件 | 信源 | 评分 |

## 🎬 博主选题池
选题

## 💭 今日碎碎念
碎碎念
"""

MOCK_FILTERED = {
    "l2_results": [make_article("e1", "OpenAI 发布 GPT-5", score=92)],
    "snr": {"filter_efficiency": 0.1, "l2_quality": 0.85, "l1_pass_rate": 0.3},
    "stats": {"raw_count": 10, "l1_pass_count": 5, "l2_count": 1},
}


@pytest.mark.asyncio
async def test_full_pipeline(tmp_path, monkeypatch) -> None:
    """完整端到端流程（Mock 采集与 LLM）。"""
    monkeypatch.setenv("OBSIDIAN_ROOT", str(tmp_path))
    from src.config import Settings

    settings = Settings(
        obsidian_root=str(tmp_path),
        db_path=tmp_path / "e2e.db",
    )

    fetch_results = {
        "qbitai": [make_article("e1", "OpenAI 发布 GPT-5", score=92)],
        "openai-blog": [make_article("e2", "GPT-5 Preview", score=90)],
        "techcrunch-ai": [make_article("e3", "Copilot 更新", score=80)],
    }

    with (
        patch("src.scheduler.jobs.SourceRegistry") as registry_cls,
        patch("src.scheduler.jobs.filter_pipeline", new=AsyncMock(return_value=MOCK_FILTERED)),
        patch(
            "src.scheduler.jobs.pipeline",
            new=AsyncMock(return_value=(MOCK_MARKDOWN, [{
                "title": "OpenAI 发布 GPT-5",
                "analysis": "## 📋 一句话总结\n> 测试",
            }], MOCK_FILTERED["l2_results"])),
        ),
    ):
        registry = registry_cls.return_value
        registry.get_enabled_sources.return_value = list(fetch_results.keys())
        registry.fetch_all = AsyncMock(return_value=fetch_results)

        result = await daily_job(settings)

    assert flatten_results(fetch_results)
    assert result["report"]
    assert Path(result["report"]).exists()
    assert "AI 日报" in Path(result["report"]).read_text(encoding="utf-8")
    assert result["deep_count"] >= 1
