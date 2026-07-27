"""文章分类：规则优先，不确定时走 LLM。"""

from __future__ import annotations

import asyncio
import logging
import re

from openai import AsyncOpenAI

from src.config import Settings, get_settings
from src.models import Article, Category
from src.pipeline.llm_client import chat_completion

logger = logging.getLogger(__name__)

ACADEMIC_SOURCES = {
    "arxiv-ai",
    "arxiv-ml",
    "arxiv-cl",
    "arxiv-cv",
    "huggingface-papers",
    "acl-anthology",
    "icml",
    "neurips",
    "synced-review",
}

LLM_CLASSIFY_PROMPT = """你是一个 AI 新闻分类专家。把以下文章分到 5 个类别之一。
只返回类别名，不要解释。

类别：ai-models / ai-products / industry / paper / tip

标题：{title}
摘要：{summary}

类别："""


def display_title(article: Article) -> str:
    """获取用于分类/展示的中文标题。"""
    return article.title_cn or article.title


def display_summary(article: Article) -> str:
    """获取用于分类/展示的摘要。"""
    return article.summary_cn or article.summary_raw or article.summary or ""


def rule_classify(title: str, summary: str, source_id: str = "") -> Category | None:
    """基于规则的文章分类，不确定时返回 None。"""
    if source_id in ACADEMIC_SOURCES:
        return Category.PAPER

    text = f"{title} {summary}".lower()
    title_lower = title.lower()

    if source_id in ACADEMIC_SOURCES or re.search(r"paper|论文|sota|benchmark|arxiv|acl|neurips|icml", text):
        if re.search(r"paper|论文|sota|benchmark|arxiv|研究", text):
            return Category.PAPER

    if re.search(r"融资|收购|裁员|财报|监管|政策|诉讼|禁令", title):
        return Category.INDUSTRY

    if re.search(r"教程|如何|指南|推荐|经验|技巧|方法论|best practice", title_lower + summary.lower()):
        return Category.TIP

    if re.search(r"发布|上线|推出|更新|launch|release", title_lower) and re.search(
        r"产品|app|api|sdk|插件|copilot|agent|平台|工具",
        text,
    ):
        return Category.AI_PRODUCTS

    if re.search(
        r"模型|llm|gpt|claude|gemini|llama|参数|训练|架构|开源|benchmark|微调|transformer",
        text,
    ):
        return Category.AI_MODELS

    return None


class ArticleClassifier:
    """文章分类器。"""

    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: AsyncOpenAI | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client

    async def _llm_classify(self, article: Article) -> Category:
        title = display_title(article)
        summary = display_summary(article)
        prompt = LLM_CLASSIFY_PROMPT.format(title=title, summary=summary[:300])
        try:
            answer = await chat_completion(
                prompt,
                settings=self.settings,
                llm_client=self.llm_client,
                temperature=0,
                max_tokens=16,
            )
            normalized = answer.strip().lower().replace("_", "-")
            for category in Category:
                if category.value == normalized:
                    return category
        except Exception as exc:
            logger.warning("LLM 分类失败，使用默认类别 ai-models: %s", exc)
        return Category.AI_MODELS

    async def classify_article(self, article: Article) -> Article:
        """为单篇文章分类。"""
        if article.category is not None:
            return article

        title = display_title(article)
        summary = display_summary(article)
        category = rule_classify(title, summary, article.source_id)
        if category is None:
            category = await self._llm_classify(article)
        return article.model_copy(update={"category": category})

    async def classify_articles(self, articles: list[Article]) -> list[Article]:
        """并发分类多篇文章。"""
        semaphore = asyncio.Semaphore(self.settings.pipeline_concurrency)

        async def _run(article: Article) -> Article:
            async with semaphore:
                return await self.classify_article(article)

        return list(await asyncio.gather(*(_run(article) for article in articles)))
