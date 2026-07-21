"""LLM 深度解读引擎 v2

使用 QClaw 本地 LLM 网关进行深度内容分析。
改用 Markdown 格式输出（解析可靠），非 JSON。
"""

import re
import httpx
import asyncio
from dataclasses import dataclass, field, asdict

# QClaw LLM Gateway
LLM_BASE = "http://127.0.0.1:59233/v1"
LLM_TOKEN = "e74df0923b103b7cd55f6d37cea0ecf3005785e2915205d0"
LLM_MODEL = "openclaw"
LLM_TIMEOUT = 60


@dataclass
class DeepInsight:
    title: str = ""
    source: str = ""
    url: str = ""
    thesis: str = ""
    category: str = ""
    frameworks: list[str] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    data_points: list[str] = field(default_factory=list)
    takeaways: list[str] = field(default_factory=list)
    content_length: int = 0
    quality_score: float = 0.0


PROMPT_TEMPLATE = """你是一个专业的AI行业分析师。请对以下文章进行深度分析，按照指定格式输出。

## 文章内容

{content}

## 输出格式（严格按以下结构，用中文回答）

【核心论点】
{thesis_placeholder}

【主题分类】
{category_placeholder}

【关键框架】
{framework_placeholder}

【洞察要点】
{insights_placeholder}

【数据看点】
{data_placeholder}

【行动启发】
{takeaways_placeholder}

## 填写规则

【核心论点】：一句话（20-50字）提炼文章最核心发现或趋势判断。必须是观点提炼，不能是"本文介绍了X"这种描述句。

【主题分类】：从以下选择最匹配的一个：AI Agent与工程、AI商业与趋势、企业数字化转型、AI创作与内容、知识管理与效率、人形机器人与硬件、跨领域综合

【关键框架】：文章中明确提出的方法论/模型/框架名称，每个一行，没有就写"无"

【洞察要点】：每条用"- "开头，20-60字。必须是因果分析、趋势判断、背后逻辑推理——绝对不要直接摘抄原文句子。insight 回答"为什么是这样"。

【数据看点】：文章中提到的关键数据，每条用"- "开头。格式："数据描述 + 具体数字"。没有就写"无关键数据"。

【行动启发】：每条用"- "开头，20-60字。面向产品经理/AI从业者的可执行建议。必须回答"可以怎么做"，与洞察要点完全不同，不能重复。

重要：
- 每个板块2-5条，宁缺毋滥
- 洞察要点和行动启发绝对不能出现相似表述
- 不要编造文章中不存在的信息"""


def _parse_section(text: str, tag: str) -> list[str]:
    """解析 Markdown 【tag】 段落到列表"""
    # 找到 【tag】 之后到下一个 【 或文末之间的内容
    pattern = re.escape(tag) + r'\s*\n(.*?)(?=\n\u3010|\Z)'
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return []
    content = match.group(1).strip()
    # 解析 "- xxx" 开头的条目
    items = []
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
        # 移除 - 、* 、数字. 前缀
        line = re.sub(r'^[-*•]\s*', '', line)
        line = re.sub(r'^\d+[.、]\s*', '', line)
        # 跳过明显的占位符
        if line in ('无', '无关键数据', '略', '（无）', '暂无'):
            continue
        if len(line) >= 6:
            items.append(line)
    return items


def _parse_single(text: str, tag: str) -> str:
    """解析 Markdown 【tag】 段落到单行"""
    matches = _parse_section(text, tag)
    return matches[0] if matches else ""


def _parse_llm_markdown(text: str) -> dict:
    """解析 LLM 返回的 Markdown 格式解读"""
    result = {
        "thesis": _parse_single(text, "【核心论点】"),
        "category": _parse_single(text, "【主题分类】"),
        "frameworks": _parse_section(text, "【关键框架】"),
        "insights": _parse_section(text, "【洞察要点】"),
        "data_points": _parse_section(text, "【数据看点】"),
        "takeaways": _parse_section(text, "【行动启发】"),
    }
    # 计算质量分
    total_items = (len(result.get("insights", [])) +
                   len(result.get("takeaways", [])) +
                   (1 if result.get("thesis") else 0))
    result["quality_score"] = min(total_items * 1.2, 10.0)
    return result


async def _call_llm(prompt: str) -> str | None:
    """调用 QClaw 本地 LLM，返回原始文本"""
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            resp = await client.post(
                f"{LLM_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {LLM_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": "你是一个专业的AI行业分析师。严格按照指定格式输出分析结果，不要额外发挥。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
            )
            if resp.status_code != 200:
                print(f"    LLM API error: {resp.status_code} {resp.text[:200]}")
                return None

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return content
    except Exception as e:
        print(f"    LLM call failed: {e}")
        return None


async def interpret_article_async(article: dict) -> DeepInsight | None:
    """使用 LLM 对单篇文章进行深度解读"""
    title = article.get("title", "")
    content = article.get("content", "")
    source = article.get("source", "")
    url = article.get("url", "")

    if not content or len(content) < 100:
        return None

    # 截断过长内容
    max_chars = 8000
    content_for_llm = content[:max_chars]
    if len(content) > max_chars:
        content_for_llm += f"\n\n[原文共 {len(content)} 字，此处仅截取前 {max_chars} 字]"

    prompt = PROMPT_TEMPLATE.format(
        content=content_for_llm,
        thesis_placeholder="（填写一句话核心论点）",
        category_placeholder="（选择主题分类）",
        framework_placeholder="（每行一个框架名，没 - 有就写无）",
        insights_placeholder="（每行用 - 开头，2-5条分析性洞察）",
        data_placeholder="（每行用 - 开头，没 - 有就写无关键数据）",
        takeaways_placeholder="（每行用 - 开头，2-5条行动建议）",
    )

    raw = await _call_llm(prompt)
    if not raw:
        return None

    result = _parse_llm_markdown(raw)

    try:
        return DeepInsight(
            title=title,
            source=source,
            url=url,
            thesis=result.get("thesis", ""),
            category=result.get("category", "跨领域综合"),
            frameworks=result.get("frameworks", []),
            insights=result.get("insights", []),
            data_points=result.get("data_points", []),
            takeaways=result.get("takeaways", []),
            content_length=len(content),
            quality_score=result.get("quality_score", 5.0),
        )
    except Exception as e:
        print(f"    Failed to construct DeepInsight: {e}")
        return None


def interpret_article(article: dict) -> DeepInsight | None:
    """同步包装器"""
    try:
        return asyncio.run(interpret_article_async(article))
    except Exception as e:
        print(f"    interpret_article sync error: {e}")
        return None


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.path.insert(0, r'C:\Users\22867\.qclaw\workspace\knowledge-scout')

    async def test():
        from content_fetcher import fetch_full_article
        text = fetch_full_article('https://36kr.com/p/3899597215745664', '36kr')
        if not text:
            print("Fetch failed")
            return
        article = {
            'title': '具身智能产业新周期',
            'content': text,
            'source': '36kr',
            'url': '',
        }
        r = await interpret_article_async(article)
        if r:
            d = asdict(r)
            for k in ['thesis', 'category', 'frameworks', 'insights', 'takeaways', 'quality_score']:
                v = d.get(k, '')
                if isinstance(v, list):
                    print(f'{k}:')
                    for i, x in enumerate(v):
                        print(f'  {i+1}. {x}')
                else:
                    print(f'{k}: {v}')
        else:
            print("FAILED")

    asyncio.run(test())
