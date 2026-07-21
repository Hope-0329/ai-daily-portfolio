"""V3 完整日报: 采集→评分→Top15抓全文→再评分→解读→生成报告"""
import sys, asyncio, time, socket
from pathlib import Path
sys.path.insert(0, r"C:\Users\22867\.qclaw\workspace\knowledge-scout")
sys.stdout.reconfigure(encoding='utf-8')
socket.setdefaulttimeout(8)

from scripts.extract.kr36 import Kr36Extractor
from scripts.extract.huxiu import HuxiuExtractor
from scripts.extract.qbitai import QbitaiExtractor
from scripts.extract.sspai import SspaiExtractor
from scripts.extract.ifanr import IfanrExtractor
from scripts.extract.zhihu import ZhihuExtractor
from scripts.extract.github_trending import GithubTrendingExtractor
from scripts.extract.huggingface import HuggingFaceExtractor
from scripts.extract.readaitime import ReadAITimeExtractor
from scripts.content_fetcher import fetch_full_article
from scripts.interpreter import score_article_depth, interpret_article

def fetch_safe(url, source, retries=2):
    for i in range(retries):
        try:
            result = fetch_full_article(url, source)
            if result and len(result) > 200:
                return result
        except Exception:
            if i < retries - 1:
                time.sleep(0.5)
    return None

async def main():
    import datetime
    today = datetime.date.today().isoformat()
    
    print(f"🚀 Knowledge Scout V3 — {today}")
    print("="*50 + "\n")
    
    # Step 1: Collection
    extractors = {
        "36氪": Kr36Extractor(), "虎嗅": HuxiuExtractor(),
        "量子位": QbitaiExtractor(), "少数派": SspaiExtractor(),
        "爱范儿": IfanrExtractor(), "知乎": ZhihuExtractor(),
        "GitHub": GithubTrendingExtractor(), "HuggingFace": HuggingFaceExtractor(),
        "读懂AI时代": ReadAITimeExtractor(),
    }
    
    all_articles = []
    source_stats = {}
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
            source_stats[name] = len(articles)
        except asyncio.TimeoutError:
            print(f"  [{name}] ⚠️ 超时")
        except Exception as e:
            print(f"  [{name}] ❌ {e}")
    
    print(f"\n📊 共采集 {len(all_articles)} 篇\n")
    
    # Step 2: Pre-score with RSS summaries
    print("📊 预评分...")
    for art in all_articles:
        text = art.get("content", "") or art.get("summary", "")
        art["_score"] = score_article_depth(text, art["title"], art["source"], art["url"])
    
    all_articles.sort(key=lambda a: a["_score"], reverse=True)
    print(f"  深度{sum(1 for a in all_articles if a['_score'] >= 4)} | "
          f"中度{sum(1 for a in all_articles if 2 <= a['_score'] < 4)} | "
          f"浅层{sum(1 for a in all_articles if a['_score'] < 2)}\n")
    
    # Step 3: Full-text for top 10 (global & RSS can't fetch, skip)
    SKIP_FETCH = {"GitHub", "HuggingFace", "读懂AI时代", "知乎"}
    print("🌐 抓取 Top 10 全文 (跳过全球/学术源)...")
    fetch_targets = [a for a in all_articles[:15] if a.get("source") not in SKIP_FETCH][:10]
    for i, art in enumerate(fetch_targets):
        text = art.get("content", "")
        is_short = len(text) < 500
        status = f"{'⚠️' if is_short else '✅'}"
        print(f"  [{i+1:2d}] {status} {art['title'][:50]}... ({len(text)}c)", end="")
        if is_short and art.get("url"):
            full = fetch_safe(art["url"], art.get("source", ""))
            if full and len(full) > 200:
                art["content"] = full
                print(f" → {len(full)}c ✅")
            else:
                print(f" → 无全文")
        else:
            print()
        time.sleep(0.3)
    
    # Step 4: Re-score with full text
    print("\n📊 重新评分 (含全文)...")
    for art in all_articles:
        text = art.get("content", "") or art.get("summary", "")
        art["_score"] = score_article_depth(text, art["title"], art["source"], art["url"])
    all_articles.sort(key=lambda a: a["_score"], reverse=True)
    
    deep = [a for a in all_articles if a["_score"] >= 4.0]
    medium = [a for a in all_articles if 2.0 <= a["_score"] < 4.0]
    shallow = [a for a in all_articles if a["_score"] < 2.0]
    print(f"  深度{len(deep)} | 中度{len(medium)} | 浅层{len(shallow)}\n")
    
    # Step 5: Deep interpret top 5
    print("🔬 深度解读 Top 5...")
    insights = []
    for i, art in enumerate(all_articles[:5]):
        text = art.get("content", "") or art.get("summary", "")
        if len(text) < 500:
            continue
        try:
            result = interpret_article({
                "title": art["title"],
                "content": text,
                "source": art.get("source", ""),
                "url": art.get("url", ""),
            })
            if result:
                insights.append({"article": art, "insight": result})
                print(f"  ✅ [{i+1}] {art['title'][:55]}... → {result.category}")
        except Exception as e:
            print(f"  ❌ [{i+1}] {e}")
    
    # Step 6: Generate report with AI blogger template
    print(f"\n📝 生成 AI 博主日报...")
    from scripts.report_v3 import build_v3_report

    deep_insights = [item["insight"] for item in insights]
    quick_briefs_list = []
    for art in medium[:15]:
        quick_briefs_list.append({
            "title": art.get("title", ""),
            "source": art.get("source", ""),
            "summary": (art.get("summary", "") or art.get("content", "") or "")[:150],
            "url": art.get("url", ""),
            "category": art.get("category", ""),
        })

    report = build_v3_report(
        deep_interpretations=deep_insights,
        quick_briefs=quick_briefs_list,
        date=today,
        total_fetched=len(all_articles),
        source_stats=source_stats,
    )

    # Save
    obsidian_dir = Path(r"D:\肠肠的Obsidian\肠肠的obsidian\00-收件箱\AI日报")
    obsidian_dir.mkdir(parents=True, exist_ok=True)
    obsidian_path = obsidian_dir / f"daily-report-{today}.md"

    try:
        obsidian_path.write_text(report, encoding="utf-8")
        print(f"💾 已写入 Obsidian: {obsidian_path}")
    except Exception as e:
        output_path = Path(r"C:\Users\22867\.qclaw\workspace\knowledge-scout") / f"daily-report-{today}.md"
        output_path.write_text(report, encoding="utf-8")
        print(f"💾 已写入本地: {output_path}")

    print(f"\n📏 日报 {len(report)} 字符 | 🔬 {len(deep_insights)} 篇深度解读 | ⚡ {len(quick_briefs_list)} 条快讯")
    print("✅ 完成")

asyncio.run(main())
