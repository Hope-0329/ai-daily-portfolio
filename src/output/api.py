"""REST API 服务。"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from src.config import get_settings
from src.database import (
    get_connection,
    get_daily_report,
    get_latest_daily_report_row,
    get_snr_trend,
    get_sources_health_summary,
    init_db,
    query_articles,
)
from src.output.dashboard import TEMPLATES_DIR, load_dashboard_context
from src.output.mcp_server import (
    deep_read_tool,
    fetch_news_tool,
    list_sources_tool,
    save_to_obsidian_tool,
    trigger_fetch_tool,
)

app = FastAPI(title="AI Daily System API", version="1.0.0")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MCPRequest(BaseModel):
    """MCP 工具调用请求体。"""

    arguments: dict[str, Any] = Field(default_factory=dict)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def root() -> RedirectResponse:
    """根路径重定向到 Dashboard。"""
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard")
def dashboard(request: Request) -> Any:
    """Web Dashboard：展示最新日报精选与概览。"""
    settings = get_settings()
    context = load_dashboard_context(settings)
    context["request"] = request
    return templates.TemplateResponse(request, "dashboard.html", context)


@app.get("/api/v1/health")
def health_check() -> dict[str, str]:
    """健康检查。"""
    return {"status": "ok"}


@app.get("/api/v1/items")
def list_items(
    mode: str = Query(default="selected", pattern="^(all|selected)$"),
    window: str = Query(default="24h"),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """查询文章列表。"""
    settings = get_settings()
    with get_connection(settings) as conn:
        items, total = query_articles(
            conn,
            mode=mode,
            window=window,
            q=q,
            page=page,
            page_size=limit,
        )
    return {"items": items, "total": total, "page": page, "page_size": limit}


@app.get("/api/v1/dailies/latest")
def latest_daily() -> dict[str, Any]:
    """获取最新日报。"""
    settings = get_settings()
    with get_connection(settings) as conn:
        row = get_latest_daily_report_row(conn)
    if row is None:
        raise HTTPException(status_code=404, detail="暂无日报")
    return row


@app.get("/api/v1/dailies/{report_date}")
def daily_by_date(report_date: date) -> dict[str, Any]:
    """获取指定日期日报。"""
    settings = get_settings()
    with get_connection(settings) as conn:
        row = get_daily_report(conn, report_date)
    if row is None:
        raise HTTPException(status_code=404, detail=f"未找到日报: {report_date.isoformat()}")
    return row


@app.get("/api/v1/sources")
def sources_health(days: int = Query(default=7, ge=1, le=30)) -> dict[str, Any]:
    """信源健康状态。"""
    settings = get_settings()
    with get_connection(settings) as conn:
        sources = get_sources_health_summary(conn, days=days)
    return {"sources": sources, "days": days}


@app.get("/api/v1/stats/snr")
def snr_stats(days: int = Query(default=30, ge=1, le=90)) -> dict[str, Any]:
    """SNR 趋势数据。"""
    settings = get_settings()
    with get_connection(settings) as conn:
        trend = get_snr_trend(conn, days=days)
    return {"trend": trend, "days": days}


@app.post("/api/v1/mcp/list_sources")
async def mcp_list_sources() -> dict[str, Any]:
    return await list_sources_tool()


@app.post("/api/v1/mcp/fetch_news")
async def mcp_fetch_news(body: MCPRequest) -> dict[str, Any]:
    return await fetch_news_tool(limit=int(body.arguments.get("limit", 20)))


@app.post("/api/v1/mcp/deep_read")
async def mcp_deep_read(body: MCPRequest) -> dict[str, Any]:
    article_id = str(body.arguments.get("article_id", ""))
    if not article_id:
        raise HTTPException(status_code=400, detail="缺少 article_id")
    return await deep_read_tool(article_id)


@app.post("/api/v1/mcp/save_to_obsidian")
async def mcp_save_to_obsidian(body: MCPRequest) -> dict[str, Any]:
    date_str = str(body.arguments.get("date", ""))
    markdown = str(body.arguments.get("markdown", ""))
    title = body.arguments.get("title")
    if not date_str or not markdown:
        raise HTTPException(status_code=400, detail="缺少 date 或 markdown")
    return await save_to_obsidian_tool(date_str, markdown, title=title)


@app.post("/api/v1/mcp/trigger_fetch")
async def mcp_trigger_fetch(body: MCPRequest) -> dict[str, Any]:
    return await trigger_fetch_tool(
        tier=int(body.arguments.get("tier", 3)),
        limit_sources=body.arguments.get("limit_sources"),
    )
