"""信源注册中心与并发调度。"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date
from pathlib import Path

import yaml

from src.config import Settings, get_settings
from src.database import (
    get_connection,
    init_db,
    insert_articles,
    log_source_health,
    upsert_source,
)
from src.models import Article, Source, SourceType
from src.sources.aihot import AIHOTCollector
from src.sources.api import APICollector
from src.sources.base import SourceCollector
from src.sources.rss import RSSCollector
from src.sources.web import WebCollector

logger = logging.getLogger(__name__)


def load_sources(config_path: str | Path | None = None, settings: Settings | None = None) -> list[Source]:
    """加载已启用的信源列表（供脚本与测试使用）。"""
    cfg = settings or get_settings()
    path = Path(config_path) if config_path else cfg.sources_config
    registry = SourceRegistry(path, settings=cfg)
    return registry.get_enabled_sources()


class SourceRegistry:
    """信源注册中心：加载配置、并发采集、写入数据库。"""

    def __init__(
        self,
        config_path: str | Path,
        settings: Settings | None = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.settings = settings or get_settings()
        self._sources = self._load_sources()
        self._collectors: dict[SourceType, SourceCollector] = {
            SourceType.RSS: RSSCollector(self.settings),
            SourceType.RSSHUB: RSSCollector(self.settings),
            SourceType.API: APICollector(self.settings),
            SourceType.WEB: WebCollector(self.settings),
        }
        self._aihot_collector = AIHOTCollector(self.settings)

    def _load_sources(self) -> list[Source]:
        """从 YAML 文件加载信源配置。"""
        with self.config_path.open(encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        raw_sources = payload.get("sources") or []
        return [Source.model_validate(item) for item in raw_sources]

    def get_enabled_sources(self, min_tier: int = 3) -> list[Source]:
        """获取启用的信源列表（tier 数值越小优先级越高）。"""
        return [
            source
            for source in self._sources
            if source.enabled and source.tier <= min_tier
        ]

    def get_all_sources(self) -> list[Source]:
        """返回全部信源（含已禁用）。"""
        return list(self._sources)

    def record_disabled_sources(self) -> None:
        """将已禁用信源写入 source_health，便于排查。"""
        disabled = [source for source in self._sources if not source.enabled]
        if not disabled:
            return
        init_db(self.settings)
        with get_connection(self.settings) as conn:
            for source in disabled:
                upsert_source(conn, source)
                log_source_health(
                    conn,
                    source_id=source.id,
                    status="disabled",
                    count=0,
                    error_msg=source.disable_reason or "已禁用",
                    response_time=0,
                    log_date=date.today(),
                )

    def get_collector(self, source: Source) -> SourceCollector:
        """根据信源类型返回对应采集器。"""
        if source.id == "aihot":
            return self._aihot_collector
        collector = self._collectors.get(source.type)
        if collector is None:
            raise ValueError(f"不支持的信源类型: {source.type}")
        return collector

    async def fetch_one(self, source: Source) -> list[Article]:
        """拉取单个信源（不写入数据库）。"""
        collector = self.get_collector(source)
        return await collector.fetch(source)

    async def fetch_all(
        self,
        sources: list[Source] | None = None,
        *,
        persist: bool = True,
    ) -> dict[str, list[Article]]:
        """并发拉取所有信源，返回 {source_id: [articles]}。"""
        target_sources = sources or self.get_enabled_sources()
        if persist:
            init_db(self.settings)
            with get_connection(self.settings) as conn:
                for source in target_sources:
                    upsert_source(conn, source)

        semaphore = asyncio.Semaphore(self.settings.max_concurrent)

        async def _run(source: Source) -> tuple[str, list[Article]]:
            async with semaphore:
                return await self._fetch_with_logging(source, persist=persist)

        results = await asyncio.gather(
            *(_run(source) for source in target_sources),
            return_exceptions=True,
        )
        output: dict[str, list[Article]] = {}
        for index, result in enumerate(results):
            source = target_sources[index]
            if isinstance(result, BaseException):
                logger.error("信源 %s 并发任务异常: %s", source.id, result)
                if persist:
                    self._log_failure(source, str(result), 0)
                output[source.id] = []
            else:
                source_id, articles = result
                output[source_id] = articles
        return output

    async def _fetch_with_logging(
        self,
        source: Source,
        *,
        persist: bool,
    ) -> tuple[str, list[Article]]:
        """拉取单个信源并记录健康状态。"""
        started = time.perf_counter()
        status = "ok"
        error_message: str | None = None
        articles: list[Article] = []
        try:
            articles = await self.fetch_one(source)
        except Exception as exc:
            status = "error"
            error_message = str(exc)
            logger.exception("信源 %s 采集失败", source.id)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if persist:
            with get_connection(self.settings) as conn:
                upsert_source(
                    conn,
                    source,
                    last_fetched_at=articles[0].fetched_at.isoformat() if articles else None,
                    increment_error=status != "ok",
                )
                if articles:
                    insert_articles(conn, articles, skip_recent_hours=24)
                log_source_health(
                    conn,
                    source_id=source.id,
                    status=status,
                    count=len(articles),
                    error_msg=error_message,
                    response_time=elapsed_ms,
                    log_date=date.today(),
                )
        return source.id, articles

    def _log_failure(self, source: Source, error_message: str, response_time_ms: int) -> None:
        """记录完全失败的并发任务。"""
        with get_connection(self.settings) as conn:
            upsert_source(conn, source, increment_error=True)
            log_source_health(
                conn,
                source_id=source.id,
                status="error",
                count=0,
                error_msg=error_message,
                response_time=response_time_ms,
                log_date=date.today(),
            )
