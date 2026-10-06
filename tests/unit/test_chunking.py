import pytest
from private_trading_core.errors import AppError
from private_trading_knowledge.chunking import chunk_pages, estimate_tokens
from private_trading_knowledge.parsing import ExtractedPage, normalize_text, validate_upload


def test_normalize_and_chunk_heading_aware() -> None:
    pages = [
        ExtractedPage(
            page=1,
            text=(
                "# Safer Entry\n"
                + ("BOS with significant volume is required. " * 40)
                + "\n## Retest\n"
                + ("Low volume retest confirms the entry. " * 40)
            ),
        )
    ]
    chunks = chunk_pages(pages, target_tokens=120, overlap_ratio=0.1)
    assert len(chunks) >= 2
    assert all(c.token_count >= 1 for c in chunks)
    assert estimate_tokens("abcd") == 1


def test_reject_exe_upload() -> None:
    with pytest.raises(AppError) as exc:
        validate_upload("malware.exe", "application/octet-stream", b"MZ")
    assert exc.value.code == "INVALID_UPLOAD"


def test_normalize_collapses_blank_lines() -> None:
    text = normalize_text("a\n\n\n\nb")
    assert text == "a\n\nb"
