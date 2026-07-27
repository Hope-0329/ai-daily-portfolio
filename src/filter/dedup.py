"""事件级去重：规则预判 + LLM 确认 + 多源合并。"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Awaitable
from urllib.parse import urlparse

from openai import AsyncOpenAI

from src.config import Settings, get_settings
from src.models import Article

logger = logging.getLogger(__name__)

SAME_EVENT_PROMPT = """以下两篇 AI 新闻是否在报道同一件事？只回答 YES 或 NO。

文章 A: {title_a}
文章 B: {title_b}

是否同一事件："""


ORIGINAL_TITLE_SUFFIX = re.compile(r"\s*\[原文：[^\]]+\]\s*")


def normalize_title_for_dedup(title: str) -> str:
    """去重前归一化标题：小写并去掉翻译原文标记。"""
    cleaned = ORIGINAL_TITLE_SUFFIX.sub("", title or "")
    return cleaned.lower().strip()


def tokenize_title(title: str) -> set[str]:
    """标题分词（中英文混合）。"""
    tokens = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", normalize_title_for_dedup(title))
    return {token for token in tokens if len(token) > 1}


def jaccard_similarity(title_a: str, title_b: str) -> float:
    """计算标题 Jaccard 相似度。"""
    set_a = tokenize_title(title_a)
    set_b = tokenize_title(title_b)
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def extract_domain(url: str) -> str:
    """提取 URL 域名。"""
    parsed = urlparse(url)
    return parsed.netloc.lower()


def extract_external_links(text: str) -> set[str]:
    """提取文本中的外链。"""
    links = re.findall(r"https?://[^\s\"'<>]+", text or "")
    return {link.rstrip(").,，。") for link in links}


def published_within_hours(article_a: Article, article_b: Article, hours: int = 24) -> bool:
    """判断两篇文章发布时间差是否在指定小时内。"""
    if article_a.published_at is None or article_b.published_at is None:
        return True

    time_a = article_a.published_at
    time_b = article_b.published_at
    if time_a.tzinfo is None:
        time_a = time_a.replace(tzinfo=timezone.utc)
    if time_b.tzinfo is None:
        time_b = time_b.replace(tzinfo=timezone.utc)
    delta_hours = abs((time_a - time_b).total_seconds()) / 3600
    return delta_hours <= hours


def share_same_source_link(article_a: Article, article_b: Article) -> bool:
    """判断是否转发同一来源链接。"""
    links_a = extract_external_links(" ".join(filter(None, [article_a.summary_raw, article_a.content])))
    links_b = extract_external_links(" ".join(filter(None, [article_b.summary_raw, article_b.content])))
    if not links_a or not links_b:
        return jaccard_similarity(
            normalize_title_for_dedup(article_a.title),
            normalize_title_for_dedup(article_b.title),
        ) >= 0.7
    return bool(links_a & links_b)


def is_rule_candidate(article_a: Article, article_b: Article) -> bool:
    """规则预判是否为同一事件候选对。"""
    if jaccard_similarity(article_a.title, article_b.title) <= 0.5:
        return False
    if extract_domain(article_a.url) == extract_domain(article_b.url):
        return False
    if not published_within_hours(article_a, article_b):
        return False
    return share_same_source_link(article_a, article_b)


class EventDeduplicator:
    """事件级去重器。"""

    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: AsyncOpenAI | None = None,
        llm_confirm: Callable[[Article, Article], Awaitable[bool]] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client
        self.llm_confirm = llm_confirm

    async def confirm_same_event(self, article_a: Article, article_b: Article) -> bool:
        """调用 LLM 确认是否为同一事件。"""
        if self.llm_confirm is not None:
            return await self.llm_confirm(article_a, article_b)

        if self.llm_client is None:
            self.llm_client = AsyncOpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
            )

        prompt = SAME_EVENT_PROMPT.format(title_a=article_a.title, title_b=article_b.title)
        response = await self.llm_client.chat.completions.create(
            model=self.settings.deepseek_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=8,
        )
        answer = (response.choices[0].message.content or "").strip().upper()
        return answer.startswith("YES")

    async def deduplicate(self, articles: list[Article]) -> list[Article]:
        """对文章列表执行事件级去重与合并。"""
        if len(articles) <= 1:
            return list(articles)

        parent = {article.id: article.id for article in articles}
        article_map = {article.id: article for article in articles}

        def find(article_id: str) -> str:
            while parent[article_id] != article_id:
                parent[article_id] = parent[parent[article_id]]
                article_id = parent[article_id]
            return article_id

        def union(id_a: str, id_b: str) -> None:
            root_a = find(id_a)
            root_b = find(id_b)
            if root_a != root_b:
                primary = root_a if article_map[root_a].score >= article_map[root_b].score else root_b
                secondary = root_b if primary == root_a else root_a
                parent[secondary] = primary

        checked: set[tuple[str, str]] = set()
        for index, article_a in enumerate(articles):
            for article_b in articles[index + 1 :]:
                pair = tuple(sorted((article_a.id, article_b.id)))
                if pair in checked:
                    continue
                checked.add(pair)
                if not is_rule_candidate(article_a, article_b):
                    continue
                try:
                    same_event = await self.confirm_same_event(article_a, article_b)
                except Exception as exc:
                    logger.warning("LLM 去重确认失败，跳过合并: %s", exc)
                    continue
                if same_event:
                    union(article_a.id, article_b.id)

        clusters: dict[str, list[Article]] = defaultdict(list)
        for article in articles:
            clusters[find(article.id)].append(article)

        merged: list[Article] = []
        for cluster in clusters.values():
            merged.append(merge_cluster(cluster))
        merged.sort(key=lambda item: item.score, reverse=True)
        return merged


def merge_cluster(cluster: list[Article]) -> Article:
    """合并同一事件的多源报道。"""
    primary = max(cluster, key=lambda item: item.score)
    merged_ids = sorted({article.id for article in cluster})
    extra_ids = [article_id for article_id in merged_ids if article_id != primary.id]
    return primary.model_copy(
        update={
            "merged_from": list(dict.fromkeys(primary.merged_from + extra_ids)),
            "score": min(100.0, max(item.score for item in cluster) + 5),
            "quality_level": primary.quality_level,
            "summary": primary.summary or primary.summary_raw,
        }
    )
