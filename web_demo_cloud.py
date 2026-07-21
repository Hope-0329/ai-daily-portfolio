"""
AI日报 MCP Server — 云部署版 (Render/Railway/Fly.io)
使用环境变量配置 LLM Provider，不依赖本地 QClaw 网关。

环境变量:
  LLM_BASE_URL   - LLM API 地址 (OpenAI 兼容)
  LLM_API_KEY    - API 密钥
  LLM_MODEL      - 模型名 (默认 deepseek-chat)
  PORT           - 服务端口 (默认 8765)
  OBSIDIAN_PATH  - Obsidian 存储路径 (默认本地)

快速部署到 Render:
  1. 上传到 GitHub
  2. Render → New Web Service → 选这个 repo
  3. 设置以上环境变量
  4. Start Command: python web_demo_cloud.py
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ── 添加 knowledge-scout 到路径（优先查找同级目录下的 knowledge-scout）──
SCOUT_ROOT = Path(__file__).resolve().parent / "knowledge-scout"
if SCOUT_ROOT.exists():
    sys.path.insert(0, str(SCOUT_ROOT))
else:
    # 本地: ai-daily-mcp 和 knowledge-scout 是兄弟目录
    SCOUT_ROOT = Path(__file__).resolve().parent.parent / "knowledge-scout"
    if SCOUT_ROOT.exists():
        sys.path.insert(0, str(SCOUT_ROOT))

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import httpx

app = FastAPI(title="AI日报 MCP Server", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── LLM Config (从环境变量读取，兼容多个 Provider) ──
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
PORT = int(os.getenv("PORT", "8765"))

# ── 加载 fetcher 模块 ──
# 云部署时 tools 在 ai-daily-mcp 下，本地时也在同一位置
TOOLS_DIR = Path(__file__).resolve().parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR.parent))

try:
    from tools.fetcher import fetch_articles, fetch_full_article_safe, SOURCE_NAMES
except ImportError as e:
    print(f"WARNING: Cannot import fetcher: {e}, SCOUT_ROOT={SCOUT_ROOT}")
    SOURCE_NAMES = {}
    async def fetch_articles(sources=None, count=15):
        return {"articles": [], "stats": {}, "total": 0, "deep_count": 0, "medium_count": 0}
    async def fetch_full_article_safe(url, source):
        return None


# ── LLM 深度解读 (Markdown 格式) ──

PROMPT_TEMPLATE = """你是一个专业的AI行业分析师。请对以下文章进行深度分析，按照指定格式输出。

## 文章内容

{content}

## 输出格式（严格按以下结构，用中文回答）

【核心论点】
（填写一句话核心论点，20-50字，必须是观点提炼）

【主题分类】
（从以下选择：AI Agent与工程、AI商业与趋势、企业数字化转型、AI创作与内容、知识管理与效率、人形机器人与硬件、跨领域综合）

【关键框架】
（文章中明确提出的方法论/模型/框架名称，每行一个，没有就写 无）

【洞察要点】
- （分析性洞察1，回答"为什么"，不要摘抄原文）
- （分析性洞察2）

【数据看点】
- （关键数据，没有就写 无关键数据）

【行动启发】
- （可执行建议1，回答"怎么做"，与洞察要点完全不同）
- （可执行建议2）

## 规则
- 洞察要点：因果分析、趋势判断、背后逻辑，绝对不能直接摘抄原文
- 行动启发：面向产品经理/AI从业者的可执行建议，与洞察要点内容不能重复
- 每板块2-5条，宁缺毋滥
- 不要编造文章中不存在的信息"""


def _parse_section(text: str, tag: str) -> list[str]:
    pattern = re.escape(tag) + r'\s*\n(.*?)(?=\n\u3010|\Z)'
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return []
    items = []
    for line in match.group(1).strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r'^[-*•]\s*', '', line)
        line = re.sub(r'^\d+[.、]\s*', '', line)
        if line in ('无', '无关键数据', '略', '（无）', '暂无'):
            continue
        if len(line) >= 6:
            items.append(line)
    return items


def _parse_single(text: str, tag: str) -> str:
    items = _parse_section(text, tag)
    return items[0] if items else ""


async def llm_deep_read(content: str, source: str = "", url: str = "") -> dict:
    """使用 LLM 深度解读文章"""
    if len(content) < 100:
        return None

    max_chars = 8000
    text = content[:max_chars]
    if len(content) > max_chars:
        text += f"\n\n[原文共 {len(content)} 字，此处截取前 {max_chars} 字]"

    prompt = PROMPT_TEMPLATE.format(content=text)

    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            resp = await client.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": "你是一个专业的AI行业分析师。严格按照指定格式输出分析结果。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
            )
            if resp.status_code != 200:
                print(f"LLM API error: {resp.status_code} {resp.text[:200]}")
                return None

            data = resp.json()
            raw = data["choices"][0]["message"]["content"]

            return {
                "thesis": _parse_single(raw, "【核心论点】"),
                "category": _parse_single(raw, "【主题分类】"),
                "frameworks": _parse_section(raw, "【关键框架】"),
                "insights": _parse_section(raw, "【洞察要点】"),
                "data_points": _parse_section(raw, "【数据看点】"),
                "takeaways": _parse_section(raw, "【行动启发】"),
            }
    except Exception as e:
        print(f"LLM call failed: {e}")
        return None


# ── 内容质量检测 ──

def _check_content_quality(text: str) -> dict:
    if not text:
        return {"noise_ratio": 1.0, "word_count": 0}
    lines = text.split("\n")
    noise_lines = 0
    noise_patterns = [
        r"^\s*[.#@]\w+\s*\{", r"^\s*(function|const|let|var|import|export)\s",
        r"^\s*(window|document|console)\.", r"^\s*\{\s*$", r"^\s*\}\s*$",
        r"^\s*\/\/", r"^\s*\/\*|\*\/", r"^\s*@media|@import|@keyframes",
        r"^\s*<\w+[^>]*>", r"^\s*;[^;]{0,5}$", r"^\s*\)\s*$",
        r"^\s*catch|try\b|finally\b", r"^\s*\.then|\.catch|\.finally",
        r"^\s*async\s+function", r"^\s*useState|useEffect|useCallback|useMemo",
    ]
    for line in lines:
        if not line.strip():
            continue
        for p in noise_patterns:
            if re.search(p, line.strip(), re.IGNORECASE):
                noise_lines += 1
                break
    return {
        "noise_ratio": round(noise_lines / max(len(lines), 1), 2),
        "word_count": len(re.findall(r"[\u4e00-\u9fff]", text)),
    }


# ── API ──

@app.get("/api/sources")
async def list_sources():
    sources = []
    for key, label in SOURCE_NAMES.items():
        sources.append({"key": key, "name": label, "type": "RSS"})
    return {"sources": sources, "total": len(sources)}


@app.get("/api/fetch")
async def fetch_news(sources: str = Query(None), count: int = Query(15)):
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
    """深度阅读单篇文章（LLM 驱动）"""
    if not url:
        return JSONResponse({"error": "请提供 URL"}, status_code=400)

    if not LLM_API_KEY:
        return {
            "status": "no_api_key",
            "message": "LLM API Key 未配置。管理员需设置 LLM_API_KEY 环境变量。",
            "url": url
        }

    full_text = await fetch_full_article_safe(url, source)
    if not full_text or len(full_text) < 200:
        return {
            "status": "fallback",
            "message": "无法获取全文（反爬或付费墙），请手动阅读原文",
            "url": url
        }

    quality = _check_content_quality(full_text)
    if quality["noise_ratio"] > 0.3 or quality["word_count"] < 50:
        return {
            "status": "low_quality",
            "message": f"内容质量过低（噪声比 {quality['noise_ratio']:.0%}），请点击原文阅读",
            "url": url
        }

    result = await llm_deep_read(full_text, source, url)
    if not result:
        return {"status": "partial", "full_text": full_text[:3000], "message": "LLM 解读失败，返回原文"}

    return {
        "status": "success",
        "full_text_length": len(full_text),
        **result
    }


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "llm_configured": bool(LLM_API_KEY),
        "model": LLM_MODEL,
        "sources": len(SOURCE_NAMES),
        "timestamp": datetime.now().isoformat()
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
    print(f"  AI日报 MCP Server v3.0 (云部署版)")
    print(f"  LLM: {LLM_MODEL} @ {LLM_BASE_URL}")
    print(f"  Key configured: {bool(LLM_API_KEY)}")
    print(f"  Sources: {len(SOURCE_NAMES)}")
    print(f"  访问: http://{local_ip}:{PORT}")
    print(f"{'='*60}\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
