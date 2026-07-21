"""微信公众号文章搜索引擎

通过搜狗微信搜索 (weixin.sogou.com) 按兴趣主题搜索公众号文章。
返回文章 URL、标题、摘要、公众号名称，供后续抓取正文和深度解读。

搜索策略：
1. 从 INTERESTS.md 提取核心关键词
2. 每个关键词搜索 top 5-10 篇
3. 去重、过滤广告/低质内容
4. 返回结构化文章列表
"""

import re
import time
import hashlib
from datetime import datetime
from urllib.parse import quote, urlparse
import urllib.request
import urllib.error


# 搜狗微信搜索
SOGOU_BASE = "https://weixin.sogou.com/weixin"

# 高质量目标公众号（可直接通过 RSSHub 抓取）
TARGET_ACCOUNTS = {
    # AI 前沿
    "量子位": "https://rsshub.rssforever.com/wechat/mp/msgalbum/QbitAI/3145849588",
    "机器之心": "https://rsshub.rssforever.com/wechat/mp/msgalbum/almosthuman2014/3470170847",
    # 分析/管理
    "咨询与管理": None,  # 需要搜狗搜索
    "AI前线": None,
    # Agent/Skill
    "夕小瑶科技说": None,
    "AI科技评论": None,
}

# 高风险低质关键词（过滤用）
LOW_QUALITY_PATTERNS = [
    r"限时.*免费", r"扫码.*领取", r"关注.*回复", r"转发.*群",
    r"广告", r"推广", r"课程.*优惠", r"仅需.*元",
    r"薅羊毛", r"福利", r"红包",
]

# 高质量信号关键词
HIGH_QUALITY_PATTERNS = [
    r"万字", r"长文", r"深度", r"拆解", r"方法论", r"框架",
    r"实践", r"复盘", r"指南", r"手册", r"白皮书",
    r"报告", r"解读", r"底层", r"本质", r"全景",
    r"架构", r"设计", r"体系", r"治理",
]


def search_wechat(query: str, max_results: int = 10) -> list[dict]:
    """
    通过搜狗微信搜索文章
    
    注意：搜狗有反爬机制，可能需要浏览器模拟。
    这里先用 HTTP 请求尝试，失败时提示用户手动输入链接。
    """
    url = f"{SOGOU_BASE}?type=2&query={quote(query)}"
    articles = []

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')

        # 解析搜索结果
        # 搜狗微信搜索结果结构：<li class="news-list2"> → <h3><a> = 标题链接
        # 摘要：<p class="txt-info">
        # 公众号：<a class="account">
        items = re.findall(
            r'<li[^>]*class="[^"]*news-list2[^"]*"[^>]*>.*?</li>',
            html, re.DOTALL | re.IGNORECASE
        )

        for item in items[:max_results]:
            # 提取标题和链接
            title_match = re.search(
                r'<h3>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
                item, re.DOTALL
            )
            if not title_match:
                continue

            link = title_match.group(1).strip()
            title = re.sub(r'<[^>]+>', '', title_match.group(2)).strip()

            # 提取摘要
            summary_match = re.search(
                r'<p[^>]*class="[^"]*txt-info[^"]*"[^>]*>(.*?)</p>',
                item, re.DOTALL
            )
            summary = ""
            if summary_match:
                summary = re.sub(r'<[^>]+>', '', summary_match.group(1)).strip()
                summary = re.sub(r'\s+', ' ', summary)[:200]

            # 提取公众号名称
            account_match = re.search(
                r'<a[^>]*class="[^"]*account[^"]*"[^>]*>(.*?)</a>',
                item, re.DOTALL
            )
            account = ""
            if account_match:
                account = re.sub(r'<[^>]+>', '', account_match.group(1)).strip()

            articles.append({
                "title": title,
                "url": link,
                "summary": summary,
                "source": account,
                "search_query": query,
                "discovered_at": datetime.now().isoformat(),
            })

    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        print(f"  ⚠️ 搜狗搜索失败 [{query}]: {e}")
    except Exception as e:
        print(f"  ⚠️ 解析失败 [{query}]: {e}")

    return articles


def fetch_article_content(url: str) -> dict | None:
    """
    抓取微信公众号文章正文。
    
    公众号文章通过 mp.weixin.qq.com 域名访问，
    需要处理防盗链和可能的验证页面。
    """
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Referer": "https://weixin.sogou.com/",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')

        # 提取文章正文
        # 公众号文章正文通常在 <div id="js_content">
        content_match = re.search(
            r'<div[^>]*id="js_content"[^>]*>(.*?)</div>\s*</div>\s*<script',
            html, re.DOTALL
        )
        if not content_match:
            # 尝试备用模式
            content_match = re.search(
                r'<div[^>]*class="[^"]*rich_media_content[^"]*"[^>]*>(.*?)</div>',
                html, re.DOTALL
            )

        raw_content = content_match.group(1) if content_match else ""

        # 清理 HTML 标签
        text = re.sub(r'<[^>]+>', '\n', raw_content)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()

        # 提取标题
        title_match = re.search(
            r'<h1[^>]*class="[^"]*rich_media_title[^"]*"[^>]*>(.*?)</h1>',
            html, re.DOTALL
        )
        title = ""
        if title_match:
            title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()

        # 提取公众号名称
        author_match = re.search(
            r'<a[^>]*id="js_name"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )
        author = ""
        if author_match:
            author = re.sub(r'<[^>]+>', '', author_match.group(1)).strip()

        return {
            "title": title,
            "url": url,
            "author": author,
            "content": text,
            "content_length": len(text),
        }

    except Exception as e:
        print(f"  ⚠️ 抓取文章失败 [{url[:60]}]: {e}")
        return None


def is_high_quality(article: dict) -> bool:
    """判断文章是否为高质量深度内容"""
    title = article.get("title", "")
    summary = article.get("summary", "")
    text = f"{title} {summary}"

    # 过滤低质
    for pattern in LOW_QUALITY_PATTERNS:
        if re.search(pattern, text):
            return False

    # 检测深度信号
    quality_score = 0
    for pattern in HIGH_QUALITY_PATTERNS:
        if re.search(pattern, text):
            quality_score += 1

    # 标题长度：太短可能是八卦/快讯
    if len(title) < 10:
        return False

    return quality_score >= 1  # 至少一个深度信号


def search_by_interests(interests_config: dict, max_per_topic: int = 5) -> list[dict]:
    """
    根据兴趣配置搜索文章
    
    Args:
        interests_config: 从 INTERESTS.md 解析的兴趣字典
        max_per_topic: 每个主题最多搜索几篇
    """
    all_articles = []
    seen_urls = set()

    # 提取核心关键词
    core_keywords = [
        "AI Agent 企业 架构",
        "大模型 落地 实践",
        "AI 方法论 框架",
        "Agent Skill 工程",
        "AI 智能体 治理",
        "企业 AI 转型 案例",
        "AI 短剧 AIGC",
        "AI 视频生成",
        "知识管理 AI",
        "Agent 自进化",
    ]

    for kw in core_keywords:
        print(f"  🔍 搜索: {kw}")
        articles = search_wechat(kw, max_per_topic)

        for art in articles:
            url = art.get("url", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)

            if is_high_quality(art):
                all_articles.append(art)

        # 避免请求过快
        time.sleep(1.5)

    # 按质量排序（深度信号越多越靠前）
    def quality_key(a):
        t = a.get("title", "") + a.get("summary", "")
        return sum(1 for p in HIGH_QUALITY_PATTERNS if re.search(p, t))

    all_articles.sort(key=quality_key, reverse=True)

    return all_articles


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    print("🔍 微信文章搜索测试\n")
    results = search_wechat("AI Agent 企业 架构", max_results=5)
    print(f"\n找到 {len(results)} 篇:")
    for r in results:
        print(f"  - {r['title'][:50]}")
        print(f"    来源: {r['source']} | 链接: {r['url'][:60]}")
