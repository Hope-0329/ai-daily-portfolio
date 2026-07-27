"""采集器抽象基类。"""

from abc import ABC, abstractmethod

from src.models import Article, Source


class SourceCollector(ABC):
    """信源采集器基类。"""

    @abstractmethod
    async def fetch(self, source: Source) -> list[Article]:
        """拉取一个信源，返回标准化 Article 列表。"""
        raise NotImplementedError
