"""生成 data/sources.yaml（52 个信源配置）。"""

from __future__ import annotations

from pathlib import Path

import yaml

MEDIA = {
    "ai-models": 0.3,
    "ai-products": 0.3,
    "industry": 0.3,
    "paper": 0.05,
    "tip": 0.05,
}
ACADEMIC = {
    "ai-models": 0.2,
    "ai-products": 0.05,
    "industry": 0.05,
    "paper": 0.6,
    "tip": 0.1,
}
OFFICIAL = {
    "ai-models": 0.4,
    "ai-products": 0.3,
    "industry": 0.2,
    "paper": 0.05,
    "tip": 0.05,
}
COMMUNITY = {
    "ai-models": 0.2,
    "ai-products": 0.2,
    "industry": 0.2,
    "paper": 0.1,
    "tip": 0.3,
}
BLOG = {
    "ai-models": 0.2,
    "ai-products": 0.1,
    "industry": 0.1,
    "paper": 0.2,
    "tip": 0.4,
}


def source(
    id_: str,
    name: str,
    url: str,
    type_: str,
    tier: int,
    language: str,
    weights: dict[str, float],
    *,
    name_display: str | None = None,
    enabled: bool = True,
    disable_reason: str | None = None,
    fetch_timeout: int | None = None,
) -> dict:
    item = {
        "id": id_,
        "name": name,
        "name_display": name_display or name,
        "url": url,
        "type": type_,
        "tier": tier,
        "language": language,
        "category_weights": weights,
        "enabled": enabled,
        "fetch_interval_min": 60,
    }
    if disable_reason:
        item["disable_reason"] = disable_reason
    if fetch_timeout is not None:
        item["fetch_timeout"] = fetch_timeout
    return item


SOURCES = [
    # Tier 1
    source("qbitai", "量子位", "https://www.qbitai.com/feed", "rss", 1, "zh", MEDIA),
    source("jiqizhixin", "机器之心", "https://www.jiqizhixin.com/rss", "rss", 1, "zh", MEDIA, fetch_timeout=30),
    source("36kr-ai", "36氪 AI", "https://36kr.com/feed?category=ai", "rss", 1, "zh", MEDIA),
    source(
        "huxiu-ai",
        "虎嗅 AI",
        "https://rsshub.rssforever.com/huxiu/moment",
        "rsshub",
        1,
        "zh",
        MEDIA,
        name_display="虎嗅 AI（RSSHub 24小时）",
        fetch_timeout=45,
    ),
    source("sspai", "少数派", "https://sspai.com/feed", "rss", 1, "zh", MEDIA),
    source("ifanr", "爱范儿", "https://www.ifanr.com/feed", "rss", 1, "zh", MEDIA),
    source(
        "dudongai",
        "读懂 AI 时代",
        "https://www.readaitime.com/",
        "web",
        1,
        "zh",
        MEDIA,
        name_display="读懂 AI 时代（Read AI Time）",
    ),
    source("openai-blog", "OpenAI Blog", "https://openai.com/news/rss.xml", "rss", 1, "en", OFFICIAL),
    source(
        "anthropic-blog",
        "Anthropic Blog",
        "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml",
        "rss",
        1,
        "en",
        OFFICIAL,
        name_display="Anthropic Blog（社区 RSS 镜像）",
    ),
    source("deepmind", "Google DeepMind", "https://blog.google/technology/ai/rss/", "rss", 1, "en", OFFICIAL),
    source(
        "meta-ai",
        "Meta AI Blog",
        "https://ai.meta.com/blog/feed/",
        "rss",
        1,
        "en",
        OFFICIAL,
        enabled=False,
        disable_reason="访问超时，疑似被墙",
    ),
    source(
        "microsoft-ai",
        "Microsoft AI Blog",
        "https://news.microsoft.com/source/topics/ai/feed/",
        "rss",
        1,
        "en",
        OFFICIAL,
    ),
    source("huggingface-blog", "Hugging Face Blog", "https://huggingface.co/blog/feed.xml", "rss", 1, "en", OFFICIAL, enabled=False, disable_reason="连接超时，疑似被墙"),
    source(
        "github-trending",
        "GitHub Trending",
        "https://api.github.com/search/repositories?q=topic:artificial-intelligence+created:>7d&sort=stars&order=desc",
        "api",
        1,
        "en",
        COMMUNITY,
    ),
    source(
        "hacker-news",
        "Hacker News",
        "https://hacker-news.firebaseio.com/v0/topstories.json",
        "api",
        1,
        "en",
        COMMUNITY,
    ),
    source("techcrunch-ai", "TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/", "rss", 1, "en", MEDIA),
    source("theverge-ai", "The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "rss", 1, "en", MEDIA),
    source("venturebeat-ai", "VentureBeat AI", "https://venturebeat.com/category/ai/feed/", "rss", 1, "en", MEDIA),
    source("arstechnica-ai", "Ars Technica AI", "https://feeds.arstechnica.com/arstechnica/technology-lab/", "rss", 1, "en", MEDIA),
    source("arxiv-ai", "arXiv AI", "https://export.arxiv.org/rss/cs.AI", "rss", 1, "en", ACADEMIC, fetch_timeout=60),
    source("arxiv-ml", "arXiv ML", "https://export.arxiv.org/rss/cs.LG", "rss", 1, "en", ACADEMIC, fetch_timeout=60),
    source("arxiv-cl", "arXiv CL", "https://export.arxiv.org/rss/cs.CL", "rss", 1, "en", ACADEMIC, fetch_timeout=60),
    source("arxiv-cv", "arXiv CV", "https://export.arxiv.org/rss/cs.CV", "rss", 1, "en", ACADEMIC, fetch_timeout=60),
    source("huggingface-papers", "Hugging Face Papers", "https://huggingface.co/api/daily_papers", "api", 1, "en", ACADEMIC, enabled=False, disable_reason="连接超时，疑似被墙"),
    source("producthunt-ai", "Product Hunt AI", "https://www.producthunt.com/feed?category=ai", "rss", 1, "en", MEDIA),
    # Tier 2
    source(
        "chaping",
        "差评",
        "https://chaping.cn/feed",
        "rss",
        2,
        "zh",
        MEDIA,
        enabled=False,
        disable_reason="网站不稳定，暂时关闭",
    ),
    source("infoq-ai", "InfoQ AI", "https://www.infoq.cn/feed", "rss", 2, "zh", MEDIA),
    source("leiphone", "雷峰网", "https://www.leiphone.com/feed", "rss", 2, "zh", MEDIA),
    source("tencent-ai-lab", "腾讯 AI Lab", "https://ai.tencent.com/ailab/zh/feed/", "rss", 2, "zh", OFFICIAL, fetch_timeout=30),
    source("alibaba-damo", "阿里达摩院", "https://damo.alibaba.com/rss/news/zh", "rss", 2, "zh", OFFICIAL, fetch_timeout=30, enabled=False, disable_reason="RSS 返回 HTML 页面，官方已停用"),
    source("baidu-ai", "百度 AI", "https://ai.baidu.com/news/rss", "rss", 2, "zh", OFFICIAL, fetch_timeout=30, enabled=False, disable_reason="RSS 返回 404 页面，官方已停用"),
    source(
        "mit-tech-review",
        "MIT Tech Review AI",
        "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
        "rss",
        2,
        "en",
        MEDIA,
    ),
    source(
        "wired-ai",
        "Wired AI",
        "https://www.wired.com/feed/tag/ai/latest/rss",
        "rss",
        2,
        "en",
        MEDIA,
    ),
    source("zdnet-ai", "ZDNet AI", "https://www.zdnet.com/topic/artificial-intelligence/rss.xml", "rss", 2, "en", MEDIA),
    source("nvidia-blog", "NVIDIA Blog AI", "https://blogs.nvidia.com/feed/", "rss", 2, "en", OFFICIAL),
    source(
        "stability-ai",
        "Stability AI Blog",
        "https://github.com/Stability-AI/generative-models/releases.atom",
        "rss",
        2,
        "en",
        OFFICIAL,
        name_display="Stability AI（GitHub Releases）",
    ),
    source(
        "mistral-ai",
        "Mistral AI Blog",
        "https://mistral.ai/news/feed.xml",
        "rss",
        2,
        "en",
        OFFICIAL,
        enabled=False,
        disable_reason="访问超时，疑似被墙",
    ),
    source(
        "cohere",
        "Cohere Blog",
        "https://rsshub.rssforever.com/cohere/blog",
        "rsshub",
        2,
        "en",
        OFFICIAL,
        name_display="Cohere Blog（RSSHub）",
    ),
    source("ai-weirdness", "AI Weirdness", "https://www.aiweirdness.com/feed/", "rss", 2, "en", BLOG),
    source("import-ai", "Import AI", "https://jack-clark.net/feed/", "rss", 2, "en", MEDIA),
    source(
        "ai-news",
        "AI News",
        "https://www.artificialintelligence-news.com/feed/",
        "rss",
        2,
        "en",
        MEDIA,
        enabled=False,
        disable_reason="Cloudflare 403，暂跳过",
    ),
    source(
        "analytics-india",
        "Analytics India Mag",
        "https://analyticsindiamag.com/feed/",
        "rss",
        2,
        "en",
        MEDIA,
        enabled=False,
        disable_reason="WAF 拦截，暂跳过",
    ),
    source("synced-review", "Synced Review", "https://syncedreview.com/feed/", "rss", 2, "en", ACADEMIC),
    # Tier 3
    source(
        "zhihu-ai-hot",
        "知乎 AI 热榜",
        "https://rsshub.app/zhihu/hot/total",
        "rsshub",
        3,
        "zh",
        COMMUNITY,
        enabled=False,
        disable_reason="知乎反爬严重，暂用 RSSHub 备用",
    ),
    source("acl-anthology", "ACL Anthology", "https://aclanthology.org/feed/", "rss", 3, "en", ACADEMIC, enabled=False, disable_reason="官方 RSS 不可用"),
    source("icml", "ICML", "https://icml.cc/Conferences/2025/feed.xml", "rss", 3, "en", ACADEMIC, enabled=False, disable_reason="官方 RSS 不可用"),
    source("neurips", "NeurIPS", "https://neurips.cc/Conferences/2025/feed.xml", "rss", 3, "en", ACADEMIC, enabled=False, disable_reason="官方 RSS 不可用"),
    source("the-decoder", "The Decoder", "https://the-decoder.com/feed/", "rss", 3, "en", MEDIA),
    source("mlops-community", "MLOps Community", "https://mlops.community/feed/", "rss", 3, "en", MEDIA, enabled=False, disable_reason="官方 RSS 不可用"),
    source("lil-log", "Lil'Log", "https://lilianweng.github.io/index.xml", "rss", 3, "en", BLOG),
    source("chip-huyen", "Chip Huyen Blog", "https://huyenchip.com/feed.xml", "rss", 3, "en", BLOG),
    source("karpathy", "Andrej Karpathy Blog", "https://karpathy.github.io/feed.xml", "rss", 3, "en", BLOG),
]


def main() -> None:
    output = Path(__file__).resolve().parent.parent / "data" / "sources.yaml"
    payload = {"sources": SOURCES}
    output.write_text(
        yaml.dump(payload, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    enabled_count = sum(1 for item in SOURCES if item["enabled"])
    print(f"已写入 {len(SOURCES)} 个信源（启用 {enabled_count}）-> {output}")


if __name__ == "__main__":
    main()
