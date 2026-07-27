# B 线 Phase 11: 信源扩容 + Web Dashboard

给 Cursor Agent 的自然语言说明：

---

A 线（日报管线）已稳定。现在 B 线两件事：用 RSSHub 镜像救回 6 个死源，以及搭建 Web Dashboard 前端。

## 一、RSSHub 救回 6 个死源

当前 6 个彻底死的源（服务端不提供 RSS），用 RSSHub 镜像：`https://rsshub.app/`

### 救回映射

| 死源 | 原因 | RSSHub 路由 | 采集方式 |
|------|------|------------|---------|
| jiqizhixin | SPA，无 RSS | `/jiqizhixin` (如果 RSSHub 有) | RSS |
| huxiu-ai | 504 网关超时 | `/huxiu/tag/人工智能` | RSS |
| tencent-ai-lab | HTML，无 RSS | `/tencent/ai-lab` (如果有) | RSS |
| cohere | Sanity SPA | `/cohere/blog` (如果有) | RSS |
| analytics-india | WAF 拦截 | 跳过，不重要 | — |
| microsoft-ai | Cloudflare 403 | `/microsoft/ai` (如果有) | RSS |
| ai-news | Cloudflare 403 | 跳过，不重要 | — |

### 实现方式

在 `data/sources.yaml` 里把上述源：
1. URL 改为对应的 RSSHub 地址（`https://rsshub.app/xxx`）
2. `source_type` 保持 `rss`
3. 先手动在浏览器验证路由是否可用：浏览器打开 `https://rsshub.app/huxiu/tag/人工智能`，看到 XML 就是通的
4. 不确认的不添加——宁可少源，不造假

### 如果 RSSHub 某些路由不可用

- **机器之心**：他们的官网可能已经没 RSS 了。替代方案——用他们的微信公众号 RSSHub 镜像（`/wechat/mp/profile/xxx`），或者直接禁用，后面用 Playwright 采集。
- **虎嗅 AI**：大概率 `/huxiu/tag/人工智能` 可用。如果也不通，试试 `/huxiu/article`。
- 不可用的直接跳过，不纠结。

## 二、小瑕疵顺手修

| 问题 | 位置 | 修法 |
|------|------|------|
| TOP 2 标题截断为一个词 | `daily_report.py` 的 TOP 3 表格生成 | 检查 truncate 逻辑，标题至少保留 30 字 |
| 去重漏了同篇文章的两个翻译版本 | `filter/dedup.py` | 去重前统一 lower + 去掉 ` [原文：...]` 标记再比较 |
| 产品板块只有 2 篇 | 非代码问题，周日后会恢复 | 不修 |

## 三、Web Dashboard（MVP）

新建 `web/` 目录，一个单页 HTML + 内嵌 CSS/JS，从 FastAPI 读数据。

### 页面结构

```
┌──────────────────────────────────────┐
│  🔭 AI 知识侦察兵                      │
│  2026-07-26 日报                      │
├──────────────────────────────────────┤
│  📊 今日概览                           │
│  33/40 信源 | 1806 篇采集 | 25 篇精选   │
│  过滤效率 1.4% | 优质率 56%            │
├──────────────────────────────────────┤
│  📌 TOP 3                             │
│  1. Anthropic 投资 1亿...             │
│  2. Anthropic Opus 5 超越...          │
│  3. 三星 × OpenAI 合作...             │
├──────────┬───────────────────────────┤
│ 🤖 模型   │ 14 篇                    │
│ 📦 产品   │ 2 篇                     │
│ 📊 行业   │ 3 篇                     │
│ 📝 论文   │ 5 篇                     │
│ 💡 技巧   │ 1 篇                     │
├──────────┴───────────────────────────┤
│  🤖 模型发布/更新                      │
│  ┌─────────────────────────────────┐ │
│  │ Anthropic 投资 1亿美元...  95分  │ │
│  │ Anthropic 砸1亿美元扶持Claude... │ │
│  └─────────────────────────────────┘ │
│  ...                                  │
└──────────────────────────────────────┘
```

### 实现方式

**最简单方案：FastAPI 模板渲染**

在 `src/output/api.py` 里加一个 `/dashboard` 路由，返回 Jinja2 渲染的 HTML。不用 React、不用构建工具、不用 npm——单文件 HTML + 内嵌 CSS。

```python
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="web/templates")

@app.get("/dashboard")
async def dashboard(request: Request):
    # 从 SQLite 读最新日报数据
    items = await get_latest_items(limit=25)
    stats = await get_latest_stats()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "items": items,
        "stats": stats,
    })
```

CSS 风格参考：简洁、深色背景 + 蓝色强调，类似 AIHOT 但不要完全照抄。

### 数据接口（已有，直接用）

```
GET /api/v1/items?mode=selected&limit=25
GET /api/v1/dailies/latest
GET /api/v1/sources
GET /api/v1/stats/snr
```

## 完成标准

- RSSHub 镜像至少救回 2-3 个源（虎嗅优先，机器之心次之）
- Web Dashboard 在 `http://localhost:8000/dashboard` 可访问
- Dashboard 展示当日 TOP 3 + 5 板块文章 + 系统概览
- 样式简洁，适配桌面和手机
- 小瑕疵（标题截断、去重）顺手修掉
- `uv run pytest tests/` 全绿
