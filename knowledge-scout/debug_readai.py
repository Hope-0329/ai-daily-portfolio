import requests, re
s = requests.Session()
s.headers['User-Agent'] = 'Mozilla/5.0'
r = s.get('https://www.readaitime.com/', timeout=15)
html = r.text

# find a specific news link and its surrounding context
m = re.search(r'href="(/news/[^"]+)"', html)
if m:
    link = m.group(1)
    idx = html.find(link)
    # print 600 chars around the link
    start = max(0, idx - 100)
    end = min(len(html), idx + 600)
    chunk = html[start:end]
    print(f'Chunk around "{link}":')
    print(chunk[:800])
    print('...')
    print(chunk[-200:])
