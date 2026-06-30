from __future__ import annotations

import re


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, size: int = 1200, overlap: int = 160) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start, end), text.rfind("。", start, end))
            if boundary > start + size // 2:
                end = boundary + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return [chunk for chunk in chunks if chunk]


def query_terms(query: str) -> set[str]:
    latin = re.findall(r"[A-Za-z0-9_.%-]{2,}", query.lower())
    chinese = re.findall(r"[\u4e00-\u9fff]{2,}", query)
    bigrams = [word[i : i + 2] for word in chinese for i in range(len(word) - 1)]
    return set(latin + chinese + bigrams)

