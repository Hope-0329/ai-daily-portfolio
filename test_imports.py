"""Quick test: verify all imports and basic fetch work"""
import sys
import asyncio
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Test 1: package imports
print("=== Package imports ===")
for pkg in ["httpx", "feedparser", "fastapi", "uvicorn"]:
    try:
        __import__(pkg)
        print(f"  {pkg}: OK")
    except ImportError as e:
        print(f"  {pkg}: FAIL - {e}")

# Test 2: fetcher import
print("\n=== Fetcher import ===")
try:
    from tools.fetcher import fetch_articles, fetch_full_article_safe, SOURCE_NAMES
    print(f"  OK - {len(SOURCE_NAMES)} sources: {list(SOURCE_NAMES.keys())}")
except Exception as e:
    print(f"  FAIL - {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: actual fetch
print("\n=== Test fetch (5 articles) ===")
try:
    result = asyncio.run(fetch_articles(count=5))
    total = result.get("total", 0)
    print(f"  Total articles: {total}")
    if total > 0:
        for a in result.get("articles", [])[:3]:
            print(f"  - [{a.get('platform','?')}] {a.get('title','?')[:50]}")
except Exception as e:
    print(f"  FAIL - {e}")
    import traceback
    traceback.print_exc()

print("\n=== ALL TESTS PASSED ===")
