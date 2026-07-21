# -*- coding: utf-8 -*-
"""
四维评分引擎 v4.0

对每篇文章计算四个维度得分，加权汇总：
  相关度 (40%)  — AI/Agent 主题匹配度
  信息密度 (25%) — 实体/数据/结构丰富度
  独家性 (20%)  — 视角独特性（独家/首发/专访）
  时效价值 (15%) — 时间敏感性 + 事件驱动

输出 0-10 总分，归一化后用于排序和星级展示。
"""

import re
import math
from datetime import datetime, timedelta
from typing import Optional


# ── AI 核心关键词（按权重分层） ──
AI_CORE = {
    5: [
        "AI Agent", "智能体", "LLM", "大模型", "GPT", "Claude", "Copilot",
        "具身智能", "多模态", "AIGC", "RAG", "提示词工程", "Agent",
        "DeepSeek", "OpenAI", "Anthropic", "月之暗面", "阶跃", "智谱",
        "Transformer", "注意力机制", "MoE", "混合专家",
    ],
    3: [
        "AI", "人工智能", "机器学习", "深度学习", "机器人", "自动化",
        "NLP", "CV", "扩散模型", "文生图", "文生视频", "视频生成",
        "强化学习", "RLHF", "SFT", "预训练", "微调", "向量数据库",
        "百川", "通义", "豆包", "文心", "混元", "腾讯元宝",
        "推理优化", "量化", "投骰解码", "模型压缩", "ICML", "NeurIPS",
        "CVPR", "ACL", "EMNLP", "论文", "SOTA", "benchmark",
    ],
    2: [
        "数字化转型", "智能化", "算法", "模型", "训练", "推理",
        "GPU", "算力", "芯片", "数据标注", "知识图谱", "联邦学习",
        "扩散", "生成式", "自回归", "蒸馏", "微调", "零样本",
    ],
    1: [
        "科技", "互联网", "软件", "云计算", "SaaS", "开源",
        "产品", "创新", "创业", "融资", "IPO", "上市",
    ],
}

# ── 独家性标记 ──
EXCLUSIVE_MARKERS = [
    ("独家", 4), ("首发", 3), ("深度", 2), ("专访", 3),
    ("特稿", 2), ("揭秘", 2), ("内幕", 2), ("第一手", 2),
    ("原创", 1), ("测评", 1), ("复盘", 2),
]

# ── 信息密度指示词（数据/数字/实体） ──
DENSITY_PATTERNS = [
    (r"\d+亿", 2),
    (r"\d+万", 2),
    (r"\d+%", 1.5),
    (r"\d+倍", 1),
    (r"\d+亿美元", 2.5),
    (r"\d+万元", 2),
    (r"Q[1-4]", 1.5),
    (r"\d{4}年", 1),
    (r"第[一二三]", 1.5),
]

# ── 时效事件关键词 ──
TIMELY_EVENTS = {
    5: ["WAIC", "苹果发布会", "Google I/O", "WWDC", "CES", "NeurIPS", "ICML", "CVPR", "ACL", "EMNLP"],
    3: ["发布", "推出", "上线", "开放", "公测", "融资", "上市", "收购", "合并", "最佳论文", "Oral"],
    2: ["更新", "升级", "降价", "合作", "战略", "签约", "裁员", "重组", "Spotlight"],
}


class Scorer:
    """四维评分引擎"""

    def __init__(self, now: Optional[datetime] = None):
        self.now = now or datetime.now()

    def score(self, title: str, summary: str, source: str = "", 
              published: str = "", url: str = "") -> float:
        """
        计算综合评分 (0-10)

        Args:
            title:   文章标题
            summary: 摘要（或前 300 字）
            source:  来源平台名
            published: 发布日期 (YYYY-MM-DD)
            url:     文章链接
        Returns:
            0-10 总分
        """
        text = f"{title} {summary}".lower()
        title_only = title.lower()

        relevance = self._score_relevance(text, title_only)       # 0-10
        density = self._score_density(text, title_only)            # 0-10
        exclusivity = self._score_exclusivity(title_only, source, text)  # 0-10
        timeliness = self._score_timeliness(published, title_only) # 0-10

        total = (
            relevance * 0.40
            + density * 0.25
            + exclusivity * 0.20
            + timeliness * 0.15
        )

        return round(total, 1)

    def _score_relevance(self, text: str, title: str) -> float:
        """相关度评分 (0-10)"""
        score = 0.0
        max_possible = 20.0  # 上限，用于归一化

        for weight, keywords in AI_CORE.items():
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in title:
                    score += weight * 1.5  # 标题中出现，加倍
                elif kw_lower in text:
                    score += weight * 0.8

        return min(10.0, score / max_possible * 10)

    def _score_density(self, text: str, title: str) -> float:
        """信息密度评分 (0-10)"""
        score = 0.0
        text_len = max(len(text), 1)

        # 1. 数据/数字密度
        for pattern, weight in DENSITY_PATTERNS:
            matches = len(re.findall(pattern, text))
            score += min(matches, 3) * weight

        # 2. 实体密度（公司名、人名等）
        # 检测 "XXX完成/发布/推出" "XXX公司/科技/AI" 等模式
        company_matches = len(re.findall(
            r'[^\s]{2,8}(?:科技|AI|机器人|智能|数据|软件|网络|云|算力|芯片)',
            text
        ))
        score += min(company_matches, 5) * 1.0

        # 3. 结构复杂度（段落/分点/章节 = 信息组织良好）
        structure_signals = len(re.findall(r'[一二三四五六]|[1-9]\d*[.、）\)]|[·●◆▪▸►]', text))
        score += min(structure_signals, 5) * 0.5

        # 4. 长度惩罚（过短的信息密度低）
        if text_len < 200:
            score *= 0.3
        elif text_len < 500:
            score *= 0.6
        elif text_len < 1000:
            score *= 0.8

        return min(10.0, score)

    def _score_exclusivity(self, title: str, source: str, text: str) -> float:
        """独家性评分 (0-10)"""
        score = 0.0

        # 1. 标题中的独家标记
        for marker, weight in EXCLUSIVE_MARKERS:
            if marker in title:
                score += weight

        # 2. 来源权威度
        authority_sources = {
            "量子位": 2.5, "机器之心": 2.5, "晚点LatePost": 2.5,
            "虎嗅": 2.0, "36氪": 2.0, "爱范儿": 1.5,
            "少数派": 1.0, "知乎日报": 0.5, "36氪快讯": 0.3,
            "Reddit ML": 2.5,
        }
        score += authority_sources.get(source, 0.5)

        # 3. 是否有引用/采访/一手信息
        interview_signals = len(re.findall(r'专访|采访|对话|Q&A|QA|问答|观点|看法', title))
        score += interview_signals * 1.5

        return min(10.0, score)

    def _score_timeliness(self, published: str, title: str) -> float:
        """时效价值评分 (0-10)"""
        score = 0.0

        # 1. 发布时间
        if published:
            try:
                pub_date = datetime.strptime(published, "%Y-%m-%d")
                days_ago = (self.now - pub_date).days
                if days_ago <= 1:
                    score += 5.0
                elif days_ago <= 3:
                    score += 3.5
                elif days_ago <= 7:
                    score += 2.0
                elif days_ago <= 14:
                    score += 1.0
            except ValueError:
                score += 1.0  # 日期不可解析，给基础分
        else:
            score += 1.0  # 没有日期，给基础分

        # 2. 事件驱动（事件型内容时效价值更高）
        for weight, events in TIMELY_EVENTS.items():
            for ev in events:
                if ev.lower() in title:
                    score += weight * 0.5

        # 3. 热度信号（"热议" "刷屏" "引爆" 等）
        hot_signals = len(re.findall(r'热议|刷屏|引爆|爆火|火了|刷爆|排队|抢购', title))
        score += hot_signals * 1.0

        return min(10.0, score)

    def score_articles(self, articles: list) -> list:
        """
        批量评分（直接在 Article 对象上设置 raw_score）
        
        Args:
            articles: list[Article]
        Returns:
            list[Article] (with raw_score set)
        """
        for a in articles:
            pub = a.published if hasattr(a, 'published') else ""
            src = a.platform if hasattr(a, 'platform') else ""
            a.raw_score = self.score(
                title=a.title,
                summary=a.summary,
                source=src,
                published=pub,
                url=a.url,
            )
        return articles

    @staticmethod
    def to_stars(score: float) -> str:
        """将评分转为星级展示"""
        if score >= 8.0:
            return "★★★★★"
        elif score >= 6.0:
            return "★★★★☆"
        elif score >= 4.0:
            return "★★★☆☆"
        elif score >= 2.0:
            return "★★☆☆☆"
        else:
            return "★☆☆☆☆"

    @staticmethod
    def score_distribution(articles: list) -> dict:
        """统计评分分布"""
        dist = {"★★★★★": 0, "★★★★☆": 0, "★★★☆☆": 0, "★★☆☆☆": 0, "★☆☆☆☆": 0}
        for a in articles:
            score = getattr(a, 'raw_score', 0)
            stars = Scorer.to_stars(score)
            dist[stars] += 1
        return dist
