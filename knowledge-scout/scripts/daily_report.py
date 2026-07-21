"""knowledge-scout V3 日报总调度器

流水线:
  1. IMA 知识库同步 → 拉取「05-文章精选」+「AI落地应用」新文章
  2. 微信搜索 → 搜狗搜索高质量公众号文章
  3. RSS 采集 → 保留 6 平台作为补充
  4. 全量内容抓取 → 获取文章正文
  5. 深度评分 → 多维度评估文章价值
  6. Top 5 深度解读 → 提取框架/洞察/启发
  7. 生成 V3 日报 → 写入 Obsidian

用法:
    python daily_report.py              # 完整 V3 日报
    python daily_report.py --dry-run    # 打印不写入
    python daily_report.py --quick      # 快速模式（不深度解读）
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.sources.ima_sync import get_new_articles as ima_get_new
from scripts.sources.wechat_search import search_wechat, fetch_article_content, is_high_quality
from scripts.extract.kr36 import Kr36Extractor
from scripts.extract.ifanr import IfanrExtractor
from scripts.extract.huxiu import HuxiuExtractor
from scripts.extract.qbitai import QbitaiExtractor
from scripts.extract.sspai import SspaiExtractor
from scripts.extract.zhihu import ZhihuExtractor
from scripts.filter import FilterEngine
from scripts.content_fetcher import fetch_full_article
from scripts.interpreter import interpret_article, DeepInsight, score_article_depth
from scripts.report_v3 import build_v3_report, build_article_dict

# ── 配置 ──
FILTER_CONFIG = {
    "min_score": 3.0,  # 提高门槛，只要深度内容
    "max_articles": 40,
    "duplicate_threshold": 0.75,
}

MAX_DEEP_INTERPRET = 5  # 最多深度解读几篇
MAX_QUICK_BRIEFS = 15   # 快讯最多多少条
WECHAT_SEARCH_LIMIT = 3  # 微信搜索每个关键词最多几篇


def extract_article_text(article) -> str:
    """从 Article 对象提取全文文本"""
    text = getattr(article, "content", "") or getattr(article, "summary", "") or ""
    if not text:
        title = getattr(article, "title", "")
        text = title * 3  # fallback
    return text


def main(date_str: str = None, dry_run: bool = False, quick: bool = False):
    """主入口"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    print(f"\n🧠 knowledge-scout V3 | {date_str}")
    print("=" * 60)

    all_articles = []  # 聚合所有文章
    source_stats = {}

    # ═══════════════════════════════════════
    # Step 1: IMA 知识库同步
    # ═══════════════════════════════════════
    print("\n📚 [1/4] IMA 知识库同步...")
    try:
        ima_articles = ima_get_new()
        print(f"  ✅ 发现 {len(ima_articles)} 篇新文章")
        for art in ima_articles:
            all_articles.append({
                "title": art["title"],
                "source": f"IMA-{art['folder']}",
                "url": "",
                "summary": "",
                "content": "",  # 稍后全量抓取
                "_ima_media_id": art.get("media_id", ""),
                "_source_type": "ima",
                "_folder": art.get("folder", ""),
            })
        source_stats["IMA-精选"] = len([a for a in ima_articles if a["folder"] == "精选"])
        source_stats["IMA-AI落地"] = len([a for a in ima_articles if a["folder"] == "AI落地"])
    except Exception as e:
        print(f"  ⚠️ IMA 同步失败: {e}")

    # ═══════════════════════════════════════
    # Step 2: 微信搜索
    # ═══════════════════════════════════════
    print("\n🔍 [2/4] 微信公众号搜索...")
    search_topics = [
        "AI Agent 企业 落地 架构 方法论",
        "大模型 应用 框架 深度解读",
        "AI 智能体 治理 工程 实践",
        "Agent Skill Harness 进化",
    ]

    wx_count = 0
    for topic in search_topics:
        try:
            results = search_wechat(topic, max_results=WECHAT_SEARCH_LIMIT)
            for art in results:
                if is_high_quality(art):
                    # 尝试抓取正文
                    content_data = fetch_article_content(art["url"])
                    content = ""
                    if content_data:
                        content = content_data.get("content", "")
                        if content_data.get("title"):
                            art["title"] = content_data["title"]

                    all_articles.append({
                        "title": art["title"],
                        "source": f"公众号-{art.get('source', '微信')}",
                        "url": art["url"],
                        "summary": art.get("summary", ""),
                        "content": content,
                        "_source_type": "wechat",
                    })
                    wx_count += 1
            time.sleep(1.0)  # 限速
        except Exception as e:
            print(f"  ⚠️ 搜索失败 [{topic[:20]}]: {e}")

    source_stats["微信公众号"] = wx_count
    print(f"  ✅ 搜到 {wx_count} 篇高质量文章")

    # ═══════════════════════════════════════
    # Step 3: RSS 采集（保留作为补充）
    # ═══════════════════════════════════════
    print("\n📡 [3/4] RSS 平台采集...")
    extractors = {
        "kr36": Kr36Extractor(),
        "ifanr": IfanrExtractor(),
        "huxiu": HuxiuExtractor(),
        "qbitai": QbitaiExtractor(),
        "sspai": SspaiExtractor(),
        "zhihu": ZhihuExtractor(),
    }

    async def collect_rss():
        tasks = {}
        for name, ext in extractors.items():
            tasks[name] = asyncio.create_task(_safe_fetch(name, ext))
        results = {}
        for name, task in tasks.items():
            try:
                results[name] = await task
            except Exception as e:
                print(f"  ⚠️ {name}: {e}")
                results[name] = []
        return results

    rss_results = asyncio.run(collect_rss())
    rss_count = 0
    for name, articles in rss_results.items():
        for art in articles:
            all_articles.append({
                "title": getattr(art, "title", ""),
                "source": name,
                "url": getattr(art, "url", ""),
                "summary": getattr(art, "summary", "") or getattr(art, "content", ""),
                "content": getattr(art, "content", "") or getattr(art, "summary", ""),
                "_source_type": "rss",
            })
            rss_count += 1
        source_stats[name] = len(articles)

    print(f"  ✅ RSS 采集 {rss_count} 条")

    total_fetched = len(all_articles)
    print(f"\n📊 全量采集: {total_fetched} 篇")

    if total_fetched == 0:
        print("⚠️ 无内容")
        return

    # ═══════════════════════════════════════
    # Step 3.5: 全文抓取（对 RSS 文章获取完整正文）
    # ═══════════════════════════════════════
    print(f"\n🌐 [3.5] 抓取全文...")

    fetched_count = 0
    for art in all_articles:
        # 只对内容不足的文章抓取全文
        text = art.get("content", "") or art.get("summary", "")
        if len(text) < 500 and art.get("url"):
            source = art.get("source", "")
            full_text = fetch_full_article(art["url"], source)
            if full_text and len(full_text) > 200:
                art["content"] = full_text
                art["_full_fetched"] = True
                fetched_count += 1
            time.sleep(0.3)  # 限速
    print(f"  ✅ 成功抓取 {fetched_count} 篇全文")

    # ═══════════════════════════════════════
    # Step 4: 深度评分 + 解读
    # ═══════════════════════════════════════
    print(f"\n🧠 [4/4] 深度评分与解读...")

    scored = []
    for art in all_articles:
        from scripts.interpreter import score_article_depth
        text = art.get("content", "") or art.get("summary", "")
        if not text:
            text = art.get("title", "")

        score = score_article_depth(
            text=text,
            title=art.get("title", ""),
            source=art.get("source", ""),
            url=art.get("url", "")
        )
        art["_depth_score"] = score
        scored.append(art)

    # 按深度评分排序
    scored.sort(key=lambda a: a["_depth_score"], reverse=True)

    # 统计评分分布
    deep_articles = [a for a in scored if a["_depth_score"] >= 4.0]
    medium_articles = [a for a in scored if 2.0 <= a["_depth_score"] < 4.0]
    shallow_articles = [a for a in scored if a["_depth_score"] < 2.0]

    print(f"  📊 深度 {len(deep_articles)} | 中度 {len(medium_articles)} | 浅层 {len(shallow_articles)}")

    # ── 深度解读 top N ──
    deep_interpretations = []
    top_for_deep = deep_articles[:MAX_DEEP_INTERPRET]

    if not quick:
        print(f"\n  🔬 对 Top {len(top_for_deep)} 篇进行深度解读...")
        for i, art in enumerate(top_for_deep, 1):
            title = art.get("title", "")[:50]
            print(f"    [{i}] {title}...")

            # 如果内容为空，尝试抓取全文
            content = art.get("content", "") or art.get("summary", "")
            if len(content) < 500 and art.get("url"):
                print(f"      ⚡ 尝试抓取全文...")
                try:
                    fetched = fetch_article_content(art["url"])
                    if fetched and fetched.get("content"):
                        content = fetched["content"]
                        art["content"] = content
                except Exception:
                    pass

            interpretation = interpret_article({
                "title": art.get("title", ""),
                "content": content,
                "source": art.get("source", ""),
                "url": art.get("url", ""),
            })

            if interpretation:
                deep_interpretations.append(interpretation)
                print(f"      ✅ 评分 {interpretation.quality_score}/10 | {len(interpretation.insights)} 个洞察")
            else:
                print(f"      ⏭️ 内容不足，跳过")

    # ── 快讯列表（中度文章作为快讯） ──
    quick_briefs = []
    for art in medium_articles[:MAX_QUICK_BRIEFS]:
        quick_briefs.append({
            "title": art.get("title", ""),
            "source": art.get("source", ""),
            "summary": art.get("summary", "")[:120] if art.get("summary") else "",
            "url": art.get("url", ""),
            "category": art.get("category", ""),
        })

    # 如果深度解读不够，从中度文章中补充
    while len(deep_interpretations) < 3 and medium_articles:
        art = medium_articles.pop(0)
        interpretation = interpret_article({
            "title": art.get("title", ""),
            "content": art.get("content", "") or art.get("summary", ""),
            "source": art.get("source", ""),
            "url": art.get("url", ""),
        })
        if interpretation:
            deep_interpretations.append(interpretation)

    # ═══════════════════════════════════════
    # Step 5: 生成日报
    # ═══════════════════════════════════════
    print(f"\n📝 生成 V3 日报...")
    print(f"  深度解读: {len(deep_interpretations)} 篇")
    print(f"  快讯速览: {len(quick_briefs)} 条")

    report_md = build_v3_report(
        deep_interpretations=deep_interpretations,
        quick_briefs=quick_briefs,
        date=date_str,
        total_fetched=total_fetched,
        source_stats=source_stats,
    )

    if dry_run:
        print("\n" + "=" * 60)
        print(report_md[:3000])
        if len(report_md) > 3000:
            print(f"\n... (共 {len(report_md)} 字符)")
        print("=" * 60)
        print("\n[DRY RUN] 未写入")
        return

    # ═══════════════════════════════════════
    # Step 6: 写入 Obsidian
    # ═══════════════════════════════════════
    from scripts.utils.obsidian_writer import write_to_obsidian

    filename = f"daily-report-{date_str}.md"
    try:
        filepath = write_to_obsidian(filename, report_md, folder="30-项目/AI博主与日报/日报存档")
        print(f"\n✅ 日报已写入: {filepath}")
    except Exception as e:
        print(f"\n⚠️ Obsidian 写入失败: {e}")
        fallback = ROOT / "output" / "daily_reports" / filename
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_text(report_md, encoding="utf-8")
        print(f"📁 备份至: {fallback}")

    print("\n" + "=" * 60)
    print("📋 日报摘要:")
    for i, ins in enumerate(deep_interpretations[:5], 1):
        stars = "⭐" * min(5, max(1, int(ins.quality_score / 2)))
        print(f"  {i}. [{stars}] {ins.title[:60]}")
    print(f"  快讯: {len(quick_briefs)} 条")


async def _safe_fetch(name: str, extractor) -> list:
    try:
        articles = await extractor.fetch()
        print(f"  [{name}] ✅ {len(articles)} 条")
        return articles
    except Exception as e:
        print(f"  [{name}] ❌ {e}")
        return []


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="knowledge-scout V3 日报")
    parser.add_argument("--date", help="日期 YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="打印不写入")
    parser.add_argument("--quick", action="store_true", help="快速模式（跳过深度解读）")
    args = parser.parse_args()
    main(date_str=args.date, dry_run=args.dry_run, quick=args.quick)
