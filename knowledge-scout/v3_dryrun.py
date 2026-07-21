"""V3 dry-run test: RSS collect + score + interpret top 3"""
import sys, asyncio
sys.path.insert(0, r"C:\Users\22867\.qclaw\workspace\knowledge-scout")
sys.stdout.reconfigure(encoding='utf-8')

from scripts.extract.kr36 import Kr36Extractor
from scripts.extract.huxiu import HuxiuExtractor
from scripts.extract.qbitai import QbitaiExtractor
from scripts.extract.sspai import SspaiExtractor
from scripts.extract.ifanr import IfanrExtractor
from scripts.extract.zhihu import ZhihuExtractor
from scripts.interpreter import interpret_article, score_article_depth
from scripts.report_v3 import build_v3_report
from dataclasses import asdict
import json

async def main():
    print("🚀 V3 dry-run\n")
    
    # Collect from RSS
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
            source_stats[name] = len(articles)
            for art in articles:
                content = getattr(art, "content", "") or getattr(art, "summary", "")
                title = getattr(art, "title", "")
                url = getattr(art, "url", "")
                source = getattr(art, "source", "") or name
                summary = getattr(art, "summary", "")
                
                all_articles.append({
                    "title": title,
                    "source": source,
                    "url": url,
                    "summary": summary,
                    "content": content or summary,
                })
        except Exception as e:
            print(f"  [{name}] ❌ {e}")
            source_stats[name] = 0
    
    total = len(all_articles)
    print(f"\n📊 共采集 {total} 篇")
    
    # Fetch full content for articles with short content
    print("\n🌐 抓取全文...")
    from scripts.content_fetcher import fetch_full_article
    import time
    fetched = 0
    for art in all_articles:
        text = art.get("content", "") or art.get("summary", "")
        if len(text) < 500 and art.get("url"):
            full = fetch_full_article(art["url"], art.get("source", ""))
            if full and len(full) > 200:
                art["content"] = full
                fetched += 1
            time.sleep(0.3)
    print(f"  ✅ 抓取 {fetched} 篇全文")
    
    # Score all (now with full text)
    print("\n📊 评分中...")
    for art in all_articles:
        text = art.get("content", "") or art.get("summary", "")
        art["_score"] = score_article_depth(text, art["title"], art["source"], art["url"])
    
    all_articles.sort(key=lambda a: a["_score"], reverse=True)
    
    # Score distribution
    deep = [a for a in all_articles if a["_score"] >= 4.0]
    medium = [a for a in all_articles if 2.0 <= a["_score"] < 4.0]
    shallow = [a for a in all_articles if a["_score"] < 2.0]
    print(f"  深度{len(deep)} | 中度{len(medium)} | 浅层{len(shallow)}")
    
    # Top scores
    print("\n🏆 Top 10 评分:")
    for i, art in enumerate(all_articles[:10], 1):
        stars = "⭐" * min(5, max(1, int(art["_score"] / 2)))
        print(f"  {i}. [{stars}] {art['_score']:.1f} | {art['title'][:55]}")
    
    # Deep interpret top 3
    print("\n" + "=" * 60)
    print("🔬 深度解读 Top 3")
    print("=" * 60)
    
    interpretations = []
    for i, art in enumerate(all_articles[:5], 1):
        print(f"\n--- [{i}] {art['title'][:60]} ---")
        result = interpret_article(art)
        if result:
            interpretations.append(result)
            print(f"  ✅ 评分: {result.quality_score}/10")
            print(f"  📂 分类: {result.category}")
            if result.frameworks:
                print(f"  🧩 框架: {result.frameworks[0][:80]}")
            if result.insights:
                print(f"  💡 洞察: {result.insights[0][:80]}")
            if result.takeaways:
                print(f"  ⚡ 启发: {result.takeaways[0][:80]}")
        else:
            print(f"  ⏭️ 跳过（内容不足）")
    
    # Quick briefs
    quick_briefs = []
    for art in medium[:8]:
        quick_briefs.append({
            "title": art["title"],
            "source": art["source"],
            "summary": art.get("summary", "")[:100],
            "url": art.get("url", ""),
            "category": art.get("category", ""),
        })
    
    # Generate report
    report = build_v3_report(
        deep_interpretations=interpretations,
        quick_briefs=quick_briefs,
        date="2026-07-18",
        total_fetched=total,
        source_stats=source_stats,
    )
    
    print(f"\n📝 日报预览 ({len(report)} 字符):")
    print(report[:3000])
    if len(report) > 3000:
        print(f"\n... 共 {len(report)} 字符，截断显示")
    
    # Save for inspection
    out_path = r"C:\Users\22867\.qclaw\workspace\knowledge-scout\v3_dryrun_preview.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n💾 完整日报已保存: {out_path}")

asyncio.run(main())
