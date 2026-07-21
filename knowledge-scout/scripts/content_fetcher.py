"""全文抓取模块 v2.0

使用 trafilatura 进行统计学正文提取，不再依赖站点的 DOM 结构变化。
trafilatura 是 Python 最成熟的内容抓取库，支持 90%+ 的中英文新闻/博客站点。

备用：启发式提取 + 站点特定正则（兜底）
"""

import re
import ssl
import urllib.request
import urllib.error
import socket
from html import unescape

import trafilatura

# ── 配置 ──
socket.setdefaulttimeout(15)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
}

# 禁用 SSL 验证（部分站点自签证书）
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def _download_html(url: str) -> str | None:
    """下载 HTML 原文"""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f"    ⚠️ 下载失败: {e}")
        return None


def fetch_with_trafilatura(url: str) -> str | None:
    """用 trafilatura 提取正文（主力方案）"""
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(
                downloaded,
                include_links=False,
                include_images=False,
                include_tables=False,
                include_formatting=False,
                favor_precision=True,
                deduplicate=True,
            )
            if text and len(text) > 200:
                return text.strip()
    except Exception as e:
        print(f"    ⚠️ trafilatura 提取失败: {e}")
    return None


def _extract_by_heuristic(html: str) -> str | None:
    """
    启发式正文提取：去掉 header/nav/footer/script/style 后用统计学方法找最长文本块。
    trafilatura 失败的兜底方案。
    """
    for tag in ['header', 'nav', 'footer', 'script', 'style', 'noscript', 'svg', 'iframe']:
        html = re.sub(rf'<{tag}[^>]*>.*?</{tag}>', '', html, flags=re.DOTALL | re.IGNORECASE)

    text = re.sub(r'</?(?:div|p|br|h[1-6]|li|tr|section|article|blockquote|pre)[^>]*>', '\n', html)
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'&nbsp;', ' ', text)

    paragraphs = re.split(r'\n\s*\n', text)
    scored = []
    for para in paragraphs:
        cn = len(re.findall(r'[\u4e00-\u9fff]', para))
        noise = len(re.findall(r'[{}();]', para))
        score = cn - noise * 2
        if score > 30:
            scored.append((score, para.strip()))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    result = '\n\n'.join(p[1] for p in scored[:20])
    return result if len(result) > 200 else None


def _strip_html_noise(html_text: str) -> str:
    """将 HTML 转为纯文本（用于站点特定正则的备选）"""
    text = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', '', html_text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'<svg[^>]*>.*?</svg>', '', text, flags=re.DOTALL)
    text = re.sub(r'\s*(?:style|on\w+)="[^"]*"', '', text)
    text = re.sub(r'</?(?:div|p|br|h[1-6]|li|tr|section|article|blockquote|pre|main|aside)[^>]*>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


# ── 站点特定正则（trafilatura 兜底）──

def fetch_36kr_regex(url: str) -> str | None:
    """36氪 文章正文 - 正则兜底"""
    try:
        html = _download_html(url)
        if not html:
            return None
        html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL)
        html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL)
        html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL)
        patterns = [
            r'<div[^>]*class="[^"]*articleDetailContent[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*article-detail[^"]*"[^>]*>(.*?)</div>',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                return _strip_html_noise(match.group(1))
        return None
    except Exception:
        return None


def fetch_huxiu_regex(url: str) -> str | None:
    """虎嗅 文章正文 - 正则兜底"""
    html = _download_html(url)
    if not html:
        return None
    patterns = [
        r'<div[^>]*class="[^"]*article-content[^"]*"[^>]*>(.*?)</div>',
        r'<article[^>]*>(.*?)</article>',
        r'<div[^>]*class="[^"]*article__content[^"]*"[^>]*>(.*?)</div>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            return _strip_html_noise(match.group(1))
    return None


def fetch_qbitai_regex(url: str) -> str | None:
    """量子位 文章正文 - 正则兜底"""
    html = _download_html(url)
    if not html:
        return None
    patterns = [
        r'<div[^>]*class="[^"]*article-content[^"]*"[^>]*>(.*?)</div>',
        r'<article[^>]*>(.*?)</article>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            return _strip_html_noise(match.group(1))
    return None


def fetch_ifanr_regex(url: str) -> str | None:
    """爱范儿 - 正则兜底"""
    html = _download_html(url)
    if not html:
        return None
    patterns = [
        r'<div[^>]*class="[^"]*article-content[^"]*"[^>]*>(.*?)</div>',
        r'<div[^>]*class="[^"]*post-content[^"]*"[^>]*>(.*?)</div>',
        r'<article[^>]*>(.*?)</article>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            return _strip_html_noise(match.group(1))
    return None


def fetch_sspai_regex(url: str) -> str | None:
    """少数派 - 正则兜底"""
    html = _download_html(url)
    if not html:
        return None
    patterns = [
        r'<div[^>]*class="[^"]*article-body[^"]*"[^>]*>(.*?)</div>',
        r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>',
        r'<article[^>]*>(.*?)</article>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            return _strip_html_noise(match.group(1))
    return None


def fetch_zhihu_regex(url: str) -> str | None:
    """知乎 - 正则兜底"""
    html = _download_html(url)
    if not html:
        return None
    json_match = re.search(
        r'"content"\s*:\s*"(.*?)(?:"\s*,\s*"(?:excerpt|title|comment))',
        html, re.DOTALL
    )
    if json_match:
        content = json_match.group(1)
        content = content.replace('\\n', '\n').replace('\\"', '"')
        return _strip_html_noise(content)
    match = re.search(
        r'<div[^>]*class="[^"]*RichContent-inner[^"]*"[^>]*>(.*?)</div>',
        html, re.DOTALL
    )
    if match:
        return _strip_html_noise(match.group(1))
    return None


# ── 站点正则映射（trafilatura 之后的备选）──
SITE_REGEX = {
    "kr36": fetch_36kr_regex,
    "36氪": fetch_36kr_regex,
    "huxiu": fetch_huxiu_regex,
    "虎嗅": fetch_huxiu_regex,
    "qbitai": fetch_qbitai_regex,
    "量子位": fetch_qbitai_regex,
    "ifanr": fetch_ifanr_regex,
    "爱范儿": fetch_ifanr_regex,
    "sspai": fetch_sspai_regex,
    "少数派": fetch_sspai_regex,
    "zhihu": fetch_zhihu_regex,
    "知乎": fetch_zhihu_regex,
}


def fetch_full_article(url: str, platform: str = "") -> str | None:
    """
    提取文章正文。

    策略（按优先级）：
    1. trafilatura（主力，统计学习，不依赖 DOM 结构变化）
    2. 站点特定正则（trafilatura 失败时的兜底）
    3. 启发式提取（终极兜底）
    """
    # ── 策略1：trafilatura ──
    text = fetch_with_trafilatura(url)
    if text and len(text) > 200:
        return text

    # ── 策略2：站点正则 ──
    fetcher = SITE_REGEX.get(platform) or SITE_REGEX.get(platform.lower(), None)
    if fetcher:
        try:
            text = fetcher(url)
            if text and len(text) > 200:
                return text
        except Exception:
            pass

    # ── 策略3：启发式 ──
    try:
        html = _download_html(url)
        if html:
            text = _extract_by_heuristic(html)
            if text:
                return text
    except Exception:
        pass

    return None


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    test_urls = [
        ("36氪", "https://36kr.com/p/3899597215745664"),
        ("虎嗅", "https://www.huxiu.com/article/4876404.html"),
        ("量子位", "https://www.qbitai.com/2025/01/24000.html"),
    ]

    for platform, url in test_urls:
        print(f"\n🔍 [{platform}] {url[:60]}")
        content = fetch_full_article(url, platform)
        if content:
            print(f"  ✅ 成功: {len(content)} 字符")
            print(f"  前 150 字符: {content[:150]}")
        else:
            print(f"  ❌ 失败")
