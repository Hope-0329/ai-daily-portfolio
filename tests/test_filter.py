"""双层过滤引擎测试。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.filter import apply_l2_paper_cap, apply_l2_source_cap, filter_pipeline
from src.filter.dedup import (
    EventDeduplicator,
    is_rule_candidate,
    jaccard_similarity,
    merge_cluster,
    normalize_title_for_dedup,
)
from src.filter.layer1_rule import apply_l1_filter, apply_source_decay, calculate_l1_score
from src.filter.layer2_llm import Layer2LLMFilter
from src.filter.snr import calculate_snr
from src.models import Article, QualityLevel

NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
TIER1 = {"openai-blog": 1, "techcrunch-ai": 1, "qbitai": 1, "arxiv-ai": 1, "noise-feed": 3}


def make_article(
    article_id: str,
    title: str,
    *,
    source_id: str = "qbitai",
    source_name: str = "量子位",
    url: str | None = None,
    summary_raw: str | None = None,
    content: str | None = None,
    hours_ago: float = 2,
) -> Article:
    """构造测试文章。"""
    return Article(
        id=article_id,
        title=title,
        url=url or f"https://example.com/{article_id}",
        source_id=source_id,
        source_name=source_name,
        summary_raw=summary_raw,
        content=content,
        published_at=NOW - timedelta(hours=hours_ago),
        fetched_at=NOW,
        language="zh",
    )


POSITIVE_ARTICLES = [
    make_article("p1", "OpenAI 发布 GPT-5 大模型，参数规模达 1 万亿", source_id="openai-blog", source_name="OpenAI Blog", content="x" * 1200),
    make_article("p2", "DeepSeek 新 LLM 推理能力提升 30%，支持 agent 智能体", source_id="qbitai", content="x" * 800),
    make_article("p3", "Meta 开源 Llama 4 多模态 transformer 模型", source_id="techcrunch-ai", source_name="TechCrunch AI", content="x" * 600),
    make_article("p4", "Google DeepMind 在 RLHF 对齐方面取得 diffusion 突破", source_id="openai-blog", source_name="OpenAI Blog", content="x" * 900),
    make_article("p5", "Hugging Face 发布 RAG 向量数据库开源工具", source_id="qbitai", content="x" * 700),
    make_article("p6", "Anthropic Claude 3.5 微调对齐新进展", source_id="techcrunch-ai", source_name="TechCrunch AI", content="x" * 650),
    make_article("p7", "Sora 多模态 AIGC 模型迎来重大更新", source_id="qbitai", content="x" * 550),
    make_article("p8", "arXiv: 新 transformer NLP 架构论文发布", source_id="arxiv-ai", source_name="arXiv AI", content="x" * 1500),
    make_article("p9", "Microsoft Copilot 集成 LLM 大模型，企业级 AI 产品正式发布", source_id="techcrunch-ai", source_name="TechCrunch AI", content="x" * 600),
    make_article("p10", "Qwen LLM 量化蒸馏教程与 GitHub 开源项目", source_id="qbitai", content="x" * 1100),
]

NOISE_ARTICLES = [
    make_article("n1", "今日足球比赛结果：主队 2比1 获胜", source_id="noise-feed", source_name="体育新闻"),
    make_article("n2", "限时优惠推广：餐饮套餐赞助活动", source_id="noise-feed", source_name="广告号", content="限时优惠推广赞助"),
    make_article("n3", "转载：美食分享收藏指南", source_id="noise-feed", source_name="生活号"),
    make_article("n4", "天气预报：明天北京有雨", source_id="noise-feed", source_name="天气"),
    make_article("n5", "明星八卦：某演员恋情曝光", source_id="noise-feed", source_name="娱乐"),
]

NON_AI_FINANCE_ARTICLES = [
    make_article(
        "f1",
        "TCL 半导体股权收购获监管批准",
        source_id="qbitai",
        content="大模型 AI 人工智能 " + "x" * 800,
    ),
    make_article(
        "f2",
        "中国再保险发布最新投资评级报告",
        source_id="qbitai",
        content="GPT 大模型 " + "x" * 800,
    ),
    make_article(
        "f3",
        "3月汽车销量榜出炉，多家车企港股涨停",
        source_id="qbitai",
        content="机器学习 深度学习 " + "x" * 800,
    ),
]


def test_l1_filters_non_ai_finance_titles() -> None:
    """标题含股票/保险/汽车销量等非 AI 关键词时应在 L1 被筛掉。"""
    passed, rejected = apply_l1_filter(NON_AI_FINANCE_ARTICLES, TIER1, now=NOW)
    assert len(passed) == 0
    assert len(rejected) == len(NON_AI_FINANCE_ARTICLES)
    for article in rejected:
        assert article.score < 60


def test_apply_source_decay_penalizes_same_source_overflow() -> None:
    articles = [
        make_article(f"o{i}", f"OpenAI GPT 大模型更新 {i}", source_id="openai-blog", source_name="OpenAI Blog", content="x" * 900)
        for i in range(6)
    ]
    scored = [article.model_copy(update={"score": calculate_l1_score(article, 1, now=NOW)}) for article in articles]
    decayed = apply_source_decay(scored)
    openai_scores = [article.score for article in decayed if article.source_id == "openai-blog"]
    assert openai_scores[:3] == sorted(openai_scores[:3], reverse=True)
    assert openai_scores[3] <= openai_scores[2] - 3
    assert all(score <= openai_scores[2] - 3 for score in openai_scores[3:])


def test_apply_l2_source_cap_limits_per_source() -> None:
    articles = [
        make_article(f"a{i}", f"标题 {i}", source_id="openai-blog", source_name="OpenAI Blog").model_copy(
            update={"score": 90 - i}
        )
        for i in range(8)
    ]
    capped = apply_l2_source_cap(articles, max_per_source=5)
    assert len(capped) == 5
    assert all(article.source_id == "openai-blog" for article in capped)


def test_apply_l2_paper_cap_limits_academic_articles() -> None:
    papers = [
        make_article(f"p{i}", f"Paper {i}", source_id="arxiv-ai", source_name="arXiv AI").model_copy(
            update={"score": 95 - i}
        )
        for i in range(12)
    ]
    news = [
        make_article(f"n{i}", f"News {i}", source_id="qbitai", source_name="量子位").model_copy(
            update={"score": 80 - i}
        )
        for i in range(5)
    ]
    selected = papers + news
    candidates = selected + [
        make_article(
            f"c{i}",
            f"Candidate {i}",
            source_id=f"source-{i % 6}",
            source_name=f"Source {i % 6}",
        ).model_copy(update={"score": 70 - i})
        for i in range(20)
    ]
    capped = apply_l2_paper_cap(
        selected,
        candidates,
        min_papers=5,
        max_papers=8,
        target_count=25,
        max_per_source=5,
    )
    paper_count = sum(1 for article in capped if article.source_id == "arxiv-ai")
    assert paper_count == 8
    assert len(capped) == 25


def test_academic_sources_get_l1_penalty_but_still_pass() -> None:
    paper = make_article(
        "sr1",
        "OpenAI GPT 大模型 benchmark 研究论文发布",
        source_id="arxiv-ai",
        source_name="arXiv AI",
        summary_raw="A comprehensive benchmark on transformer neural network optimization.",
        content="深度学习 " * 100,
        hours_ago=2,
    )
    news = make_article(
        "news1",
        "OpenAI GPT 大模型 benchmark 研究论文发布",
        source_id="qbitai",
        source_name="量子位",
        summary_raw="A comprehensive benchmark on transformer neural network optimization.",
        content="深度学习 " * 100,
        hours_ago=2,
    )
    paper_score = calculate_l1_score(paper, 3, now=NOW)
    news_score = calculate_l1_score(news, 1, now=NOW)
    passed, rejected = apply_l1_filter([paper], TIER1, now=NOW)
    assert paper_score <= news_score - 10
    assert len(passed) == 1
    assert len(rejected) == 0


def test_l1_filters_noise_articles() -> None:
    passed, rejected = apply_l1_filter(POSITIVE_ARTICLES + NOISE_ARTICLES, TIER1, now=NOW)
    passed_ids = {article.id for article in passed}
    rejected_ids = {article.id for article in rejected}

    for article in POSITIVE_ARTICLES:
        assert article.id in passed_ids, f"正例未通过: {article.title}"
    for article in NOISE_ARTICLES:
        assert article.id in rejected_ids, f"噪音未被筛掉: {article.title}"


def test_l1_assigns_quality_levels() -> None:
    passed, _ = apply_l1_filter(POSITIVE_ARTICLES[:3], TIER1, now=NOW)
    for article in passed:
        assert article.score >= 60
        assert article.quality_level in {QualityLevel.MEDIUM, QualityLevel.HIGH}


def test_l1_score_formula_reasonable() -> None:
    good = POSITIVE_ARTICLES[0]
    bad = NOISE_ARTICLES[0]
    assert calculate_l1_score(good, 1, now=NOW) >= 60
    assert calculate_l1_score(bad, 3, now=NOW) < 60


def test_jaccard_similarity_detects_same_event_titles() -> None:
    title_a = "OpenAI 发布 GPT-5 大模型"
    title_b = "OpenAI 发布 GPT-5 大模型最新进展"
    title_c = "今日足球比赛结果"
    assert jaccard_similarity(title_a, title_b) > 0.5
    assert jaccard_similarity(title_a, title_c) < 0.5


def test_normalize_title_for_dedup_strips_original_suffix() -> None:
    raw = "Anthropic 投资 1 亿美元 [原文：Anthropic invests $100M]"
    normalized = normalize_title_for_dedup(raw)
    assert "[原文" not in normalized
    assert "anthropic invests" not in normalized
    assert jaccard_similarity(
        "Anthropic 投资 1 亿美元",
        "Anthropic 投资 1 亿美元 [原文：Anthropic invests $100M]",
    ) == 1.0


def _build_same_event_group(
    prefix: str,
    base_title: str,
    *,
    sources: list[tuple[str, str, str]],
) -> list[Article]:
    articles: list[Article] = []
    for index, (source_id, source_name, domain) in enumerate(sources):
        article_id = f"{prefix}{index}"
        articles.append(
            make_article(
                article_id,
                base_title if index == 0 else f"{base_title}（{source_name}报道）",
                source_id=source_id,
                source_name=source_name,
                url=f"https://{domain}/news/{article_id}",
                summary_raw=f"原文链接 https://official.example.com/release/{prefix}",
                content="详情 " * 100,
                hours_ago=index + 1,
            )
        )
    return articles


DEDUP_GROUP_1 = _build_same_event_group(
    "g1",
    "OpenAI 发布 GPT-5 大模型",
    sources=[
        ("techcrunch-ai", "TechCrunch AI", "techcrunch.com"),
        ("qbitai", "量子位", "qbitai.com"),
        ("openai-blog", "OpenAI Blog", "openai.com"),
    ],
)

DEDUP_GROUP_2 = _build_same_event_group(
    "g2",
    "DeepSeek 发布新 LLM 模型",
    sources=[
        ("qbitai", "量子位", "qbitai.com"),
        ("techcrunch-ai", "TechCrunch AI", "techcrunch.com"),
    ],
)

DEDUP_GROUP_3 = _build_same_event_group(
    "g3",
    "Meta 开源 Llama 4 多模态模型",
    sources=[
        ("techcrunch-ai", "TechCrunch AI", "techcrunch.com"),
        ("qbitai", "量子位", "qbitai.com"),
    ],
)


async def always_yes(_a: Article, _b: Article) -> bool:
    return True


@pytest.mark.asyncio
async def test_dedup_merges_same_event_group_1() -> None:
    scored = [article.model_copy(update={"score": 75.0}) for article in DEDUP_GROUP_1]
    deduplicator = EventDeduplicator(llm_confirm=always_yes)
    merged = await deduplicator.deduplicate(scored)
    assert len(merged) == 1
    assert len(merged[0].merged_from) >= 2
    assert merged[0].score >= 80


@pytest.mark.asyncio
async def test_dedup_merges_three_event_groups() -> None:
    articles: list[Article] = []
    for index, group in enumerate([DEDUP_GROUP_1, DEDUP_GROUP_2, DEDUP_GROUP_3]):
        for article in group:
            articles.append(article.model_copy(update={"score": 70.0 + index}))

    deduplicator = EventDeduplicator(llm_confirm=always_yes)
    merged = await deduplicator.deduplicate(articles)
    assert len(merged) == 3
    assert all(item.merged_from for item in merged)


def test_merge_cluster_keeps_highest_score_primary() -> None:
    articles = [
        DEDUP_GROUP_1[0].model_copy(update={"score": 72.0}),
        DEDUP_GROUP_1[1].model_copy(update={"score": 85.0}),
        DEDUP_GROUP_1[2].model_copy(update={"score": 78.0}),
    ]
    merged = merge_cluster(articles)
    assert merged.id == articles[1].id
    assert merged.score == 90.0
    assert set(merged.merged_from) >= {articles[0].id, articles[2].id}


def test_rule_candidate_requires_different_domains() -> None:
    same_domain_a = DEDUP_GROUP_1[0]
    same_domain_b = same_domain_a.model_copy(update={"id": "dup-local", "url": same_domain_a.url})
    assert is_rule_candidate(same_domain_a, same_domain_b) is False


def test_calculate_snr_metrics() -> None:
    snr = calculate_snr(raw_count=200, l1_count=60, l2_count=20, l2_high_quality_count=17)
    assert snr["l1_pass_rate"] == 0.3
    assert snr["filter_efficiency"] == 0.1
    assert snr["l2_quality"] == 0.85
    assert snr["raw_to_l1_ratio"] == snr["l1_pass_rate"]
    assert snr["overall_snr"] == snr["filter_efficiency"]
    assert snr["quality_rate"] == snr["l2_quality"]


def _mock_l2_response(articles: list[Article]) -> MagicMock:
    payload = [
        {
            "id": article.id,
            "score": 90 - index,
            "reason": f"理由{index}",
            "rank": index + 1,
        }
        for index, article in enumerate(articles[:3])
    ]
    message = MagicMock()
    message.content = json.dumps(payload, ensure_ascii=False)
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.mark.asyncio
async def test_layer2_llm_returns_ranked_json_results() -> None:
    candidates = [article.model_copy(update={"score": 70.0}) for article in POSITIVE_ARTICLES[:5]]
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_mock_l2_response(candidates))

    layer2 = Layer2LLMFilter(llm_client=mock_client)
    results = await layer2.select_top_articles(candidates)

    assert len(results) == 3
    assert results[0].score >= results[-1].score
    assert all(article.summary for article in results)
    mock_client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_filter_pipeline_end_to_end_with_mock_llm() -> None:
    dedup_articles = POSITIVE_ARTICLES[:6] + NOISE_ARTICLES
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=_mock_l2_response(POSITIVE_ARTICLES[:6]))

    result = await filter_pipeline(
        dedup_articles,
        source_tier_map=TIER1,
        llm_client=mock_client,
        skip_l2=False,
    )

    assert len(result["l1_results"]) >= 6
    assert len(result["l1_rejected"]) == len(NOISE_ARTICLES)
    assert result["stats"]["raw_count"] == len(dedup_articles)
    assert "filter_efficiency" in result["snr"]
    assert "l2_quality" in result["snr"]
    assert len(result["l2_results"]) <= 25
