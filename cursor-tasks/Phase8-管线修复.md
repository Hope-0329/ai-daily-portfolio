# Phase 8: 管线连接修复（A 线）

给 Cursor Agent 的自然语言说明：

---

`uv run run.py now` 跑通了，但生出来的日报是旧 knowledge-scout v4 格式——50 篇流水账，没有 5 板块、没有 LLM 摘要、没有博主视角。

原因是 `src/scheduler/jobs.py` 的 `daily_job()` 没有调用 Phase 4 的内容管线。

## 修复点

### 1. 修 `daily_job()` — 接入新管线

当前流程里，采集和过滤用的是新代码，但到了"生成日报"这一步跳回了旧格式。需要把 `daily_job()` 的后半段改成调用 `src/pipeline/pipeline()`。

具体改动 `src/scheduler/jobs.py`：

```
采集 → 过滤 → pipeline(l2_results, stats) → 写入 Obsidian
```

`pipeline()` 返回 `(markdown, deep_results)`，其中：
- `markdown` — 完整日报 Markdown（5 板块 + TOP 3 + 选题池 + 碎碎念 + 系统自检）
- `deep_results` — 深度解读列表

### 2. 修深度解读 Obsidian 路径

当前深度解读声称生成了但文件没落地。检查 `src/output/obsidian.py` 的写入逻辑：

- `write_daily_report()` 写到了 `30-项目/AI博主与日报/日报存档/`，这 OK
- `write_deep_analysis()` 如果也写到了这个路径，需要确认真实写入位置

确保深度解读写到 `D:\肠肠的Obsidian\肠肠的obsidian\30-项目\AI博主与日报\深度解读\` 目录下。

### 3. 修 non-AI 文章混入

在 `src/filter/layer1_rule.py` 里，AI 相关度评分增加反例检测：
- 标题含"股票/评级/涨停/港股/A股/投资评级/保险/再保险/汽车销量/半导体股权"等词，扣 20 分
- 确保 #26 TCL 半导体收购、#46 中国再保险、#47 汽车销量这类文章在 L1 就被筛掉

### 4. 减少 RSS 超时失败

在 `src/sources/rss.py` 的 `_download_feed` 方法里，对 429（限流）做特殊处理：等 5 秒重试，不要直接抛异常。

---

## 完成标准

- `uv run run.py now` 生成的日报是 5 板块格式（模型/产品/行业/论文/技巧）
- 每篇文章有 LLM 生成的一句话摘要（非原文截取）
- 有 TOP 3 + 选题池 + 碎碎念
- 有系统自检（SNR、质量率、失败信源）
- 深度解读文件真实存在于 Obsidian 目录中
- 非 AI 文章被过滤掉
- `uv run pytest tests/` 全绿

完成后把日报贴出来给我审。
