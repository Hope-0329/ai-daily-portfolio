"""Dashboard 页面数据组装。"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from src.database import get_connection, get_latest_daily_report_row, query_articles

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"

CATEGORY_SECTIONS: list[tuple[str, str, str]] = [
    ("ai-models", "🤖", "模型发布/更新"),
    ("ai-products", "📦", "产品发布/更新"),
    ("industry", "📊", "行业动态"),
    ("paper", "📝", "论文研究"),
    ("tip", "💡", "技巧与观点"),
]

_EMPTY_DAILY = {
    "date": date.today().isoformat(),
    "generated_at": "",
    "raw_count": 0,
    "l1_count": 0,
    "l2_count": 0,
}


def load_dashboard_context(settings) -> dict[str, Any]:
    """从 SQLite 加载 Dashboard 渲染上下文（无数据时返回空态）。"""
    with get_connection(settings) as conn:
        daily = get_latest_daily_report_row(conn)
        items: list[dict[str, Any]] = []
        if daily is not None:
            items, _ = query_articles(conn, mode="selected", window="7d", page_size=25)

    if daily is None:
        return {
            "daily": _EMPTY_DAILY,
            "items": [],
            "top3": [],
            "grouped": {},
            "category_counts": {},
            "category_sections": CATEGORY_SECTIONS,
            "filter_efficiency": 0.0,
            "l1_pass_rate": None,
            "quality_rate": None,
            "sources_success": None,
            "sources_total": None,
            "empty": True,
        }

    stats_payload: dict[str, Any] = {}
    if daily.get("stats"):
        try:
            stats_payload = json.loads(daily["stats"])
        except json.JSONDecodeError:
            stats_payload = {}

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    category_counts: dict[str, int] = defaultdict(int)
    for item in items:
        category = item.get("category") or "ai-models"
        grouped[category].append(item)
        category_counts[category] += 1

    top3 = sorted(items, key=lambda row: row.get("score") or 0, reverse=True)[:3]

    return {
        "daily": daily,
        "items": items,
        "top3": top3,
        "grouped": dict(grouped),
        "category_counts": dict(category_counts),
        "category_sections": CATEGORY_SECTIONS,
        "filter_efficiency": daily.get("snr", 0),
        "l1_pass_rate": stats_payload.get("l1_pass_rate"),
        "quality_rate": stats_payload.get("l2_quality") or stats_payload.get("quality_rate"),
        "sources_success": stats_payload.get("sources_success"),
        "sources_total": stats_payload.get("sources_total"),
        "empty": False,
    }
