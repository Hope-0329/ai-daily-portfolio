# Phase 13.1: 信源清算 — 删掉漏网之鱼

## 问题

Phase 13 删了 14 个禁用源，但漏了 3 个实际跑不动但 YAML 里 enable=true 的：

```
microsoft-ai  → 403 Forbidden，RSS 反爬
jiqizhixin    → 机器之心，SPA 无 RSS
tencent-ai-lab → 腾讯 AI Lab，无公开 RSS
```

全量跑的时候 microsoft-ai 三次重试全挂，拖慢整条管线。

## 修复

### 1. 删掉 3 个源

在 `data/sources.yaml` 中删除以下条目：
- `id: microsoft-ai`
- `id: jiqizhixin`
- `id: tencent-ai-lab`

### 2. 更新测试断言

`tests/test_sources.py` 里如果写死了信源总数（39），改成动态读取或改为 36。

### 3. 验证

```
uv run run.py now
```

预期：不再有 microsoft-ai 的 403 错误，全量跑更干净。

---

完成标准：`uv run pytest tests/` 全绿 + `run.py now` 无 ERROR 日志。
