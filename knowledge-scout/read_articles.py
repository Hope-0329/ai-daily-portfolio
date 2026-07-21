import subprocess, json, urllib.request, sys
sys.stdout.reconfigure(encoding='utf-8')

result = subprocess.run(
    ["powershell", "-ExecutionPolicy", "Bypass", "-File",
     r"C:\Users\22867\.qclaw\skills\ima\get-token.ps1"],
    capture_output=True, text=True
)
creds = json.loads(result.stdout)
headers = {
    "ima-openapi-clientid": creds["client_id"],
    "ima-openapi-apikey": creds["api_key"],
    "Content-Type": "application/json"
}

def call(path, body):
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(f"https://ima.qq.com/{path}", data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))

kb_id = "lwjCfLlHb19EQM3u4_Hha9T7hL5ApcPo0wnzNaNiB-8="

# Browse "AI落地应用" subfolder
ai_folder = "folder_7470455841625252"
print("=== AI落地应用 子文件夹内容 ===\n")
cursor = ""
while True:
    resp = call("openapi/wiki/v1/get_knowledge_list", {
        "knowledge_base_id": kb_id, "folder_id": ai_folder, "cursor": cursor, "limit": 50
    })
    data = resp.get("data", {})
    items = data.get("knowledge_list", [])
    for i, item in enumerate(items):
        title = item.get("title", "")
        mid = item.get("media_id", "")
        fid = item.get("folder_id", "")
        icon = "📁" if fid else "📄"
        print(f"  {i+1}. {icon} {title} | {mid}")
    if data.get("is_end", True): break
    cursor = data.get("next_cursor", "")

# Also search for articles about AI/Agent/大模型 in the KB
print("\n=== 搜索 KB中的AI相关文章 (preview) ===\n")
for q in ["Agent", "大模型", "AI", "人工智能"]:
    resp = call("openapi/wiki/v1/search_knowledge", {
        "query": q, "knowledge_base_id": kb_id, "cursor": "", "limit": 5
    })
    items = resp.get("data", {}).get("info_list", [])
    if items:
        print(f"🔍 '{q}': {len(items)} matches")
        for item in items[:3]:
            title = item.get("title", "")
            highlight = item.get("highlight_content", "")[:120]
            print(f"   {title}")
            if highlight: print(f"   > {highlight}...")
        print()
