"""最小化 V3 测试: 仅前5篇抓取+评分，找卡死原因"""
import sys, asyncio, time, socket
sys.path.insert(0, r"C:\Users\22867\.qclaw\workspace\knowledge-scout")
sys.stdout.reconfigure(encoding='utf-8')
socket.setdefaulttimeout(8)

from scripts.extract.kr36 import Kr36Extractor
from scripts.extract.huxiu import HuxiuExtractor
from scripts.extract.qbitai import QbitaiExtractor
from scripts.extract.sspai import SspaiExtractor
from scripts.extract.ifanr import IfanrExtractor
from scripts.extract.zhihu import ZhihuExtractor
from scripts.content_fetcher import fetch_full_article
from scripts.interpreter import score_article_depth

async def main():
    print("🚀 最小化 V3 测试\n")
    
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
            articles = await asyncio.wait_for(ext.fetch(), timeout=15)
            print(f"  [{name}] ✅ {len(articles)} 条")
            for art in articles:
                all_articles.append({
                    "title": getattr(art, "title", ""),
                    "source": name,
                    "url": getattr(art, "url", ""),
                    "summary": getattr(art, "summary", "") or getattr(art, "content", ""),
                    "content": getattr(art, "content", "") or getattr(art, "summary", ""),
                })
        except asyncio.TimeoutError:
            print(f"  [{name}] ⚠️ 超时")
        except Exception as e:
            print(f"  [{name}] ❌ {e}")
    
    print(f"\n📊 共采集 {len(all_articles)} 篇")
    
    # Only fetch content for articles with short content (limit 5)
    print("\n🌐 抓取全文 (限 5 篇)")
    fetched = 0
    for art in all_articles:
        print(f"  [{fetched+1}/{min(5, len(all_articles))}] 检查: {art['title'][:40]}...")
        text = art.get("content", "")
        if len(text) < 500 and art.get("url") and fetched < 5:
            print(f"    内容不足 ({len(text)}c)，正在抓取...")
            try:
                full = fetch_full_article(art["url"], art.get("source", ""))
                if full and len(full) > 200:
                    art["content"] = full
                    fetched += 1
                    print(f"    ✅ {len(full)} 字符")
                else:
                    print(f"    ❌ 抓取失败")
            except Exception as e:
                print(f"    ❌ {e}")
            time.sleep(0.5)
        elif fetched >= 5:
            break
    
    print(f"\n✅ 抓取 {fetched} 篇\n")
    
    # Score
    print("📊 TOP 5 评分:")
    for art in all_articles:
        text = art.get("content", "") or art.get("summary", "")
        if not text:
            text = art.get("title", "")
        art["_score"] = score_article_depth(text, art["title"], art["source"], art["url"])
    
    all_articles.sort(key=lambda a: a["_score"], reverse=True)
    
    for i, art in enumerate(all_articles[:5], 1):
        stars = "⭐" * min(5, max(1, int(art["_score"] / 2)))
        text_len = len(art.get("content", ""))
        print(f"  {i}. [{stars}] {art['_score']:.1f} | {text_len}c | {art['title'][:55]}")

    print("\n✅ 最小化测试完成")

asyncio.run(main())
