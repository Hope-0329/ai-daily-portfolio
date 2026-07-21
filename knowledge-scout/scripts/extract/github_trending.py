"""GitHub Trending — 开发者热门项目追踪"""

import sys, asyncio, requests, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.interest_filter import classify_article
from .base import BaseExtractor, Article


class GithubTrendingExtractor(BaseExtractor):
    TRENDING_URL = "https://github.com/trending?since=daily"

    async def fetch(self) -> list[Article]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fetch_sync)

    def _fetch_sync(self) -> list[Article]:
        articles = []
        try:
            r = requests.get(self.TRENDING_URL, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html",
            }, timeout=12)
            r.raise_for_status()
            html = r.text
        except Exception:
            return articles

        # 提取仓库: href="/owner/repo" 且包含 <span class="text-normal">owner /</span>
        # 简化版: 直接找 href="/owner/repo" + 后面的文本
        repo_pattern = re.compile(
            r'href="/([^/]+)/([^/"]+)"[^>]*>(?:<svg[^>]*>.*?</svg>)?\s*(?:<span[^>]*>(?:\s*([^/]+)\s*/\s*)?</span>)?\s*([^<]+)',
            re.DOTALL
        )
        desc_pattern = re.compile(
            r'<p\s+class="[^"]*color-fg-muted[^"]*"[^>]*>\s*([^<]*?)\s*</p>',
        )
        lang_pattern = re.compile(
            r'<span\s+itemprop="programmingLanguage">([^<]+)</span>',
        )

        repos = repo_pattern.findall(html)
        descriptions = desc_pattern.findall(html)
        languages = lang_pattern.findall(html)

        ai_kw = ["ai", "llm", "gpt", "agent", "ml-", "deep", "neural", "transform", "diffusion", "langchain", "rag", "vector", "embedding", "fine-tun", "chatgpt", "llama", "openai", "anthropic", "stable-diffusion"]

        for i, (owner, name, span_text, rest) in enumerate(repos[:40]):
            repo_path = f"{owner}/{name}"
            # 跳过非仓库链接
            if owner in ("login", "signup", "settings", "features", "marketplace", "explore"):
                continue

            desc = descriptions[i].strip() if i < len(descriptions) else ""
            lang = languages[i].strip() if i < len(languages) else ""

            full_title = f"{owner}/{name}"
            if desc:
                full_title += f": {desc[:80]}"

            summary = desc[:200]
            if lang:
                summary += f" [{lang}]"

            # 只保留 AI 相关
            title_lower = full_title.lower()
            if not any(kw in title_lower for kw in ai_kw):
                continue

            category, score = classify_article(full_title, summary)
            if score < 1.0:
                score = 3.0

            articles.append(Article(
                platform="github",
                title=full_title[:120],
                url=f"https://github.com/{repo_path}",
                summary=summary[:200],
                author=owner,
                category="AI Agent与工程",
                raw_score=max(score, 3.0),
                metadata={"source": "GitHub Trending", "language": lang},
            ))
        return articles
