# -*- coding: utf-8 -*-
"""
knowledge-scout v4.0 — 全流程日报+深度解读管线
==============================================

流程:
  [采集] → [评分+过滤] → [日报生成] → [AI自检] → [深度分析候选] → [入库]

两种运行模式:
  1. 日报模式（默认）: 采集→评分→日报→写入 Obsidian
  2. 日报+深度模式: 日报 + 准备深度解读候选队列 → Agent 生成解读 → 写入

设计:
  - 日报生成复用 v3 Reporter（已验证稳定）
  - 深度解读用 DeepAnalyzer 模块
  - 所有配置集中管理
"""

import io
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.scorer import Scorer
from scripts.extract.collector import Collector
from scripts.filter import FilterEngine
from scripts.reporter import Reporter
from scripts.deep_analyzer import DeepAnalyzer, DeepCandidate

# ── 编码 ──
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass

# ── 配置 ──
CONFIG = {
    # 日报
    "top_n": 50,
    "min_score": 1.0,
    "obsidian_vault": r"D:\肠肠的Obsidian\肠肠的obsidian",
    "report_folder": "30-项目/AI博主与日报/日报存档",

    # 深度解读
    "deep_enabled": False,
    "deep_top_n": 5,
    "deep_min_score": 4.5,
    "queue_file": "candidate_queue.json",

    # 自检
    "skip_check": False,
}


class ReportV4:
    """v4.0 全流程管线"""

    def __init__(self, config: dict = None):
        self.cfg = {**CONFIG, **(config or {})}
        self.reporter = Reporter({
            "top_n": self.cfg["top_n"],
            "min_score": self.cfg["min_score"],
            "obsidian_vault": self.cfg["obsidian_vault"],
            "report_folder": self.cfg["report_folder"],
        })
        self.analyzer = DeepAnalyzer()
        self.now = datetime.now()

    # ═══════════════════════════════════════
    # Phase 1: 日报管线（复用 v3 Reporter）
    # ═══════════════════════════════════════

    def run_report(self, dry_run: bool = False) -> tuple:
        """
        执行日报管线：采集→评分→过滤→生成→写入
        
        Returns:
            (report_md, report_path, articles)
        """
        print(f"\n{'='*60}")
        print(f"📰 knowledge-scout v4.0 日报管线")
        print(f"{'='*60}")
        print(f"时间: {self.now.strftime('%Y-%m-%d %H:%M')}")
        print(f"")

        t0 = time.time()

        # 1-3: 采集 → 评分 → 过滤
        articles = self.reporter.collect_and_score()

        # 4: AI 自检
        check_results = {}
        if not self.cfg["skip_check"]:
            check_results = self.reporter.self_check(articles)

        # 5: 生成日报
        report_md = self.reporter.generate_report(articles)

        # 自检结果追加
        if check_results and check_results.get("checked", 0) > 0:
            check_note = (
                f"\n\n---\n"
                f"## 🔍 AI 自检报告\n\n"
                f"- 链接验证: {check_results['checked']} 条\n"
                f"- 死链: {check_results['dead']} 条\n"
                f"- 摘要修正: {check_results['fixed_summaries']} 条\n"
            )
            report_md += check_note

        elapsed = time.time() - t0

        report_path = ""
        if dry_run:
            preview = report_md[:2000]
            print(f"\n{'='*60}")
            print(preview)
            if len(report_md) > 2000:
                print(f"\n... (共 {len(report_md)} 字符)")
            print(f"{'='*60}")
        else:
            report_path = self.reporter.write_to_obsidian(report_md)

        print(f"\n✅ 日报完成 ({elapsed:.1f}s)")
        print(f"   文章数: {len(articles)}")
        if report_path:
            print(f"   输出: {report_path}")
            print(f"   大小: {len(report_md)} 字符")

        return report_md, report_path, articles

    # ═══════════════════════════════════════
    # Phase 2: 深度解读管线
    # ═══════════════════════════════════════

    def run_deep_analysis(self, articles: list, top_n: int = None,
                          min_score: float = None, dry_run: bool = False) -> list:
        """
        准备深度解读候选队列。

        Args:
            articles: 已评分的文章列表
            top_n: 深度解读 Top N
            min_score: 最低分数门槛

        Returns:
            candidates 列表
        """
        top_n = top_n or self.cfg["deep_top_n"]
        min_score = min_score or self.cfg["deep_min_score"]

        # 筛选高分文章
        qualified = [
            a for a in articles
            if getattr(a, 'raw_score', 0) >= min_score
        ]
        qualified = sorted(qualified, key=lambda a: getattr(a, 'raw_score', 0), reverse=True)

        print(f"\n{'='*60}")
        print(f"🧠 深度解读管线 (合格 {len(qualified)} → Top {top_n})")
        print(f"{'='*60}")

        candidates = self.analyzer.prepare(qualified, top_n=top_n)

        if not dry_run:
            queue_path = self.analyzer.export_queue(candidates, self.cfg["queue_file"])

        return candidates

    # ═══════════════════════════════════════
    # Phase 3: 写入已完成解读
    # ═══════════════════════════════════════

    def ingest_completed(self, queue_path: str = None) -> list:
        """
        将 Agent 已完成解读的候选写入 Obsidian。

        工作流:
          1. Agent 读取 candidate_queue.json
          2. Agent 为每个 candidate 生成 interpretation
          3. Agent 回填 interpretation 到 JSON
          4. 调用本方法写入 Obsidian + 更新 MOC
        """
        queue_path = queue_path or self.cfg["queue_file"]
        candidates = self.analyzer.load_queue(queue_path)
        paths = self.analyzer.ingest_all(candidates)
        return paths

    # ═══════════════════════════════════════
    # 全流程入口
    # ═══════════════════════════════════════

    def run(self, dry_run: bool = False) -> dict:
        """
        一键运行完整流程。

        Returns:
            {
                "report_md": str,
                "report_path": str,
                "articles": list,
                "candidates": list,
                "deep_outputs": list,
            }
        """
        result = {
            "report_md": "",
            "report_path": "",
            "articles": [],
            "candidates": [],
            "deep_outputs": [],
        }

        # Phase 1: 日报
        report_md, report_path, articles = self.run_report(dry_run=dry_run)
        result["report_md"] = report_md
        result["report_path"] = report_path
        result["articles"] = articles

        # Phase 2: 深度解读（如果有启用且有合格文章）
        if self.cfg["deep_enabled"] and articles:
            candidates = self.run_deep_analysis(articles, dry_run=dry_run)
            result["candidates"] = candidates

            # 如果是 dry_run，展示 prompt 摘要
            if dry_run and candidates:
                print(f"\n{'='*60}")
                print(f"📋 深度解读候选预览")
                print(f"{'='*60}")
                for i, c in enumerate(candidates):
                    print(f"\n[{i+1}] {c.title[:50]}")
                    print(f"    评分: {c.score:.1f} | 模板: {c.template_id}")
                    print(f"    域: {c.domain} | 标签: {', '.join(c.tags[:5])}")
                    print(f"    Prompt 长度: {len(c.prompt)} 字符")

        # 总结
        print(f"\n{'='*60}")
        print(f"🏁 knowledge-scout v4.0 完成")
        print(f"{'='*60}")
        print(f"  日报: {len(articles)} 篇 → {report_path or '(dry-run)'}")
        print(f"  深度候选: {len(result['candidates'])} 篇")
        if result["deep_outputs"]:
            print(f"  深度写入: {len(result['deep_outputs'])} 篇")
        print(f"")

        return result


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="knowledge-scout v4.0 — 日报+深度解读管线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python report_v4.py                          # 只生成日报
  python report_v4.py --dry-run                # 预览不写入
  python report_v4.py --deep 5                 # 日报 + Top5深度候选队列
  python report_v4.py --deep 5 --dry-run       # 预览深度候选
  python report_v4.py --ingest queue.json      # 写入已完成解读
  python report_v4.py --report-only            # 仅日报(跳过深度)
        """,
    )

    parser.add_argument("--dry-run", action="store_true", help="预览不写入")
    parser.add_argument("--skip-check", action="store_true", help="跳过 AI 自检")
    parser.add_argument("--top", type=int, default=50, help="日报 Top N (默认50)")
    parser.add_argument("--deep", type=int, default=0, help="深度解读 Top N (默认0=禁用)")
    parser.add_argument("--min-score", type=float, default=4.5, help="深度解读最低分数")
    parser.add_argument("--queue", default="candidate_queue.json", help="队列文件路径")
    parser.add_argument("--ingest", default=None, help="仅写入已完成解读(需指定队列JSON)")
    parser.add_argument("--report-only", action="store_true", help="仅生成日报，跳过深度解读")

    args = parser.parse_args()

    # ── 模式：仅写入已完成解读 ──
    if args.ingest:
        config = CONFIG.copy()
        config["queue_file"] = args.ingest
        rv4 = ReportV4(config)
        paths = rv4.ingest_completed(args.ingest)
        print(f"\n✅ 已写入 {len(paths)} 篇到 Obsidian")
        for p in paths:
            print(f"   {p}")
        sys.exit(0)

    # ── 模式：日报 + 可选深度解读 ──
    config = CONFIG.copy()
    config["top_n"] = args.top
    config["skip_check"] = args.skip_check
    config["deep_enabled"] = args.deep > 0
    config["deep_top_n"] = args.deep
    config["deep_min_score"] = args.min_score
    config["queue_file"] = args.queue

    if args.report_only:
        config["deep_enabled"] = False

    rv4 = ReportV4(config)
    result = rv4.run(dry_run=args.dry_run)
