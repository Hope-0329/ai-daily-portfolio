"""英文文章翻译：标题与摘要。"""

from __future__ import annotations

import asyncio
import logging

from openai import AsyncOpenAI

from src.config import Settings, get_settings
from src.models import Article
from src.pipeline.llm_client import chat_completion

logger = logging.getLogger(__name__)

TITLE_PROMPT = """你是一个专业的 AI 行业翻译。请把以下英文 AI 新闻标题翻译成中文。

要求：
- 专业术语准确（比如 "fine-tuning" → "微调"，"hallucination" → "幻觉"）
- 保持原文的信息密度，不要删减
- 不要加"据报道""据悉"等废话
- 中文表达自然流畅，读起来像中文写的

英文原文：{text}
中文翻译："""

SUMMARY_PROMPT = """你是一个专业的 AI 行业翻译。请把以下英文 AI 新闻摘要翻译成中文。

要求：
- 专业术语准确（比如 "fine-tuning" → "微调"，"hallucination" → "幻觉"）
- 保持原文的信息密度，不要删减
- 不要加"据报道""据悉"等废话
- 中文表达自然流畅，读起来像中文写的

英文原文：{text}
中文翻译："""


class ArticleTranslator:
    """英文文章翻译器。"""

    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: AsyncOpenAI | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client

    def _needs_translation(self, article: Article) -> bool:
        return (article.language or "").lower() == "en"

    async def _translate_text(self, text: str, *, kind: str) -> str | None:
        if not text.strip():
            return None
        try:
            prompt_template = TITLE_PROMPT if kind == "title" else SUMMARY_PROMPT
            prompt = prompt_template.format(text=text)
            return await chat_completion(
                prompt,
                settings=self.settings,
                llm_client=self.llm_client,
                temperature=0.1,
                max_tokens=256,
            )
        except Exception as exc:
            logger.warning("翻译失败，保留原文: %s", exc)
            return None

    async def translate_article(self, article: Article) -> Article:
        """翻译单篇文章的标题与摘要。"""
        if article.pre_summarized:
            return article
        if not self._needs_translation(article):
            return article

        title_task = self._translate_text(article.title, kind="title")
        summary_task = self._translate_text(article.summary_raw or article.summary or "", kind="summary")
        title_cn, summary_cn = await asyncio.gather(title_task, summary_task)

        updates: dict[str, str | None] = {}
        if title_cn:
            updates["title_cn"] = title_cn
        if summary_cn:
            updates["summary_cn"] = summary_cn
        return article.model_copy(update=updates) if updates else article

    async def translate_articles(self, articles: list[Article]) -> list[Article]:
        """并发翻译多篇文章。"""
        semaphore = asyncio.Semaphore(self.settings.pipeline_concurrency)

        async def _run(article: Article) -> Article:
            async with semaphore:
                return await self.translate_article(article)

        return list(await asyncio.gather(*(_run(article) for article in articles)))
