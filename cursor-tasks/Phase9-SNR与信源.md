# Phase 9: SNR 修正 + 同源衰减 + 信源救回

给 Cursor Agent 的自然语言说明：

---

Phase 8 的日报格式已经完全对了。但还有几个影响质量的问题需要修。

## 修改 1: SNR 指标修正

当前 SNR 公式是 `l2 / raw = 25 / 1766 ≈ 1%`，这没意义。

修 `src/filter/snr.py`，计算三个指标：

```python
# filter_efficiency: L2 精选 / 原始文章（反映过滤效率）
filter_efficiency = l2_count / raw_count

# l1_pass_rate: L1 通过 / 原始文章（反映 L1 的宽松度）
l1_pass_rate = l1_count / raw_count

# l2_quality: L2 精选里 score >= 80 的比例（反映精选质量）
l2_quality = high_score_count / l2_count
```

日报里显示的 SNR 改成 `filter_efficiency`，这个值通常会在 5%-15% 之间，是真实的"端到端信噪比"。`l2_quality` 才是 85%+ 目标的指标。

同时修 `daily_report.py` 的 YAML frontmatter，加 `l2_quality` 字段。

## 修改 2: 同源衰减

当前 OpenAI Blog 在模型板块贡献了 11/15 篇，日报看起来像公关稿。

修 `src/filter/layer1_rule.py`：

```python
# 同源文章计数
source_counts = {}
for article in articles_sorted_by_score:
    source = article.source_id
    source_counts[source] = source_counts.get(source, 0) + 1
    if source_counts[source] > 3:
        article.penalty += 3  # 超过 3 篇后逐篇扣分
```

如果重新算分后排名变了，L2 之前的排序也要同步更新。

## 修改 3: 12 个失败源救回

上一版 40/42 成功，这版掉到 30/42。重点救回：

| 源 | 怀疑原因 | 排查方向 |
|---|---------|---------|
| jiqizhixin（机器之心）| URL 过期 | 搜索最新 RSS 地址 |
| huxiu-ai（虎嗅 AI）| 不稳定 | 检查是否被 429/超时 |
| arxiv-ai/mi/cl/cv | SSL 校验失败 | 换 RSSHub 镜像，比如 `https://rsshub.app/arxiv/...` |
| tencent-ai-lab | URL 失效 | 搜索替代 RSS |
| baidu-ai | URL 失效 | 搜索替代 RSS |
| alibaba-damo | URL 失效 | 搜索替代 RSS |

对 SSL 失败的源（arxiv 四个），跳过证书验证参数应该已经设了，但别忘了在 `_download_feed` 里传 `verify_ssl=False`。

对换了 RSSHub 镜像的源，URL 里要确认是 `https://rsshub.app/` 开头。

## 完成标准

- SNR 显示合理（5%-15% 之间）
- l2_quality 独立显示（目标 85%+）
- OpenAI Blog 单源不超过 5 篇进入 L2
- 成功信源数恢复到 35+/42
- 论文板块不空
- `uv run pytest tests/` 全绿
- 跑一次 `uv run run.py now`，日报质量显著提升
