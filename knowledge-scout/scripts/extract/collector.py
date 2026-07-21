# -*- coding: utf-8 -*-
"""
knowledge-scout v4.0 — 统一采集层
用 RSSHub 公共实例 + 原站直连 RSS，替代手写采集器。

设计原则:
- 每个源定义一个 SOURCE dict（name + url + type + fetch_method）
- 统一输出 list[Article]，对接现有 filter.py
- DIRECT RSS > RSSHub 降级链
"""
import ssl
import sys
import io
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.request import Request, urlopen

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---- 编码 (仅 CLI 直接运行时) ----
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass

# ---- 日志 ----
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("collector")

# ---- HTTP 会话 ----
feedparser.USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)

_session = requests.Session()
_session.headers.update({"User-Agent": feedparser.USER_AGENT})
retry = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503])
_session.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=5, pool_maxsize=10))

TIMEOUT = 15
RSSHUB_PRIMARY = "https://rsshub.rssforever.com"

# ---- 数据模型 ----
@dataclass
class Article:
    platform: str
    title: str
    url: str
    summary: str = ""
    author: str = ""
    published: str = ""
    category: str = "AI技术"
    raw_score: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "author": self.author,
            "published": self.published,
            "category": self.category,
            "raw_score": self.raw_score,
            "metadata": self.metadata,
        }


# ---- 信息源配置 ----
SOURCES = [
    # --- 行业媒体：原站直连 RSS ---
    {"name": "36氪", "type": "direct", "url": "https://36kr.com/feed",
     "category": "AI技术", "desc": "AI产业/创投/政策"},
    {"name": "爱范儿", "type": "direct", "url": "https://www.ifanr.com/feed",
     "category": "AI技术", "desc": "产品+科技"},
    {"name": "少数派", "type": "direct", "url": "https://sspai.com/feed",
     "category": "效率工具", "desc": "工具+效率"},
    {"name": "量子位", "type": "direct", "url": "https://www.qbitai.com/feed",
     "category": "AI技术", "desc": "AI专业媒体（核心源）"},
    # --- RSSHub 桥接 ---
    {"name": "虎嗅", "type": "rsshub", "route": "/huxiu/article",
     "category": "AI技术", "desc": "深度商业分析"},
    {"name": "知乎日报", "type": "rsshub", "route": "/zhihu/daily",
     "category": "综合", "desc": "知乎每日精选"},
    {"name": "晚点LatePost", "type": "rsshub", "route": "/latepost",
     "category": "AI技术", "desc": "科技商业深度"},
    {"name": "36氪快讯", "type": "rsshub", "route": "/36kr/newsflashes",
     "category": "AI技术", "desc": "36氪快讯补充"},
    # --- 国际社区：原站直连 RSS ---
    {"name": "Reddit ML", "type": "direct", 
     "url": "https://www.reddit.com/r/MachineLearning/.rss",
     "category": "AI技术", "desc": "ML学术与产业讨论"},
]

# 可选源（待修复后启用）
OPTIONAL = [
    {"name": "GitHub Trending", "type": "direct",
     "url": "https://github.com/trending.atom", "category": "开源"},
    {"name": "HuggingFace", "type": "direct",
     "url": "https://huggingface.co/papers/feed.xml", "category": "AI研究"},
]


# ---- 采集引擎 ----
class Collector:
    """统一采集器：RSS直连 + RSSHub 降级"""

    def __init__(self, sources=None):
        self.sources = sources or SOURCES
        self.articles: list[Article] = []

    def fetch_all(self) -> list[Article]:
        """采集所有源，容错每个源独立失败"""
        log.info(f"开始采集 {len(self.sources)} 个信息源...")
        start = time.time()

        for i, src in enumerate(self.sources):
            name = src["name"]
            try:
                if src["type"] == "direct":
                    articles = self._fetch_direct(src)
                else:
                    articles = self._fetch_rsshub(src)
                self.articles.extend(articles)
                log.info(f"  [{i+1}/{len(self.sources)}] {name}: {len(articles)} 篇")
            except Exception as e:
                log.warning(f"  [{i+1}/{len(self.sources)}] {name}: 失败 ({e})")

        elapsed = time.time() - start
        log.info(f"采集完成: {len(self.articles)} 篇, 耗时 {elapsed:.1f}s")
        return self.articles

    def _fetch_direct(self, src: dict) -> list[Article]:
        """直接 RSS 采集"""
        text = self._http_get(src["url"])
        feed = feedparser.parse(text)
        return self._parse_entries(feed, src)

    def _fetch_rsshub(self, src: dict) -> list[Article]:
        """RSSHub 桥接采集"""
        url = f"{RSSHUB_PRIMARY}{src['route']}"
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            raise Exception(f"RSSHub返回异常: {feed.bozo_exception}")
        return self._parse_entries(feed, src)

    def _http_get(self, url: str) -> str:
        """带重试的 HTTP GET，返回文本"""
        resp = _session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.text

    def _parse_entries(self, feed, src: dict) -> list[Article]:
        """将 feedparser entries 转为 Article 列表"""
        articles = []
        for e in feed.entries:
            # 提取 URL
            url = e.get("link", "")
            if not url:
                url = e.get("id", "")
            # 提取摘要
            summary = ""
            if hasattr(e, "summary"):
                summary = self._strip_html(getattr(e, "summary", ""))
            elif hasattr(e, "description"):
                summary = self._strip_html(getattr(e, "description", ""))
            # 截断摘要
            summary = summary[:300]
            # 提取发布时间
            published = ""
            if hasattr(e, "published_parsed") and e.published_parsed:
                published = time.strftime("%Y-%m-%d", e.published_parsed)
            elif hasattr(e, "updated_parsed") and e.updated_parsed:
                published = time.strftime("%Y-%m-%d", e.updated_parsed)
            # 作者
            author = getattr(e, "author", "") or ""
            # 分类
            cat = src.get("category", "AI技术")

            article = Article(
                platform=src["name"],
                title=getattr(e, "title", "").strip(),
                url=url,
                summary=summary,
                author=author,
                published=published,
                category=cat,
                metadata={"source_type": src["type"], "source_desc": src.get("desc", "")},
            )
            articles.append(article)
        return articles

    @staticmethod
    def _strip_html(text: str) -> str:
        """简单的 HTML 标签去除"""
        import re
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def to_dicts(self) -> list[dict]:
        return [a.to_dict() for a in self.articles]


# ---- CLI 入口 ----
if __name__ == "__main__":
    collector = Collector()
    articles = collector.fetch_all()

    print(f"\n{'='*60}")
    print(f"采集结果: {len(articles)} 篇文章")
    print(f"{'='*60}")

    # 按平台统计
    from collections import Counter
    stats = Counter(a.platform for a in articles)
    for name, count in stats.most_common():
        print(f"  {name}: {count} 篇")

    # 显示前5篇样例
    print(f"\n--- 样例 ---")
    for a in articles[:5]:
        print(f"\n  [{a.platform}] {a.title[:60]}")
        print(f"    {a.url[:80]}")
        print(f"    {a.summary[:80]}...")
