# Phase 12: Render 云部署 — 公网可访问的 Dashboard

给 Cursor Agent 的自然语言说明：

---

目标：部署到 Render，任何人通过 URL 就能打开日报 Dashboard，不依赖电脑开机。

## 关键设计决策

**云上 ≠ 本地。** 以下内容在云上不适用，需要适配：

| 本地 | 云上 |
|------|------|
| 写入 Obsidian（D 盘路径） | ❌ 不存在 → 日报数据存 SQLite，Dashboard 是唯一交付渠道 |
| `run.py now` 手动触发 | ✅ 用 Render Cron 自动跑 |
| `run.py serve` 本地 8000 端口 | ✅ Render Web Service 自动分配域名 |

## 一、新增部署文件

### 1. `Dockerfile`（项目根目录）

用 uv + Python 3.11 构建镜像，入口启动 `serve` 模式：

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
EXPOSE 8000

CMD ["uv", "run", "run.py", "serve"]
```

### 2. `render.yaml`（项目根目录）

```yaml
services:
  - type: web
    name: ai-daily-dashboard
    runtime: docker
    plan: free
    healthCheckPath: /dashboard
    envVars:
      - key: DEEPSEEK_API_KEY
        sync: false
      - key: DEEPSEEK_BASE_URL
        value: https://api.deepseek.com
      - key: DEEPSEEK_MODEL
        value: deepseek-v4-flash
      - key: OBSIDIAN_ENABLED
        value: "false"
      - key: AI_DAILY_DB
        value: /app/data/ai_daily.db
    disk:
      name: sqlite-data
      mountPath: /app/data
      sizeGB: 1

  - type: cron
    name: daily-report
    runtime: docker
    schedule: "0 23 * * *"
    plan: free
    dockerCommand: uv run run.py now
    envVars:
      - key: DEEPSEEK_API_KEY
        sync: false
      - key: DEEPSEEK_BASE_URL
        value: https://api.deepseek.com
      - key: DEEPSEEK_MODEL
        value: deepseek-v4-flash
      - key: OBSIDIAN_ENABLED
        value: "false"
      - key: AI_DAILY_DB
        value: /app/data/ai_daily.db
    disk:
      name: sqlite-data
      mountPath: /app/data
      sizeGB: 1
```

注意：cron `schedule` 用 UTC。用户要求北京时间 07:00，所以 UTC = **23:00（前一天）**。

### 3. `.dockerignore`（项目根目录）

```
.venv/
.pytest_cache/
__pycache__/
*.pyc
.git/
.env
cursor-tasks/
tests/
```

## 二、代码适配

### 2.1 Obsidian 输出改为可选

修 `src/output/obsidian.py`：加了 `OBSIDIAN_ENABLED=false` 环境变量时跳过写入，只 log 一条 "[obsidian] 已禁用（云环境）"。

### 2.2 数据库路径兼容

`src/database.py` 里数据库路径已经在通过环境变量 `AI_DAILY_DB` 读取了。如果没设，默认到项目目录内的 `data/ai_daily.db`，而不是本地 D 盘。

确认 `src/config.py` 加了这行：

```python
AI_DAILY_DB: str = str(Path(__file__).parent.parent / "data" / "ai_daily.db")
```

### 2.3 Dashboard 页面加分享元信息

`web/templates/dashboard.html` 的 `<head>` 加入：

```html
<!-- 微信/社交分享 -->
<meta property="og:title" content="AI 知识侦察兵 · 日报" />
<meta property="og:description" content="AI 领域每日精选，过滤噪音，只留精华" />
<meta name="twitter:card" content="summary_large_image" />
```

### 2.4 FastAPI 根路径重定向

`src/output/api.py` 加一个根路由重定向到 `/dashboard`：

```python
@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard")
```

## 三、部署步骤（你在 Render 网站上操作）

1. 把项目 push 到 GitHub（`Hope-0329/ai-daily-portfolio` 或新建仓库）
2. 登录 [render.com](https://render.com)，点 "New Web Service"
3. 连接 GitHub 仓库，Render 自动识别 `render.yaml`
4. 在 Render Dashboard 设置环境变量 `DEEPSEEK_API_KEY` = `sk-你的key`
5. 部署完成后，拿到域名（如 `ai-daily-dashboard.onrender.com`）
6. 浏览器打开 `https://你的域名.onrender.com/dashboard`

**首次部署后**：
- Web 页面立即可访问（数据为空→先等 cron 跑一次）
- 也可以手动触发 cron（Render Dashboard 里点 "Trigger Run"）

---

## 完成标准

- `Dockerfile`、`render.yaml`、`.dockerignore` 已创建
- `OBSIDIAN_ENABLED=false` 时跳过 Obsidian 写入
- `localhost:8000/` 自动跳转到 `/dashboard`
- Dashboard HTML 加了 OG meta 标签
- `uv run pytest tests/` 全绿
- 所有改动提交到 GitHub
