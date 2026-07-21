"""IMA 知识库同步模块

从「AI×管理咨询实战库」的「05-文章精选」和「AI落地应用」目录
拉取最新文章，追踪已读，增量同步。
"""

import subprocess
import json
import urllib.request
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STATE_FILE = ROOT / "state" / "ima_sync_state.json"

# IMA 知识库配置
KB_ID = "lwjCfLlHb19EQM3u4_Hha9T7hL5ApcPo0wnzNaNiB-8="
TARGET_FOLDERS = {
    "精选": "folder_7470453459256336",      # 05-文章精选
    "AI落地": "folder_7470455841625252",     # AI落地应用
}

# 关注的文章类型（media_type）
ARTICLE_TYPES = {"wechatarticle", "weburl", "note"}


def _get_credentials():
    """获取 IMA 凭证"""
    result = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File",
         r"C:\Users\22867\.qclaw\skills\ima\get-token.ps1"],
        capture_output=True, text=True, timeout=15
    )
    return json.loads(result.stdout)


def _call_ima(path: str, body: dict) -> dict:
    """调用 IMA API"""
    creds = _get_credentials()
    headers = {
        "ima-openapi-clientid": creds["client_id"],
        "ima-openapi-apikey": creds["api_key"],
        "Content-Type": "application/json"
    }
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(
        f"https://ima.qq.com/{path}", data=data, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def load_state() -> dict:
    """加载同步状态"""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    return {"seen_ids": [], "last_sync": None, "article_history": {}}


def save_state(state: dict):
    """保存同步状态"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def fetch_folder_articles(folder_id: str, max_pages: int = 5) -> list[dict]:
    """拉取文件夹中所有文章"""
    all_items = []
    cursor = ""
    page = 0

    while page < max_pages:
        resp = _call_ima("openapi/wiki/v1/get_knowledge_list", {
            "knowledge_base_id": KB_ID,
            "folder_id": folder_id,
            "cursor": cursor,
            "limit": 50
        })
        data = resp.get("data", {})
        items = data.get("knowledge_list", [])
        all_items.extend(items)

        if data.get("is_end", True):
            break
        cursor = data.get("next_cursor", "")
        page += 1

    return all_items


def get_new_articles() -> list[dict]:
    """获取所有新文章（尚未解读过的）"""
    state = load_state()
    seen = set(state.get("seen_ids", []))
    new_articles = []

    for folder_name, folder_id in TARGET_FOLDERS.items():
        print(f"  📂 扫描「{folder_name}」...")
        items = fetch_folder_articles(folder_id)

        for item in items:
            mid = item.get("media_id", "")
            fid = item.get("folder_id", "")

            # 跳过文件夹
            if fid:
                continue

            # 跳过已读
            if mid in seen:
                continue

            title = item.get("title", "")
            media_type = item.get("media_type", "")

            article = {
                "title": title,
                "media_id": mid,
                "folder": folder_name,
                "media_type": media_type,
                "discovered_at": datetime.now().isoformat(),
            }
            new_articles.append(article)
            seen.add(mid)

    # 更新状态
    state["seen_ids"] = list(seen)
    state["last_sync"] = datetime.now().isoformat()
    save_state(state)

    return new_articles


def read_article_content(media_id: str) -> str | None:
    """读取文章正文内容（通过 IMA 内部读取接口）"""
    try:
        # 使用 qclaw_read_ima_content 等效的 HTTP 调用
        # 这个接口返回文章的 XML 格式全文
        resp = _call_ima("openapi/knowledge/v1/get_knowledge_content", {
            "media_id": media_id,
            "knowledge_base_id": KB_ID,
        })
        data = resp.get("data", {})
        content = data.get("content", "")
        return content
    except Exception as e:
        print(f"    ⚠️ 读取失败 [{media_id[:20]}...]: {e}")
        return None


if __name__ == "__main__":
    # 测试
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    print("🔍 IMA 知识库同步模块测试\n")
    articles = get_new_articles()
    print(f"\n📊 发现 {len(articles)} 篇新文章")
    for a in articles[:5]:
        print(f"  - [{a['folder']}] {a['title'][:60]}")
