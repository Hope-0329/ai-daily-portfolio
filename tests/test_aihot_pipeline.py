"""AIHOT pipeline 跳过逻辑测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.models import Article, Category
from src.pipeline.classifier import ArticleClassifier
from src.pipeline.daily_report import DailyReportBuilder
from src.pipeline.summarizer import ArticleSummarizer
from src.pipeline.translator import ArticleTranslator

NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)


def _aihot_article() -> Article:
    return Article(
        id="aihot-1",
        title="OpenAI 发布 GPT-5",
        url="https://openai.com/blog/gpt-5",
        source_id="aihot",
        source_name="OpenAI Blog",
        summary="OpenAI 推出新一代大模型。",
        summary_raw="OpenAI 推出新一代大模型。",
        content="OpenAI 推出新一代大模型。",
        published_at=NOW,
        fetched_at=NOW,
        language="zh",
        category=Category.AI_MODELS,
        score=92.0,
        pre_summarized=True,
        pre_classified=True,
    )


@pytest.mark.asyncio
@patch("src.pipeline.translator.chat_completion", new=AsyncMock(return_value="不应调用"))
async def test_translator_skips_pre_summarized() -> None:
    translator = ArticleTranslator()
    result = await translator.translate_article(_aihot_article())
    assert result.title_cn is None
    assert result.summary_cn is None


@pytest.mark.asyncio
@patch("src.pipeline.classifier.chat_completion", new=AsyncMock(return_value="不应调用"))
async def test_classifier_skips_pre_classified() -> None:
    classifier = ArticleClassifier()
    result = await classifier.classify_article(_aihot_article())
    assert result.category == Category.AI_MODELS


@pytest.mark.asyncio
@patch("src.pipeline.summarizer.chat_completion", new=AsyncMock(return_value="不应调用"))
async def test_summarizer_skips_pre_summarized() -> None:
    summarizer = ArticleSummarizer()
    result = await summarizer.summarize_article(_aihot_article())
    assert result.summary == "OpenAI 推出新一代大模型。"


def test_daily_report_formats_aihot_source_name() -> None:
    article = _aihot_article()
    assert DailyReportBuilder.format_source_name(article) == "AIHOT · OpenAI Blog"
