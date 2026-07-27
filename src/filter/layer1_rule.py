"""L1 规则引擎：纯 Python 四维评分，不调用 LLM。"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from src.config import Settings, get_settings
from src.models import Article, QualityLevel

# ── 关键词库 ────────────────────────────────────────────────

HIGH_KEYWORDS = (
    "大模型",
    "llm",
    "gpt",
    "claude",
    "gemini",
    "deepseek",
    "qwen",
    "llama",
    "mixtral",
    "transformer",
    "diffusion",
    "rlhf",
    "agent",
    "智能体",
    "多模态",
    "sora",
)

MEDIUM_KEYWORDS = (
    "深度学习",
    "机器学习",
    "神经网络",
    "nlp",
    "cv",
    "rl",
    "微调",
    "对齐",
    "推理",
    "生成式",
    "aigc",
    "rag",
    "向量数据库",
    "embedding",
    "lora",
    "量化",
    "蒸馏",
)

LOW_KEYWORDS = (
    "ai",
    "人工智能",
    "chatgpt",
    "copilot",
    "midjourney",
    "stable diffusion",
    "suno",
    "提示词",
    "prompt",
)

OFFICIAL_SOURCE_IDS = {
    "openai-blog",
    "anthropic-blog",
    "deepmind",
    "meta-ai",
    "microsoft-ai",
    "huggingface-blog",
    "tencent-ai-lab",
    "alibaba-damo",
    "baidu-ai",
    "nvidia-blog",
    "stability-ai",
    "mistral-ai",
    "cohere",
}

KNOWN_ENTITIES = (
    "openai",
    "google",
    "meta",
    "apple",
    "microsoft",
    "字节",
    "阿里",
    "百度",
    "腾讯",
    "anthropic",
    "nvidia",
    "deepseek",
)

ACTIONABLE_KEYWORDS = ("教程", "工具", "开源", "guide", "tutorial", "open source", "github")

NON_AI_TITLE_KEYWORDS = (
    "股票",
    "评级",
    "涨停",
    "港股",
    "A股",
    "投资评级",
    "保险",
    "再保险",
    "汽车销量",
    "半导体股权",
    "半导体收购",
)

ACADEMIC_SOURCE_IDS = {
    "arxiv-ai",
    "arxiv-ml",
    "arxiv-cl",
    "arxiv-cv",
    "synced-review",
    "huggingface-papers",
}

REPOST_MARKERS = ("转载", "分享", "收藏")
AD_MARKERS = ("推广", "赞助", "限时优惠")


def score_to_quality_level(score: float) -> QualityLevel:
    """根据分数映射质量等级。"""
    if score >= 80:
        return QualityLevel.HIGH
    if score >= 60:
        return QualityLevel.MEDIUM
    return QualityLevel.LOW


def _contains_keyword(text: str, keyword: str) -> bool:
    if keyword.isascii():
        return keyword.lower() in text.lower()
    return keyword in text


def _count_keyword_hits(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if _contains_keyword(text, keyword))


def _extract_body_preview(article: Article, limit: int = 500) -> str:
    parts = [article.title, article.summary_raw or "", article.summary or "", article.content or ""]
    return " ".join(part for part in parts if part)[:limit]


def _title_has_non_ai_marker(title: str) -> bool:
    """检测标题是否含非 AI 财经/产业类关键词。"""
    for keyword in NON_AI_TITLE_KEYWORDS:
        if keyword.isascii():
            if keyword.lower() in title.lower():
                return True
        elif keyword in title:
            return True
    return False


def score_relevance(article: Article) -> float:
    """维度 1：AI 相关度（上限 40）。"""
    title = article.title
    preview = _extract_body_preview(article)
    total = 0.0

    for keyword in HIGH_KEYWORDS:
        if _contains_keyword(title, keyword):
            total += 20
        if _contains_keyword(preview, keyword):
            total += 15

    for keyword in MEDIUM_KEYWORDS:
        if _contains_keyword(title, keyword):
            total += 10
        if _contains_keyword(preview, keyword):
            total += 8

    for keyword in LOW_KEYWORDS:
        if _contains_keyword(preview, keyword):
            total += 3

    keyword_chars = 0
    preview_lower = preview.lower()
    for keyword in HIGH_KEYWORDS + MEDIUM_KEYWORDS + LOW_KEYWORDS:
        if keyword.isascii():
            if keyword.lower() in preview_lower:
                keyword_chars += len(keyword)
        elif keyword in preview:
            keyword_chars += len(keyword)
    if preview and keyword_chars / max(len(preview), 1) > 0.03:
        total += 10

    if _title_has_non_ai_marker(title):
        total -= 20

    return max(0.0, min(total, 40.0))


def score_density(article: Article) -> float:
    """维度 2：信息密度（上限 25）。"""
    content = article.content or article.summary_raw or article.summary or ""
    total = 0.0
    length = len(content)

    if length > 500:
        total += 5
    if length > 1000:
        total += 10
    if length > 2000:
        total += 15

    if re.search(r"(^|\n)\s*[-*•]\s+", content) or "<table" in content.lower() or "```" in content:
        total += 5

    title = article.title
    if any(marker in title for marker in REPOST_MARKERS):
        total -= 10
    if any(marker in content for marker in AD_MARKERS):
        total -= 15

    return max(0.0, min(total, 25.0))


def score_source_value(article: Article, source_tier: int) -> float:
    """维度 3：信源价值（上限 20）。"""
    tier_bonus = {1: 15, 2: 8, 3: 3}.get(source_tier, 3)
    total = float(tier_bonus)

    if article.source_id in OFFICIAL_SOURCE_IDS:
        total += 5

    content = article.content or article.summary_raw or ""
    if len(content) < 200 and ("@" in content or "#" in content):
        total -= 10

    return max(0.0, min(total, 20.0))


def score_timeliness(article: Article, *, now: datetime | None = None) -> float:
    """维度 4：时效价值（上限 15）。"""
    if article.published_at is None:
        return 0.0

    current = now or datetime.now(timezone.utc)
    published = article.published_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    hours = (current - published.astimezone(timezone.utc)).total_seconds() / 3600

    if hours <= 1:
        return 15.0
    if hours <= 6:
        return 10.0
    if hours <= 24:
        return 5.0
    if hours <= 48:
        return 2.0
    return 0.0


def score_bonus(article: Article) -> float:
    """独立加分项。"""
    preview = _extract_body_preview(article, limit=800)
    total = 0.0

    if re.search(r"\d+(\.\d+)?%|\d+\s*(亿|万|k|m|b|参数|tokens?)", preview, re.IGNORECASE):
        total += 3

    lowered = preview.lower()
    if any(entity.lower() in lowered or entity in preview for entity in KNOWN_ENTITIES):
        total += 3

    if any(keyword in preview.lower() or keyword in preview for keyword in ACTIONABLE_KEYWORDS):
        total += 3

    return total


def calculate_l1_score(article: Article, source_tier: int, *, now: datetime | None = None) -> float:
    """计算 L1 综合得分。"""
    relevance = score_relevance(article)
    density = score_density(article)
    source_value = score_source_value(article, source_tier)
    timeliness = score_timeliness(article, now=now)
    bonus = score_bonus(article)
    total = relevance + density + source_value + timeliness + bonus
    if article.source_id in ACADEMIC_SOURCE_IDS:
        # Phase 10：学术论文 L1 降权，避免淹没新闻源
        total -= 15
    return min(100.0, max(0.0, total))


def apply_source_decay(articles: list[Article]) -> list[Article]:
    """
    同源衰减：同一信源超过 3 篇后，每多 1 篇扣 3 分，并重新排序。

    按初始分数从高到低遍历，确保高分文章优先占用配额。
    """
    sorted_articles = sorted(articles, key=lambda item: item.score, reverse=True)
    source_counts: dict[str, int] = {}
    decayed: list[Article] = []

    for article in sorted_articles:
        count = source_counts.get(article.source_id, 0) + 1
        source_counts[article.source_id] = count
        penalty = 3 if count > 3 else 0
        new_score = max(0.0, round(article.score - penalty, 2))
        decayed.append(
            article.model_copy(
                update={
                    "score": new_score,
                    "quality_level": score_to_quality_level(new_score),
                }
            )
        )

    decayed.sort(key=lambda item: item.score, reverse=True)
    return decayed


def apply_l1_filter(
    articles: list[Article],
    source_tier_map: dict[str, int],
    settings: Settings | None = None,
    *,
    now: datetime | None = None,
) -> tuple[list[Article], list[Article]]:
    """
    对文章列表执行 L1 过滤。

    返回 (通过列表, 被筛掉列表)。
    """
    cfg = settings or get_settings()
    scored_articles: list[Article] = []
    rejected: list[Article] = []

    for article in articles:
        tier = source_tier_map.get(article.source_id, 3)
        score = calculate_l1_score(article, tier, now=now)
        threshold = cfg.l1_min_score
        if article.source_id in ACADEMIC_SOURCE_IDS:
            threshold = max(cfg.l1_min_score - 15, 45)
        scored = article.model_copy(
            update={
                "score": round(score, 2),
                "quality_level": score_to_quality_level(score),
            }
        )
        if score >= threshold:
            scored_articles.append(scored)
        else:
            rejected.append(scored)

    decayed = apply_source_decay(scored_articles)
    passed: list[Article] = []
    for article in decayed:
        threshold = cfg.l1_min_score
        if article.source_id in ACADEMIC_SOURCE_IDS:
            threshold = max(cfg.l1_min_score - 15, 45)
        if article.score >= threshold:
            passed.append(article)
        else:
            rejected.append(article)

    return passed, rejected
