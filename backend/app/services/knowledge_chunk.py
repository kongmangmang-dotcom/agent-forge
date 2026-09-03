"""Text chunking for knowledge documents.

- ``chunk_text``: legacy paragraph/char splitter (AgentForge MVP).
- ``chunk_text_by_token``: Python port of SolarSense Java
  ``TokenTextSplitter`` as used in ``AiKnowledgeSegmentServiceImpl``:

      TokenTextSplitter.builder()
          .withChunkSize(segmentMaxTokens)
          .withMinChunkSizeChars(Integer.MAX_VALUE)  // disables punctuation cut
          .withMinChunkLengthToEmbed(1)
          .withMaxNumChunks(Integer.MAX_VALUE)
          .withKeepSeparator(true)
          .build();

  Encoding: cl100k_base (Spring AI default).
"""

from __future__ import annotations

import math

_ENCODER = None


def _encoder():
    global _ENCODER
    if _ENCODER is None:
        import tiktoken

        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return _ENCODER


def chunk_text_by_token(
    text: str,
    chunk_size: int = 800,
    *,
    min_chunk_size_chars: int | None = None,
    min_chunk_length_to_embed: int = 1,
    max_num_chunks: int | None = None,
    keep_separator: bool = True,
) -> list[str]:
    """Mirror Spring AI TokenTextSplitter with SolarSense's production knobs.

    SolarSense sets ``minChunkSizeChars = Integer.MAX_VALUE``, which disables
    punctuation-based early truncation; chunks are therefore contiguous token
    windows of ``chunk_size``.
    """
    content = text or ""
    if not content.strip():
        return []
    chunk_size = max(1, int(chunk_size))
    min_chars = (
        math.inf if min_chunk_size_chars is None else max(0, int(min_chunk_size_chars))
    )
    min_embed = max(0, int(min_chunk_length_to_embed))
    max_chunks = math.inf if max_num_chunks is None else max(1, int(max_num_chunks))

    enc = _encoder()
    tokens = enc.encode(content)
    if not tokens:
        return []

    punctuation = (".", "?", "!", "\n", "。", "？", "！")
    out: list[str] = []
    start = 0
    n = len(tokens)
    while start < n and len(out) < max_chunks:
        end = min(start + chunk_size, n)
        chunk_tokens = tokens[start:end]
        chunk_text = enc.decode(chunk_tokens)

        # Punctuation truncate only when window is "full" and min_chars allows it.
        if n - start > chunk_size and min_chars != math.inf:
            last_punct = -1
            for mark in punctuation:
                last_punct = max(last_punct, chunk_text.rfind(mark))
            if last_punct != -1 and last_punct > min_chars:
                chunk_text = chunk_text[: last_punct + 1]
                # Advance by tokens corresponding to truncated text
                consumed = len(enc.encode(chunk_text))
                end = start + max(1, consumed)

        piece = chunk_text.strip() if keep_separator else chunk_text.replace("\n", " ").strip()
        if len(piece) >= min_embed:
            out.append(piece)
        if end <= start:
            end = start + 1
        start = end
    return out


def chunk_text(text: str, max_chars: int = 800, overlap: int = 80) -> list[str]:
    """Legacy paragraph-first char chunker (kept for compatibility)."""
    content = (text or "").strip()
    if not content:
        return []
    max_chars = max(100, max_chars)
    overlap = max(0, min(overlap, max_chars // 4))

    paragraphs = [p.strip() for p in content.replace("\r\n", "\n").split("\n\n") if p.strip()]
    units = paragraphs if len(paragraphs) > 1 else [content]

    chunks: list[str] = []
    buf = ""
    for unit in units:
        if not buf:
            buf = unit
        elif len(buf) + 2 + len(unit) <= max_chars:
            buf = f"{buf}\n\n{unit}"
        else:
            chunks.extend(_split_long(buf, max_chars, overlap))
            buf = unit
    if buf:
        chunks.extend(_split_long(buf, max_chars, overlap))
    return [c for c in chunks if c.strip()]


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    out: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            window = text[start:end]
            cut = max(window.rfind("\n"), window.rfind(" "), window.rfind("。"), window.rfind("."))
            if cut >= max_chars // 2:
                end = start + cut + 1
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return out
