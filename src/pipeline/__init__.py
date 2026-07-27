"""内容管线统一入口。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from openai import AsyncOpenAI

from src.config import Settings, get_settings
from src.models import Article
from src.output.obsidian import ObsidianWriter
from src.pipeline.classifier import ArticleClassifier
from src.pipeline.daily_report import SHANGHAI_TZ, DailyReportBuilder, ReportStats
from src.pipeline.deep_analysis import DeepAnalyzer
from src.pipeline.summarizer import ArticleSummarizer
from src.pipeline.translator import ArticleTranslator


async def pipeline(
    articles: list[Article],
    *,
    settings: Settings | None = None,
    llm_client: AsyncOpenAI | None = None,
    report_stats: ReportStats | None = None,
    skip_deep_analysis: bool = False,
    write_obsidian: bool = True,
) -> tuple[str, list[dict[str, Any]], list[Article]]:
    """
    完整内容管线。

    输入：L2 精选后的 Article 列表
    处理：翻译 → 分类 → 摘要 → 组装日报 → 深度解读
    输出：(日报 Markdown, 深度解读结果列表)
    """
    cfg = settings or get_settings()

    translator = ArticleTranslator(settings=cfg, llm_client=llm_client)
    classifier = ArticleClassifier(settings=cfg, llm_client=llm_client)
    summarizer = ArticleSummarizer(settings=cfg, llm_client=llm_client)
    report_builder = DailyReportBuilder(settings=cfg, llm_client=llm_client)

    translated = await translator.translate_articles(articles)
    classified = await classifier.classify_articles(translated)
    summarized = await summarizer.summarize_articles(classified)

    if report_stats is None:
        now = datetime.now(timezone.utc)
        report_stats = ReportStats(
            report_date=now.astimezone(SHANGHAI_TZ).date(),
            generated_at=now,
            l2_count=len(summarized),
        )

    markdown = await report_builder.build(summarized, stats=report_stats)

    deep_results: list[dict[str, Any]] = []
    if not skip_deep_analysis and summarized:
        analyzer = DeepAnalyzer(settings=cfg, llm_client=llm_client)
        deep_results = await analyzer.run(summarized)
        if write_obsidian:
            writer = ObsidianWriter(cfg.obsidian_root, index_filename=cfg.index_filename)
            date_str = report_stats.report_date.isoformat()
            for result in deep_results:
                result["filepath"] = writer.write_deep_analysis(
                    date_str,
                    result["title"],
                    result["analysis"],
                )

    return markdown, deep_results, summarized


__all__ = ["pipeline", "ReportStats"]
