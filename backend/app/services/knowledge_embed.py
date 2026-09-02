"""Embedding backends for knowledge segments.

Uses OpenAI-compatible HTTP API when configured; otherwise a local hash embedding
so ingest/search still works offline for demos.
"""

from __future__ import annotations

import hashlib
import math
import struct

import httpx

from app.core.config import settings
from app.core.exceptions import ValidationError

LOCAL_DIM = 384


def embedding_backend_name() -> str:
    if settings.embedding_api_url.strip() and settings.embedding_api_key.strip():
        return "openai_compatible"
    return "local_hash"


def default_embedding_model() -> str:
    return (settings.embedding_model or "text-embedding-3-small").strip()


async def embed_texts(texts: list[str], model: str | None = None) -> list[list[float]]:
    cleaned = [(t or "").strip() or " " for t in texts]
    if not cleaned:
        return []
    if embedding_backend_name() == "openai_compatible":
        return await _embed_openai(cleaned, model or default_embedding_model())
    return [_local_embed(t) for t in cleaned]


async def embed_query(query: str, model: str | None = None) -> list[float]:
    vectors = await embed_texts([query], model=model)
    return vectors[0]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / math.sqrt(na * nb)


async def _embed_openai(texts: list[str], model: str) -> list[list[float]]:
    url = settings.embedding_api_url.strip().rstrip("/")
    if not url.endswith("/embeddings"):
        url = f"{url}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.embedding_api_key.strip()}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "input": texts}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise ValidationError(f"Embedding API 调用失败: {exc}") from exc

    items = data.get("data")
    if not isinstance(items, list) or len(items) != len(texts):
        raise ValidationError("Embedding API 返回格式异常")
    # API may return unsorted indices
    ordered = sorted(items, key=lambda x: int(x.get("index", 0)))
    vectors: list[list[float]] = []
    for item in ordered:
        emb = item.get("embedding")
        if not isinstance(emb, list) or not emb:
            raise ValidationError("Embedding API 缺少 embedding 字段")
        vectors.append([float(v) for v in emb])
    return vectors


def _local_embed(text: str) -> list[float]:
    """Deterministic bag-of-token hash embedding (L2-normalized)."""
    vec = [0.0] * LOCAL_DIM
    tokens = _tokenize(text)
    if not tokens:
        tokens = [" "]
    for tok in tokens:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        # Use several uint32 from hash to sprinkle energy across dims.
        for i in range(0, 16, 4):
            (idx_raw,) = struct.unpack_from(">I", digest, i)
            sign = 1.0 if (idx_raw & 1) == 0 else -1.0
            idx = (idx_raw >> 1) % LOCAL_DIM
            vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _tokenize(text: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    for ch in text.lower():
        if ch.isalnum() or ("\u4e00" <= ch <= "\u9fff"):
            if "\u4e00" <= ch <= "\u9fff":
                if buf:
                    out.append("".join(buf))
                    buf = []
                out.append(ch)
            else:
                buf.append(ch)
        else:
            if buf:
                out.append("".join(buf))
                buf = []
    if buf:
        out.append("".join(buf))
    return out
