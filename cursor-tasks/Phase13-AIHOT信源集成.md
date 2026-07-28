# Phase 13: 集成 AIHOT 公开 API 作为信源

给 Cursor Agent 的自然语言说明：

---

## 背景

AIHOT（https://aihot.virxact.com）是「数字生命卡兹克」做的 AI 热点聚合站，168 个信源，API 公开匿名免 Key。每篇文章已带 AI 摘要（30-60 字）、分类（5 板块）、评分（0-100）。接入 AIHOT 后，我们相当于立刻多了 168 个信源——同时保留自有的 38 个信源做差异化。

## API 参考

```
# 核心接口：最近 24h 精选（约 30-50 篇）
GET https://aihot.virxact.com/api/v1/items?mode=selected&window=24h

# 按分类
GET /api/v1/items?mode=selected&category=model&window=24h

# 需要设置 User-Agent
User-Agent: aihot-skill/1.2.0 (+https://aihot.virxact.com/aihot-skill/)
```

返回字段（每篇文章）：
- `title` — 标题
- `summary` — AI 生成的中文摘要（可直接用）
- `category` — model / product / industry / paper / tips
- `score` — 0-100 分
- `source.name` — 原始信源名
- `links.aihot` — AIHOT 站内链接
- `links.original` — 原始文章链接
- `publishedAt` — 原文发布时间
- `discoveredAt` — AIHOT 收录时间

## 设计决策

1. **标记驱动**：给 Article 模型加 `pre_summarized` 和 `pre_classified` 布尔字段，AIHOT 文章设 True，pipeline 据此跳过翻译/分类
2. **去重保留自采**：AIHOT 的 `links.original` 与自采库 URL 对比，匹配到的保留自采版本（自采有完整正文，AIHOT 只有摘要）
3. **降级模式**：AIHOT API 不可用时不影响其他 38 个源

---

## Step 0：清理 sources.yaml

删掉以下一直禁用的源（14 个）：

```
machine-heart, tencent-ai-lab, microsoft-ai, ai-news, analytics-india,
jiqizhixin（禁用）, huxiu-ai（禁用，已由 RSSHub 虎嗅替代）,
以及 data/sources.yaml 中所有 enable=false 且 disable_reason 为永久不可用的条目
```

只保留 38 个已启用的源。改完后检查 `uv run python -c "from src.sources.registry import load_sources; print(len(load_sources()))"` 应该输出 38。

---

## Step 1：新增 AIHOT 源配置

在 `data/sources.yaml` 最前面新增：

```yaml
- id: aihot
  name: AIHOT
  name_en: AIHOT
  type: api
  enable: true
  base_url: https://aihot.virxact.com/api/v1
  endpoint: /items?mode=selected&window=24h
  category_weights:
    model: 0.80
    product: 0.80
    industry: 0.80
    paper: 0.80
    tips: 0.80
  headers:
    User-Agent: "aihot-skill/1.2.0 (+https://aihot.virxact.com/aihot-skill/)"
```

## Step 2：实现 AIHOT 采集器

新建 `src/sources/aihot.py`：

**不需要从头写**。参考现有的 `src/sources/api.py` 的结构。AIHOT 采集器是 api 类型的特殊实现：

放的关键逻辑：
1. `async def fetch(self) -> list[Article]`：调 `GET {base_url}{endpoint}`，带 headers
2. 响应 JSON 是 `{items: [...], cursor: ...}`，遍历 items 构建 Article
3. 字段映射：

| AIHOT 字段 | Article 字段 |
|-----------|-------------|
| title | title |
| summary | summary |
| links.original | url |
| category | category（映射：model→模型, product→产品, industry→行业, paper→论文, tips→技巧）|
| score | score（除以 10 转 0-10 分制）|
| source.name | source_name |
| publishedAt 或 discoveredAt | published_at |

4. **关键**：设置 `pre_summarized=True`、`pre_classified=True`
5. 设置 `source_id="aihot"`、`source_type="aihot"`

**注意**：AIHOT 文章没有 body，`content` 字段设为 summary。

## Step 3：Article 模型加标记字段

在 `src/models.py` 的 Article dataclass/dict 里加两个可选字段：

```python
pre_summarized: bool = False    # AIHOT 等预摘要源的文章为 True
pre_classified: bool = False    # 同上
```

## Step 4：Pipeline 跳过逻辑

改 `src/pipeline/translator.py`：
- 检查 `article.get("pre_summarized")` 为 True → 跳过翻译，直接透传

改 `src/pipeline/classifier.py`：
- 检查 `article.get("pre_classified")` 为 True → 跳过分类，直接用 article 里的 category 字段

改 `src/pipeline/daily_report.py`（日报组装处）：
- AIHOT 文章展示时，摘要直接用 summary（无需 LLM 再生成一次）
- 文章来源显示为「AIHOT · {信源名}」格式

## Step 5：去重

改 `src/filter/dedup.py`：

AIHOT 文章和自采文章可能描述同一篇原文。去重逻辑：
1. 对 AIHOT 文章，用 `links.original` 作为去重键
2. 对自采文章，用 `url` 作为去重键
3. URL 标准化（去 www、去末尾 /、统一 https）
4. 匹配到时，优先保留自采版本（自采有 body）
5. 去重发生在 L1 过滤之前

## Step 6：注册采集器

在 `src/sources/registry.py` 里注册 aiht 采集器。参考现有的 api 类型采集器注册方式。

## Step 7：测试

在 `tests/` 目录下新增：

1. **`test_aihot_collector.py`** — 采集器单元测试
   - mock aiohttp 返回示例 JSON
   - 验证字段映射正确（title、summary、category、score 转换）
   - 验证 pre_summarized/pre_classified 标记

2. **`test_aihot_dedup.py`** — 去重测试
   - AIHOT 文章 url 与自采文章 url 匹配 → 自采保留
   - 不同 url → 两者保留

3. **`test_aihot_pipeline.py`** — pipeline 集成测试
   - 标记为 pre_summarized → translator 跳过
   - 标记为 pre_classified → classifier 跳过

## Step 8：端到端验证

```bash
uv run run.py now
```

预期：
- AIHOT 采集成功，返回 30-50 篇文章
- 与自采文章正常去重
- 日报中 AIHOT 文章展示为「AIHOT · xxx」来源
- `uv run pytest tests/` 全绿

---

## 关键提醒

- **AIHOT API 是第三方的，无 SLA**。可能偶尔 503 或限流。采集失败时只打 warning log，不阻塞流程
- **不要频繁轮询**。API 文档要求至少间隔 60 秒，每天跑日报时调一次就够了
- **AIHOT 文章没有正文**（body），深度解读只用于自采文章
