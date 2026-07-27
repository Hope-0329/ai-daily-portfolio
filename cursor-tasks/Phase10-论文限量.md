# Phase 10: 论文限量 + 降权，恢复板块均衡

给 Cursor Agent 的自然语言说明：

---

arxiv 救回来了，但 320 篇论文淹没了日报——22/25 是论文，TOP 3 全变论文标题。现在修三个点让板块恢复均衡。

## 修改 1: arxiv 限量

修 `src/sources/rss.py` 或 `src/sources/api.py`（看 arxiv 走的是哪个采集器），每源只取最新 15 篇。

目前配置里 arxiv-ai、arxiv-ml、arxiv-cl、arxiv-cv 四个源各拉 ~80 篇，改成每源 max_items=15。

## 修改 2: 论文 L1 降权

修 `src/filter/layer1_rule.py`，对 source_type 为 "academic" 或 "paper" 的文章，默认扣 15 分。

这样论文还能进，但不会碾压新闻源——同分情况下新闻优先。

## 修改 3: L2 论文硬上限

修 `src/filter/layer2_llm.py` 或 `src/filter/__init__.py`，在 select_top_articles 里加论文上限：
- L2 精选总数 K=25 时，论文最多 8 篇
- 选法：先把论文和非论文分开排序 → 各取前 N → 合并 → 总 25 篇

## 修改 4: 论文标题翻译（加分项，不做也行）

在 `src/pipeline/translator.py` 或 `src/pipeline/summarizer.py` 里，对论文做一次 LLM "大白话"翻译：

```
把以下学术论文标题翻译成通俗易懂的中文，让非专业读者能看懂：

英文标题：Token Budget Saturation and Non-Convergence of Reasoning in Chain-of-Thought Models

中文翻译：思维链模型里的"推理越多不一定越好"——一篇新论文发现 token 预算有上限
```

不做也行，至少做前三个。

## 完成标准

- 论文板块 5-8 篇（回到合理比例）
- 非论文板块（模型/产品/行业/技巧）每个至少有 2-3 篇
- TOP 3 不全是论文，至少混入 1 篇行业新闻
- l2_quality 回升到 60%+
- `uv run run.py now` 全流程跑通
