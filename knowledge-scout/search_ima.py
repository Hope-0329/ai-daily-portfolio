import subprocess, json, urllib.request, sys
sys.stdout.reconfigure(encoding='utf-8')

# Get credentials
result = subprocess.run(
    ["powershell", "-ExecutionPolicy", "Bypass", "-File",
     r"C:\Users\22867\.qclaw\skills\ima\get-token.ps1"],
    capture_output=True, text=True
)
creds = json.loads(result.stdout)

client_id = creds["client_id"]
api_key = creds["api_key"]
headers = {
    "ima-openapi-clientid": client_id,
    "ima-openapi-apikey": api_key,
    "Content-Type": "application/json"
}

def call(path, body):
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(
        f"https://ima.qq.com/{path}",
        data=data, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))

# Search for "05" across all knowledge bases to find the folder
kbs = [
    ("共享知识库同步", "U5M1SOlN70DJRcXPwytSkqj5O2oBD7KmaScrzptus-c="),
    ("蒙牛乳业", "ggMYHw0TIh67qOJpD0nCkGQofCAIn3URUTFHnvRFOl4="),
    ("肠肠的私藏", "FHwyXlArdO1EPfwOsF2yuC8nnUmFvmRp5vL9pHvouAI="),
    ("中汽中心", "hUuQcTyoYkaeSd_RPvT87zX8xCpZEsEhGbzzYTQcqro="),
]

print("=== Searching for '05' or '精选' folders ===\n")
for name, kb_id in kbs:
    try:
        resp = call("openapi/wiki/v1/search_knowledge", {
            "query": "05",
            "knowledge_base_id": kb_id,
            "cursor": ""
        })
        items = resp.get("data", {}).get("info_list", [])
        if items:
            print(f"📚 {name}: {len(items)} matches")
            for item in items[:10]:
                title = item.get("title", "")
                mid = item.get("media_id", "")
                fid = item.get("folder_id", "")
                print(f"   {'📁' if fid else '📄'} {title} | id: {mid or fid}")
            print()
    except Exception as e:
        print(f"📚 {name}: error - {e}\n")
