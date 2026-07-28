"""LLM 一句话摘要生成。"""

from __future__ import annotations

import asyncio
import logging

from openai import AsyncOpenAI

from src.config import Settings, get_settings
from src.models import Article
from src.pipeline.classifier import display_title
from src.pipeline.llm_client import chat_completion

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """你是 AI 行业资讯编辑。请用一句话（30-60 字）总结以下新闻的核心信息。

要求：
1. 说人话，有信息量，不要照抄原文句式
2. 包含最关键的 1-2 个数字或事实
3. 不要用"据报道""据悉""近日"等套话
4. 如果是产品发布，说清楚"谁发布了什么、有什么用"
5. 如果是行业动态，说清楚"发生了什么事、对谁有影响"

标题：{title}
原文摘要：{summary_raw}
正文片段：{content}

一句话总结："""


class ArticleSummarizer:
    """文章摘要生成器。"""

    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: AsyncOpenAI | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client

    async def summarize_article(self, article: Article) -> Article:
        """为单篇文章生成一句话摘要。"""
        if article.pre_summarized:
            existing = article.summary or article.summary_raw
            if existing:
                return article.model_copy(update={"summary": existing})
            return article
        title = display_title(article)
        summary_raw = article.summary_cn or article.summary_raw or article.summary or "无"
        content = (article.content or "")[:500]
        prompt = SUMMARY_PROMPT.format(title=title, summary_raw=summary_raw, content=content)
        try:
            summary = await chat_completion(
                prompt,
                settings=self.settings,
                llm_client=self.llm_client,
                temperature=0.3,
                max_tokens=128,
            )
            if summary:
                return article.model_copy(update={"summary": summary})
        except Exception as exc:
            logger.warning("摘要生成失败，保留原始摘要: %s", exc)
        return article

    async def summarize_articles(self, articles: list[Article]) -> list[Article]:
        """并发为多篇文章生成摘要。"""
        semaphore = asyncio.Semaphore(self.settings.pipeline_concurrency)

        async def _run(article: Article) -> Article:
            async with semaphore:
                return await self.summarize_article(article)

        return list(await asyncio.gather(*(_run(article) for article in articles)))
