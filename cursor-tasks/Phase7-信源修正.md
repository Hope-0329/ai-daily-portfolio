# Phase 7: 信源 URL 修正 + 稳定性加固

给 Cursor Agent 的自然语言说明：

---

首次运行发现两类问题需要修复。

## 问题 1: API Key 读取不到

**症状**: `OpenAIError: Missing credentials`

**原因**: config.py 里 `deepseek_api_key` 用了 `validation_alias="DEEPSEEK_API_KEY"`，但当前终端读不到这个环境变量（`setx` 设的值需要新终端才生效）。

**修复**: 让 config.py 增加 .env 文件回退机制，并在项目根目录创建 .env 文件。

1. 修改 config.py 的 Settings 类：
   - 去掉 `validation_alias`，改用 `env_file = ".env"` 自动加载
   - 如果 .env 文件和系统环境变量都没有，才报错

2. 在项目根目录创建 `.env` 文件（不提交到 git）:
   ```
   DEEPSEEK_API_KEY=你的DeepSeek_API_Key
   ```

3. 验证：`uv run python -c "from src.config import settings; print(settings.deepseek_api_key[:10])"` 输出 `sk-aa8d00`

## 问题 2: 大量信源 URL 失效

**失效清单**（共 18 个）：

| 信源 | 错误 | 修复方案 |
|------|------|---------|
| dudongai（读懂AI时代） | DNS 解析失败 | 域名可能已变，搜索确认后更新 URL |
| anthropic-blog | 404 | Anthropic 改了 RSS URL，搜新地址 |
| deepmind | 404 | Google DeepMind RSS 路径变了 |
| theverge-ai | 404 | The Verge RSS 格式变更 |
| microsoft-ai | 410 Gone | 微软 AI 博客已迁移 |
| mit-tech-review | 404 | MIT Tech Review RSS 路径错误 |
| wired-ai | 404 | Wired 的 tag feed 路径变了 |
| acl-anthology | 404 | ACL Anthology 可能换了域名 |
| icml | 404 | ICML 2024 页面已下线，改 2025 |
| neurips | 404 | NeurIPS 2024 页面已下线，改 2025 |
| lil-log | 404 | Lilian Weng 博客 RSS 路径变更 |
| mlops-community | 404 | MLOps Community 域名或 RSS 路径变更 |
| huxiu-ai | 超时 + SSL | 虎嗅 RSS 不稳定，加长超时到 30s |
| meta-ai | 超时 | Meta AI 博客可能被墙，先禁用 |
| huggingface-blog | 超时 | HF 可能被限流，增加重试间隔 |
| huggingface-papers | 超时 | 同上 |
| mistral-ai | 超时 | Mistral 博客可能被墙 |
| chaping（差评） | 502 | 网站临时故障，等恢复 |
| zhihu-ai-hot | 403 | 知乎反爬，改用 RSSHub |

**修复策略**:

1. **能修的修**: 对 404/410 的源，搜索正确的 RSS URL 并更新
   - Anthropic: 试试 `https://www.anthropic.com/feed.xml` 或其他路径
   - DeepMind: 试试 `https://blog.google/technology/ai/rss/`
   - The Verge: 试试 `https://www.theverge.com/rss/ai-artificial-intelligence/index.xml`
   - Microsoft AI: 试试 `https://news.microsoft.com/source/topics/ai/feed/`
   - Wired: 试试 `https://www.wired.com/feed/category/artificial-intelligence/latest/rss`
   - ICML/NeurIPS: 改 2025 年份
   - Lil'Log: 试试 `https://lilianweng.github.io/posts/feed.xml`
   - 读懂AI时代: 搜索确认当前域名

2. **暂时禁用**: 
   - meta-ai: `enabled: false`（被墙）
   - mistral-ai: `enabled: false`（被墙）
   - zhihu-ai-hot: `enabled: false`（反爬严重）
   - chaping: `enabled: false`（不稳定，等他恢复再开）

3. **重试策略优化**:
   - RSS 超时从 15s 改为 25s
   - 重试次数从 1 次改为 2 次
   - 重试之间间隔 3 秒
   - 信源禁用后在 source_health 表记录原因

## 修复后的预期

52 个源 → 约 35-40 个能稳定拉取（24 小时内成功率 > 90%），其余要么被墙、要么被封、要么暂时性故障。后续可以逐步用 RSSHub 路由补充。

## 完成标准

- `uv run python -c "from src.config import settings; assert settings.deepseek_api_key.startswith('sk-')"`
- `uv run run.py now` 全流程跑通，不再因 API Key 崩溃
- 信源成功率 > 70%（35/52 以上）
- `uv run pytest tests/` 全绿

完成后在终端重新跑一遍 `uv run run.py now`，然后打开 Obsidian 看日报是否生成到 `D:\肠肠的Obsidian\肠肠的obsidian\00-收件箱\AI日报\` 里。
