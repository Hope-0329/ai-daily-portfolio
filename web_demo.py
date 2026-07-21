"""
AI日报 MCP Server — Web Demo 后端
FastAPI + 对接 knowledge-scout V3 管道

访问 http://localhost:8765 打开可视化 Demo
面试官无需安装任何东西，浏览器直接查看完整能力
"""
import re
import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

SCOUT_ROOT = Path(r"C:\Users\22867\.qclaw\workspace\knowledge-scout")
sys.path.insert(0, str(SCOUT_ROOT))

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from tools.fetcher import fetch_articles, fetch_full_article_safe, SOURCE_NAMES, EXTRACTORS
from scripts.llm_interpreter import interpret_article_async

app = FastAPI(title="AI日报 MCP Server Demo", version="2.0.0")


# ── 内容质量检测 ──
def _check_content_quality(text: str) -> dict:
    """检测抓取内容的纯净度，返回噪声比和有效字数"""
    if not text:
        return {"noise_ratio": 1.0, "word_count": 0}

    lines = text.split("\n")
    noise_lines = 0
    total_lines = len(lines)

    # 噪声特征（CSS、JS、乱码、导航残留）
    noise_patterns = [
        r"^\s*[.#@]\w+\s*\{",        # CSS 选择器
        r"^\s*(function|const|let|var|import|export)\s",  # JS 代码
        r"^\s*(window|document|console)\.",  # DOM API
        r"^\s*\{\s*$",                # 裸花括号
        r"^\s*\}\s*$",
        r"^\s*\/\/.*",                # 注释行
        r"^\s*\/\*|\*\/",            # 块注释
        r"^\s*@media|@import|@keyframes",
        r"^\s*<\w+[^>]*>",           # HTML 标签
        r"^\s*;[^;]{0,5}$",          # 裸分号
        r"^\s*\)\s*$",               # 裸括号
        r"^\s*}\s*\)\s*$",           # 闭包结束
        r"^\s*catch|try\b|finally\b", # JS 关键字
        r"^\s*\.then|\.catch|\.finally",  # Promise 链
        r"^\s*async\s+function",
        r"^\s*useState|useEffect|useCallback|useMemo",
    ]
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        for pattern in noise_patterns:
            if re.search(pattern, stripped, re.IGNORECASE):
                noise_lines += 1
                break

    # 有效中文字数
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    noise_ratio = noise_lines / max(total_lines, 1)

    return {
        "noise_ratio": round(noise_ratio, 2),
        "word_count": chinese_chars,
        "total_lines": total_lines,
        "noise_lines": noise_lines,
    }


# ── API ──

@app.get("/api/sources")
async def list_sources():
    """列出所有可用信源"""
    sources = []
    for key, label in SOURCE_NAMES.items():
        ext = EXTRACTORS.get(key)
        sources.append({
            "key": key,
            "name": label,
            "type": "RSS" if ext else "API"
        })
    return {"sources": sources, "total": len(sources)}


@app.get("/api/fetch")
async def fetch_news(sources: str = Query(None), count: int = Query(15)):
    """
    抓取新闻并评分。

    sources: 逗号分隔的信源 key，如 "36kr,huxiu,qbitai"。不传则全部。
    count: 返回条数
    """
    source_list = None
    if sources:
        source_list = [s.strip() for s in sources.split(",") if s.strip() in SOURCE_NAMES]

    result = await fetch_articles(sources=source_list, count=count)

    return {
        "articles": result["articles"],
        "stats": result["stats"],
        "total": result["total"],
        "deep_count": result["deep_count"],
        "medium_count": result["medium_count"],
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/deep-read")
async def deep_read(url: str = Query(...), source: str = Query("")):
    """深度阅读单篇文章"""
    if not url:
        return JSONResponse({"error": "请提供 URL"}, status_code=400)

    full_text = await fetch_full_article_safe(url, source)

    if not full_text or len(full_text) < 200:
        return {
            "status": "fallback",
            "full_text": None,
            "message": "无法获取全文（反爬或付费墙），请手动阅读原文链接",
            "url": url
        }

    # ── 质量检测：过滤掉抓取失败的噪声（CSS/JS 残片）──
    quality = _check_content_quality(full_text)
    if quality["noise_ratio"] > 0.3 or quality["word_count"] < 50:
        return {
            "status": "low_quality",
            "full_text": None,
            "message": f"提取到的内容质量过低（噪声比 {quality['noise_ratio']:.0%}，有效字数 {quality['word_count']}），可能是页面改版导致正则失效。\n\n请直接点击原文链接阅读。",
            "url": url
        }

    try:
        insight = await interpret_article_async({
            "title": "",
            "content": full_text,
            "source": source,
            "url": url,
        })

        if insight:
            return {
                "status": "success",
                "full_text_length": len(full_text),
                "category": insight.category,
                "quality_score": insight.quality_score,
                "thesis": insight.thesis,
                "frameworks": insight.frameworks,
                "insights": insight.insights,
                "data_points": insight.data_points,
                "takeaways": insight.takeaways,
            }

    except Exception as e:
        print(f"Deep-read error: {e}")

    return {
        "status": "partial",
        "full_text": full_text[:3000],
        "full_text_length": len(full_text),
        "message": "解释器未返回结构化结果，已返回原文前 3000 字"
    }


@app.post("/api/save-obsidian")
async def save_to_obsidian(data: dict):
    """保存到 Obsidian 知识库"""
    content = data.get("content", "")
    filename = data.get("filename", f"daily-report-{datetime.now().strftime('%Y-%m-%d')}.md")

    if not content.strip():
        return JSONResponse({"error": "内容不能为空"}, status_code=400)

    vault_path = Path(r"D:\肠肠的Obsidian\肠肠的obsidian\00-收件箱\AI日报")
    vault_path.mkdir(parents=True, exist_ok=True)

    filepath = vault_path / filename
    try:
        filepath.write_text(content, encoding="utf-8")
        return {
            "status": "success",
            "path": str(filepath),
            "size": len(content)
        }
    except Exception as e:
        fallback = Path(r"C:\Users\22867\.qclaw\workspace\ai-daily-mcp") / filename
        fallback.write_text(content, encoding="utf-8")
        return {
            "status": "fallback",
            "path": str(fallback),
            "size": len(content),
            "error": str(e)
        }


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return html_path.read_text(encoding="utf-8")


if __name__ == "__main__":
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"\n{'='*60}")
    print(f"  🌐 Web Demo 启动成功！")
    print(f"  本机访问:  http://127.0.0.1:8765")
    print(f"  局域网访问: http://{local_ip}:8765")
    print(f"{'='*60}\n")
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")
