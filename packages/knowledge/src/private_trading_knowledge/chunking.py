from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from private_trading_knowledge.parsing import ExtractedPage, normalize_text


@dataclass(slots=True)
class ChunkDraft:
    ordinal: int
    content: str
    token_count: int
    content_hash: str
    heading_path: str | None
    page_start: int | None
    page_end: int | None


def estimate_tokens(text: str) -> int:
    # Lightweight estimator; good enough for chunk sizing without tokenizer dep.
    return max(1, len(text) // 4)


def chunk_pages(
    pages: list[ExtractedPage],
    *,
    target_tokens: int = 650,
    overlap_ratio: float = 0.15,
) -> list[ChunkDraft]:
    overlap_tokens = max(20, int(target_tokens * overlap_ratio))
    chunks: list[ChunkDraft] = []
    buffer = ""
    heading: str | None = None
    page_start: int | None = None
    page_end: int | None = None

    def flush() -> None:
        nonlocal buffer, heading, page_start, page_end
        content = normalize_text(buffer)
        if not content:
            buffer = ""
            return
        ordinal = len(chunks)
        chunks.append(
            ChunkDraft(
                ordinal=ordinal,
                content=content,
                token_count=estimate_tokens(content),
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                heading_path=heading,
                page_start=page_start,
                page_end=page_end,
            )
        )
        # overlap tail
        words = content.split()
        keep = max(1, overlap_tokens)
        # approximate tokens→words
        tail_words = words[-keep:] if len(words) > keep else words
        buffer = " ".join(tail_words)
        page_start = page_end
        heading = heading

    for page in pages:
        text = normalize_text(page.text)
        if not text:
            continue
        # heading-aware split on markdown-like headings
        parts = re.split(r"(?m)(?=^#{1,3}\s+)", text) if "#" in text else [text]
        for part in parts:
            part = part.strip()
            if not part:
                continue
            part_heading = page.heading_path
            first_line = part.split("\n", 1)[0]
            if first_line.startswith("#"):
                part_heading = first_line.lstrip("#").strip()
            if page_start is None:
                page_start = page.page
            page_end = page.page
            heading = part_heading or heading
            if estimate_tokens(buffer) + estimate_tokens(part) > target_tokens and buffer:
                flush()
            buffer = f"{buffer}\n\n{part}".strip() if buffer else part
            if estimate_tokens(buffer) >= target_tokens:
                flush()

    if normalize_text(buffer):
        # final flush without forcing overlap recycle
        content = normalize_text(buffer)
        chunks.append(
            ChunkDraft(
                ordinal=len(chunks),
                content=content,
                token_count=estimate_tokens(content),
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                heading_path=heading,
                page_start=page_start,
                page_end=page_end,
            )
        )
    return chunks
