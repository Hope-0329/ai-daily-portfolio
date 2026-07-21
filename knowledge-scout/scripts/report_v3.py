"""V3 日报生成器 — AI 博主模板

生成符合 AI 博主工作流的日报，包含：
1. YAML frontmatter + 一句话速览
2. 🔥 头条（≤3条）+ 博主视角
3. 📊 行业速览
4. 🔬 深度解读（方法论/框架/洞察）
5. 📄 论文/报告速读
6. 🎬 内容创作选题池
7. 📡 信息源脚印
8. ⚡ 快讯速览
9. 💭 今日碎碎念
"""

from datetime import datetime
from scripts.interpreter import DeepInsight


def build_v3_report(
    deep_interpretations: list[DeepInsight],
    quick_briefs: list[dict],
    date: str,
    total_fetched: int,
    source_stats: dict,
) -> str:
    """生成 V3 博主版日报"""
    dt = datetime.strptime(date, "%Y-%m-%d")
    weekday = ["一", "二", "三", "四", "五", "六", "日"][dt.weekday()]
    date_display = dt.strftime("%Y年%m月%d日")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = []
    # ── YAML frontmatter ──
    lines.append("---")
    lines.append(f"date: {date}")
    lines.append(f"day: 周{weekday}")
    lines.append("tags:")
    lines.append("  - AI日报")
    lines.append("  - AI新闻")
    lines.append(f"created: \"{now}\"")
    lines.append("---")
    lines.append("")

    # ── 标题 ──
    lines.append(f"# 🗞️ AI 日报 — {date_display}（周{weekday}）")
    lines.append("")

    # ── 📌 一句话速览 ──
    lines.append("## 📌 一句话速览")
    lines.append("")
    oneliner = _build_oneliner(deep_interpretations, quick_briefs)
    lines.append(f"> {oneliner}")
    lines.append("")

    # ── 🔥 头条（≤3条）+ 博主视角 ──
    lines.append("## 🔥 头条")
    lines.append("")
    headlines = _build_headlines(deep_interpretations, quick_briefs)
    for i, hl in enumerate(headlines[:3], 1):
        lines.append(f"### {i}. {hl['title']}")
        lines.append("")
        lines.append(f"- **来源**：{hl['source']}")
        lines.append(f"- **核心内容**：{hl['content']}")
        lines.append(f"- **🎤 博主视角**：{hl['blogger_angle']}")
        lines.append("")

    # ── 📊 行业速览 ──
    lines.append("## 📊 行业速览")
    lines.append("")
    lines.append(_build_industry_table(deep_interpretations, quick_briefs))
    lines.append("")

    # ── 🔬 深度解读 ──
    if deep_interpretations:
        lines.append("## 🔬 深度解读")
        lines.append("")
        for i, ins in enumerate(deep_interpretations[:5], 1):
            stars = "⭐" * min(5, max(1, int(ins.quality_score / 2)))
            lines.append(f"### {i}. {ins.title}")
            lines.append("")
            lines.append(f"**来源**: {ins.source} | **分类**: {ins.category} | **评分**: {stars} ({ins.quality_score}/10)")
            lines.append("")

            if ins.thesis:
                lines.append(f"> 💡 **核心观点**: {ins.thesis}")
                lines.append("")

            if ins.frameworks:
                lines.append("**🧩 方法论/框架**:")
                for fw in ins.frameworks:
                    lines.append(f"- {fw}")
                lines.append("")

            if ins.insights:
                lines.append("**🎯 关键洞察**:")
                for idx, insight in enumerate(ins.insights[:3], 1):
                    lines.append(f"{idx}. {insight}")
                lines.append("")

            if ins.takeaways:
                lines.append("**⚡ 行动启发**:")
                for tw in ins.takeaways:
                    lines.append(f"- {tw}")
                lines.append("")

            if ins.url:
                lines.append(f"📎 [阅读原文]({ins.url})")
            lines.append("")
            lines.append("---")
            lines.append("")

    # ── 📄 论文/报告速读 ──
    lines.append("## 📄 论文/报告速读")
    lines.append("")
    papers = _extract_papers(deep_interpretations, quick_briefs)
    if papers:
        lines.append("| 标题 | 机构 | 一句话要点 |")
        lines.append("|:-----|:-----|:-----------|")
        for p in papers:
            lines.append(f"| {p['title']} | {p['org']} | {p['point']} |")
    else:
        lines.append("> 今日未检测到新论文/报告。")
    lines.append("")

    # ── 🎬 内容创作选题池 ──
    lines.append("## 🎬 内容创作选题池")
    lines.append("")
    topics = _generate_topics(deep_interpretations, quick_briefs)
    if topics:
        for i, t in enumerate(topics[:3], 1):
            lines.append(f"**{i}. {t['title']}**")
            lines.append(f"- 角度：{t['angle']}")
            lines.append(f"- 适合平台：{t['platform']}")
            lines.append("")
    else:
        lines.append("> 💡 选题池需 LLM 深度解读补充——可触发 Agent session 获取。")
        lines.append("")

    # ── 📡 信息源脚印 ──
    lines.append("## 📡 信息源脚印")
    lines.append("")
    lines.append("> 今日扫描的信源：")
    lines.append("")
    footprint = _build_footprint(source_stats, deep_interpretations)
    lines.append(footprint)

    # ── ⚡ 快讯速览 ──
    if quick_briefs:
        lines.append("## ⚡ 快讯速览")
        lines.append("")
        for i, brief in enumerate(quick_briefs[:10], 1):
            title = brief.get("title", "")
            source = brief.get("source", "")
            summary = brief.get("summary", "")[:100]
            url = brief.get("url", "")
            if url:
                lines.append(f"{i}. **[{title}]({url})** — {source}")
            else:
                lines.append(f"{i}. **{title}** — {source}")
            if summary:
                lines.append(f"   > {summary}")
        lines.append("")

    # ── 💭 今日碎碎念 ──
    lines.append("## 💭 今日碎碎念")
    lines.append("")
    musing = _build_musing(deep_interpretations)
    lines.append(musing)
    lines.append("")

    # ── 页脚 ──
    lines.append("---")
    lines.append("")
    lines.append(f"*由 QClaw · knowledge-scout V3 自动生成 | {now}*")

    return "\n".join(lines)


def _build_oneliner(deep_ins, briefs) -> str:
    """生成一句话速览"""
    cats = set()
    for i in deep_ins[:3]:
        cats.add(i.category)

    highlights = []
    if deep_ins:
        highlights.append(f"{len(deep_ins)}篇深度解读")
    if briefs:
        highlights.append(f"{len(briefs)}条快讯")

    cat_str = "、".join(cats) if cats else "AI行业"
    return f"今日聚焦{cat_str}领域，共{', '.join(highlights)}。[需 LLM 补全要点]"


def _build_headlines(deep_ins, briefs) -> list[dict]:
    """构建头条（≤3条）+ 博主视角"""
    headlines = []
    for ins in deep_ins[:3]:
        headlines.append({
            "title": ins.title,
            "source": ins.source,
            "content": ins.thesis or ins.title,
            "blogger_angle": f"[需 LLM 生成] 可从{ins.category}角度分析，关联{', '.join(fw for fw in ins.frameworks[:2]) if ins.frameworks else '行业趋势'}",
        })
    return headlines


def _build_industry_table(deep_ins, briefs) -> str:
    """生成行业速览表格"""
    rows = [
        "| 赛道 | 事件摘要 | 信源 | 热度 |",
        "|:-----|:---------|:-----|:----:|",
    ]
    cat_map = {}
    for ins in deep_ins:
        cat = ins.category
        if cat not in cat_map:
            cat_map[cat] = []
        cat_map[cat].append(ins)

    for cat, items in list(cat_map.items())[:8]:
        item = items[0]
        rows.append(f"| {cat} | {item.title[:40]} | {item.source} | {'⭐' * min(3, len(items))} |")
    return "\n".join(rows)


def _extract_papers(deep_ins, briefs) -> list[dict]:
    """从深度解读+快讯中提取论文/报告，并接入HuggingFace"""
    papers = []
    # 先从 HF/GitHub 来源提取
    for ins in deep_ins:
        if ins.source in ("huggingface", "github"):
            papers.append({
                "title": ins.title[:50],
                "org": ins.author or ins.source,
                "point": ins.thesis[:60] if ins.thesis else ins.summary[:60],
            })
    # 再从快讯中提取
    paper_kw = ["论文", "报告", "白皮书", "研究", "arXiv", "发布."]
    for b in briefs[:15]:
        title = b.get("title", "")
        if any(kw in title for kw in paper_kw):
            papers.append({
                "title": title[:50],
                "org": b.get("source", "—")[:15],
                "point": b.get("summary", "")[:60] or "—",
            })
    return papers[:8]


def _generate_topics(deep_ins, briefs) -> list[dict]:
    """生成内容创作选题（基于匹配信号）"""
    topics = []
    for ins in deep_ins[:5]:
        cat = ins.category
        platform = "公众号 / 小红书"
        if "短剧" in ins.title or "视频" in ins.title or "AIGC" in ins.category:
            platform = "抖音 / B站 / 小红书"
        elif "机器人" in ins.category or "硬件" in ins.category:
            platform = "B站 / 公众号"
        elif "知识" in ins.category or "效率" in ins.category:
            platform = "小红书 / 公众号"

        angle = ins.thesis[:80] if ins.thesis else ins.title[:80]
        topics.append({
            "title": f"深度解读: {ins.title[:35]}",
            "angle": angle,
            "platform": platform,
        })
    return topics[:3]


def _build_footprint(source_stats, deep_ins) -> str:
    """生成信息源脚印"""
    lines = []
    # RSS 源
    rss_sources = ["36氪", "虎嗅", "爱范儿", "量子位", "少数派", "知乎"]
    for s in rss_sources:
        status = "✅" if s in source_stats else "—"
        count = source_stats.get(s, 0)
        lines.append(f"- [{status}] **{s}**（{count}条）")

    # 全球/学术源
    lines.append("")
    lines.append("**🌐 全球/学术源**")
    for s in ["GitHub Trending", "HuggingFace", "读懂AI时代"]:
        status = "✅" if s in (source_stats or {}) else "→"
        count = (source_stats or {}).get(s, 0)
        lines.append(f"- [{status}] **{s}**（{count}条）")

    # 可用但需 Agent 的源
    lines.append("")
    lines.append("> ⚠️ 以下源需 Agent session 支持：")
    for s in ["微信公众号（黄钊/赛博禅心等）", "IMA 知识库"]:
        lines.append(f"- [ ] {s}")
    return "\n".join(lines)


def _build_musing(deep_ins) -> str:
    """生成今日碎碎念"""
    if not deep_ins:
        return "> 今日无深度内容。"
    
    cats = [i.category for i in deep_ins[:3]]
    cat_set = set(cats)
    topics = []
    for ins in deep_ins[:3]:
        if ins.thesis:
            topics.append(ins.thesis[:60])

    lines = [
        "> *自动生成的观察，需人工补充观点。*",
        "",
        f"- 📊 今日覆盖 {len(cat_set)} 个赛道: {'、'.join(cat_set)}",
    ]
    if topics:
        lines.append(f"- 💡 值得深挖: {'; '.join(topics)}")
    lines.append("- 🔍 建议: 选 1-2 条头条做深度内容创作")
    return "\n".join(lines)


def build_article_dict(article) -> dict:
    """从 Article 对象提取简要字典"""
    return {
        "title": getattr(article, "title", ""),
        "source": getattr(article, "source", ""),
        "summary": getattr(article, "summary", "") or getattr(article, "content", "")[:120],
        "url": getattr(article, "url", ""),
        "category": getattr(article, "category", ""),
    }
