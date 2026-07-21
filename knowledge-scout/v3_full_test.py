"""完整 V3 dry-run: 采集 + 全文抓取 + 评分 + 解读 + 生成日报"""
import sys, asyncio, time
sys.path.insert(0, r"C:\Users\22867\.qclaw\workspace\knowledge-scout")
sys.stdout.reconfigure(encoding='utf-8')

from scripts.extract.kr36 import Kr36Extractor
from scripts.extract.huxiu import HuxiuExtractor
from scripts.extract.qbitai import QbitaiExtractor
from scripts.extract.sspai import SspaiExtractor
from scripts.extract.ifanr import IfanrExtractor
from scripts.extract.zhihu import ZhihuExtractor
from scripts.content_fetcher import fetch_full_article
from scripts.interpreter import score_article_depth, interpret_article
import socket
socket.setdefaulttimeout(10)

async def main():
    import datetime
    today = datetime.date.today().isoformat()
    
    print(f"🚀 Knowledge Scout V3 完整测试 — {today}\n{'='*60}\n")
    
    extractors = {
        "36氪": Kr36Extractor(),
        "虎嗅": HuxiuExtractor(),
        "量子位": QbitaiExtractor(),
        "少数派": SspaiExtractor(),
        "爱范儿": IfanrExtractor(),
        "知乎": ZhihuExtractor(),
    }
    
    all_articles = []
    source_stats = {}
    
    for name, ext in extractors.items():
        try:
            articles = await ext.fetch()
            print(f"  [{name}] ✅ {len(articles)} 条")
            for art in articles:
                all_articles.append({
                    "title": getattr(art, "title", ""),
                    "source": name,
                    "url": getattr(art, "url", ""),
                    "summary": getattr(art, "summary", "") or getattr(art, "content", ""),
                    "content": getattr(art, "content", "") or getattr(art, "summary", ""),
                })
            source_stats[name] = len(articles)
        except Exception as e:
            print(f"  [{name}] ❌ {e}")
            source_stats[name] = 0
    
    print(f"\n📊 共采集 {len(all_articles)} 篇\n")
    
    # Full content fetch
    print("🌐 抓取全文...")
    fetched = 0
    for art in all_articles:
        text = art.get("content", "")
        if len(text) < 500 and art.get("url"):
            full = fetch_full_article(art["url"], art.get("source", ""))
            if full and len(full) > 200:
                art["content"] = full
                fetched += 1
            time.sleep(0.3)
    print(f"  ✅ 成功抓取 {fetched} 篇全文\n")
    
    # Score
    print("📊 深度评分...")
    for art in all_articles:
        text = art.get("content", "") or art.get("summary", "")
        if not text:
            text = art.get("title", "")
        art["_score"] = score_article_depth(text, art["title"], art["source"], art["url"])
    
    all_articles.sort(key=lambda a: a["_score"], reverse=True)
    
    deep = [a for a in all_articles if a["_score"] >= 4.0]
    medium = [a for a in all_articles if 2.0 <= a["_score"] < 4.0]
    shallow = [a for a in all_articles if a["_score"] < 2.0]
    print(f"  深度{len(deep)} | 中度{len(medium)} | 浅层{len(shallow)}\n")
    
    # Deep interpret top articles
    print("="*60)
    print("🔬 深度解读 (Top 5)")
    print("="*60)
    
    insights = []
    for i, art in enumerate(all_articles[:5], 1):
        text = art.get("content", "") or art.get("summary", "")
        url = art.get("url", "")
        print(f"\n--- [{i}] {art['title'][:60]} ---")
        print(f"  来源: {art.get('source', '')} | 文本长度: {len(text)} | 评分: {art['_score']:.1f}")
        
        if len(text) < 500:
            print(f"  ⏭️ 跳过（内容不足）")
            continue
        
        try:
            insight = interpret_article({
                "title": art["title"],
                "content": text,
                "source": art.get("source", ""),
                "url": url,
            })
            if insight:
                insights.append({
                    "article": art,
                    "insight": insight,
                })
                print(f"  ✅ 解读成功")
                print(f"  📂 分类: {insight.category}")
                print(f"  💡 核心观点: {insight.key_thesis[:120]}")
                print(f"  🧩 框架: {', '.join(insight.frameworks[:3])[:100]}")
            else:
                print(f"  ⏭️ 解读返回空")
        except Exception as e:
            print(f"  ❌ 解读异常: {e}")
    
    # Generate report
    print(f"\n{'='*60}")
    print(f"📝 日报生成")
    print(f"{'='*60}")
    
    report = f"# 📰 专业知识日报 — {today}\n\n"
    report += f"> 采集 {len(all_articles)} 篇 → 精选 {len(insights)} 篇深度解读 + {len(medium)} 条快讯\n\n"
    
    # Source distribution
    report += "## 📡 来源分布\n\n| 来源 | 采集数 |\n|------|--------|\n"
    for name, count in source_stats.items():
        report += f"| {name} | {count} |\n"
    report += "\n---\n\n"
    
    # Deep insights
    if insights:
        report += f"## 🔬 深度解读（{len(insights)} 篇）\n\n"
        for i, item in enumerate(insights, 1):
            art = item["article"]
            ins = item["insight"]
            stars = "⭐" * min(5, max(1, int(art["_score"] / 2)))
            report += f"### {i}. {art['title']}\n\n"
            report += f"**来源**: {art.get('source', '')} | **分类**: {ins.category} | **深度评分**: {stars} ({art['_score']:.1f}/10)\n\n"
            report += f"> 💡 **核心观点**: {ins.key_thesis}\n\n"
            if ins.frameworks:
                report += "**🧩 方法论/框架**:\n"
                for fw in ins.frameworks[:5]:
                    report += f"- {fw}\n"
                report += "\n"
            if ins.action_items:
                report += "**⚡ 行动启发**:\n"
                for ai in ins.action_items[:5]:
                    report += f"- {ai}\n"
                report += "\n"
            if ins.knowledge_links:
                report += "**🔗 知识连接**:\n"
                for kl in ins.knowledge_links[:3]:
                    report += f"- {kl}\n"
                report += "\n"
            report += f"📎 [阅读原文]({art.get('url', '')})\n\n"
            report += "---\n\n"
    
    # Briefs
    if medium:
        report += f"## ⚡ 快讯速览（{len(medium)} 条）\n\n"
        for i, art in enumerate(medium, 1):
            summary = (art.get("summary", "") or art.get("content", "") or "")[:200]
            report += f"{i}. **[{art['title']}]({art.get('url', '')})** — {art.get('source', '')}\n"
            if summary:
                report += f"   > {summary}\n"
    
    # Topic graph
    categories = {}
    for item in insights:
        cat = item["insight"].category
        categories[cat] = categories.get(cat, 0) + 1
    
    if categories:
        report += "\n## 🗺️ 主题关联图\n\n```\n今日主题关联:\n"
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            bar = "█" * count
            report += f"  {cat:25s} {bar} ({count}篇)\n"
        report += "```\n\n"
    
    report += "---\n\n"
    report += f"*由 knowledge-scout V3 自动生成 · {today} · 深度解读引擎驱动*"
    
    # Save
    output_path = rf"C:\Users\22867\.qclaw\workspace\knowledge-scout\v3_full_report_{today}.md"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n💾 完整日报已保存: {output_path}")
    print(f"📏 日报长度: {len(report)} 字符")
    print(f"📊 深度解读: {len(insights)} 篇")
    print(f"⚡ 快讯: {len(medium)} 条")

asyncio.run(main())
