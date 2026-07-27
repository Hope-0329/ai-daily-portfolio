# Phase 1: 项目骨架搭建

给 Cursor Agent 的自然语言说明：

---

你好，我在做一个 AI 日报自动采编系统，项目名叫 ai-daily-system。
我需要你帮我从零搭建这个项目的骨架。

## 项目是什么

这是一个自动化系统，每天从 50+ 全球 AI 新闻信源采集文章，经过双层过滤筛选高质量内容，用 LLM 生成中文日报，最后写入 Obsidian 笔记库。

## 技术选型

- Python 3.11+
- 包管理用 uv（就是那个 Rust 写的 Python 包管理器）
- LLM 调用用 DeepSeek API（OpenAI 兼容接口，用 openai 这个 Python 库就行）
- 数据库用 SQLite（标准库自带，不需要额外装）
- 配置管理用 pydantic-settings
- 异步用 asyncio + aiohttp

## 项目路径

```
C:\Users\22867\.qclaw\workspace\ai-daily-system\
```

旧版代码在 `C:\Users\22867\.qclaw\workspace\ai-daily-mcp\`，有大概 5000 行 Python，可以参考逻辑但不要照搬，旧版有不少架构问题和硬编码。

## 本轮要做什么

只做骨架——目录结构、基础配置、数据模型、数据库初始化。具体来说：

### 第一步：创建 pyproject.toml

用 uv 初始化项目，依赖列表：

- pydantic >= 2.0
- pydantic-settings >= 2.0
- openai >= 1.0
- aiohttp >= 3.9
- feedparser >= 6.0
- pyyaml >= 6.0
- python-dateutil >= 2.8
- jinja2 >= 3.1
- fastapi >= 0.109
- uvicorn >= 0.27
- 开发依赖: pytest >= 8.0, pytest-asyncio >= 0.23

### 第二步：创建目录结构

```
src/
  __init__.py
  config.py
  models.py
  database.py
data/
  (空目录，后面放 sources.yaml 和 scout.db)
tests/
  __init__.py
  test_config.py
```

### 第三步：写 config.py

用 pydantic-settings 的 BaseSettings，从环境变量读取配置：

- `DEEPSEEK_API_KEY` — DeepSeek 的 API Key（已经在系统环境变量里了）
- `deepseek_base_url` — 默认 `https://api.deepseek.com/v1`
- `obsidian_root` — 默认 `D:\肠肠的Obsidian\肠肠的obsidian\00-收件箱\AI日报\`
- `db_path` — 默认 `data/scout.db`
- `sources_config` — 默认 `data/sources.yaml`
- `fetch_timeout` — 默认 15 秒
- `max_concurrent` — 默认 10
- `l1_min_score` — 默认 60（第一层过滤的最低分）
- `l2_top_n` — 默认 25（第二层精选的上限）

所有路径都要可配置，不要硬编码。

### 第四步：写 models.py

用 Pydantic 定义这几个数据模型：

1. **Category 枚举**：ai-models（模型发布/更新）、ai-products（产品发布/更新）、industry（行业动态）、paper（论文研究）、tip（技巧与观点）
2. **SourceType 枚举**：rss、api、web、rsshub
3. **QualityLevel 枚举**：high、medium、low
4. **Source 模型**：id、name、name_display、url、type（SourceType）、tier（1=核心/2=辅助/3=备用）、language（zh/en）、category_weights（字典）、enabled（bool）、fetch_interval_min
5. **Article 模型**：id（url hash）、title、title_cn（中文翻译）、url、source_id、source_name、summary（LLM 生成的摘要）、summary_raw（原文摘要）、content（正文可选）、published_at（可选 datetime）、fetched_at（datetime）、category（可选）、score（0-100 float）、quality_level、language、merged_from（多源合并的 id 列表）
6. **DailyReport 模型**：date、generated_at、sections（dict）、top_stories（Article 列表）、topic_pool（字符串列表）、thoughts（字符串）、snr（float）、stats（dict）

### 第五步：写 database.py

用 Python 标准库的 sqlite3，数据库文件路径从 config 读取。

建四张表：

1. **sources** — 信源注册表（id, name, url, type, tier, language, enabled, last_fetched_at, error_count）
2. **articles** — 文章表（id, title, title_cn, url unique, source_id, source_name, summary, published_at, fetched_at, category, score, quality_level, language, merged_from JSON, content_hash, is_selected）
3. **daily_reports** — 日报表（date primary key, generated_at, file_path, snr, raw_count, l1_count, l2_count, stats JSON）
4. **source_health** — 信源健康日志（id auto, source_id, date, status, articles_count, error_message, response_time_ms）

提供 `init_db()` 函数和基本的 CRUD 方法骨架（insert_source、get_source、insert_article、get_articles_by_date 等）。

### 第六步：写 .gitignore 和 .env.example

- .gitignore：排除 .env、data/scout.db、__pycache__、.venv
- .env.example：只放 DEEPSEEK_API_KEY 和 LOG_LEVEL 的示例

### 第七步：写一个简单的测试

tests/test_config.py：导入 Settings，验证默认值是否正确（fetch_timeout=15、max_concurrent=10、l1_min_score=60）

## 完成标准

- `cd C:\Users\22867\.qclaw\workspace\ai-daily-system`
- `uv sync` 安装依赖成功
- `uv run pytest tests/` 全绿

完成这些后告诉我，我给你 Phase 2 的指令（信源层）。
