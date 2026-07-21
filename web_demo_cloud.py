"""
AI鏃ユ姤 MCP Server 鈥?浜戦儴缃茬増 v3.1 (Render/Railway)
绋冲仴鍚姩锛氭墍鏈夐噸鍨嬫ā鍧楀欢杩熷姞杞斤紝鍚姩鏃跺彧鍋氭渶灏忓鍏ャ€?
鐜鍙橀噺:
  LLM_BASE_URL   - LLM API 鍦板潃 (榛樿 DeepSeek)
  LLM_API_KEY    - API 瀵嗛挜 (蹇呭～)
  LLM_MODEL      - 妯″瀷鍚?(榛樿 deepseek-chat)
  PORT           - 鏈嶅姟绔彛 (榛樿 8765锛孯ender 鑷姩娉ㄥ叆)
"""

import os
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

# 鈹€鈹€ 鍚姩璇婃柇 鈹€鈹€
print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}")
print(f"Workdir: {os.getcwd()}")
print(f"Files in workdir: {os.listdir('.')[:20]}")

# 鈹€鈹€ 閰嶇疆鐭ヨ瘑鎺㈤拡璺緞 鈹€鈹€
SCOUT_ROOT = Path(__file__).resolve().parent / "knowledge-scout"
if SCOUT_ROOT.exists():
    sys.path.insert(0, str(SCOUT_ROOT))
    print(f"SCOUT_ROOT found: {SCOUT_ROOT}")
else:
    SCOUT_ROOT = Path(__file__).resolve().parent.parent / "knowledge-scout"
    if SCOUT_ROOT.exists():
        sys.path.insert(0, str(SCOUT_ROOT))
        print(f"SCOUT_ROOT found (parent): {SCOUT_ROOT}")
    else:
        print(f"WARNING: knowledge-scout not found at {SCOUT_ROOT}")

TOOLS_DIR = Path(__file__).resolve().parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR.parent))

# 鈹€鈹€ 鏈€灏忓鍏ワ紙FastAPI + uvicorn锛岀‘淇濇湇鍔″櫒鑷冲皯鑳藉惎鍔級 鈹€鈹€
try:
    from fastapi import FastAPI, Query
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
    import httpx
    print("Core imports OK (fastapi, uvicorn, httpx)")
except ImportError as e:
    print(f"FATAL: Core import failed: {e}")
    print(traceback.format_exc())
    sys.exit(1)

app = FastAPI(title="AI鏃ユ姤 MCP Server", version="3.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 鈹€鈹€ 閰嶇疆 鈹€鈹€
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
PORT = int(os.getenv("PORT", "8765"))

# 鈹€鈹€ 寤惰繜鍔犺浇 fetcher锛堥伩鍏嶅惎鍔ㄦ椂 import 閾惧穿婧冿級鈹€鈹€
_fetcher_loaded = False
SOURCE_NAMES: dict = {}
_fetch_articles_fn = None
_fetch_full_fn = None

def _ensure_fetcher():
    """寤惰繜鍔犺浇锛岄娆?API 璋冪敤鏃舵墠 import"""
    global _fetcher_loaded, SOURCE_NAMES, _fetch_articles_fn, _fetch_full_fn
    if _fetcher_loaded:
        return True
    try:
        from tools.fetcher import fetch_articles as fa, fetch_full_article_safe as ff, SOURCE_NAMES as sn
        _fetch_articles_fn = fa
        _fetch_full_fn = ff
        SOURCE_NAMES = sn
        _fetcher_loaded = True
        print(f"Fetcher OK: {len(SOURCE_NAMES)} sources loaded")
        return True
    except Exception as e:
        print(f"Fetcher load failed: {e}")
        print(traceback.format_exc())
        return False

async def fetch_articles(sources=None, count=15):
    if _ensure_fetcher():
        return await _fetch_articles_fn(sources=sources, count=count)
    return {"articles": [], "stats": {}, "total": 0, "deep_count": 0, "medium_count": 0}

async def fetch_full_article_safe(url, source):
    if _ensure_fetcher():
        return await _fetch_full_fn(url, source)
    return None

# 鈹€鈹€ LLM 娣卞害瑙ｈ 鈹€鈹€

PROMPT_TEMPLATE = """浣犳槸涓€涓笓涓氱殑AI琛屼笟鍒嗘瀽甯堛€傝瀵逛互涓嬫枃绔犺繘琛屾繁搴﹀垎鏋愶紝鎸夌収鎸囧畾鏍煎紡杈撳嚭銆?
## 鏂囩珷鍐呭

{content}

## 杈撳嚭鏍煎紡锛堜弗鏍兼寜浠ヤ笅缁撴瀯锛岀敤涓枃鍥炵瓟锛?
銆愭牳蹇冭鐐广€?锛堝～鍐欎竴鍙ヨ瘽鏍稿績璁虹偣锛?0-50瀛楋紝蹇呴』鏄鐐规彁鐐硷級

銆愪富棰樺垎绫汇€?锛堜粠浠ヤ笅閫夋嫨锛欰I Agent涓庡伐绋嬨€丄I鍟嗕笟涓庤秼鍔裤€佷紒涓氭暟瀛楀寲杞瀷銆丄I鍒涗綔涓庡唴瀹广€佺煡璇嗙鐞嗕笌鏁堢巼銆佷汉褰㈡満鍣ㄤ汉涓庣‖浠躲€佽法棰嗗煙缁煎悎锛?
銆愬叧閿鏋躲€?锛堟枃绔犱腑鏄庣‘鎻愬嚭鐨勬柟娉曡/妯″瀷/妗嗘灦鍚嶇О锛屾瘡琛屼竴涓紝娌℃湁灏卞啓 鏃狅級

銆愭礊瀵熻鐐广€?- 锛堝垎鏋愭€ф礊瀵?锛屽洖绛?涓轰粈涔?锛屼笉瑕佹憳鎶勫師鏂囷級
- 锛堝垎鏋愭€ф礊瀵?锛?
銆愭暟鎹湅鐐广€?- 锛堝叧閿暟鎹紝娌℃湁灏卞啓 鏃犲叧閿暟鎹級

銆愯鍔ㄥ惎鍙戙€?- 锛堝彲鎵ц寤鸿1锛屽洖绛?鎬庝箞鍋?锛屼笌娲炲療瑕佺偣瀹屽叏涓嶅悓锛?- 锛堝彲鎵ц寤鸿2锛?
## 瑙勫垯
- 娲炲療瑕佺偣锛氬洜鏋滃垎鏋愩€佽秼鍔垮垽鏂€佽儗鍚庨€昏緫锛岀粷瀵逛笉鑳界洿鎺ユ憳鎶勫師鏂?- 琛屽姩鍚彂锛氶潰鍚戜骇鍝佺粡鐞?AI浠庝笟鑰呯殑鍙墽琛屽缓璁紝涓庢礊瀵熻鐐瑰唴瀹逛笉鑳介噸澶?- 姣忔澘鍧?-5鏉★紝瀹佺己姣嬫互
- 涓嶈缂栭€犳枃绔犱腑涓嶅瓨鍦ㄧ殑淇℃伅"""

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
        line = re.sub(r'^[-*鈥\s*', '', line)
        line = re.sub(r'^\d+[.銆乚\s*', '', line)
        if line in ('鏃?, '鏃犲叧閿暟鎹?, '鐣?, '锛堟棤锛?, '鏆傛棤'):
            continue
        if len(line) >= 6:
            items.append(line)
    return items

def _parse_single(text: str, tag: str) -> str:
    items = _parse_section(text, tag)
    return items[0] if items else ""

async def llm_deep_read(content: str, source: str = "", url: str = "") -> dict:
    if len(content) < 100:
        return None
    max_chars = 8000
    text = content[:max_chars]
    if len(content) > max_chars:
        text += f"\n\n[鍘熸枃鍏?{len(content)} 瀛楋紝姝ゅ鎴彇鍓?{max_chars} 瀛梋"
    prompt = PROMPT_TEMPLATE.format(content=text)
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            resp = await client.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": "浣犳槸涓€涓笓涓氱殑AI琛屼笟鍒嗘瀽甯堛€備弗鏍兼寜鐓ф寚瀹氭牸寮忚緭鍑哄垎鏋愮粨鏋溿€?},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3, "max_tokens": 2000,
                },
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            return {
                "thesis": _parse_single(raw, "銆愭牳蹇冭鐐广€?),
                "category": _parse_single(raw, "銆愪富棰樺垎绫汇€?),
                "frameworks": _parse_section(raw, "銆愬叧閿鏋躲€?),
                "insights": _parse_section(raw, "銆愭礊瀵熻鐐广€?),
                "data_points": _parse_section(raw, "銆愭暟鎹湅鐐广€?),
                "takeaways": _parse_section(raw, "銆愯鍔ㄥ惎鍙戙€?),
            }
    except Exception as e:
        print(f"LLM call failed: {e}")
        return None

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
    return {"noise_ratio": round(noise_lines / max(len(lines), 1), 2),
            "word_count": len(re.findall(r"[\u4e00-\u9fff]", text))}


# 鈹€鈹€ API 璺敱 鈹€鈹€

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "llm_configured": bool(LLM_API_KEY),
        "model": LLM_MODEL,
        "fetcher_loaded": _fetcher_loaded,
        "sources": len(SOURCE_NAMES),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/diag")
async def diag():
    """鍚姩璇婃柇锛氭鏌ユ墍鏈変緷璧栨槸鍚﹀彲鐢?""
    result = {"python": sys.version, "packages": {}}
    for pkg in ["fastapi", "uvicorn", "httpx", "aiohttp", "trafilatura", "feedparser", "lxml"]:
        try:
            __import__(pkg)
            result["packages"][pkg] = "OK"
        except ImportError:
            result["packages"][pkg] = "MISSING"
    result["fetcher_ok"] = _ensure_fetcher()
    result["sources"] = len(SOURCE_NAMES) if _fetcher_loaded else 0
    return result

@app.get("/api/sources")
async def list_sources():
    _ensure_fetcher()
    return {"sources": [{"key": k, "name": v} for k, v in SOURCE_NAMES.items()],
            "total": len(SOURCE_NAMES)}

@app.get("/api/fetch")
async def fetch_news(sources: str = Query(None), count: int = Query(15)):
    source_list = None
    if sources:
        source_list = [s.strip() for s in sources.split(",") if s.strip() in SOURCE_NAMES]
    result = await fetch_articles(sources=source_list, count=count)
    return {"articles": result["articles"], "stats": result["stats"],
            "total": result["total"], "deep_count": result["deep_count"],
            "medium_count": result["medium_count"], "timestamp": datetime.now().isoformat()}

@app.get("/api/deep-read")
async def deep_read(url: str = Query(...), source: str = Query("")):
    if not url:
        return JSONResponse({"error": "璇锋彁渚?URL"}, status_code=400)
    if not LLM_API_KEY:
        return {"status": "no_api_key", "message": "LLM API Key 鏈厤缃?, "url": url}
    full_text = await fetch_full_article_safe(url, source)
    if not full_text or len(full_text) < 200:
        return {"status": "fallback", "message": "鏃犳硶鑾峰彇鍏ㄦ枃锛堝弽鐖垨浠樿垂澧欙級", "url": url}
    quality = _check_content_quality(full_text)
    if quality["noise_ratio"] > 0.3 or quality["word_count"] < 50:
        return {"status": "low_quality",
                "message": f"鍐呭璐ㄩ噺杩囦綆锛堝櫔澹版瘮 {quality['noise_ratio']:.0%}锛?, "url": url}
    result = await llm_deep_read(full_text, source, url)
    if not result:
        return {"status": "partial", "full_text": full_text[:3000], "message": "LLM 瑙ｈ澶辫触"}
    return {"status": "success", "full_text_length": len(full_text), **result}

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return html_path.read_text(encoding="utf-8")

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  AI鏃ユ姤 MCP Server v3.1 (浜戦儴缃茬増)")
    print(f"  LLM: {LLM_MODEL} @ {LLM_BASE_URL}")
    print(f"  Key configured: {bool(LLM_API_KEY)}")
    print(f"{'='*60}\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
