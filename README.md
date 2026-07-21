# AI日报 MCP Server — 云部署指南

## 当前状态（本地 + 公网隧道）

- 本机: http://127.0.0.1:8765 ✅
- 公网: https://badly-breath-sarah-whats.trycloudflare.com ✅
- LLM: DeepSeek-chat（需充值后生效）
- 9 个信源全部在线

⚠️ 当前公网地址依赖你的电脑 + cloudflared 隧道，关机即失效。

## 实现 24/7 永久访问（Render.com）

### 前置条件
1. DeepSeek 余额 >= ¥10（[platform.deepseek.com](https://platform.deepseek.com) 充值）
2. GitHub 账号（免费，上传代码用）
3. Render 账号（免费，注册时关联 GitHub）

### 部署步骤（约 10 分钟）

**步骤 1：上传到 GitHub**
- 在 GitHub 创建新仓库，如 `ai-daily-portfolio`
- 将 `C:\Users\22867\.qclaw\workspace\ai-daily-mcp` 整个文件夹推送到该仓库

**步骤 2：Render 部署**
1. 打开 [dashboard.render.com](https://dashboard.render.com)
2. 点击 **New +** → **Web Service**
3. 连接刚创建的 GitHub 仓库
4. 填写配置：
   - Name: `ai-daily-portfolio`
   - Region: **Singapore**（国内访问快）
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python web_demo_cloud.py`
5. 添加环境变量（Advanced → Environment Variables）：
   - `LLM_API_KEY` = 你的 DeepSeek API Key
   - `LLM_BASE_URL` = `https://api.deepseek.com/v1`
   - `LLM_MODEL` = `deepseek-chat`
6. 点击 **Deploy Web Service**

### 部署后
- 等 2-3 分钟 → 拿到 `https://ai-daily-portfolio.onrender.com`
- 电脑关机也能用，HR 手机随时访问
- 首次访问可能较慢（free tier 冷启动，约 30s），之后流畅

### 成本
- Render: 免费（含 750 小时/月）
- DeepSeek API: 每次深度解读约 ¥0.001，¥10 够用 ~10,000 次
- 总计: ¥10（一次性）

---

## 本地启动（备选）

```powershell
# 本地启动（电脑开机时）
cd C:\Users\22867\.qclaw\workspace\ai-daily-mcp
python web_demo_cloud.py
```

环境变量:
| 变量 | 默认值 | 说明 |
|------|--------|------|
| LLM_BASE_URL | https://api.deepseek.com/v1 | LLM API 地址 |
| LLM_API_KEY | （必填） | API 密钥 |
| LLM_MODEL | deepseek-chat | 模型名 |
| PORT | 8765 | 服务端口 |
