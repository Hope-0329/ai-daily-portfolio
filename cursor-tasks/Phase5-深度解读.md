# Phase 5: 深度解读引擎

给 Cursor Agent 的自然语言说明：

---

这是系统的差异化能力——竞品 AIHOT 只有摘要和筛选，我们能对重点文章做结构化深度分析。每天从精选里挑 2-3 篇最重要的，拉取全文，用 LLM 生成深度解读，存档到 Obsidian。

## 一、模块结构

新建 `src/pipeline/deep_analysis.py`。

```python
class DeepAnalyzer:
    async def select_candidates(self, articles: list[Article]) -> list[Article]:
        """从精选文章中选出值得深度解读的"""
    
    async def fetch_full_content(self, article: Article) -> str:
        """拉取完整原文，HTML → Markdown 清洗"""
    
    async def deep_analyze(self, article: Article, content: str) -> str:
        """LLM 结构化深度分析，返回 Markdown"""
    
    async def run(self, articles: list[Article]) -> list[dict]:
        """完整流程：选取 → 拉取 → 分析 → 返回结果列表"""
```

## 二、候选文章选取

选 2-3 篇，优先级：

1. score >= 80 且 merged_from 数量 >= 3（多源验证的高分文章）—— 最优先
2. score >= 80 但只来自 1-2 个源 —— 次优先
3. 如果 >= 80 的不够 2 篇，降到 >= 70 的补充

最多选 3 篇，至少选 1 篇（如果精选本身就只有十几篇）。

## 三、正文拉取 + 清洗

用 aiohttp 拉取原文 URL 的 HTML：

1. 拉取 HTML（timeout 15s）
2. 提取正文内容：
   - 优先用 readability-lxml（Python 版的 Mozilla Readability）提取主内容
   - 如果没有 readability-lxml，用 BeautifulSoup 提取 `<article>` 或 `<main>` 标签
   - 都不行就用 body 的全部文本
3. 清洗：
   - 去掉 `<script>`、`<style>`、`<nav>`、`<footer>` 标签
   - 去掉 CSS/JS 残留
   - 把 HTML 转成纯文本（保留段落结构）
   - 截断到 6000 字（太长了 LLM 处理不了）
4. 失败处理：如果拉不到全文（404、超时等），跳过这篇，换下一篇候选

依赖：在 pyproject.toml 加 `beautifulsoup4>=4.12`、`readability-lxml>=0.8`、`lxml>=5.0`

## 四、LLM 深度分析

Prompt：
```
你是 AI 行业深度分析师。请对以下文章进行结构化深度解读。

原文标题：{title}
来源：{source_name}
原文链接：{url}

全文内容：
{content[:6000]}

请按以下结构输出 Markdown：

## 📋 一句话总结
> 用一句话说清楚这篇文章在讲什么（30-60 字）

## 🔑 核心要点
1. **{要点标题}**：{2-3 句话展开}
2. **{要点标题}**：{2-3 句话展开}
3. （至少 3 个要点，最多 5 个）

## 📊 背景与上下文
{说明这条新闻发生的背景、前因后果、跟之前事件的关联、行业格局中的位置。200-300 字。}

## 💡 深度分析
{这是最有价值的部分。基于文章内容和你的行业知识，做出有洞见的分析：
- 这件事意味着什么？
- 谁会受益？谁会被影响？
- 跟其他公司的类似动作有什么异同？
- 未来 6-12 个月会怎么发展？
300-400 字。}

## 🔗 延伸阅读
- {相关的文章、论文、资源（如果文章里有提到）}

---

> 分析时间：{now}
> 原文链接：{url}
```

要求：
- 深度分析部分要有观点，不是复述原文
- 背景部分要把孤立事件放进行业脉络里
- 专业术语翻译准确
- 中文流畅自然

## 五、Obsidian 写入

在 `src/output/obsidian.py`（Phase 6 会完善）里先写一个简单版本：

```python
class ObsidianWriter:
    def __init__(self, root_path: str):
        self.root = root_path
    
    def write_deep_analysis(self, date_str: str, title: str, content: str) -> str:
        """写入深度解读到 Obsidian，返回文件路径"""
        filename = f"{date_str} {title[:50]}.md"
        filepath = os.path.join(self.root, "深度解读", filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath
```

文件名：`深度解读/2026-07-25 GPT-5 Preview 发布.md`

## 六、整合到 Pipeline

更新 `src/pipeline/__init__.py` 的 pipeline 函数，日报生成完成后自动跑深度解读：

```python
async def pipeline(articles, report_stats=None):
    # ... 现有的翻译、分类、摘要、日报生成 ...
    
    # 深度解读
    analyzer = DeepAnalyzer()
    deep_results = await analyzer.run(l2_articles)
    
    return markdown, deep_results
```

## 七、更新 pyproject.toml

加三个依赖：
```
beautifulsoup4 >= 4.12
readability-lxml >= 0.8
lxml >= 5.0
```

## 完成标准

- 能从精选文章中正确选出 2-3 篇候选
- 能成功拉取一篇实际文章的全文并清洗（比如量子位或机器之心的一篇文章）
- LLM 能生成完整的深度解读 Markdown（四点结构齐全）
- 解读文件能写入 Obsidian 指定目录
- `uv run pytest tests/` 全绿

完成后告诉我，给你 Phase 6（输出层 + 定时调度，最后一步——端到端跑通）。
