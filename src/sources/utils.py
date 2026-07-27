"""采集层通用工具函数。"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from dateutil import parser as date_parser

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
    "AIDailyScout/2.0"
)

AI_KEYWORDS = (
    "ai",
    "artificial intelligence",
    "llm",
    "gpt",
    "machine learning",
    "deep learning",
    "neural network",
    "transformer",
    "openai",
    "anthropic",
    "claude",
    "gemini",
    "diffusion",
    "generative",
)


def url_hash(url: str) -> str:
    """将 URL 转为 MD5 哈希作为文章 ID。"""
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    """返回当前 UTC 时间。"""
    return datetime.now(timezone.utc)


def parse_published_at(value: str | None) -> datetime | None:
    """解析多种格式的时间字符串。"""
    if not value:
        return None
    try:
        dt = date_parser.parse(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def strip_html(text: str) -> str:
    """移除 HTML 标签并压缩空白。"""
    cleaned = re.sub(r"<[^>]+>", " ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def matches_ai_keywords(text: str) -> bool:
    """判断文本是否包含 AI 相关关键词。"""
    lowered = text.lower()
    return any(keyword in lowered for keyword in AI_KEYWORDS)
