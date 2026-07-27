"""Pipeline 共享 LLM 客户端。"""

from __future__ import annotations

from openai import AsyncOpenAI

from src.config import Settings, ensure_api_key, get_settings


def get_llm_client(settings: Settings | None = None, llm_client: AsyncOpenAI | None = None) -> AsyncOpenAI:
    """获取或创建 DeepSeek 异步客户端。"""
    if llm_client is not None:
        return llm_client
    cfg = settings or get_settings()
    ensure_api_key(cfg)
    return AsyncOpenAI(api_key=cfg.deepseek_api_key, base_url=cfg.deepseek_base_url)


async def chat_completion(
    prompt: str,
    *,
    settings: Settings | None = None,
    llm_client: AsyncOpenAI | None = None,
    temperature: float = 0.2,
    max_tokens: int = 512,
) -> str:
    """调用 DeepSeek 聊天补全并返回文本。"""
    cfg = settings or get_settings()
    client = get_llm_client(cfg, llm_client)
    response = await client.chat.completions.create(
        model=cfg.deepseek_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (response.choices[0].message.content or "").strip()
