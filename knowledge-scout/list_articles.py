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
folder_id = "folder_7470453459256336"

print("=== 05-文章精选 全部内容 ===\n")
all_titles = []
cursor = ""
while True:
    resp = call("openapi/wiki/v1/get_knowledge_list", {
        "knowledge_base_id": kb_id,
        "folder_id": folder_id,
        "cursor": cursor,
        "limit": 50
    })
    data = resp.get("data", {})
    items = data.get("knowledge_list", [])
    for i, item in enumerate(items):
        title = item.get("title", "")
        mid = item.get("media_id", "")
        fid = item.get("folder_id", "")
        all_titles.append((title, mid, fid))
        icon = "📁" if fid else "📄"
        print(f"  {i+1}. {icon} {title}")
        if not fid:
            print(f"     media_id: {mid}")
    if data.get("is_end", True):
        break
    cursor = data.get("next_cursor", "")

print(f"\n\n总共 {len(all_titles)} 条\n")

# Save media_ids for article reading
import json as j
with open("article_ids.json", "w", encoding="utf-8") as f:
    j.dump([{"title": t, "mid": m, "is_folder": bool(fid)} for t, m, fid in all_titles], f, ensure_ascii=False, indent=2)
print("Saved to article_ids.json")
