"""深度解读引擎：候选选取、全文拉取、结构化分析。"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from bs4 import BeautifulSoup
from openai import AsyncOpenAI

from src.config import Settings, get_settings
from src.models import Article
from src.pipeline.classifier import display_title
from src.pipeline.llm_client import chat_completion
from src.sources.utils import USER_AGENT

logger = logging.getLogger(__name__)

SHANGHAI_TZ = timezone(timedelta(hours=8))

DEEP_ANALYSIS_PROMPT = """你是 AI 行业深度分析师。请对以下文章进行结构化深度解读。

原文标题：{title}
来源：{source_name}
原文链接：{url}

全文内容：
{content}

请按以下结构输出 Markdown：

## 📋 一句话总结
> 用一句话说清楚这篇文章在讲什么（30-60 字）

## 🔑 核心要点
1. **{{要点标题}}**：{{2-3 句话展开}}
2. **{{要点标题}}**：{{2-3 句话展开}}
3. （至少 3 个要点，最多 5 个）

## 📊 背景与上下文
{{说明这条新闻发生的背景、前因后果、跟之前事件的关联、行业格局中的位置。200-300 字。}}

## 💡 深度分析
{{这是最有价值的部分。基于文章内容和你的行业知识，做出有洞见的分析：
- 这件事意味着什么？
- 谁会受益？谁会被影响？
- 跟其他公司的类似动作有什么异同？
- 未来 6-12 个月会怎么发展？
300-400 字。}}

## 🔗 延伸阅读
- {{相关的文章、论文、资源（如果文章里有提到）}}

---

> 分析时间：{now}
> 原文链接：{url}
"""


def _priority_tier(article: Article, settings: Settings) -> int:
    """数值越小优先级越高。"""
    merged_count = len(article.merged_from)
    if article.score >= settings.deep_analysis_min_score_high and merged_count >= 3:
        return 0
    if article.score >= settings.deep_analysis_min_score_high:
        return 1
    if article.score >= settings.deep_analysis_min_score_fallback:
        return 2
    return 3


def extract_main_html(html: str) -> str:
    """从 HTML 中提取正文区域。"""
    try:
        from readability import Document

        return Document(html).summary()
    except Exception:
        logger.debug("readability-lxml 提取失败，回退到 BeautifulSoup")

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.body
    return str(main) if main else html


def html_to_text(html: str, *, limit: int = 6000) -> str:
    """将 HTML 转为保留段落结构的纯文本。"""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text[:limit]


class DeepAnalyzer:
    """深度解读分析器。"""

    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: AsyncOpenAI | None = None,
        *,
        fetcher: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client
        self.fetcher = fetcher

    def select_candidates(self, articles: list[Article]) -> list[Article]:
        """从精选文章中选出值得深度解读的候选。"""
        if not articles:
            return []

        max_count = self.settings.deep_analysis_max_count
        ranked = sorted(
            articles,
            key=lambda article: (_priority_tier(article, self.settings), -article.score),
        )
        candidates = [
            article
            for article in ranked
            if article.source_id != "aihot"
            and not article.pre_summarized
            and _priority_tier(article, self.settings) <= 2
        ][:max_count]

        if not candidates:
            candidates = [max(articles, key=lambda article: article.score)]

        return candidates[:max_count]

    async def fetch_full_content(self, article: Article) -> str:
        """拉取完整原文并清洗为纯文本。"""
        if self.fetcher is not None:
            return await self.fetcher(article)

        if article.content and len(article.content.strip()) >= 200:
            return article.content[: self.settings.deep_analysis_content_limit]

        timeout = aiohttp.ClientTimeout(total=self.settings.fetch_timeout)
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(article.url) as response:
                response.raise_for_status()
                html = await response.text()

        main_html = extract_main_html(html)
        return html_to_text(main_html, limit=self.settings.deep_analysis_content_limit)

    async def deep_analyze(self, article: Article, content: str) -> str:
        """调用 LLM 生成结构化深度解读 Markdown。"""
        now = datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M")
        prompt = DEEP_ANALYSIS_PROMPT.format(
            title=display_title(article),
            source_name=article.source_name,
            url=article.url,
            content=content[: self.settings.deep_analysis_content_limit],
            now=now,
        )
        return await chat_completion(
            prompt,
            settings=self.settings,
            llm_client=self.llm_client,
            temperature=0.4,
            max_tokens=2048,
        )

    async def run(self, articles: list[Article]) -> list[dict[str, Any]]:
        """完整流程：选取 → 拉取 → 分析 → 返回结果列表。"""
        candidates = self.select_candidates(articles)
        results: list[dict[str, Any]] = []

        for article in candidates:
            try:
                content = await self.fetch_full_content(article)
                if not content.strip():
                    logger.warning("正文为空，跳过: %s", article.id)
                    continue
                analysis = await self.deep_analyze(article, content)
                results.append(
                    {
                        "article_id": article.id,
                        "title": display_title(article),
                        "url": article.url,
                        "source_name": article.source_name,
                        "score": article.score,
                        "merged_count": len(article.merged_from) + 1,
                        "analysis": analysis,
                        "filepath": None,
                    }
                )
            except Exception as exc:
                logger.warning("深度解读失败，尝试下一篇: %s", exc)
                continue

        return results
