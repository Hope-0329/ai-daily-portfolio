"""深度解读引擎测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.models import Article
from src.output.obsidian import ObsidianWriter
from src.pipeline import pipeline
from src.pipeline.deep_analysis import DeepAnalyzer, extract_main_html, html_to_text

NOW = datetime(2026, 7, 25, 7, 0, tzinfo=timezone.utc)

SAMPLE_HTML = """
<html>
  <head><title>Test Page</title><script>console.log('x')</script></head>
  <body>
    <nav>导航栏</nav>
    <article>
      <h1>OpenAI 发布 GPT-5 Preview</h1>
      <p>数学推理能力提升 40%，支持 10 万 token 上下文窗口。</p>
      <p>这是第二段正文，包含更多细节和数据。</p>
    </article>
    <footer>页脚信息</footer>
  </body>
</html>
"""

MOCK_ANALYSIS = """## 📋 一句话总结
> OpenAI 发布 GPT-5 Preview，数学推理能力显著提升。

## 🔑 核心要点
1. **推理能力提升**：数学推理能力提升 40%。
2. **上下文扩展**：支持 10 万 token 上下文。
3. **行业影响**：可能重塑 Copilot 类产品体验。

## 📊 背景与上下文
GPT 系列持续迭代，本次 Preview 聚焦推理能力而非参数规模竞赛。

## 💡 深度分析
这意味着 OpenAI 正在从 benchmark 竞争转向实用能力竞争，开发者生态将率先受益。

## 🔗 延伸阅读
- OpenAI 官方博客

---

> 分析时间：2026-07-25 15:00
> 原文链接：https://example.com/a1
"""


def make_article(
    article_id: str,
    title: str,
    *,
    score: float,
    merged_from: list[str] | None = None,
    url: str = "https://example.com/article",
    content: str | None = None,
) -> Article:
    return Article(
        id=article_id,
        title=title,
        url=url,
        source_id="qbitai",
        source_name="量子位",
        summary_raw="摘要",
        content=content,
        published_at=NOW,
        fetched_at=NOW,
        language="zh",
        score=score,
        merged_from=merged_from or [],
    )


def test_select_candidates_priority() -> None:
    analyzer = DeepAnalyzer()
    articles = [
        make_article("a1", "多源高分", score=92, merged_from=["m1", "m2", "m3"]),
        make_article("a2", "单源高分", score=88),
        make_article("a3", "中分补充", score=72),
        make_article("a4", "低分", score=55),
    ]
    candidates = analyzer.select_candidates(articles)
    assert 1 <= len(candidates) <= 3
    assert candidates[0].id == "a1"


def test_html_extraction_and_cleaning() -> None:
    main_html = extract_main_html(SAMPLE_HTML)
    text = html_to_text(main_html, limit=6000)
    assert "GPT-5 Preview" in text
    assert "数学推理能力提升 40%" in text
    assert "导航栏" not in text
    assert "页脚信息" not in text
    assert "console.log" not in text


@pytest.mark.asyncio
async def test_fetch_full_content_from_html_fixture() -> None:
    async def mock_fetcher(article: Article) -> str:
        return html_to_text(extract_main_html(SAMPLE_HTML))

    analyzer = DeepAnalyzer(fetcher=mock_fetcher)
    article = make_article("f1", "测试文章", score=90)
    content = await analyzer.fetch_full_content(article)
    assert "GPT-5 Preview" in content
    assert len(content) > 20


@pytest.mark.asyncio
@patch("src.pipeline.deep_analysis.chat_completion", new=AsyncMock(return_value=MOCK_ANALYSIS))
async def test_deep_analyze_returns_structured_markdown() -> None:
    analyzer = DeepAnalyzer()
    article = make_article("d1", "OpenAI 发布 GPT-5 Preview", score=90)
    result = await analyzer.deep_analyze(article, "正文内容 " * 100)
    assert "## 📋 一句话总结" in result
    assert "## 🔑 核心要点" in result
    assert "## 📊 背景与上下文" in result
    assert "## 💡 深度分析" in result
    assert "## 🔗 延伸阅读" in result


@pytest.mark.asyncio
@patch("src.pipeline.deep_analysis.chat_completion", new=AsyncMock(return_value=MOCK_ANALYSIS))
async def test_analyzer_run_end_to_end() -> None:
    async def mock_fetcher(article: Article) -> str:
        return html_to_text(extract_main_html(SAMPLE_HTML))

    analyzer = DeepAnalyzer(fetcher=mock_fetcher)
    articles = [
        make_article("r1", "OpenAI 发布 GPT-5 Preview", score=92, merged_from=["m1", "m2", "m3"]),
        make_article("r2", "其他新闻", score=60),
    ]
    results = await analyzer.run(articles)
    assert len(results) >= 1
    assert results[0]["analysis"]


def test_obsidian_writer_writes_deep_analysis(tmp_path: Path) -> None:
    writer = ObsidianWriter(tmp_path)
    filepath = writer.write_deep_analysis(
        "2026-07-25",
        "GPT-5 Preview 发布",
        MOCK_ANALYSIS,
    )
    path = Path(filepath)
    assert path.exists()
    assert path.parent.name == "深度解读"
    assert path.name.startswith("2026-07-25")
    assert path.read_text(encoding="utf-8") == MOCK_ANALYSIS


@pytest.mark.asyncio
@patch("src.pipeline.deep_analysis.DeepAnalyzer.run", new=AsyncMock(return_value=[{
    "article_id": "a1",
    "title": "GPT-5 Preview 发布",
    "url": "https://example.com/a1",
    "source_name": "量子位",
    "score": 92,
    "merged_count": 4,
    "analysis": MOCK_ANALYSIS,
    "filepath": None,
}]))
@patch("src.pipeline.summarizer.chat_completion", new=AsyncMock(return_value="一句话摘要。"))
@patch("src.pipeline.translator.chat_completion", new=AsyncMock(return_value="翻译"))
async def test_pipeline_returns_markdown_and_deep_results(tmp_path: Path) -> None:
    from src.config import Settings
    from src.pipeline.daily_report import ReportStats

    settings = Settings(obsidian_root=str(tmp_path))
    article = make_article("a1", "GPT-5 Preview 发布", score=92, content="x" * 300)
    stats = ReportStats(report_date=NOW.date(), generated_at=NOW, l2_count=1)

    daily_side_effect = [
        '[{"id":"a1","reason":"重要","rank":1}]',
        '[{"title":"选题","reason":"理由","sources":["量子位"]}]',
        "碎碎念内容。",
    ]

    with patch("src.pipeline.daily_report.chat_completion", new=AsyncMock(side_effect=daily_side_effect)):
        markdown, deep_results, _processed = await pipeline([article], settings=settings, report_stats=stats)

    assert "# AI 日报" in markdown
    assert len(deep_results) == 1
    assert deep_results[0]["filepath"]
    assert Path(deep_results[0]["filepath"]).exists()
