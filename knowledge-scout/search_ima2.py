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

# Search for "文章精选" across all KBs
kbs = [
    ("共享知识库同步", "U5M1SOlN70DJRcXPwytSkqj5O2oBD7KmaScrzptus-c="),
    ("蒙牛乳业", "ggMYHw0TIh67qOJpD0nCkGQofCAIn3URUTFHnvRFOl4="),
    ("肠肠的私藏", "FHwyXlArdO1EPfwOsF2yuC8nnUmFvmRp5vL9pHvouAI="),
    ("中汽中心", "hUuQcTyoYkaeSd_RPvT87zX8xCpZEsEhGbzzYTQcqro="),
]

print("=== Searching '文章精选' ===\n")
for name, kb_id in kbs:
    try:
        resp = call("openapi/wiki/v1/search_knowledge", {
            "query": "文章精选",
            "knowledge_base_id": kb_id, "cursor": ""
        })
        items = resp.get("data", {}).get("info_list", [])
        if items:
            print(f"📚 {name}: {len(items)} matches")
            for item in items[:15]:
                title = item.get("title", "")
                fid = item.get("folder_id", "")
                mid = item.get("media_id", "")  
                print(f"   {'📁' if fid else '📄'} {title} | id: {mid or fid}")
            print()
    except Exception as e:
        print(f"📚 {name}: {e}\n")

# Also browse root of "共享知识库同步" for folder structure
print("=== Browsing root of '共享知识库同步' ===")
kb_id = "U5M1SOlN70DJRcXPwytSkqj5O2oBD7KmaScrzptus-c="
try:
    resp = call("openapi/wiki/v1/get_knowledge_list", {
        "knowledge_base_id": kb_id, "cursor": "", "limit": 50
    })
    items = resp.get("data", {}).get("knowledge_list", [])
    for item in items:
        fid = item.get("folder_id", "")
        mid = item.get("media_id", "")
        name = item.get("name", "") or item.get("title", "")
        fn = item.get("file_number", "")
        fn2 = item.get("folder_number", "")
        if fid:
            print(f"  📁 {name} (files:{fn}, folders:{fn2}) | id: {fid}")
        else:
            print(f"  📄 {name} | id: {mid}")
except Exception as e:
    print(f"Error: {e}")
