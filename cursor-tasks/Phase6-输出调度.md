# Phase 6: 输出层 + 定时调度

给 Cursor Agent 的自然语言说明：

---

这是最后一步。前面五个 Phase 已经把采集、过滤、管线、深度解读全部搭好了，现在把它们串起来——每天自动跑、结果写 Obsidian、提供 API 接口。

## 一、完善 Obsidian 写入

完善 `src/output/obsidian.py`（Phase 5 只写了深度解读的写入，现在补日报写入）。

```python
class ObsidianWriter:
    def __init__(self, root_path: str):
        self.root = root_path
    
    def write_daily_report(self, date_str: str, markdown: str) -> str:
        """写入日报 Markdown"""
        # 文件名: 2026-07-26 AI日报.md
        # 路径: {root}/2026-07-26 AI日报.md
    
    def write_deep_analysis(self, date_str: str, title: str, content: str) -> str:
        """写入深度解读"""
        # 文件名: 深度解读/2026-07-26 {标题}.md（标题截断到 50 字，去特殊字符）
    
    def update_index(self, date_str: str, report_md_path: str, deep_paths: list[str]):
        """更新日报索引文件（根目录下的 README.md 或 INDEX.md）"""
```

日报写入路径：`D:\肠肠的Obsidian\肠肠的obsidian\00-收件箱\AI日报\2026-07-26 AI日报.md`

## 二、FastAPI 接口

新建 `src/output/api.py`。

提供 REST API，对标竞品 AIHOT 的数据接口：

```
GET /api/v1/items?mode=selected&window=24h&limit=20
  → 返回最近精选文章列表

GET /api/v1/items?mode=all&q=OpenAI&window=7d&limit=20
  → 搜索最近 7 天的所有文章

GET /api/v1/dailies/latest
  → 返回最新日报

GET /api/v1/dailies/{date}
  → 返回指定日期的日报

GET /api/v1/sources
  → 信源健康状态（最近 7 天的成功率和响应时间）

GET /api/v1/stats/snr
  → SNR 趋势数据（最近 30 天）

GET /api/v1/health
  → 健康检查
```

实现要点：
- 用 FastAPI + uvicorn
- 从 SQLite 读数据，不依赖 Markdown 文件
- 分页支持（page、limit 参数）
- 日期格式用 ISO 8601（YYYY-MM-DD）
- CORS 开启（允许 localhost 前端调用）
- 启动命令：`uv run uvicorn src.output.api:app --host 0.0.0.0 --port 8000`

响应格式示例：
```json
{
  "items": [
    {
      "id": "abc123",
      "title": "GPT-5 Preview 发布",
      "title_cn": "GPT-5 Preview 发布",
      "url": "https://openai.com/blog/gpt-5-preview",
      "source_name": "OpenAI Blog",
      "summary": "OpenAI 发布 GPT-5 Preview，数学推理能力提升 40%，支持 10 万 token 上下文窗口",
      "published_at": "2026-07-25T10:00:00Z",
      "category": "ai-models",
      "score": 92,
      "merged_count": 5
    }
  ],
  "total": 20,
  "page": 1,
  "page_size": 20
}
```

## 三、MCP 接口

新建 `src/output/mcp_server.py`。

兼容旧版 MCP Tool 接口（让 QClaw 能通过 MCP 协议调用）：

```python
# 四个 Tool：
# 1. list_sources — 列出所有信源及健康状态
# 2. fetch_news — 拉取最新 AI 新闻
# 3. deep_read — 深度解读指定文章
# 4. save_to_obsidian — 保存到 Obsidian
```

用 Python 的 mcp 库实现 stdio 传输。如果不想引入额外依赖，可以先用 FastAPI 的 POST 接口模拟 MCP 协议，后面再切。

## 四、定时调度

新建 `src/scheduler/jobs.py`。

每天 07:00 自动执行的完整流程：

```python
async def daily_job():
    """每日 07:00 执行的完整流程"""
    
    # 1. 采集中 — 并发拉取所有信源
    registry = SourceRegistry("data/sources.yaml")
    results = await registry.fetch_all()
    
    # 2. 双层过滤
    all_articles = flatten(results.values())
    filtered = await filter_pipeline(all_articles)
    
    # 3. 内容管线
    markdown, deep_results = await pipeline(
        filtered["l2_results"],
        report_stats=ReportStats(...)
    )
    
    # 4. 写入 Obsidian
    writer = ObsidianWriter(settings.obsidian_root)
    today = datetime.now().strftime("%Y-%m-%d")
    report_path = writer.write_daily_report(today, markdown)
    deep_paths = [writer.write_deep_analysis(today, r["title"], r["analysis"]) 
                  for r in deep_results]
    writer.update_index(today, report_path, deep_paths)
    
    # 5. 记录统计
    # 存入 daily_reports 表
    
    return {"report": report_path, "deep_count": len(deep_paths)}
```

调度方式：用 Python 的 APScheduler 或者简单用 asyncio.create_task + 循环检查时间。不需要外部 cron——系统自己管理。

```python
# 轻量定时器
import asyncio
from datetime import datetime, timedelta

async def scheduler():
    """每 60 秒检查一次，到 07:00 就执行"""
    while True:
        now = datetime.now()
        if now.hour == 7 and now.minute == 0:
            await daily_job()
            await asyncio.sleep(120)  # 跑完后等 2 分钟，避免 07:01 又触发
        await asyncio.sleep(60)

# 启动
asyncio.create_task(scheduler())
```

另外提供一个手动触发的方式：
```python
# uv run python -m src.scheduler.jobs --now
# → 立即执行一次完整流程（用于测试）
```

## 五、启动脚本

在项目根目录新建 `run.py`：

```python
"""
ai-daily-system 启动入口

用法:
  uv run run.py serve     # 启动 API 服务 + 定时调度
  uv run run.py now        # 立即执行一次完整日报流程
  uv run run.py sources    # 检查信源健康状态
"""
```

`uv run run.py serve` 启动后：
- API 服务跑在 localhost:8000
- 定时调度在后台运行
- 每天 07:00 自动生成日报写入 Obsidian

## 六、端到端测试

在 tests/ 下新建 `test_e2e.py`：

```python
@pytest.mark.asyncio
async def test_full_pipeline():
    """完整端到端流程测试"""
    # 1. 加载信源
    registry = SourceRegistry("data/sources.yaml")
    sources = registry.get_enabled_sources(min_tier=1)  # 只测 Tier 1
    
    # 2. 采集（只拉 3 个）
    results = await registry.fetch_all(sources[:3])
    
    # 3. 过滤
    all_articles = flatten(results.values())
    assert len(all_articles) > 0, "采集失败：没有拉到文章"
    filtered = await filter_pipeline(all_articles)
    
    # 4. 管线
    markdown, deep_results = await pipeline(
        filtered["l2_results"],
        report_stats=ReportStats(...)
    )
    
    # 5. 验证输出
    assert markdown is not None
    assert len(markdown) > 0
    assert "AI 日报" in markdown
    assert "博主选题池" in markdown
    assert "今日碎碎念" in markdown
```

## 完成标准

- `uv run run.py now` 能跑通完整流程：采集 → 过滤 → 管线 → 深度解读 → 写入 Obsidian
- `uv run run.py serve` 启动后，访问 `http://localhost:8000/api/v1/health` 返回 200
- `http://localhost:8000/docs` 能看到 Swagger 文档
- Obsidian 里出现一份完整的 AI 日报 + 2-3 篇深度解读
- `uv run pytest tests/` 全绿（含端到端测试）
