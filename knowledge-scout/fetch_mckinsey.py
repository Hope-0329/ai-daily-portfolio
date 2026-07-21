"""获取 McKinsey 文章全文用于测试"""
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

# McKinsey article: 麦肯锡这组图，厉害的不是说增长，而是把增长拆到让人信服
media_id = "wechatarticle_a4bc6f9134c09995041e9c885fa3fc8a_f18ae37b33ded6390d7a43f2cc52e5367470125003317188"

def call(path, body):
    data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(f"https://ima.qq.com/{path}", data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))

kb_id = "lwjCfLlHb19EQM3u4_Hha9T7hL5ApcPo0wnzNaNiB-8="

# Get content
resp = call("openapi/knowledge/v1/get_knowledge_content", {
    "media_id": media_id,
    "knowledge_base_id": kb_id
})

content = resp.get("data", {}).get("content", "") or resp.get("data", {}).get("markdown", "")
if not content:
    # Try alternative format
    content = json.dumps(resp, ensure_ascii=False)

print(f"Content length: {len(content)} chars")
print(f"First 500 chars:\n{content[:500]}")
print(f"\n... writing to test file")
with open(r"C:\Users\22867\.qclaw\workspace\knowledge-scout\mckinsey_test.txt", "w", encoding="utf-8") as f:
    f.write(content)
print("Done.")
