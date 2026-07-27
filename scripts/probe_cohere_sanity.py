"""探测 Cohere Sanity API。"""

from __future__ import annotations

import asyncio
import json
from urllib.parse import quote

import aiohttp

from src.sources.utils import USER_AGENT

QUERY = '*[_type=="post"]|order(publishedAt desc)[0...10]{title,"slug":slug.current,publishedAt}'


async def main() -> None:
    url = f"https://rjtqmwfu.api.sanity.io/v2021-10-21/data/query/production?query={quote(QUERY)}"
    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30), ssl=False) as response:
            text = await response.text()
            print("status", response.status)
            print(text[:800])
            if response.status == 200:
                payload = json.loads(text)
                result = payload.get("result") or []
                print("count", len(result))
                if result:
                    print("sample", result[0])


if __name__ == "__main__":
    asyncio.run(main())
