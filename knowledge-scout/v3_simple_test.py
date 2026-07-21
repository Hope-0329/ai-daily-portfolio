"""简化 V3 测试: 只测采集+全文抓取+评分，不跑解读"""
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
from scripts.interpreter import score_article_depth

async def main():
    print("🚀 V3 简化测试: 采集+抓取+评分\n")
    
    extractors = {
        "36氪": Kr36Extractor(),
        "虎嗅": HuxiuExtractor(),
        "量子位": QbitaiExtractor(),
        "少数派": SspaiExtractor(),
        "爱范儿": IfanrExtractor(),
        "知乎": ZhihuExtractor(),
    }
    
    all_articles = []
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
        except Exception as e:
            print(f"  [{name}] ❌ {e}")
    
    total = len(all_articles)
    print(f"\n📊 共采集 {total} 篇\n")
    
    # 全文抓取
    print("🌐 抓取全文...")
    fetched = 0
    for art in all_articles:
        text = art.get("content", "")
        if len(text) < 300 and art.get("url"):
            print(f"  抓取: {art['title'][:50]}...")
            full = fetch_full_article(art["url"], art.get("source", ""))
            if full and len(full) > 200:
                art["content"] = full
                fetched += 1
                print(f"    ✅ {len(full)} 字符")
            else:
                print(f"    ❌ 失败")
            time.sleep(0.5)
    
    print(f"\n✅ 成功抓取 {fetched} 篇全文\n")
    
    # 评分
    print("📊 评分...")
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
    
    # Top 15 with scores and text lengths
    print("🏆 Top 15:")
    for i, art in enumerate(all_articles[:15], 1):
        stars = "⭐" * min(5, max(1, int(art["_score"] / 2)))
        text_len = len(art.get("content", ""))
        print(f"  {i:2}. [{stars}] {art['_score']:.1f} | {text_len}c | {art['title'][:55]}")

    # Quick briefs
    print(f"\n⚡ 快讯 ({len(medium)} 条):")
    for i, art in enumerate(medium[:8], 1):
        print(f"  {i}. {art['title'][:60]}")

asyncio.run(main())
