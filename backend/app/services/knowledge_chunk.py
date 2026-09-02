"""Simple text chunking for knowledge documents."""


def chunk_text(text: str, max_chars: int = 800, overlap: int = 80) -> list[str]:
    content = (text or "").strip()
    if not content:
        return []
    max_chars = max(100, max_chars)
    overlap = max(0, min(overlap, max_chars // 4))

    # Prefer paragraph boundaries when possible.
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
            # Prefer break at whitespace near the end.
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
