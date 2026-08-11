"""Simple chunk + keyword retrieval before structured extraction (RAG-lite)."""

import re
from typing import Iterable


def chunk_text(text: str, max_chars: int = 1200) -> list[tuple[str, str]]:
    """Return (chunk_id, chunk_text) preserving page markers when present."""
    if not text.strip():
        return []
    sections = re.split(r"(?=--- Page \d+ ---)", text)
    chunks: list[tuple[str, str]] = []
    buf = ""
    cid = 0
    for sec in sections:
        if len(buf) + len(sec) < max_chars:
            buf += sec
        else:
            if buf.strip():
                chunks.append((f"c{cid}", buf.strip()))
                cid += 1
            buf = sec
    if buf.strip():
        chunks.append((f"c{cid}", buf.strip()))
    return chunks


def retrieve_relevant_chunks(
    text: str,
    field_names: Iterable[str],
    field_keywords: dict[str, list[str]] | None = None,
    top_k: int = 3,
) -> str:
    field_keywords = field_keywords or {}
    chunks = chunk_text(text)
    if not chunks:
        return text[:4000]

    scores: list[tuple[float, str]] = []
    for cid, chunk in chunks:
        lower = chunk.lower()
        score = 0.0
        for fname in field_names:
            for kw in field_keywords.get(fname, [fname.replace("_", " ")]):
                if kw.lower() in lower:
                    score += 1.0
        scores.append((score, chunk))

    scores.sort(key=lambda x: -x[0])
    selected = [c for s, c in scores[:top_k] if s > 0]
    if not selected:
        selected = [c for _, c in chunks[:top_k]]
    return "\n\n".join(selected)
