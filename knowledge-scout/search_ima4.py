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

# Check the two large subscribed KBs
kbs = [
    ("AI管理咨询实战库", "lwjCfLlHb19EQM3u4_Hha9T7hL5ApcPo0wnzNaNiB-8="),
    ("Wedd共享知识库", "XMvEulW30AcOEYL04eDA0rodbYJn6HO_4oQrF8t6aYA="),
]

for name, kb_id in kbs:
    print(f"=== {name} ===")
    try:
        # Get root folder list
        resp = call("openapi/wiki/v1/get_knowledge_list", {
            "knowledge_base_id": kb_id, "cursor": "", "limit": 50
        })
        items = resp.get("data", {}).get("knowledge_list", [])
        found = False
        for item in items:
            fid = item.get("folder_id", "")
            mid = item.get("media_id", "")
            item_name = item.get("name", "") or item.get("title", "")
            fn = item.get("file_number", "0")
            fn2 = item.get("folder_number", "0")
            if fid:
                print(f"  📁 {item_name} ({fn} files, {fn2} folders) | {fid}")
                if "05" in item_name or "精选" in item_name or "文章" in item_name:
                    found = True
            else:
                print(f"  📄 {item_name}")
        
        if not found:
            # Try searching "文章精选", "微信", "公众号"
            for q in ["文章精选", "微信公众号", "精选文章", "05"]:
                resp = call("openapi/wiki/v1/search_knowledge", {
                    "query": q, "knowledge_base_id": kb_id, "cursor": ""
                })
                items = resp.get("data", {}).get("info_list", [])
                if items:
                    print(f"  🔍 '{q}': {len(items)} matches")
                    for item in items[:5]:
                        title = item.get("title", "")
                        fid = item.get("folder_id", "")
                        mid = item.get("media_id", "")
                        print(f"     {'📁' if fid else '📄'} {title} | {mid or fid}")
        print()
    except Exception as e:
        print(f"  Error: {e}\n")
