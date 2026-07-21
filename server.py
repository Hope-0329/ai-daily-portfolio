"""
AI日报 MCP Server — 让任何大模型都能生成 AI 日报

四步流水线 → 四个标准化 Tool:
  1. list_sources   → 列出所有可用信源
  2. fetch_news      → 抓取新闻 + 预评分
  3. deep_read       → 抓全文 + 深度解读
  4. save_to_obsidian → 写入 Obsidian 知识库

用法: python server.py
需要在 Claude Desktop 配置中注册此 Server。
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 确保输出无乱码
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mcp.server import Server
from mcp.server.models import InitializationOptions, ServerCapabilities
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ToolsCapability

# ── 导入知识管线 ──
SCOUT_ROOT = Path(r"C:\Users\22867\.qclaw\workspace\knowledge-scout")
sys.path.insert(0, str(SCOUT_ROOT))

from tools.fetcher import fetch_articles, fetch_full_article_safe, SOURCE_NAMES, EXTRACTORS

# ── 解释器（延迟导入，避免启动时加载） ──
_interpreter = None

def _get_interpreter():
    global _interpreter
    if _interpreter is None:
        from scripts.interpreter import interpret_article
        _interpreter = interpret_article
    return _interpreter

# ── 创建 Server ──
server = Server("ai-daily-mcp")

# ═══════════════════════════════════════════
# Tool 1: list_sources
# ═══════════════════════════════════════════
@server.list_tools()
async def handle_list_tools():
    return [
        Tool(
            name="list_sources",
            description="列出所有可用的AI新闻信源（36氪、虎嗅、量子位、GitHub Trending等），了解有哪些平台可以抓取",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="fetch_news",
            description="从指定信源抓取AI领域最新文章，自动预评分（深度/中度/浅层），返回按质量排序的结果",
            inputSchema={
                "type": "object",
                "properties": {
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "信源 key 列表，如 ['36kr', 'huxiu', 'qbitai']。不传则抓取全部信源"
                    },
                    "count": {
                        "type": "integer",
                        "description": "返回文章数量，默认15条",
                        "default": 15
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="deep_read",
            description="深度阅读一篇文章：抓取全文 → LLM解读 → 提取核心论点、框架、数据要点和启发。适合对 fetch_news 返回的高分文章做深度分析",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要深度阅读的文章 URL"
                    },
                    "source": {
                        "type": "string",
                        "description": "文章来源（如 '36kr'、'huxiu'），帮助选择正确的解析器"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="save_to_obsidian",
            description="将日报内容保存到 Obsidian 知识库的 AI日报文件夹中",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "要保存的 Markdown 格式日报内容"
                    },
                    "filename": {
                        "type": "string",
                        "description": "文件名（不含路径），如 'daily-report-2026-07-21.md'。默认自动生成当天日期"
                    }
                },
                "required": ["content"]
            }
        )
    ]

# ═══════════════════════════════════════════
# Tool 实现
# ═══════════════════════════════════════════
@server.call_tool()
async def handle_call_tool(name: str, arguments: dict):
    # ── Tool 1: list_sources ──
    if name == "list_sources":
        lines = ["📡 **可用的 AI 新闻信源**\n"]
        for key, label in SOURCE_NAMES.items():
            ext = EXTRACTORS.get(key)
            type_tag = "RSS" if ext and hasattr(ext, "fetch") else "API"
            lines.append(f"- **{label}** (`{key}`) — {type_tag}")
        lines.append(f"\n共 {len(SOURCE_NAMES)} 个信源，覆盖中文科技媒体 + GitHub/HuggingFace 全球信源")
        return [TextContent(type="text", text="\n".join(lines))]

    # ── Tool 2: fetch_news ──
    elif name == "fetch_news":
        sources = arguments.get("sources")
        count = arguments.get("count", 15)

        result = await fetch_articles(sources=sources, count=count)

        lines = [f"## 📰 AI 日报 · {datetime.now().strftime('%Y-%m-%d')}\n"]
        lines.append(f"**信源覆盖**: {len(result['stats'])} 个平台 | "
                     f"**原始采集**: {result['total']} 篇 | "
                     f"**深度**: {result['deep_count']} | "
                     f"**中度**: {result['medium_count']}\n")

        # 各信源统计
        lines.append("### 各信源采集情况")
        for src, stat in result["stats"].items():
            lines.append(f"- {src}: {stat}")

        # Top 文章列表
        lines.append(f"\n### 🔝 Top {len(result['articles'])} 文章（按质量评分排序）\n")
        for i, art in enumerate(result["articles"], 1):
            level_icon = {"深度": "🔬", "中度": "📖", "浅层": "📄"}.get(art["level"], "📄")
            lines.append(f"**{i}. [{level_icon} {art['level']}] {art['title']}**")
            lines.append(f"   来源: {art['source']} | 评分: {art['score']:.1f}")
            lines.append(f"   摘要: {art['summary'][:150]}")
            if art.get("url"):
                lines.append(f"   链接: {art['url']}")
            lines.append("")

        return [TextContent(type="text", text="\n".join(lines))]

    # ── Tool 3: deep_read ──
    elif name == "deep_read":
        url = arguments.get("url", "")
        source = arguments.get("source", "")

        if not url:
            return [TextContent(type="text", text="❌ 请提供要阅读的文章 URL")]

        # Step 1: 抓取全文
        lines = [f"## 🔬 深度阅读\n"]
        lines.append(f"**URL**: {url}\n")
        lines.append("⏳ 正在抓取全文...\n")

        full_text = await fetch_full_article_safe(url, source)

        if not full_text or len(full_text) < 200:
            lines.append("⚠️ 无法获取文章全文（可能被反爬或付费墙拦截）")
            return [TextContent(type="text", text="\n".join(lines))]

        lines.append(f"✅ 全文获取成功 ({len(full_text)} 字符)\n")

        # Step 2: 解释器提取内容
        try:
            interpret = _get_interpreter()
            title = ""  # 从全文第一行尝试提取
            insight = interpret({
                "title": title,
                "content": full_text,
                "source": source,
                "url": url,
            })
            if insight:
                lines.append(f"### 📊 核心发现")
                lines.append(f"- **主题分类**: {getattr(insight, 'category', '未分类')}")
                lines.append(f"- **质量评分**: {getattr(insight, 'quality_score', 'N/A')}/10")

                if hasattr(insight, 'thesis') and insight.thesis:
                    lines.append(f"\n### 💡 核心论点")
                    lines.append(insight.thesis)

                if hasattr(insight, 'frameworks') and insight.frameworks:
                    lines.append(f"\n### 🧩 关键框架")
                    for fw in insight.frameworks:
                        lines.append(f"- {fw}")

                if hasattr(insight, 'insights') and insight.insights:
                    lines.append(f"\n### 🔑 洞察要点")
                    for ins in insight.insights:
                        lines.append(f"- {ins}")

                if hasattr(insight, 'data_points') and insight.data_points:
                    lines.append(f"\n### 📈 数据看点")
                    for dp in insight.data_points:
                        lines.append(f"- {dp}")

                if hasattr(insight, 'takeaways') and insight.takeaways:
                    lines.append(f"\n### 🎯 行动启发")
                    for take in insight.takeaways:
                        lines.append(f"- {take}")
            else:
                lines.append("\n⚠️ 解读器未能提取结构化见解（内容可能不包含足够的分析框架）")
        except Exception as e:
            lines.append(f"\n⚠️ 深度解读失败: {e}")
            # 降级：直接返回前 2000 字
            lines.append(f"\n### 📄 文章前 2000 字\n")
            lines.append(full_text[:2000])

        return [TextContent(type="text", text="\n".join(lines))]

    # ── Tool 4: save_to_obsidian ──
    elif name == "save_to_obsidian":
        content = arguments.get("content", "")
        filename = arguments.get("filename", f"daily-report-{datetime.now().strftime('%Y-%m-%d')}.md")

        if not content.strip():
            return [TextContent(type="text", text="❌ 内容不能为空")]

        # 写入 Obsidian
        vault_path = Path(r"D:\肠肠的Obsidian\肠肠的obsidian\00-收件箱\AI日报")
        vault_path.mkdir(parents=True, exist_ok=True)

        filepath = vault_path / filename
        try:
            filepath.write_text(content, encoding="utf-8")
            return [TextContent(
                type="text",
                text=f"✅ 已保存到 Obsidian\n\n📁 路径: `{filepath}`\n📏 大小: {len(content)} 字符"
            )]
        except Exception as e:
            # 降级到 workspace
            fallback = Path(r"C:\Users\22867\.qclaw\workspace\ai-daily-mcp") / filename
            fallback.write_text(content, encoding="utf-8")
            return [TextContent(
                type="text",
                text=f"⚠️ Obsidian 写入失败 ({e})\n📁 已保存到本地: `{fallback}`"
            )]

    else:
        return [TextContent(type="text", text=f"❌ 未知工具: {name}")]


# ═══════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="ai-daily-mcp",
                server_version="1.0.0",
                capabilities=ServerCapabilities(
                    tools=ToolsCapability()
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
