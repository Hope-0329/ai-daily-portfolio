"""Obsidian 笔记写入。"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ObsidianWriter:
    """Obsidian 文件写入器。"""

    def __init__(
        self,
        root_path: str | Path,
        *,
        index_filename: str = "INDEX.md",
        enabled: bool = True,
    ) -> None:
        self.root = Path(root_path)
        self.index_filename = index_filename
        self.enabled = enabled

    def _ensure_enabled(self, action: str) -> bool:
        if self.enabled:
            return True
        logger.info("[obsidian] 已禁用（云环境），跳过 %s", action)
        return False

    @staticmethod
    def _sanitize_filename(name: str, *, max_length: int = 50) -> str:
        """清理文件名中的非法字符。"""
        cleaned = re.sub(r'[<>:"/\\|?*]', "_", name)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned[:max_length] or "untitled"

    def write_daily_report(self, date_str: str, markdown: str) -> str:
        """写入日报 Markdown 到「日报存档」子目录，返回文件路径。"""
        if not self._ensure_enabled("日报写入"):
            return ""
        filename = f"{date_str} AI日报.md"
        filepath = self.root / "日报存档" / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(markdown, encoding="utf-8")
        return str(filepath)

    def write_deep_analysis(self, date_str: str, title: str, content: str) -> str:
        """写入深度解读到 Obsidian，返回文件路径。"""
        if not self._ensure_enabled("深度解读写入"):
            return ""
        safe_title = self._sanitize_filename(title)
        filename = f"{date_str} {safe_title}.md"
        filepath = self.root / "深度解读" / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        return str(filepath)

    def update_index(self, date_str: str, report_md_path: str, deep_paths: list[str]) -> str:
        """更新日报索引文件。"""
        if not self._ensure_enabled("索引更新"):
            return ""
        index_path = self.root / self.index_filename
        index_path.parent.mkdir(parents=True, exist_ok=True)

        report_name = Path(report_md_path).name
        deep_links = "\n".join(f"  - [[{Path(path).stem}]]" for path in deep_paths)
        entry = (
            f"\n## {date_str}\n"
            f"- 日报：[[{Path(report_name).stem}]]\n"
            f"- 深度解读 ({len(deep_paths)} 篇)：\n{deep_links or '  - 无'}\n"
        )

        if index_path.exists():
            content = index_path.read_text(encoding="utf-8")
            marker = f"## {date_str}"
            if marker in content:
                pattern = rf"\n## {re.escape(date_str)}[\s\S]*?(?=\n## |\Z)"
                content = re.sub(pattern, entry.rstrip(), content)
            else:
                content = content.rstrip() + entry
        else:
            content = f"# AI 日报索引\n\n> 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{entry}"

        index_path.write_text(content.rstrip() + "\n", encoding="utf-8")
        return str(index_path)
