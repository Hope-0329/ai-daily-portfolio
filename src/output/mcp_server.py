"""MCP 风格工具接口（可被 FastAPI 或 QClaw 调用）。"""

from __future__ import annotations

from typing import Any

from src.config import Settings, get_settings
from src.database import (
    get_article,
    get_connection,
    get_sources_health_summary,
    init_db,
    query_articles,
)
from src.models import Article
from src.output.obsidian import ObsidianWriter
from src.pipeline.deep_analysis import DeepAnalyzer
from src.sources.registry import SourceRegistry


async def list_sources_tool(settings: Settings | None = None) -> dict[str, Any]:
    """列出所有信源及健康状态。"""
    cfg = settings or get_settings()
    init_db(cfg)
    with get_connection(cfg) as conn:
        sources = get_sources_health_summary(conn, days=7)
    return {"sources": sources, "total": len(sources)}


async def fetch_news_tool(
    *,
    limit: int = 20,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """拉取最新 AI 新闻（从数据库读取已采集内容）。"""
    cfg = settings or get_settings()
    init_db(cfg)
    with get_connection(cfg) as conn:
        items, total = query_articles(conn, mode="selected", window="24h", page=1, page_size=limit)
    return {"items": items, "total": total}


async def deep_read_tool(
    article_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """对指定文章做深度解读。"""
    cfg = settings or get_settings()
    init_db(cfg)
    with get_connection(cfg) as conn:
        row = get_article(conn, article_id)
    if row is None:
        return {"error": f"文章不存在: {article_id}"}

    article = Article(
        id=row["id"],
        title=row["title"],
        title_cn=row.get("title_cn"),
        url=row["url"],
        source_id=row["source_id"],
        source_name=row["source_name"],
        summary=row.get("summary"),
        summary_raw=row.get("summary"),
        content=row.get("summary"),
        published_at=None,
        fetched_at=row["fetched_at"],
        language=row.get("language"),
        score=float(row.get("score") or 0),
    )
    analyzer = DeepAnalyzer(settings=cfg)
    content = await analyzer.fetch_full_content(article)
    analysis = await analyzer.deep_analyze(article, content)
    return {"article_id": article_id, "title": article.title, "analysis": analysis}


async def save_to_obsidian_tool(
    date_str: str,
    markdown: str,
    *,
    title: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """保存 Markdown 内容到 Obsidian。"""
    cfg = settings or get_settings()
    writer = ObsidianWriter(cfg.obsidian_root, index_filename=cfg.index_filename)
    if title:
        path = writer.write_deep_analysis(date_str, title, markdown)
    else:
        path = writer.write_daily_report(date_str, markdown)
    return {"filepath": path}


async def trigger_fetch_tool(
    *,
    tier: int = 3,
    limit_sources: int | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """触发信源采集并写入数据库。"""
    cfg = settings or get_settings()
    registry = SourceRegistry(cfg.sources_config, settings=cfg)
    sources = registry.get_enabled_sources(min_tier=tier)
    if limit_sources is not None:
        sources = sources[:limit_sources]
    results = await registry.fetch_all(sources)
    total_articles = sum(len(items) for items in results.values())
    return {
        "sources_fetched": len(results),
        "articles_count": total_articles,
        "source_ids": list(results.keys()),
    }
