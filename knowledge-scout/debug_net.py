import requests, re

s = requests.Session()
s.headers['User-Agent'] = 'Mozilla/5.0'

# GitHub
r = s.get('https://github.com/trending?since=daily', timeout=15)
html = r.text
# find any repo links
repo_matches = re.findall(r'href="/([^/]+/[^/"]+)"', html)
repos = [m for m in repo_matches if '/' in m and not m.startswith(('login', 'signup', 'settings', 'features', 'marketplace', 'explore', 'topics', 'collections', 'events', 'sponsors'))][:20]
print(f'GitHub repos: {repos}')
# find h2 tags
h2s = re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.DOTALL)
print(f'GitHub h2 count: {len(h2s)}, sample={h2s[:3]}')

# HuggingFace
r2 = s.get('https://huggingface.co/api/papers', headers={'Accept': 'application/json'}, timeout=15)
data = r2.json()
print(f'\nHF type={type(data).__name__}')
if isinstance(data, list):
    print(f'HF len={len(data)}')
    # check all items are dicts
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            print(f'HF item[{i}] not dict: {type(item).__name__} = {str(item)[:100]}')
    if data:
        print(f'HF[0] keys={list(data[0].keys())}')
        print(f'HF[0] title={data[0].get("title","")[:80]}')

# ReadAITime
r3 = s.get('https://www.readaitime.com/', timeout=15)
html3 = r3.text
# find all hrefs
all_links = re.findall(r'href="([^"]+)"', html3)
news_links = [l for l in all_links if '/news/' in l]
print(f'\nReadAI news links: {len(news_links)}')
for l in news_links[:5]:
    # extract title near each link
    idx = html3.find(l)
    chunk = html3[max(0,idx-200):idx+300]
    title_match = re.search(r'>([^<]{10,100})<', chunk[200:])
    if title_match:
        print(f'  {l} -> {title_match.group(1).strip()[:80]}')
    else:
        print(f'  {l} -> (no title)')
