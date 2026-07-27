"""每日定时任务与手动触发入口。"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.config import Settings, ensure_api_key, get_settings
from src.database import (
    get_connection,
    init_db,
    insert_daily_report,
    mark_articles_selected,
)
from src.filter import filter_pipeline
from src.output.obsidian import ObsidianWriter
from src.pipeline import pipeline
from src.pipeline.daily_report import SHANGHAI_TZ, ReportStats
from src.sources.registry import SourceRegistry

logger = logging.getLogger(__name__)


def flatten_results(results: dict[str, list]) -> list:
    """将 {source_id: [articles]} 展平为文章列表。"""
    articles = []
    for items in results.values():
        articles.extend(items)
    return articles


def _build_report_stats(
    filtered: dict[str, Any],
    *,
    sources_success: int,
    sources_total: int,
    failed_sources: list[str],
    report_date: datetime,
) -> ReportStats:
    snr = filtered["snr"]
    stats = filtered["stats"]
    return ReportStats(
        report_date=report_date.date(),
        generated_at=report_date,
        sources_success=sources_success,
        sources_total=sources_total,
        raw_count=stats["raw_count"],
        l1_count=stats["l1_pass_count"],
        l2_count=stats["l2_count"],
        snr=snr["filter_efficiency"],
        quality_rate=snr.get("l2_quality", 0.0),
        l1_pass_rate=snr.get("l1_pass_rate", 0.0),
        failed_sources=failed_sources,
    )


async def daily_job(settings: Settings | None = None) -> dict[str, Any]:
    """每日完整流程：采集 → 过滤 → 管线 → 写入 Obsidian → 记录统计。"""
    cfg = settings or get_settings()
    ensure_api_key(cfg)
    init_db(cfg)

    registry = SourceRegistry(cfg.sources_config, settings=cfg)
    registry.record_disabled_sources()
    enabled_sources = registry.get_enabled_sources()
    results = await registry.fetch_all(enabled_sources)

    all_articles = flatten_results(results)
    sources_success = sum(1 for items in results.values() if items)
    sources_total = len(results)
    failed_sources = [source_id for source_id, items in results.items() if not items]

    filtered = await filter_pipeline(all_articles)
    l2_articles = filtered["l2_results"]

    now = datetime.now(timezone.utc)
    report_stats = _build_report_stats(
        filtered,
        sources_success=sources_success,
        sources_total=sources_total,
        failed_sources=failed_sources,
        report_date=now.astimezone(SHANGHAI_TZ),
    )

    markdown, deep_results, processed_articles = await pipeline(
        l2_articles,
        settings=cfg,
        report_stats=report_stats,
        write_obsidian=False,
    )

    with get_connection(cfg) as conn:
        mark_articles_selected(conn, processed_articles)

    writer = ObsidianWriter(
        cfg.obsidian_root,
        index_filename=cfg.index_filename,
        enabled=cfg.obsidian_enabled,
    )
    today = report_stats.report_date.isoformat()
    report_path = writer.write_daily_report(today, markdown)
    deep_paths = [
        writer.write_deep_analysis(today, result["title"], result["analysis"])
        for result in deep_results
    ]
    for index, path in enumerate(deep_paths):
        deep_results[index]["filepath"] = path
    index_path = writer.update_index(today, report_path, deep_paths)

    with get_connection(cfg) as conn:
        insert_daily_report(
            conn,
            {
                "date": today,
                "generated_at": report_stats.generated_at.isoformat(),
                "file_path": report_path,
                "snr": report_stats.snr,
                "raw_count": report_stats.raw_count,
                "l1_count": report_stats.l1_count,
                "l2_count": report_stats.l2_count,
                "stats": json.dumps(
                    {
                        **filtered["snr"],
                        "sources_success": report_stats.sources_success,
                        "sources_total": report_stats.sources_total,
                    },
                    ensure_ascii=False,
                ),
            },
        )

    logger.info("日报完成: %s, 深度解读 %s 篇", report_path, len(deep_paths))
    return {
        "report": report_path,
        "index": index_path,
        "deep_count": len(deep_paths),
        "deep_paths": deep_paths,
        "raw_count": report_stats.raw_count,
        "l2_count": report_stats.l2_count,
    }


async def check_sources_health(settings: Settings | None = None) -> dict[str, Any]:
    """检查信源健康状态摘要。"""
    return await __import__("src.output.mcp_server", fromlist=["list_sources_tool"]).list_sources_tool(settings)


_last_run_date: str | None = None


async def scheduler_loop(settings: Settings | None = None) -> None:
    """每 60 秒检查一次，到配置时间就执行 daily_job。"""
    global _last_run_date
    cfg = settings or get_settings()
    logger.info("定时调度已启动，目标时间 %02d:%02d", cfg.schedule_hour, cfg.schedule_minute)

    while True:
        now = datetime.now(SHANGHAI_TZ)
        today = now.date().isoformat()
        if (
            now.hour == cfg.schedule_hour
            and now.minute == cfg.schedule_minute
            and _last_run_date != today
        ):
            try:
                await daily_job(cfg)
                _last_run_date = today
            except Exception:
                logger.exception("定时任务执行失败")
            await asyncio.sleep(120)
        await asyncio.sleep(60)


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="ai-daily-system 调度任务")
    parser.add_argument("--now", action="store_true", help="立即执行一次完整日报流程")
    args = parser.parse_args()
    logging.basicConfig(level=get_settings().log_level)

    if args.now:
        result = asyncio.run(daily_job())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
