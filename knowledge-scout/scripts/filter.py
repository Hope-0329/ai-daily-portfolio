"""筛选评分引擎 — 粗筛 → 精筛 → 去重 → 排序"""

import re
from difflib import SequenceMatcher
from .extract.base import Article


class FilterEngine:
    """通用筛选引擎"""

    def __init__(self, config: dict):
        self.config = config
        self.min_score = config.get("min_score", 50)
        self.max_articles = config.get("max_articles", 40)
        self.duplicate_threshold = config.get("duplicate_threshold", 0.75)
        self.category_weights = config.get("category_weights", {
            "AI技术": 1.0,
            "投资分析": 0.9,
            "经济趋势": 0.8,
            "产业研究": 0.85,
        })

    def process(self, articles: list[Article]) -> list[Article]:
        """全流程：评分 → 过滤 → 去重 → 排序 → 截断"""
        # 1. 分类加权
        scored = [self._apply_category_weight(a) for a in articles]

        # 2. 最低分过滤
        filtered = [a for a in scored if a.raw_score >= self.min_score]

        # 3. 去重
        deduped = self._deduplicate(filtered)

        # 4. 排序（按 raw_score 降序）
        deduped.sort(key=lambda a: a.raw_score, reverse=True)

        # 5. 截断
        return deduped[:self.max_articles]

    def _apply_category_weight(self, article: Article) -> Article:
        weight = self.category_weights.get(article.category, 0.7)
        article.raw_score *= weight
        return article

    def _deduplicate(self, articles: list[Article]) -> list[Article]:
        """基于标题相似度去重，保留高分条目"""
        kept = []
        for article in sorted(articles, key=lambda a: a.raw_score, reverse=True):
            is_dup = False
            for existing in kept:
                sim = self._title_similarity(article.title, existing.title)
                if sim >= self.duplicate_threshold:
                    is_dup = True
                    break
            if not is_dup:
                kept.append(article)
        return kept

    @staticmethod
    def _title_similarity(t1: str, t2: str) -> float:
        """基于 SequenceMatcher 的标题相似度"""
        # 预处理：去标点、小写
        def clean(s):
            return re.sub(r'[^\w\s]', '', s).lower().strip()
        return SequenceMatcher(None, clean(t1), clean(t2)).ratio()

    @staticmethod
    def normalize_scores(articles: list[Article]) -> list[Article]:
        """将 raw_score 归一化到 1-5 星"""
        if not articles:
            return articles
        scores = [a.raw_score for a in articles]
        min_s, max_s = min(scores), max(scores)
        if max_s == min_s:
            for a in articles:
                a.raw_score = 3.0
            return articles
        for a in articles:
            a.raw_score = 1 + 4 * (a.raw_score - min_s) / (max_s - min_s)
        return articles
