# Phase 2: 信源层

给 Cursor Agent 的自然语言说明：

---

上一轮你帮我建好了 ai-daily-system 的项目骨架，config、models、database 都通了。现在我需要搭建采集层——让系统能从 50+ 个全球 AI 信源拉取新闻。

## 本轮做什么

三件事：
1. 创建 data/sources.yaml，把 52 个信源配置写进去
2. 写通用采集器（RSS、API、Web 三种）
3. 写信源注册中心 + 并发调度

## 一、创建 data/sources.yaml

每个信源的配置格式是这样的：

```yaml
sources:
  - id: qbitai
    name: "量子位"
    name_display: "量子位（RSS）"
    url: "https://www.qbitai.com/feed"
    type: rss
    tier: 1
    language: zh
    category_weights:
      ai-models: 0.3
      ai-products: 0.3
      industry: 0.3
      paper: 0.05
      tip: 0.05
```

下面是全部 52 个信源，请完整写入 sources.yaml：

### Tier 1（核心源，25 个）—— 每天必采

1. **量子位** — RSS: `https://www.qbitai.com/feed` — zh — 综合 AI 媒体
2. **机器之心** — RSS: `https://www.jiqizhixin.com/rss` — zh — 综合 AI 深度
3. **36氪 AI** — RSS: `https://36kr.com/feed?category=ai` — zh — AI 商业
4. **虎嗅 AI** — RSS: `https://www.huxiu.com/rss/0.xml` — zh — 科技商业
5. **少数派** — RSS: `https://sspai.com/feed` — zh — 数字工具/AI 应用
6. **爱范儿** — RSS: `https://www.ifanr.com/feed` — zh — 数码/AI 消费
7. **读懂 AI 时代** — RSS: `https://www.dudongai.com/feed` — zh — AI 深度分析
8. **OpenAI Blog** — RSS: `https://openai.com/blog/rss.xml` — en — 官方公告
9. **Anthropic Blog** — RSS: `https://www.anthropic.com/blog/rss.xml` — en — Claude
10. **Google DeepMind** — RSS: `https://deepmind.google/discover/blog/feed.xml` — en — 研究前沿
11. **Meta AI Blog** — RSS: `https://ai.meta.com/blog/feed/` — en — Meta AI
12. **Microsoft AI Blog** — RSS: `https://blogs.microsoft.com/ai/feed/` — en — 微软 AI
13. **Hugging Face Blog** — RSS: `https://huggingface.co/blog/feed.xml` — en — 开源生态
14. **GitHub Trending** — API: `https://api.github.com/search/repositories?q=topic:artificial-intelligence+created:>7d&sort=stars&order=desc` — en — 开源项目
15. **Hacker News** — API: `https://hacker-news.firebaseio.com/v0/topstories.json` — en — 技术社区
16. **TechCrunch AI** — RSS: `https://techcrunch.com/category/artificial-intelligence/feed/` — en — 科技媒体
17. **The Verge AI** — RSS: `https://www.theverge.com/ai-artificial-intelligence/rss/index.xml` — en — 科技媒体
18. **VentureBeat AI** — RSS: `https://venturebeat.com/category/ai/feed/` — en — AI 商业
19. **Ars Technica AI** — RSS: `https://feeds.arstechnica.com/arstechnica/technology-lab/` — en — 技术深度
20. **arXiv AI** — RSS: `https://rss.arxiv.org/rss/cs.AI` — en — 学术论文
21. **arXiv ML** — RSS: `https://rss.arxiv.org/rss/cs.LG` — en — 机器学习论文
22. **arXiv CL** — RSS: `https://rss.arxiv.org/rss/cs.CL` — en — NLP 论文
23. **arXiv CV** — RSS: `https://rss.arxiv.org/rss/cs.CV` — en — 计算机视觉论文
24. **Hugging Face Papers** — API: `https://huggingface.co/api/daily_papers` — en — 每日热门论文
25. **Product Hunt AI** — RSS: `https://www.producthunt.com/feed?category=ai` — en — AI 产品

### Tier 2（辅助源，18 个）—— 不是每天都有优质内容

26. **差评** — RSS: `https://chaping.cn/feed` — zh — 科技趣闻
27. **InfoQ AI** — RSS: `https://www.infoq.cn/feed` — zh — 技术社区
28. **雷峰网** — RSS: `https://www.leiphone.com/feed` — zh — AI 产业
29. **腾讯 AI Lab** — RSS: `https://ai.tencent.com/ailab/zh/feed/` — zh — 学术研究
30. **阿里达摩院** — RSS: `https://damo.alibaba.com/rss/news/zh` — zh — 产业研究
31. **百度 AI** — RSS: `https://ai.baidu.com/feed` — zh — 百度 AI
32. **MIT Tech Review AI** — RSS: `https://www.technologyreview.com/feed/ai/` — en — 深度科技
33. **Wired AI** — RSS: `https://www.wired.com/feed/tag/ai` — en — 科技文化
34. **ZDNet AI** — RSS: `https://www.zdnet.com/topic/artificial-intelligence/rss.xml` — en — 企业 AI
35. **NVIDIA Blog AI** — RSS: `https://blogs.nvidia.com/feed/` — en — GPU/AI 硬件
36. **Stability AI Blog** — RSS: `https://stability.ai/news/rss.xml` — en — 开源模型
37. **Mistral AI Blog** — RSS: `https://mistral.ai/news/feed.xml` — en — 欧洲 AI
38. **Cohere Blog** — RSS: `https://cohere.com/blog/rss.xml` — en — 企业 AI
39. **AI Weirdness** — RSS: `https://www.aiweirdness.com/feed/` — en — AI 趣味
40. **Import AI** — RSS: `https://jack-clark.net/feed/` — en — 每周 AI 综述
41. **AI News** — RSS: `https://www.artificialintelligence-news.com/feed/` — en — AI 新闻
42. **Analytics India Mag** — RSS: `https://analyticsindiamag.com/feed/` — en — AI 产业
43. **Synced Review** — RSS: `https://syncedreview.com/feed/` — en — AI 论文解读

### Tier 3（备用源，9 个）—— 补充视角，信噪比低

44. **知乎 AI 热榜** — Web: `https://www.zhihu.com/topic/19551321/hot` — zh — 中文社区
45. **ACL Anthology** — RSS: `https://aclanthology.org/feed.xml` — en — NLP 论文
46. **ICML** — RSS: `https://icml.cc/Conferences/2024/feed.xml` — en — 顶会论文
47. **NeurIPS** — RSS: `https://neurips.cc/Conferences/2024/feed.xml` — en — 顶会论文
48. **The Decoder** — RSS: `https://the-decoder.com/feed/` — en — AI 政策监管
49. **MLOps Community** — RSS: `https://mlops.community/feed/` — en — MLOps
50. **Lil'Log** — RSS: `https://lilianweng.github.io/feed.xml` — en — AI 技术博客
51. **Chip Huyen Blog** — RSS: `https://huyenchip.com/feed.xml` — en — AI 工程
52. **Andrej Karpathy Blog** — RSS: `https://karpathy.github.io/feed.xml` — en — AI 教程

注意：如果上面某些 RSS URL 查不到或者 404，就用对应的网站首页 URL 替换，type 改成 web，标记一下。

category_weights 的默认值（根据信源性质微调）：
- AI 媒体/新闻类：ai-models:0.3, ai-products:0.3, industry:0.3, paper:0.05, tip:0.05
- 学术类（arXiv 等）：ai-models:0.2, ai-products:0.05, industry:0.05, paper:0.6, tip:0.1
- 官方博客（OpenAI 等）：ai-models:0.4, ai-products:0.3, industry:0.2, paper:0.05, tip:0.05
- 技术社区（HN 等）：ai-models:0.2, ai-products:0.2, industry:0.2, paper:0.1, tip:0.3

## 二、写通用采集器

在 src/sources/ 目录下创建：

### src/sources/__init__.py
空文件就行

### src/sources/base.py
定义抽象基类 SourceCollector：

```python
from abc import ABC, abstractmethod
from ..models import Source, Article

class SourceCollector(ABC):
    @abstractmethod
    async def fetch(self, source: Source) -> list[Article]:
        """拉取一个信源，返回标准化 Article 列表"""
        pass
```

### src/sources/rss.py
RSS 通用采集器，继承 SourceCollector：

- 用 aiohttp 异步拉取 RSS/Atom feed
- 用 feedparser 解析（feedparser 支持同步，用 asyncio.to_thread 包一下就行）
- 自动识别 RSS 2.0、Atom、JSON Feed 三种格式
- 把 feed 条目转成 Article 对象：
  - id = url 的 MD5 hash
  - title = feed 条目标题
  - summary_raw = feed 条目摘要
  - published_at = feed 条目时间（解析多种时间格式）
  - fetched_at = 当前时间
  - language = 信源的语言
- User-Agent 设为 `ai-daily-scout/2.0`
- timeout 用 config 里的 fetch_timeout（默认 15s）
- 每个源失败重试 1 次
- 如果 RSS URL 是 https 但证书报错，设 verify_ssl=False 试试

### src/sources/api.py
API 采集器，处理 GitHub Trending 和 Hacker News 这类：

- GitHub Trending：调 GitHub Search API，不需要 token，抓 topic:artificial-intelligence + topic:machine-learning，最近 7 天创建的项目，按 stars 排序，取前 20
- Hacker News：先调 /v0/topstories.json 拿 id 列表（前 30 个），再逐条调 /v0/item/{id}.json 拿详情，用 AI 关键词过滤标题（含 AI/LLM/GPT/ML/deep learning/neural network 等）
- HuggingFace Papers：调 /api/daily_papers，返回当天的 paper 列表

### src/sources/web.py
网页采集器（备用）：

- 用 aiohttp 拉 HTML
- 用 BeautifulSoup 或直接用正则提取 title 和 meta description
- 仅当 RSS/API 都不可用时使用

## 三、信源注册中心 + 并发调度

### src/sources/registry.py

```python
class SourceRegistry:
    def __init__(self, config_path: str):
        """从 sources.yaml 加载所有信源配置"""
    
    def get_enabled_sources(self, min_tier: int = 3) -> list[Source]:
        """获取启用的信源列表"""
    
    async def fetch_all(self, sources: list[Source] = None) -> dict[str, list[Article]]:
        """并发拉取所有信源，返回 {source_id: [articles]}"""
```

并发调度的关键要求：
- 用 asyncio.Semaphore 控制并发数（默认 10 个）
- 用 asyncio.gather 并发执行，return_exceptions=True
- 单个源失败不影响其他源（隔离异常）
- 每个源的结果记录到数据库的 source_health 表
- 已拉取的文章（同样 url）24 小时内不重复入库

## 四、更新数据库

在 database.py 里完善 methods：
- `upsert_source(source: Source)` — 插入或更新信源
- `insert_articles(articles: list[Article])` — 批量插入文章（ignore 重复的 url）
- `log_source_health(source_id, status, count, error_msg, response_time)` — 记录健康日志

## 五、写测试

tests/test_sources.py：
1. 测试 registry 能正确加载 sources.yaml
2. 测试 RSS 采集器能成功解析一个已知可用的 RSS（比如量子位 `https://www.qbitai.com/feed`）
3. 测试 API 采集器能拉取 GitHub Trending

## 完成标准

- sources.yaml 包含全部 52 个信源，格式正确
- `uv run python -c "from src.sources.registry import SourceRegistry; r = SourceRegistry('data/sources.yaml'); sources = r.get_enabled_sources(); print(f'Loaded {len(sources)} sources')"` 输出 52
- 至少量子位的 RSS 能成功拉取
- `uv run pytest tests/` 全绿

完成后告诉我，给你 Phase 3（双层过滤引擎，这个是最核心的）。
