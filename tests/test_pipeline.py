"""内容管线测试。"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.models import Article, Category
from src.pipeline import pipeline
from src.pipeline.classifier import ArticleClassifier, display_title, rule_classify
from src.pipeline.daily_report import DailyReportBuilder, ReportStats
from src.pipeline.summarizer import ArticleSummarizer
from src.pipeline.translator import ArticleTranslator

NOW = datetime(2026, 7, 25, 7, 5, tzinfo=timezone.utc)


def make_article(
    article_id: str,
    title: str,
    *,
    language: str = "zh",
    source_name: str = "量子位",
    source_id: str = "qbitai",
    summary_raw: str | None = None,
    content: str | None = None,
    score: float = 85.0,
    category: Category | None = None,
) -> Article:
    return Article(
        id=article_id,
        title=title,
        url=f"https://example.com/{article_id}",
        source_id=source_id,
        source_name=source_name,
        summary_raw=summary_raw,
        content=content or "正文内容 " * 50,
        published_at=NOW,
        fetched_at=NOW,
        language=language,
        score=score,
        category=category,
    )


SAMPLE_ARTICLES = [
    make_article("a1", "OpenAI Releases GPT-5 Preview", language="en", source_name="OpenAI Blog", source_id="openai-blog", summary_raw="Math reasoning improves 40 percent", score=92),
    make_article("a2", "字节跳动推出豆包大模型 2.0", source_name="量子位", score=88, category=Category.AI_MODELS),
    make_article("a3", "Copilot 企业版发布新 API 功能", source_name="TechCrunch AI", source_id="techcrunch-ai", score=80, category=Category.AI_PRODUCTS),
    make_article("a4", "OpenAI 完成新一轮融资", source_name="36氪 AI", source_id="36kr-ai", score=78, category=Category.INDUSTRY),
    make_article("a5", "arXiv 新论文提出 SOTA benchmark", source_name="arXiv AI", source_id="arxiv-ai", score=75, category=Category.PAPER),
    make_article("a6", "如何构建 RAG 系统的实用教程", source_name="少数派", source_id="sspai", score=70, category=Category.TIP),
]

REPORT_STATS = ReportStats(
    report_date=date(2026, 7, 25),
    generated_at=NOW,
    sources_success=48,
    sources_total=52,
    raw_count=203,
    l1_count=62,
    l2_count=6,
    snr=0.032,
    quality_rate=0.88,
    l1_pass_rate=0.305,
    failed_sources=["知乎热榜", "百度AI", "阿里达摩院", "arXiv CV"],
)


async def mock_chat_completion(prompt: str, **kwargs) -> str:
    if "英文 AI 新闻标题" in prompt:
        if "GPT-5" in prompt:
            return "OpenAI 发布 GPT-5 Preview"
        return "翻译标题"
    if "英文 AI 新闻摘要" in prompt:
        return "数学推理能力提升 40%"
    if "一句话" in prompt and "总结" in prompt:
        return "OpenAI 发布 GPT-5 Preview，数学推理能力提升 40%，支持更长上下文。"
    if "TOP 3" in prompt:
        return json.dumps(
            [
                {"id": "a1", "reason": "OpenAI 发布 GPT-5，行业格局生变"},
                {"id": "a2", "reason": "豆包 2.0 中文能力领先"},
                {"id": "a3", "reason": "Copilot 企业 API 升级"},
            ],
            ensure_ascii=False,
        )
    if "选题" in prompt:
        return json.dumps(
            [
                {
                    "title": "GPT-5 vs 豆包 2.0：2026 年中大模型格局",
                    "reason": "两大模型同日更新，值得深度对比",
                    "sources": ["OpenAI Blog", "量子位"],
                }
            ],
            ensure_ascii=False,
        )
    if "碎碎念" in prompt or "知识侦察兵" in prompt:
        return "今天最让我兴奋的是 GPT-5 把数学推理单独拎出来讲，这意味着下一代 Copilot 可能迎来质变。"
    if "分类" in prompt:
        return "ai-models"
    return "默认回复"


@pytest.mark.asyncio
@patch("src.pipeline.translator.chat_completion", new=AsyncMock(side_effect=mock_chat_completion))
async def test_translator_translates_english_and_skips_chinese() -> None:
    translator = ArticleTranslator()
    articles = [
        SAMPLE_ARTICLES[0],
        SAMPLE_ARTICLES[1],
    ]
    results = await translator.translate_articles(articles)

    assert results[0].title_cn == "OpenAI 发布 GPT-5 Preview"
    assert results[0].summary_cn == "数学推理能力提升 40%"
    assert results[1].title_cn is None
    assert results[1].summary_cn is None


def test_rule_classify_categories() -> None:
    assert rule_classify("OpenAI 发布新 LLM 模型，参数达 1 万亿", "训练架构更新", "openai-blog") == Category.AI_MODELS
    assert rule_classify("Copilot 企业版正式上线新 API", "产品功能更新", "techcrunch-ai") == Category.AI_PRODUCTS
    assert rule_classify("OpenAI 完成 100 亿美元融资", "", "techcrunch-ai") == Category.INDUSTRY
    assert rule_classify("ACL 2026 论文提出新 SOTA benchmark", "arxiv 研究", "arxiv-ai") == Category.PAPER
    assert rule_classify("RAG 系统构建实用教程", "经验分享", "sspai") == Category.TIP


@pytest.mark.asyncio
@patch("src.pipeline.classifier.chat_completion", new=AsyncMock(side_effect=mock_chat_completion))
async def test_classifier_uses_llm_when_rule_unsure() -> None:
    classifier = ArticleClassifier()
    article = make_article("x1", "Weekly AI roundup highlights", language="en", summary_raw="Various updates this week")
    result = await classifier.classify_article(article)
    assert result.category == Category.AI_MODELS


@pytest.mark.asyncio
@patch("src.pipeline.summarizer.chat_completion", new=AsyncMock(side_effect=mock_chat_completion))
async def test_summarizer_generates_one_line_summary() -> None:
    summarizer = ArticleSummarizer()
    article = SAMPLE_ARTICLES[1]
    result = await summarizer.summarize_article(article)
    assert result.summary
    assert len(result.summary) >= 10


@pytest.mark.asyncio
@patch("src.pipeline.daily_report.chat_completion", new=AsyncMock(side_effect=mock_chat_completion))
async def test_daily_report_contains_all_sections() -> None:
    articles = []
    for article in SAMPLE_ARTICLES:
        articles.append(
            article.model_copy(
                update={
                    "title_cn": article.title_cn or (article.title if article.language == "zh" else "OpenAI 发布 GPT-5 Preview"),
                    "summary": "一句话核心看点示例。",
                }
            )
        )

    builder = DailyReportBuilder()
    markdown = await builder.build(articles, stats=REPORT_STATS)

    assert markdown.startswith("---")
    assert "date: 2026-07-25" in markdown
    assert "filter_efficiency: 0.032" in markdown
    assert "l2_quality: 0.880" in markdown
    assert "# AI 日报 2026-07-25" in markdown
    assert "## 📌 今日 TOP 3" in markdown
    assert "## 🤖 模型发布/更新" in markdown
    assert "## 📦 产品发布/更新" in markdown
    assert "## 📊 行业动态" in markdown
    assert "## 📝 论文研究" in markdown
    assert "## 💡 技巧与观点" in markdown
    assert "## 🎬 博主选题池" in markdown
    assert "## 💭 今日碎碎念" in markdown
    assert "## 🔍 系统自检" in markdown
    assert "GPT-5" in markdown
    assert "知识侦察兵 v2.0" in markdown


def test_display_title_prefers_chinese_translation() -> None:
    article = SAMPLE_ARTICLES[0].model_copy(update={"title_cn": "OpenAI 发布 GPT-5 Preview"})
    assert display_title(article) == "OpenAI 发布 GPT-5 Preview"


def test_format_top3_event_keeps_at_least_30_chars() -> None:
    article = SAMPLE_ARTICLES[0].model_copy(
        update={
            "title_cn": "Anthropic 向 Claude 合作伙伴网络投资 1 亿美元",
            "score": 95,
        }
    )
    event = DailyReportBuilder._format_top3_event(article, reason="Anthropic")
    assert len(event) >= 30
    assert "Anthropic" in event


@pytest.mark.asyncio
@patch("src.pipeline.daily_report.chat_completion", new=AsyncMock(side_effect=mock_chat_completion))
@patch("src.pipeline.summarizer.chat_completion", new=AsyncMock(side_effect=mock_chat_completion))
@patch("src.pipeline.classifier.chat_completion", new=AsyncMock(side_effect=mock_chat_completion))
@patch("src.pipeline.translator.chat_completion", new=AsyncMock(side_effect=mock_chat_completion))
async def test_pipeline_end_to_end() -> None:
    markdown, deep_results, _processed = await pipeline(
        SAMPLE_ARTICLES,
        report_stats=REPORT_STATS,
        skip_deep_analysis=True,
    )
    assert "# AI 日报 2026-07-25" in markdown
    assert "OpenAI 发布 GPT-5 Preview" in markdown
    assert "## 🤖 模型发布/更新" in markdown
    assert deep_results == []
