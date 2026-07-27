# Phase 3: 双层过滤引擎

给 Cursor Agent 的自然语言说明：

---

这是整个系统最核心的模块。上一轮你搭好了 52 个信源的采集层，每轮能拉回来大概 200+ 篇文章。但里面大部分是噪音——跟 AI 无关的、没信息量的、重复报道同一件事的。这一轮要建一个双层过滤引擎，把 200 篇筛成 15-25 篇高质量内容。

## 架构

```
200+ 篇原始文章
  → L1 规则引擎（纯 Python，不调 LLM）
    → 50-80 篇（score >= 60）
      → L2 LLM 精筛（调 DeepSeek）
        → 15-25 篇精选 + 事件合井去重
```

## 一、L1 规则引擎

新建 `src/filter/layer1_rule.py`。这是一套纯 Python 规则，不调 LLM，速度快、零成本。

### 四维评分（0-100 分）

**维度 1：AI 相关度（权重 40%）**

关键词库分三级：

高权重词（+20 分/个，命中标题额外 +10）：大模型、LLM、GPT、Claude、Gemini、DeepSeek、Qwen、Llama、Mixtral、transformer、diffusion、RLHF、agent、智能体、多模态、Sora

中权重词（+10 分/个）：深度学习、机器学习、神经网络、NLP、CV、RL、微调、对齐、推理、生成式、AIGC、RAG、向量数据库、embedding、LoRA、量化、蒸馏

低权重词（+5 分/个）：AI、人工智能、ChatGPT、Copilot、Midjourney、Stable Diffusion、Suno、提示词、prompt

计算方式：
- 标题中命中高权重词：每个 +20
- 标题中命中中权重词：每个 +10
- 摘要/正文前 500 字中命中：高权重 +15、中权重 +8、低权重 +3
- 关键词密度（前 500 字）> 3%：额外 +10
- 总分上限 40

**维度 2：信息密度（权重 25%）**

- 正文长度 > 500 字：+5
- 正文长度 > 1000 字：+10
- 正文长度 > 2000 字：+15
- 含列表/表格/代码块：+5
- 纯转载（标题含"转载/分享/收藏"）：-10
- 纯广告/公关稿（含"推广/赞助/限时优惠"）：-15
- 总分上限 25

**维度 3：信源价值（权重 20%）**

- Tier 1 信源：+15
- Tier 2 信源：+8
- Tier 3 信源：+3
- 官方博客（OpenAI/Anthropic 等）：额外 +5（一手信息）
- 纯 Twitter/X 贴子（正文 < 200 字且含 @ 或 #）：-10
- 总分上限 20

**维度 4：时效价值（权重 15%）**

- 1 小时内发布：+15
- 6 小时内：+10
- 24 小时内：+5
- 48 小时内：+2
- 超过 48 小时：0（但不禁掉，学术论文可能值得）
- 总分上限 15

### 加分项（独立计算）

- 含具体数字/数据（如"提升 30%"、"1 亿参数"）：+3
- 提及知名公司/产品（OpenAI、Google、Meta、Apple、Microsoft、字节、阿里、百度、腾讯等）：+3
- 可操作性（教程/工具/开源项目）：+3

### 最终得分

```python
score = min(100, 
    relevance * 0.40 +
    density * 0.25 +
    source_value * 0.20 +
    timeliness * 0.15 +
    bonus
)
```

### 输出

L1 筛掉 score < 60 的文章，给每篇通过的打上 `score` 和 `quality_level`（< 60: low, 60-79: medium, 80+: high）。

## 二、事件级去重

新建 `src/filter/dedup.py`。

这是差异化能力——同一个新闻事件被多个源报道时，我们要合并成一条，显示"6 个信源同时报道"。

### 算法

先用规则快速预判：
1. Jaccard 相似度：标题分词后算交集/并集 > 0.5 → 候选
2. 同一个域名？否 → 继续
3. 发布时间差 < 24 小时？是 → 继续
4. 都转发同一条来源？是 → 合并

规则预判通过的候选对，用 LLM 最终确认：

Prompt：
```
以下两篇 AI 新闻是否在报道同一件事？只回答 YES 或 NO。

文章 A: {title_a}
文章 B: {title_b}

是否同一事件：
```

### 合并逻辑

```python
merged_article = {
    "id": primary.id,  # 保留评分最高的作为主记录
    "merged_from": [a.id, b.id, c.id, ...],  # 被合并的文章 ID 列表
    "score": max([a.score, b.score, ...]) + 5,  # 合并后 +5 分（多源验证加分）
    "summary": primary.summary,
}
```

### 去重后的输出

比如 60 篇 L1 输出 → 去重合并后变 35-45 篇事件 → 进入 L2

## 三、L2 LLM 精筛

新建 `src/filter/layer2_llm.py`。

去重后的 35-45 篇事件，取 Top 30（按 L1 评分），用 LLM 做最后的质量把关。

### LLM 评选 Prompt

```
你是一个严格、挑剔的 AI 日报编辑。

以下是 {N} 条 AI 新闻候选。你需要选出最值得进入今日日报的 {K} 条。

评分标准（每项 0-25 分）：
1. 重要性：这条新闻对 AI 行业有多大影响？
2. 新颖性：是不是今天才有的新信息？有没有独家视角？
3. 信息量：有没有具体数据、案例、分析？还是泛泛而谈？
4. 可读性：对中文 AI 博主读者来说，这条好读懂吗？

新闻列表：
{每篇：编号、标题、来源、L1 评分、一句话描述}

请返回 JSON 列表，每条包含：
{
  "id": "文章编号",
  "score": 0-100,
  "reason": "一句话理由（20 字以内）",
  "rank": 1  # 1 最好，N 最差
}

只返回 JSON 数组，不要其他内容。
```

### L2 输出

LLM 返回的 Top K 篇（K = config 里的 l2_top_n，默认 25），按 LLM 给的 rank 排序。

## 四、信噪比计算

新建 `src/filter/snr.py`。

```python
def calculate_snr(raw_count: int, l1_count: int, l2_count: int, 
                  l2_high_quality_count: int = None) -> dict:
    """
    计算多层 SNR 指标
    
    raw_count: 原始拉取的文章数
    l1_count: L1 规则过滤后的数量
    l2_count: L2 LLM 精选后的数量
    l2_high_quality_count: L2 中 score >= 80 的数量
    """
    return {
        "raw_to_l1_ratio": round(l1_count / raw_count, 3) if raw_count else 0,
        "l1_to_l2_ratio": round(l2_count / l1_count, 3) if l1_count else 0,
        "overall_snr": round(l2_count / raw_count, 3) if raw_count else 0,
        "quality_rate": round(l2_high_quality_count / l2_count, 3) if l2_count else 0,
        # quality_rate >= 0.85 就是我们简历上说的"信噪比提升至 85%+"
    }
```

## 五、整合

新建 `src/filter/__init__.py`，导出一个统一的过滤流程：

```python
async def filter_pipeline(articles: list[Article]) -> dict:
    """
    完整双层过滤流程
    返回: {
        "l1_results": [...],      # L1 通过的
        "dedup_results": [...],   # 去重合井后的
        "l2_results": [...],      # L2 精选的
        "snr": {...},             # SNR 指标
        "stats": {...}            # 统计数据
    }
    """
```

## 完成标准

- 准备一篇测试用的 AI 新闻列表（10 篇正例 + 5 篇噪音），验证 L1 能筛掉噪音
- 准备 3 组"同一事件多源报道"的测试数据，验证去重逻辑正确合并
- L2 LLM 调用成功后返回正确的 JSON
- SNR 计算结果合理
- `uv run pytest tests/test_filter.py` 全绿

完成后告诉我，给你 Phase 4（内容管线：摘要生成、翻译、分类、日报排版）。
