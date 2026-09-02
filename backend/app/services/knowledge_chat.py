"""OpenAI-compatible chat completion for knowledge Q&A."""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.exceptions import ValidationError


def chat_backend_name() -> str:
    url = (settings.chat_api_url or settings.embedding_api_url or "").strip()
    key = (settings.chat_api_key or settings.embedding_api_key or "").strip()
    if url and key:
        return "openai_compatible"
    return "extractive"


def default_chat_model() -> str:
    return (settings.chat_model or "gpt-4o-mini").strip()


async def chat_complete(system: str, user: str, model: str | None = None) -> str:
    if chat_backend_name() != "openai_compatible":
        raise ValidationError("未配置 Chat API")

    base = (settings.chat_api_url or settings.embedding_api_url).strip().rstrip("/")
    # Accept either .../v1 or .../v1/chat/completions
    if base.endswith("/chat/completions"):
        url = base
    elif base.endswith("/embeddings"):
        url = base[: -len("/embeddings")] + "/chat/completions"
    elif base.endswith("/v1"):
        url = f"{base}/chat/completions"
    else:
        url = f"{base}/chat/completions"

    key = (settings.chat_api_key or settings.embedding_api_key).strip()
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model or default_chat_model(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise ValidationError(f"Chat API 调用失败: {exc}") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValidationError("Chat API 返回格式异常") from exc
    if not isinstance(content, str) or not content.strip():
        raise ValidationError("Chat API 返回空内容")
    return content.strip()
