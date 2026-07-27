"""Obsidian 写入测试。"""

from pathlib import Path

from src.output.obsidian import ObsidianWriter

CONTENT = "# 测试日报\n\n正文"


def test_write_daily_report(tmp_path: Path) -> None:
    writer = ObsidianWriter(tmp_path)
    path = writer.write_daily_report("2026-07-26", CONTENT)
    file_path = Path(path)
    assert file_path.parent.name == "日报存档"
    assert file_path.name == "2026-07-26 AI日报.md"
    assert file_path.read_text(encoding="utf-8") == CONTENT


def test_update_index_creates_and_updates(tmp_path: Path) -> None:
    writer = ObsidianWriter(tmp_path)
    report_path = writer.write_daily_report("2026-07-26", CONTENT)
    deep_path = writer.write_deep_analysis("2026-07-26", "GPT-5 解读", "深度内容")
    index_path = writer.update_index("2026-07-26", report_path, [deep_path])
    text = Path(index_path).read_text(encoding="utf-8")
    assert "2026-07-26" in text
    assert "AI 日报索引" in text

    index_path_2 = writer.update_index("2026-07-26", report_path, [deep_path])
    assert Path(index_path_2).read_text(encoding="utf-8").count("## 2026-07-26") == 1


def test_obsidian_writer_skips_when_disabled(tmp_path: Path) -> None:
    writer = ObsidianWriter(tmp_path, enabled=False)
    assert writer.write_daily_report("2026-07-26", CONTENT) == ""
    assert writer.write_deep_analysis("2026-07-26", "标题", "内容") == ""
    assert writer.update_index("2026-07-26", "", []) == ""
    assert not (tmp_path / "日报存档").exists()
