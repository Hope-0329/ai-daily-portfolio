# -*- coding: utf-8 -*-
"""
日报生成器 v4.0

流水线:
  1. 评分 → 四维评分（Scorer）
  2. 过滤 → 去重 + Top N 截断
  3. 格式化 → Markdown 日报
  4. 自检 → 链接验证 + 摘要对比修正
  5. 写入 → Obsidian Vault

设计:
  - 日报格式：平铺 Top 50，每条标题+2句话摘要+链接+来源+类型
  - AI 自检：验证 HTTP 200 + 摘要偏差 >30% 则修正
"""

import sys, io, os, time, re
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.scorer import Scorer
from scripts.extract.collector import Collector
from scripts.filter import FilterEngine

# ── HTTP 会话（用于自检） ──
_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})
retry = Retry(total=1, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503])
_session.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=5, pool_maxsize=10))

# ── 配置 ──
CONFIG = {
    "top_n": 50,
    "min_score": 1.0,
    "duplicate_threshold": 0.75,
    "obsidian_vault": r"D:\肠肠的Obsidian\肠肠的obsidian",
    "report_folder": "30-项目/AI博主与日报/日报存档",
    "max_summary_chars": 200,
    "self_check_timeout": 8,
    "max_self_check": 15,                      # 只检查前15条链接
    "summary_deviation_threshold": 0.3,        # 摘要偏差 >30% 则修正
    "url_blacklist": [                         # 跳过自检的域名
        "zhihu.com", "weixin.qq.com", "mp.weixin.qq.com",
    ],
}

# ── 来源类型映射 ──
SOURCE_TYPES = {
    "36氪": "🚀 产业快讯",
    "36氪快讯": "⚡ 快讯",
    "虎嗅": "📝 深度分析",
    "量子位": "🔬 AI专业",
    "爱范儿": "📱 产品科技",
    "少数派": "🛠 效率工具",
    "知乎日报": "💬 综合精选",
    "晚点LatePost": "📰 商业深度",
    "Reddit ML": "🌐 学术社区",
}


class Reporter:
    """日报生成器：评分 → 格式化 → 自检 → 写入"""

    def __init__(self, config: dict = None):
        self.cfg = {**CONFIG, **(config or {})}
        self.scorer = Scorer()
        self.filter_engine = FilterEngine({
            "min_score": self.cfg["min_score"],
            "max_articles": self.cfg["top_n"],
            "duplicate_threshold": self.cfg["duplicate_threshold"],
        })
        self.now = datetime.now()

    # ═══════════════════════════════════════
    # Step 1: 采集 + 评分 + 过滤
    # ═══════════════════════════════════════
    def collect_and_score(self) -> list:
        """从 Collector 采集 + 四维评分 + 过滤 → Top N"""
        print("[1/4] 采集...")
        collector = Collector()
        articles = collector.fetch_all()
        total = len(articles)

        print(f"[2/4] 评分 ({total} 篇)...")
        articles = self.scorer.score_articles(articles)

        print(f"[3/4] 过滤去重 → Top {self.cfg['top_n']}...")
        filtered = self.filter_engine.process(articles)

        return filtered

    # ═══════════════════════════════════════
    # Step 2: 生成日报 Markdown
    # ═══════════════════════════════════════
    def generate_report(self, articles: list) -> str:
        """生成平铺 Top N 日报"""
        date_str = self.now.strftime("%Y-%m-%d")
        weekday = ["一", "二", "三", "四", "五", "六", "日"][self.now.weekday()]

        # 统计
        source_count = len(set(a.platform for a in articles))
        dist = Scorer.score_distribution(articles)

        lines = []
        lines.append(f"# AI 日报 {date_str} (周{weekday})")
        lines.append("")
        lines.append(
            f"> 📊 **采集源**: {source_count} 个 | "
            f"**收录**: {len(articles)} 篇 | "
            f"**生成时间**: {self.now.strftime('%H:%M')}"
        )
        lines.append("")

        # 评分分布
        stars_line = " | ".join(
            f"{k} {v}" for k, v in dist.items() if v > 0
        )
        lines.append(f"**评分分布**: {stars_line}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # ── Top N 平铺 ──
        for i, a in enumerate(articles, 1):
            score = getattr(a, 'raw_score', 0)
            stars = Scorer.to_stars(score)
            source_type = SOURCE_TYPES.get(a.platform, "📌 其他")
            summary = a.summary[:self.cfg["max_summary_chars"]].strip()

            lines.append(f"### {i}. {a.title}  {stars}")
            lines.append("")
            lines.append(f"**来源**: {a.platform} | **类型**: {source_type}")
            lines.append("")
            lines.append(f"{summary}")
            lines.append("")
            lines.append(f"🔗 [{a.platform}原文]({a.url})")
            lines.append("")
            if i < len(articles):
                lines.append("---")
                lines.append("")

        # ── 底部 ──
        lines.append("---")
        lines.append("")
        lines.append(f"> 🤖 由 knowledge-scout v4.0 自动生成")
        lines.append(f"> 📅 下次更新: {(self.now + __import__('datetime').timedelta(days=1)).strftime('%Y-%m-%d')} 07:00")

        return "\n".join(lines)

    # ═══════════════════════════════════════
    # Step 3: AI 自检
    # ═══════════════════════════════════════
    def self_check(self, articles: list) -> dict:
        """
        验证链接有效性 + 摘要准确性
        
        Returns:
            {"checked": N, "dead": N, "fixed_summaries": N, "details": [...]}
        """
        print(f"\n[AI自检] 验证链接与摘要...")

        results = {"checked": 0, "dead": 0, "fixed_summaries": 0, "details": []}
        check_limit = min(self.cfg["max_self_check"], len(articles))

        for i, a in enumerate(articles[:check_limit]):
            url = a.url if hasattr(a, "url") else ""
            if not url:
                continue

            # 跳过黑名单域名
            if any(domain in url for domain in self.cfg["url_blacklist"]):
                continue

            result = {"title": a.title[:50], "url": url[:80], "status": "OK"}

            try:
                # 1. 链接验证
                resp = _session.head(
                    url,
                    timeout=self.cfg["self_check_timeout"],
                    allow_redirects=True,
                )
                if resp.status_code >= 400:
                    result["status"] = f"DEAD({resp.status_code})"
                    results["dead"] += 1
                elif resp.status_code == 200:
                    # 2. 摘要对比（如果响应是 HTML）
                    ct = resp.headers.get("content-type", "")
                    if "html" in ct and hasattr(a, "summary") and a.summary:
                        try:
                            resp2 = _session.get(
                                url,
                                timeout=self.cfg["self_check_timeout"],
                                allow_redirects=True,
                                stream=True,
                            )
                            # 拿前 300 字
                            body = ""
                            for chunk in resp2.iter_content(chunk_size=1024, decode_unicode=True):
                                if isinstance(chunk, bytes):
                                    body += chunk.decode("utf-8", errors="ignore")
                                else:
                                    body += chunk
                                if len(body) > 5000:
                                    break
                            resp2.close()

                            # 简单提取文本
                            text = re.sub(r"<[^>]+>", " ", body)
                            text = re.sub(r"\s+", " ", text).strip()[:300]

                            if text:
                                # 对比摘要与原文前300字的相似度
                                sim = self._text_overlap(a.summary[:200], text)
                                if sim < (1 - self.cfg["summary_deviation_threshold"]):
                                    # 摘要偏差大，用原文前 150 字替换
                                    a.summary = text[:150]
                                    result["status"] = f"FIXED(sim={sim:.2f})"
                                    results["fixed_summaries"] += 1
                        except Exception:
                            pass  # GET 失败不影响链接验证结果

                results["checked"] += 1
                results["details"].append(result)

            except requests.ConnectionError:
                result["status"] = "DEAD(conn)"
                results["dead"] += 1
                results["details"].append(result)
            except requests.Timeout:
                result["status"] = "DEAD(timeout)"
                results["dead"] += 1
                results["details"].append(result)
            except Exception as e:
                result["status"] = f"ERR({str(e)[:30]})"
                results["details"].append(result)

            time.sleep(0.3)  # 礼貌限速

        # 汇总
        print(f"  检查: {results['checked']} | 死链: {results['dead']} | 摘要修正: {results['fixed_summaries']}")
        for d in results["details"]:
            if "DEAD" in d["status"] or "FIXED" in d["status"]:
                print(f"  [{d['status']}] {d['title'][:40]}")

        return results

    @staticmethod
    def _text_overlap(a: str, b: str) -> float:
        """计算两个文本的词级重叠率（简单 Jaccard）"""
        a_words = set(re.findall(r"[\w\u4e00-\u9fff]+", a.lower()))
        b_words = set(re.findall(r"[\w\u4e00-\u9fff]+", b.lower()))
        if not a_words or not b_words:
            return 0.0
        intersection = a_words & b_words
        union = a_words | b_words
        return len(intersection) / len(union) if union else 0.0

    # ═══════════════════════════════════════
    # Step 4: 写入 Obsidian
    # ═══════════════════════════════════════
    def write_to_obsidian(self, md_content: str) -> str:
        """写入日报到 Obsidian Vault"""
        vault = Path(self.cfg["obsidian_vault"])
        folder = vault / self.cfg["report_folder"]
        folder.mkdir(parents=True, exist_ok=True)

        date_str = self.now.strftime("%Y-%m-%d")
        filename = f"AI日报_{date_str}.md"
        filepath = folder / filename
        filepath.write_text(md_content, encoding="utf-8")
        return str(filepath)

    # ═══════════════════════════════════════
    # 全流程入口
    # ═══════════════════════════════════════
    def run(self, dry_run: bool = False, skip_check: bool = False) -> str:
        """
        一键生成日报

        Args:
            dry_run: 打印不写入
            skip_check: 跳过 AI 自检
        Returns:
            日报 Markdown 内容
        """
        t0 = time.time()

        # 1-3: 采集 → 评分 → 过滤
        articles = self.collect_and_score()

        # 自检
        check_results = {"checked": 0, "dead": 0, "fixed_summaries": 0}
        if not skip_check:
            check_results = self.self_check(articles)

        # 4: 生成日报
        print(f"\n[4/4] 生成日报...")
        report_md = self.generate_report(articles)

        elapsed = time.time() - t0
        print(f"\n✅ 日报生成完成 ({elapsed:.1f}s)")

        # 自检结果追加到日报
        if check_results["checked"] > 0:
            check_note = (
                f"\n\n---\n"
                f"## 🔍 AI 自检报告\n\n"
                f"- 链接验证: {check_results['checked']} 条\n"
                f"- 死链: {check_results['dead']} 条\n"
                f"- 摘要修正: {check_results['fixed_summaries']} 条\n"
            )
            report_md += check_note

        if dry_run:
            preview = report_md[:2000]
            print(f"\n{'='*60}")
            print(preview)
            if len(report_md) > 2000:
                print(f"\n... (共 {len(report_md)} 字符)")
            print(f"{'='*60}")
            return report_md

        # 5: 写入 Obsidian
        filepath = self.write_to_obsidian(report_md)
        print(f"📁 已写入: {filepath}")
        print(f"📏 共 {len(report_md)} 字符, {len(articles)} 篇")

        return report_md


# ── CLI ──
if __name__ == "__main__":
    import argparse

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    parser = argparse.ArgumentParser(description="knowledge-scout v4 日报生成器")
    parser.add_argument("--dry-run", action="store_true", help="打印预览不写入")
    parser.add_argument("--skip-check", action="store_true", help="跳过 AI 自检")
    parser.add_argument("--top", type=int, default=50, help="Top N 条数")
    args = parser.parse_args()

    config = CONFIG.copy()
    config["top_n"] = args.top

    reporter = Reporter(config)
    reporter.run(dry_run=args.dry_run, skip_check=args.skip_check)
