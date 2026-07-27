"""L2 LLM 精筛：DeepSeek 评选 Top K 高质量文章。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from src.config import Settings, get_settings
from src.models import Article, QualityLevel
from src.filter.layer1_rule import score_to_quality_level

logger = logging.getLogger(__name__)

L2_SELECTION_PROMPT = """你是一个严格、挑剔的 AI 日报编辑。

以下是 {count} 条 AI 新闻候选。你需要选出最值得进入今日日报的 {top_k} 条。

评分标准（每项 0-25 分）：
1. 重要性：这条新闻对 AI 行业有多大影响？
2. 新颖性：是不是今天才有的新信息？有没有独家视角？
3. 信息量：有没有具体数据、案例、分析？还是泛泛而谈？
4. 可读性：对中文 AI 博主读者来说，这条好读懂吗？

新闻列表：
{articles_block}

请返回 JSON 列表，每条包含：
{{
  "id": "文章编号",
  "score": 0-100,
  "reason": "一句话理由（20 字以内）",
  "rank": 1
}}

只返回 JSON 数组，不要其他内容。"""


class Layer2LLMFilter:
    """L2 LLM 精筛器。"""

    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: AsyncOpenAI | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client

    def _get_client(self) -> AsyncOpenAI:
        if self.llm_client is None:
            self.llm_client = AsyncOpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
            )
        return self.llm_client

    @staticmethod
    def _build_articles_block(articles: list[Article]) -> str:
        lines: list[str] = []
        for index, article in enumerate(articles, start=1):
            summary = article.summary_raw or article.summary or "无摘要"
            lines.append(
                f"{index}. [{article.id}] {article.title}\n"
                f"   来源: {article.source_name} | L1 评分: {article.score}\n"
                f"   描述: {summary[:120]}"
            )
        return "\n".join(lines)

    @staticmethod
    def _parse_json_response(content: str) -> list[dict[str, Any]]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise ValueError("L2 返回结果不是 JSON 数组")
        return payload

    async def select_top_articles(self, articles: list[Article]) -> list[Article]:
        """从候选文章中精选 Top K。"""
        if not articles:
            return []

        candidate_limit = self.settings.l2_candidate_limit
        top_k = self.settings.l2_top_n
        candidates = articles[:candidate_limit]

        prompt = L2_SELECTION_PROMPT.format(
            count=len(candidates),
            top_k=top_k,
            articles_block=self._build_articles_block(candidates),
        )

        client = self._get_client()
        response = await client.chat.completions.create(
            model=self.settings.deepseek_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        content = response.choices[0].message.content or "[]"
        selections = self._parse_json_response(content)

        article_map = {article.id: article for article in candidates}
        ranked: list[tuple[int, Article, str]] = []

        for item in selections:
            article_id = str(item.get("id", ""))
            article = article_map.get(article_id)
            if article is None:
                continue
            llm_score = float(item.get("score", article.score))
            reason = str(item.get("reason", ""))
            rank = int(item.get("rank", 999))
            updated = article.model_copy(
                update={
                    "score": round(llm_score, 2),
                    "quality_level": score_to_quality_level(llm_score),
                    "summary": reason or article.summary,
                }
            )
            ranked.append((rank, updated, reason))

        ranked.sort(key=lambda item: item[0])
        return [item[1] for item in ranked[:top_k]]
