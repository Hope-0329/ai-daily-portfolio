"""解析 IMA 返回的 XML 格式文章，提取纯文本，测试深度解读"""
import sys, json, re, html
sys.path.insert(0, r"C:\Users\22867\.qclaw\workspace\knowledge-scout")
sys.stdout.reconfigure(encoding='utf-8')

from scripts.interpreter import interpret_article, score_article_depth
from dataclasses import asdict

# 从 LCM 文件中读取内容
# qclaw_read_ima_content 返回 JSON: {"content":"<xml>..."}
raw = r'C:\Users\22867\.qclaw\workspace\knowledge-scout\mckinsey_test.txt'

# 直接用 Palantir 文章的内容片段来做测试
# (从 LCM 输出中提取的 XML 内容)
xml_content = None

# 先尝试从 IMA 结果文件中读取
import subprocess, urllib.request

# 用 qclaw_read_ima_content 的另一种方式：直接通过 ima API 读取
result = subprocess.run(
    ["powershell", "-ExecutionPolicy", "Bypass", "-File",
     r"C:\Users\22867\.qclaw\skills\ima\get-token.ps1"],
    capture_output=True, text=True
)
creds = json.loads(result.stdout)

# 使用 FetchMediaContent 端点（qclaw_read_ima_content 内部调用的）
headers = {
    "ima-openapi-clientid": creds["client_id"],
    "ima-openapi-apikey": creds["api_key"],
    "Content-Type": "application/json",
    "Accept": "application/json",
}

kb_id = "lwjCfLlHb19EQM3u4_Hha9T7hL5ApcPo0wnzNaNiB-8="
media_id = "wechatarticle_a4bc6f9134c09995041e9c885fa3fc8a_7470c7da6b5d1b81a7c8602490a71a147470125003317188"

# FetchMediaContent
body = json.dumps({
    "media_id": media_id,
    "knowledge_base_id": kb_id,
}).encode("utf-8")

# Try the trpc endpoint that qclaw_read_ima_content uses
req = urllib.request.Request(
    "https://ima.qq.com/openapi/wiki/v1/fetch_media_content",
    data=body, headers=headers, method="POST"
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw_data = resp.read().decode("utf-8")
        result = json.loads(raw_data)
        
        data = result.get("data", {})
        content = data.get("content", "")
        
        if not content:
            print("No content field, checking structure...")
            print(json.dumps(result, ensure_ascii=False)[:500])
        else:
            print(f"Raw content length: {len(content)}")
            
            # The content might be XML with escaped JSON
            # Try parsing as-is first
            text = content
            
            # If it's JSON string containing XML
            if content.startswith('{'):
                try:
                    inner = json.loads(content)
                    if isinstance(inner, dict) and "content" in inner:
                        text = inner["content"]
                except:
                    pass
            
            # Parse XML to plain text
            # Remove XML tags
            text = re.sub(r'<[^>]+>', '\n', text)
            # Decode HTML entities
            text = html.unescape(text)
            # Clean up
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = re.sub(r' {2,}', ' ', text)
            text = text.strip()
            
            print(f"Cleaned text length: {len(text)} chars")
            print(f"\nFirst 500 chars:\n{text[:500]}")
            
            # Save for testing
            test_path = r"C:\Users\22867\.qclaw\workspace\knowledge-scout\palantir_test.txt"
            with open(test_path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"\nSaved to: {test_path}")
            
            # Test interpreter
            print("\n" + "=" * 60)
            print("🧠 深度解读测试")
            article = {
                "title": "从 Palantir AIP 看：企业级 AI Agent 的行动治理链路",
                "content": text,
                "source": "由智AI洞见",
                "url": "",
            }
            
            score = score_article_depth(text, article["title"], article["source"], "")
            print(f"深度评分: {score}/10")
            
            result = interpret_article(article)
            if result:
                print(f"\n✅ 解读成功!")
                print(f"  质量评分: {result.quality_score}/10")
                print(f"  分类: {result.category}")
                print(f"  框架数: {len(result.frameworks)}")
                for fw in result.frameworks[:3]:
                    print(f"    - {fw[:80]}")
                print(f"  洞察数: {len(result.insights)}")
                for ins in result.insights[:3]:
                    print(f"    {ins[:100]}...")
                print(f"  启发数: {len(result.takeaways)}")
                for tw in result.takeaways[:3]:
                    print(f"    {tw[:100]}")
            else:
                print("❌ 评分不足，跳过")

except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.reason}")
    print(e.read().decode("utf-8", errors="ignore")[:500])
except Exception as e:
    print(f"Error: {e}")
