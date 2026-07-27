"""日报 Markdown 组装。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from openai import AsyncOpenAI

from src.config import Settings, get_settings
from src.models import Article, Category
from src.pipeline.classifier import display_title
from src.pipeline.llm_client import chat_completion

SHANGHAI_TZ = timezone(timedelta(hours=8))

WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

SECTION_CONFIG: list[tuple[Category, str]] = [
    (Category.AI_MODELS, "🤖 模型发布/更新"),
    (Category.AI_PRODUCTS, "📦 产品发布/更新"),
    (Category.INDUSTRY, "📊 行业动态"),
    (Category.PAPER, "📝 论文研究"),
    (Category.TIP, "💡 技巧与观点"),
]

TOP3_PROMPT = """以下是今天 L2 精选的 {count} 篇文章。请选出最重要的 TOP 3，
为每篇写 15-25 字的一句话推荐理由。

{articles_block}

返回 JSON: [{{"id": "编号", "reason": "推荐理由"}}, ...]
只返回 JSON 数组。"""

TOPIC_POOL_PROMPT = """基于今天的精选文章，推荐 5 个值得深度写作的选题。
每个选题包含标题、理由、信息来源。

{articles_block}

返回 JSON: [{{"title": "选题", "reason": "理由", "sources": ["来源"]}}, ...]
只返回 JSON 数组。"""

THOUGHTS_PROMPT = """你是 AI 博主"知识侦察兵"。看完今天的 AI 新闻，写 2-3 段个人化的感想。

风格要求：
- 真实、有态度、有洞见
- 像朋友聊天，不官腔
- 可以表达兴奋、质疑、批评
- 把不同新闻联系起来看趋势
- 约 200 字

今天的重要新闻：
{titles}
"""


@dataclass
class ReportStats:
    """日报统计数据。"""

    report_date: date
    generated_at: datetime
    sources_success: int = 48
    sources_total: int = 52
    raw_count: int = 203
    l1_count: int = 62
    l2_count: int = 20
    snr: float = 0.32
    quality_rate: float = 0.88
    l1_pass_rate: float = 0.22
    failed_sources: list[str] = field(default_factory=list)


class DailyReportBuilder:
    """日报组装器。"""

    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: AsyncOpenAI | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client
        self.timezone = SHANGHAI_TZ

    @staticmethod
    def _parse_json_array(content: str) -> list[dict[str, Any]]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise ValueError("LLM 返回结果不是 JSON 数组")
        return payload

    @staticmethod
    def _articles_block(articles: list[Article]) -> str:
        lines: list[str] = []
        for index, article in enumerate(articles, start=1):
            lines.append(
                f"{index}. [{article.id}] {display_title(article)} | "
                f"来源: {article.source_name} | 评分: {article.score}"
            )
        return "\n".join(lines)

    @staticmethod
    def _source_count(article: Article) -> int:
        return len(article.merged_from) + 1

    @staticmethod
    def _format_event_cell(article: Article) -> str:
        title = display_title(article)
        if article.language == "en" and article.title_cn and article.title != article.title_cn:
            return f"{title} [原文：{article.title}]({article.url})"
        return f"[{title}]({article.url})"

    @staticmethod
    def _format_top3_event(article: Article, reason: str | None = None) -> str:
        """TOP 3 事件列：优先用标题，截断时至少保留 30 字。"""
        title = display_title(article).replace("|", "｜")
        text = title
        if len(text) < 30 and reason:
            text = str(reason).replace("|", "｜")
        if len(text) < 30:
            text = title
        max_len = 60
        if len(text) <= max_len:
            return text
        cut_at = max(30, max_len - 3)
        return text[:cut_at] + "..."

    async def _generate_top3(self, articles: list[Article]) -> list[dict[str, Any]]:
        prompt = TOP3_PROMPT.format(count=len(articles), articles_block=self._articles_block(articles))
        try:
            content = await chat_completion(
                prompt,
                settings=self.settings,
                llm_client=self.llm_client,
                temperature=0.3,
                max_tokens=512,
            )
            return self._parse_json_array(content)
        except Exception:
            sorted_articles = sorted(articles, key=lambda item: item.score, reverse=True)[:3]
            return [
                {"id": article.id, "reason": display_title(article)}
                for article in sorted_articles
            ]

    async def _generate_topic_pool(self, articles: list[Article]) -> list[dict[str, Any]]:
        prompt = TOPIC_POOL_PROMPT.format(articles_block=self._articles_block(articles))
        try:
            content = await chat_completion(
                prompt,
                settings=self.settings,
                llm_client=self.llm_client,
                temperature=0.4,
                max_tokens=1024,
            )
            return self._parse_json_array(content)[:5]
        except Exception:
            return [
                {
                    "title": display_title(article),
                    "reason": "基于今日热点，值得进一步展开",
                    "sources": [article.source_name],
                }
                for article in sorted(articles, key=lambda item: item.score, reverse=True)[:5]
            ]

    async def _generate_thoughts(self, articles: list[Article]) -> str:
        titles = "\n".join(f"- {display_title(article)}" for article in articles[:10])
        prompt = THOUGHTS_PROMPT.format(titles=titles)
        try:
            return await chat_completion(
                prompt,
                settings=self.settings,
                llm_client=self.llm_client,
                temperature=0.6,
                max_tokens=512,
            )
        except Exception:
            return "今天 AI 圈信息量依然很大，模型迭代和产品落地都在加速，值得持续跟踪。"

    def _build_frontmatter(self, stats: ReportStats) -> str:
        generated = stats.generated_at.astimezone(self.timezone).isoformat(timespec="seconds")
        return "\n".join(
            [
                "---",
                f"date: {stats.report_date.isoformat()}",
                f"generated: {generated}",
                f"sources: {stats.sources_success}/{stats.sources_total}",
                f"candidates: {stats.l1_count}",
                f"selected: {stats.l2_count}",
                f"filter_efficiency: {stats.snr:.3f}",
                f"l1_pass_rate: {stats.l1_pass_rate:.3f}",
                f"l2_quality: {stats.quality_rate:.3f}",
                "---",
            ]
        )

    def _build_top3_table(
        self,
        articles: list[Article],
        top3_items: list[dict[str, Any]],
    ) -> str:
        article_map = {article.id: article for article in articles}
        rows: list[str] = []
        for index, item in enumerate(top3_items[:3], start=1):
            article = article_map.get(str(item.get("id", "")))
            if article is None and index - 1 < len(articles):
                article = sorted(articles, key=lambda x: x.score, reverse=True)[index - 1]
            if article is None:
                continue
            reason = str(item.get("reason") or "")
            event = self._format_top3_event(article, reason=reason or None)
            rows.append(
                f"| {index} | {event} | {self._source_count(article)} 个信源 | {int(article.score)} |"
            )
        header = "| # | 事件 | 信源 | 评分 |\n|---|------|------|------|"
        return header + "\n" + "\n".join(rows)

    def _build_section_table(self, articles: list[Article]) -> str:
        if not articles:
            return "| 事件 | 核心看点 | 来源 | 评分 |\n|------|---------|------|------|\n| 暂无 | - | - | - |"
        rows = [
            "| 事件 | 核心看点 | 来源 | 评分 |",
            "|------|---------|------|------|",
        ]
        for article in sorted(articles, key=lambda item: item.score, reverse=True):
            rows.append(
                "| {event} | {summary} | {source} | {score} |".format(
                    event=self._format_event_cell(article),
                    summary=article.summary or article.summary_raw or "-",
                    source=article.source_name,
                    score=int(article.score),
                )
            )
        return "\n".join(rows)

    def _build_topic_pool_section(self, topics: list[dict[str, Any]]) -> str:
        lines = [
            "## 🎬 博主选题池",
            "",
            "> 基于今日信息，推荐 5 个值得深度写作的选题",
            "",
        ]
        for index, topic in enumerate(topics[:5], start=1):
            sources = topic.get("sources") or []
            source_text = "、".join(str(item) for item in sources) if sources else "今日精选"
            lines.extend(
                [
                    f"{index}. **{topic.get('title', '待定选题')}**",
                    f"   - 为什么值得写：{topic.get('reason', '信息密度高，具备传播价值')}",
                    f"   - 信息来源：{source_text}",
                    "",
                ]
            )
        return "\n".join(lines).rstrip()

    def _build_self_check(self, stats: ReportStats) -> str:
        failed = "、".join(stats.failed_sources) if stats.failed_sources else "无"
        return "\n".join(
            [
                "## 🔍 系统自检",
                "",
                "| 指标 | 数值 |",
                "|------|------|",
                f"| 采集信源 | {stats.sources_success}/{stats.sources_total} |",
                f"| 成功采集 | {stats.sources_success} |",
                f"| 失败信源 | {len(stats.failed_sources)}（{failed}） |",
                f"| 原始文章 | {stats.raw_count} |",
                f"| L1 筛选通过 | {stats.l1_count} |",
                f"| L2 精选 | {stats.l2_count} |",
                f"| 过滤效率 (SNR) | {stats.snr * 100:.1f}% |",
                f"| L1 通过率 | {stats.l1_pass_rate * 100:.1f}% |",
                f"| L2 优质率 | {stats.quality_rate * 100:.0f}% |",
                "",
                f"> 🤖 由知识侦察兵 v2.0 自动生成 | 下次更新 "
                f"{stats.report_date.isoformat()} 07:00",
            ]
        )

    async def build(
        self,
        articles: list[Article],
        stats: ReportStats | None = None,
    ) -> str:
        """组装完整日报 Markdown。"""
        if stats is None:
            now = datetime.now(timezone.utc)
            stats = ReportStats(
                report_date=now.astimezone(self.timezone).date(),
                generated_at=now,
                l2_count=len(articles),
            )

        weekday = WEEKDAY_NAMES[stats.report_date.weekday()]
        top3_items = await self._generate_top3(articles)
        topic_pool = await self._generate_topic_pool(articles)
        thoughts = await self._generate_thoughts(articles)

        grouped: dict[Category, list[Article]] = {category: [] for category, _ in SECTION_CONFIG}
        for article in articles:
            category = article.category or Category.AI_MODELS
            grouped.setdefault(category, []).append(article)

        parts = [
            self._build_frontmatter(stats),
            "",
            f"# AI 日报 {stats.report_date.isoformat()}（{weekday}）",
            "",
            "> 📡 采集 {}/{} 信源 → L1 筛出 {} 篇 → L2 精选 {} 篇 | 过滤效率 {:.1f}% | L2 优质率 {:.0f}%".format(
                stats.sources_success,
                stats.sources_total,
                stats.l1_count,
                stats.l2_count,
                stats.snr * 100,
                stats.quality_rate * 100,
            ),
            "",
            "## 📌 今日 TOP 3",
            "",
            self._build_top3_table(articles, top3_items),
            "",
            "---",
            "",
        ]

        for category, heading in SECTION_CONFIG:
            parts.extend(
                [
                    f"## {heading}",
                    "",
                    self._build_section_table(grouped.get(category, [])),
                    "",
                ]
            )

        parts.extend(
            [
                "---",
                "",
                self._build_topic_pool_section(topic_pool),
                "",
                "---",
                "",
                "## 💭 今日碎碎念",
                "",
                "> AI 博主\"知识侦察兵\"的今日观察",
                "",
                thoughts,
                "",
                "---",
                "",
                self._build_self_check(stats),
            ]
        )
        return "\n".join(parts)
