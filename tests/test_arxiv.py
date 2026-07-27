"""arXiv API 回退测试。"""

from __future__ import annotations

import pytest

from src.models import Source, SourceType
from src.sources.arxiv import fetch_arxiv_category


@pytest.mark.asyncio
async def test_fetch_arxiv_category_returns_papers() -> None:
    source = Source(
        id="arxiv-ai",
        name="arXiv AI",
        name_display="arXiv AI",
        url="https://export.arxiv.org/rss/cs.AI",
        type=SourceType.RSS,
        tier=1,
        language="en",
        fetch_timeout=60,
    )
    articles = await fetch_arxiv_category(source)
    assert 0 < len(articles) <= 15
    assert all(article.title for article in articles)
    assert all(article.url.startswith("http") for article in articles)
    assert all(article.source_id == "arxiv-ai" for article in articles)
