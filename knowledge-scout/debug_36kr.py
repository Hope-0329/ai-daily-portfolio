import sys, re, ssl, urllib.request
sys.stdout.reconfigure(encoding='utf-8')

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

url = "https://36kr.com/p/3899597215745664?f=rss"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

print(f"HTML length: {len(html)}")

# Find all div class patterns
classes = set(re.findall(r'class="([^"]*)"', html))
print(f"\nClasses found ({len(classes)}):")
for c in sorted(classes):
    if 'content' in c.lower() or 'article' in c.lower() or 'detail' in c.lower() or 'body' in c.lower():
        print(f"  -> {c}")

# Check for common patterns
for pat_name, pattern in [
    ("articleContent", r'class="[^"]*article[^"]*[Cc]ontent[^"]*"'),
    ("richContent", r'class="[^"]*rich[^"]*[Cc]ontent[^"]*"'),
    ("mainContent", r'class="[^"]*main[^"]*[Cc]ontent[^"]*"'),
    ("detailContent", r'class="[^"]*detail[^"]*[Cc]ontent[^"]*"'),
]:
    matches = re.findall(pattern, html)
    if matches:
        print(f"\n{pat_name}: {len(matches)} matches")
        for m in matches[:3]:
            print(f"  {m}")

# Show first 500 chars
print(f"\nFirst 500 chars:")
print(html[:500])

# Check if it's a SPA (React/Vue)
if "window.__NUXT__" in html or "__NEXT_DATA__" in html or "window.__INITIAL_STATE__" in html:
    print("\n⚠️ SPA detected - content may be in JS data")
    # Try extracting from JSON data
    for key in ["window.__NUXT__", "__NEXT_DATA__", "window.__INITIAL_STATE__"]:
        idx = html.find(key)
        if idx >= 0:
            print(f"Found {key} at position {idx}")
            print(html[idx:idx+300])

# Look for articleDetailContent specifically
idx = html.find("articleDetailContent")
if idx >= 0:
    print(f"\nFound 'articleDetailContent' at position {idx}")
    # Get surrounding context
    start = max(0, idx - 200)
    end = min(len(html), idx + 500)
    print(html[start:end])
else:
    print("\n' articleDetailContent ' NOT FOUND in HTML!")
    # Try other possible content containers
    for tag in ["article-body", "article_content", "post-content", "entry-content", "main-content"]:
        idx = html.find(tag)
        if idx >= 0:
            print(f"Found '{tag}' at position {idx}")
