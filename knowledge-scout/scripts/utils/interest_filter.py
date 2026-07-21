"""兴趣关键词与筛选规则 — v2：聚焦行业分析，过滤纯技术内容"""

# === 行业领域域（必须是AI/科技相关才收录）===
DOMAIN_KEYWORDS = [
    "AI", "人工智能", "大模型", "GPT", "ChatGPT", "DeepSeek",
    "智能", "算法", "数据", "机器人", "自动驾驶", "芯片",
    "SaaS", "云计算", "开源", "编程", "开发者",
]

# === 用户兴趣分类（按优先级排序）===
INTEREST_CATEGORIES = {
    "AI行业趋势": {
        "weight": 5.0,
        "keywords": [
            "行业分析", "产业趋势", "商业化", "商业模式",
            "市场规模", "融资", "上市", "财报", "战略",
            "竞争格局", "赛道", "风口", "独角兽", "估值",
            "收购", "合并", "转型", "布局", "出海",
            "下沉市场", "ToB", "ToC", "营收", "利润",
        ],
    },
    "AI工具与应用": {
        "weight": 4.5,
        "keywords": [
            "效率工具", "AI工具", "产品评测", "实用", "教程",
            "上手", "推荐", "神器", "工作流", "自动化",
            "插件", "浏览器", "编程助手", "代码生成",
            "办公", "协作", "笔记", "知识管理",
        ],
    },
    "AI创作": {
        "weight": 4.0,
        "keywords": [
            "短剧", "视频生成", "AI视频", "AI绘画",
            "内容创作", "AIGC", "数字人", "虚拟人",
            "AI写作", "AI配音", "AI音乐", "AI设计",
            "Stable Diffusion", "Midjourney", "Sora", "可灵",
            "Runway", "剪映", "即梦", "白日梦",
        ],
    },
    "效率与自动化": {
        "weight": 3.5,
        "keywords": [
            "Agent", "智能体", "自动化", "工作流",
            "效率提升", "NoCode", "低代码", "RPA",
            "API", "数据抓取", "定时任务", "推送",
            "Obsidian", "Notion", "飞书", "企业微信",
        ],
    },
    "科技商业": {
        "weight": 3.0,
        "keywords": [
            "互联网", "科技", "数字经济", "数字化",
            "平台", "生态", "用户增长", "流量",
            "变现", "付费", "订阅", "会员",
            "新消费", "电商", "直播", "短视频",
        ],
    },
}

# === 降权关键词（这些词让文章偏技术，降低得分）===
TECHNICAL_PENALTY_KEYWORDS = [
    "PyTorch", "TensorFlow", "CUDA", "transformer", "RNN", "CNN",
    "损失函数", "梯度下降", "反向传播", "激活函数", "正则化",
    "微调", "fine-tune", "预训练", "tokenizer", "embedding",
    "分布式训练", "GPU", "TPU", "显存", "量化",
    "推理加速", "模型压缩", "剪枝", "蒸馏",
    "源码", "GitHub", "代码实现", "安装教程",
]


def classify_article(title: str, summary: str) -> tuple[str, float]:
    """分类 + 评分

    Returns:
        (category, score) — category 是最匹配的类型，score 是综合评分
    """
    text = (title + " " + summary).lower()

    # 1. 域检查：必须是 AI/科技相关
    domain_match = any(kw.lower() in text for kw in DOMAIN_KEYWORDS)
    if not domain_match:
        return "", 0.0

    # 2. 纯技术惩罚
    penalty = sum(
        2.0 for kw in TECHNICAL_PENALTY_KEYWORDS if kw.lower() in text
    )

    # 3. 按兴趣分类打分
    best_cat = ""
    best_score = 0.0
    for cat, cfg in INTEREST_CATEGORIES.items():
        hits = sum(1 for kw in cfg["keywords"] if kw.lower() in text)
        if hits > 0:
            score = cfg["weight"] + hits * 0.5
            if score > best_score:
                best_score = score
                best_cat = cat

    final_score = max(0, best_score - penalty)
    return best_cat, final_score


def is_quality_article(title: str, summary: str) -> bool:
    """快速判断：这篇文章值得收录吗？"""
    _, score = classify_article(title, summary)
    return score >= 2.0
