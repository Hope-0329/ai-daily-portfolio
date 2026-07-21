"""日报 Markdown 生成器"""

from datetime import datetime
from .extract.base import Article


def star_emoji(score: float) -> str:
    """分数 → 星级"""
    stars = int(round(score))
    return "⭐" * max(1, min(5, stars))


def build_daily_report(
    articles: list[Article],
    date: str = None,
    total_fetched: int = 0,
) -> str:
    """生成结构化日报 Markdown"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    # 分类
    by_category: dict[str, list[Article]] = {}
    for a in articles:
        cat = a.category or "其他"
        by_category.setdefault(cat, []).append(a)

    # 构建 Markdown
    lines = []
    lines.append(f"# 📊 AI 知识日报 | {date}")
    lines.append("")
    lines.append(f"> 共采集 {total_fetched} 条，精选 {len(articles)} 条")
    lines.append("")

    # ── TOP 精选 ──
    top_n = min(10, len(articles))
    lines.append("---")
    lines.append("")
    lines.append("## 🔥 今日精选 TOP {}".format(top_n))
    lines.append("")

    for i, a in enumerate(articles[:top_n], 1):
        stars = star_emoji(a.raw_score)
        lines.append(f"### {i}. [{stars}] {a.title}")
        lines.append("")
        lines.append(f"📄 来源：{a.platform}  ·  ✏️ {a.author}")
        if a.url:
            lines.append(f"🔗 {a.url}")
        if a.summary:
            lines.append(f"💡 {a.summary[:200]}")
        lines.append("")

    # ── 分类速览 ──
    lines.append("---")
    lines.append("")
    lines.append("## 📋 分类速览")
    lines.append("")

    for cat, items in by_category.items():
        lines.append(f"### {cat}（{len(items)} 条）")
        lines.append("")
        for a in items:
            stars = star_emoji(a.raw_score)
            lines.append(f"- [{stars}] [{a.title}]({a.url}) — {a.platform}")
        lines.append("")

    # ── 平台分布 ──
    lines.append("---")
    lines.append("")
    lines.append("## 📡 平台分布")
    lines.append("")
    by_platform: dict[str, int] = {}
    for a in articles:
        by_platform[a.platform] = by_platform.get(a.platform, 0) + 1
    for plat, count in sorted(by_platform.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- {plat}：{count} 条")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*由 knowledge-scout 自动生成 · 回复「分析 序号」深挖任意条目*")

    return "\n".join(lines)
