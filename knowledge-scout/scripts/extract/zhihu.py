"""鐭ヤ箮 鈥?鐑 + 鎼滅储锛屽亸琛屼笟璁ㄨ鑰岄潪绾妧鏈?""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.env_reader import get_env
from utils.interest_filter import is_quality_article, classify_article
import httpx
from .base import BaseExtractor, Article


class ZhihuExtractor(BaseExtractor):
    HOT_LIST_URL = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total"

    async def fetch(self) -> list[Article]:
        zc0 = get_env("ZHIHU_ZC0", "")
        cookies = {"z_c0": zc0} if zc0 else {}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "x-api-version": "3.0.40",
        }

        articles = []
        async with httpx.AsyncClient(cookies=cookies, headers=headers) as session:
            # 鐑
            try:
                async with session.get(
                    self.HOT_LIST_URL, params={"limit": 50}, timeout=10
                ) as resp:
                    data = resp.json()
                for item in data.get("data", []):
                    target = item.get("target", {})
                    title = target.get("title", "")
                    excerpt = target.get("excerpt", "")
                    if not title:
                        continue

                    if not is_quality_article(title, excerpt):
                        continue

                    category, score = classify_article(title, excerpt)
                    hot_val = target.get("detail_count", 0) or target.get("vote_count", 0) or 0
                    final_score = score * 2 + hot_val * 0.01

                    url = f"https://api.zhihu.com/questions/{target.get('id', '')}"
                    if not target.get("id"):
                        url = target.get("url", "")

                    articles.append(Article(
                        platform="zhihu",
                        title=title,
                        url=url,
                        summary=excerpt[:200],
                        author=target.get("author", {}).get("name", ""),
                        published=str(target.get("created", "")),
                        category=category,
                        raw_score=final_score,
                        metadata={"hot_value": hot_val, "type": "hot_list"},
                    ))
            except Exception:
                pass

        return articles
