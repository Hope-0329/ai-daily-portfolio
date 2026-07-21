"""Article base class — all extractors return list[Article]"""

from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Optional


@dataclass
class Article:
    """标准化条目"""
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


class BaseExtractor(ABC):
    """采集器基类"""

    @abstractmethod
    async def fetch(self) -> list[Article]:
        """从平台获取内容列表"""
        ...
