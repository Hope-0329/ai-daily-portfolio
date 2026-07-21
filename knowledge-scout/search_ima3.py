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

def browse_all(kb_id, kb_name, cursor=""):
    """Browse and show all folders"""
    print(f"\n=== {kb_name} ===")
    folders = []
    while True:
        resp = call("openapi/wiki/v1/get_knowledge_list", {
            "knowledge_base_id": kb_id, "cursor": cursor, "limit": 50
        })
        data = resp.get("data", {})
        items = data.get("knowledge_list", [])
        for item in items:
            fid = item.get("folder_id", "")
            name = item.get("name", "") or item.get("title", "")
            fn = item.get("file_number", "0")
            fn2 = item.get("folder_number", "0")
            if fid:
                print(f"  📁 {name} ({fn} files, {fn2} folders) | {fid}")
                folders.append((name, fid))
            else:
                print(f"  📄 {name}")
        if data.get("is_end", True):
            break
        cursor = data.get("next_cursor", "")
    return folders

# Browse all KBs for top-level folder structure
kbs = [
    ("蒙牛乳业", "ggMYHw0TIh67qOJpD0nCkGQofCAIn3URUTFHnvRFOl4="),
    ("中汽中心", "hUuQcTyoYkaeSd_RPvT87zX8xCpZEsEhGbzzYTQcqro="),
    ("天津轨交", "NoaTi7Oa9Ps1Uxq_z8B1kyYsUk-naXBXSmeFad3QnOo="),
]

for name, kb_id in kbs:
    try:
        browse_all(kb_id, name)
    except Exception as e:
        print(f"\n=== {name}: Error {e} ===")
