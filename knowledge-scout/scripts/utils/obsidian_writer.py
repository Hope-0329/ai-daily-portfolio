"""Obsidian Vault 写入工具"""

import os
from pathlib import Path


OBSIDIAN_VAULT = r"D:\肠肠的Obsidian\肠肠的obsidian"


def write_to_obsidian(filename: str, content: str, folder: str = "00-收件箱") -> str:
    """写入 Obsidian Vault

    Args:
        filename: 文件名（不含路径）
        content: Markdown 内容
        folder: Vault 内的相对文件夹

    Returns:
        写入的完整路径
    """
    vault_path = Path(OBSIDIAN_VAULT)
    target_dir = vault_path / folder
    target_dir.mkdir(parents=True, exist_ok=True)

    filepath = target_dir / filename
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


def write_knowledge_card(
    title: str,
    content: str,
    category: str = "AI技术",
    tags: list[str] = None,
    source_url: str = "",
) -> str:
    """写入知识卡片到 02-专业知识库"""
    folder_map = {
        "AI技术": "02-专业知识库/AI技术",
        "投资分析": "02-专业知识库/投资分析",
        "经济趋势": "02-专业知识库/经济趋势",
        "产业研究": "02-专业知识库/产业研究",
    }
    folder = folder_map.get(category, "02-专业知识库")

    safe_title = title.replace("/", "-").replace("\\", "-")[:80]
    filename = f"{safe_title}.md"

    tags_yaml = "\n".join(f"  - {t}" for t in (tags or []))
    full_content = f"""---
title: "{title}"
source_url: "{source_url}"
date: {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}
category: {category}
tags:
{tags_yaml}
---

{content}
"""
    return write_to_obsidian(filename, full_content, folder)
