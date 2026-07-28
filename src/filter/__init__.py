"""双层过滤引擎入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from openai import AsyncOpenAI

from src.config import Settings, get_settings
from src.filter.dedup import EventDeduplicator, dedupe_aihot_by_url
from src.filter.layer1_rule import apply_l1_filter
from src.filter.layer2_llm import Layer2LLMFilter
from src.filter.snr import calculate_snr
from src.models import Article, QualityLevel


def load_source_tier_map(sources_config: Path | None = None) -> dict[str, int]:
    """从 sources.yaml 加载信源 tier 映射。"""
    cfg = get_settings()
    path = sources_config or cfg.sources_config
    with path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    tier_map: dict[str, int] = {}
    for item in payload.get("sources") or []:
        tier_map[item["id"]] = int(item.get("tier", 3))
    return tier_map


ACADEMIC_SOURCE_IDS = {
    "arxiv-ai",
    "arxiv-ml",
    "arxiv-cl",
    "arxiv-cv",
    "synced-review",
    "huggingface-papers",
    "acl-anthology",
    "icml",
    "neurips",
}


def apply_l2_source_cap(
    articles: list[Article],
    *,
    max_per_source: int,
) -> list[Article]:
    """限制 L2 结果中每个信源最多进入 N 篇。"""
    source_counts: dict[str, int] = {}
    capped: list[Article] = []
    for article in articles:
        count = source_counts.get(article.source_id, 0)
        if count >= max_per_source:
            continue
        source_counts[article.source_id] = count + 1
        capped.append(article)
    return capped


def backfill_l2_results(
    selected: list[Article],
    candidates: list[Article],
    *,
    target_count: int,
    max_per_source: int,
) -> list[Article]:
    """单源上限截断后，从候选池补齐到目标篇数。"""
    if len(selected) >= target_count:
        return selected[:target_count]

    source_counts: dict[str, int] = {}
    for article in selected:
        source_counts[article.source_id] = source_counts.get(article.source_id, 0) + 1

    selected_ids = {article.id for article in selected}
    filled = list(selected)
    for article in candidates:
        if len(filled) >= target_count:
            break
        if article.id in selected_ids:
            continue
        count = source_counts.get(article.source_id, 0)
        if count >= max_per_source:
            continue
        source_counts[article.source_id] = count + 1
        selected_ids.add(article.id)
        filled.append(article)
    return filled


def ensure_paper_quota(
    selected: list[Article],
    candidates: list[Article],
    *,
    min_papers: int = 2,
    max_per_source: int,
) -> list[Article]:
    """确保 L2 结果中至少包含若干论文类文章。"""
    paper_count = sum(
        1 for article in selected if article.source_id in ACADEMIC_SOURCE_IDS
    )
    if paper_count >= min_papers:
        return selected

    source_counts: dict[str, int] = {}
    for article in selected:
        source_counts[article.source_id] = source_counts.get(article.source_id, 0) + 1

    selected_ids = {article.id for article in selected}
    filled = list(selected)
    for article in candidates:
        if paper_count >= min_papers:
            break
        if article.source_id not in ACADEMIC_SOURCE_IDS:
            continue
        if article.id in selected_ids:
            continue
        count = source_counts.get(article.source_id, 0)
        if count >= max_per_source:
            continue
        source_counts[article.source_id] = count + 1
        selected_ids.add(article.id)
        filled.append(article)
        paper_count += 1
    return filled


def apply_l2_paper_cap(
    selected: list[Article],
    candidates: list[Article],
    *,
    min_papers: int = 5,
    max_papers: int,
    target_count: int,
    max_per_source: int,
) -> list[Article]:
    """
    L2 论文配额：至少 min_papers、最多 max_papers 篇，其余用非论文补齐到 target_count。
    """
    selected_ids = {article.id for article in selected}
    pool_papers = sorted(
        [article for article in selected if article.source_id in ACADEMIC_SOURCE_IDS],
        key=lambda item: item.score,
        reverse=True,
    )
    pool_ids = {article.id for article in pool_papers}
    if len(pool_papers) < min_papers:
        for article in sorted(candidates, key=lambda item: item.score, reverse=True):
            if article.source_id not in ACADEMIC_SOURCE_IDS:
                continue
            if article.id in pool_ids:
                continue
            pool_papers.append(article)
            pool_ids.add(article.id)
            if len(pool_papers) >= min_papers:
                break

    kept_papers = pool_papers[:max_papers]
    paper_ids = {article.id for article in kept_papers}

    source_counts: dict[str, int] = {}
    for article in kept_papers:
        source_counts[article.source_id] = source_counts.get(article.source_id, 0) + 1

    non_papers = sorted(
        [article for article in selected if article.id not in paper_ids and article.source_id not in ACADEMIC_SOURCE_IDS],
        key=lambda item: item.score,
        reverse=True,
    )
    result = list(kept_papers)
    for article in non_papers:
        if len(result) >= target_count:
            break
        count = source_counts.get(article.source_id, 0)
        if count >= max_per_source:
            continue
        source_counts[article.source_id] = count + 1
        result.append(article)

    if len(result) < target_count:
        for article in sorted(candidates, key=lambda item: item.score, reverse=True):
            if len(result) >= target_count:
                break
            if article.source_id in ACADEMIC_SOURCE_IDS or article.id in {item.id for item in result}:
                continue
            count = source_counts.get(article.source_id, 0)
            if count >= max_per_source:
                continue
            source_counts[article.source_id] = count + 1
            result.append(article)

    result.sort(key=lambda item: item.score, reverse=True)
    return result[:target_count]


async def filter_pipeline(
    articles: list[Article],
    *,
    settings: Settings | None = None,
    source_tier_map: dict[str, int] | None = None,
    llm_client: AsyncOpenAI | None = None,
    skip_l2: bool = False,
) -> dict[str, Any]:
    """
    完整双层过滤流程。

    返回:
        {
            "l1_results": [...],
            "dedup_results": [...],
            "l2_results": [...],
            "l1_rejected": [...],
            "snr": {...},
            "stats": {...},
        }
    """
    cfg = settings or get_settings()
    tiers = source_tier_map or load_source_tier_map(cfg.sources_config)

    raw_count = len(articles)
    url_deduped = dedupe_aihot_by_url(articles)
    l1_results, l1_rejected = apply_l1_filter(url_deduped, tiers, cfg)

    deduplicator = EventDeduplicator(settings=cfg, llm_client=llm_client)
    dedup_results = await deduplicator.deduplicate(l1_results)

    if skip_l2:
        l2_results: list[Article] = dedup_results[: cfg.l2_top_n]
    else:
        layer2 = Layer2LLMFilter(settings=cfg, llm_client=llm_client)
        l2_results = await layer2.select_top_articles(dedup_results)

    l2_results = apply_l2_source_cap(l2_results, max_per_source=cfg.l2_max_per_source)
    l2_results = backfill_l2_results(
        l2_results,
        dedup_results,
        target_count=cfg.l2_top_n,
        max_per_source=cfg.l2_max_per_source,
    )
    l2_results = apply_l2_paper_cap(
        l2_results,
        dedup_results,
        min_papers=5,
        max_papers=cfg.l2_max_papers,
        target_count=cfg.l2_top_n,
        max_per_source=cfg.l2_max_per_source,
    )

    l2_high_quality_count = sum(
        1 for article in l2_results if article.score >= 80 or article.quality_level == QualityLevel.HIGH
    )
    snr = calculate_snr(raw_count, len(l1_results), len(l2_results), l2_high_quality_count)

    stats = {
        "raw_count": raw_count,
        "l1_pass_count": len(l1_results),
        "l1_reject_count": len(l1_rejected),
        "dedup_count": len(dedup_results),
        "url_dedup_removed": raw_count - len(url_deduped),
        "l2_count": len(l2_results),
        "merged_events": sum(1 for article in dedup_results if article.merged_from),
        "l2_high_quality_count": l2_high_quality_count,
    }

    return {
        "l1_results": l1_results,
        "l1_rejected": l1_rejected,
        "dedup_results": dedup_results,
        "l2_results": l2_results,
        "snr": snr,
        "stats": stats,
    }


__all__ = [
    "filter_pipeline",
    "load_source_tier_map",
    "apply_l2_source_cap",
    "backfill_l2_results",
    "ensure_paper_quota",
    "apply_l2_paper_cap",
]
