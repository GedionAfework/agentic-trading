from __future__ import annotations

from dataclasses import dataclass

from private_trading_core.errors import AppError

ALLOWED_MIME = {
    "text/plain": ".txt",
    "text/markdown": ".md",
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
PARSER_VERSION = "knowledge-parser-v1"


@dataclass(slots=True)
class ExtractedPage:
    page: int | None
    text: str
    heading_path: str | None = None


def validate_upload(filename: str, content_type: str | None, data: bytes) -> str:
    if len(data) == 0:
        raise AppError("INVALID_UPLOAD", "Empty file", retryable=False)
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError("INVALID_UPLOAD", "File exceeds size limit", retryable=False)

    mime = (content_type or "").split(";")[0].strip().lower()
    lower_name = filename.lower()
    if mime not in ALLOWED_MIME:
        if lower_name.endswith(".txt"):
            mime = "text/plain"
        elif lower_name.endswith(".md"):
            mime = "text/markdown"
        elif lower_name.endswith(".pdf"):
            mime = "application/pdf"
        elif lower_name.endswith(".docx"):
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            raise AppError("INVALID_UPLOAD", "Unsupported file type", retryable=False)
    return mime


def extract_text(mime: str, data: bytes) -> list[ExtractedPage]:
    if mime in {"text/plain", "text/markdown"}:
        text = data.decode("utf-8", errors="replace")
        return [ExtractedPage(page=1, text=text, heading_path=None)]

    if mime == "application/pdf":
        import fitz  # pymupdf

        pages: list[ExtractedPage] = []
        with fitz.open(stream=data, filetype="pdf") as doc:
            for i, page in enumerate(doc, start=1):
                pages.append(ExtractedPage(page=i, text=page.get_text("text"), heading_path=None))
        return pages

    if mime.endswith("wordprocessingml.document"):
        from io import BytesIO

        from docx import Document

        document = Document(BytesIO(data))
        blocks: list[str] = []
        current_heading: str | None = None
        pages: list[ExtractedPage] = []
        for para in document.paragraphs:
            style = (para.style.name if para.style else "") or ""
            text = para.text.strip()
            if not text:
                continue
            if style.startswith("Heading"):
                if blocks:
                    pages.append(
                        ExtractedPage(
                            page=None,
                            text="\n".join(blocks),
                            heading_path=current_heading,
                        )
                    )
                    blocks = []
                current_heading = text
            else:
                blocks.append(text)
        if blocks:
            pages.append(
                ExtractedPage(page=None, text="\n".join(blocks), heading_path=current_heading)
            )
        if not pages:
            pages = [ExtractedPage(page=1, text="", heading_path=None)]
        return pages

    raise AppError("INVALID_UPLOAD", "Unsupported file type", retryable=False)


def normalize_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n")]
    collapsed: list[str] = []
    blank = 0
    for line in lines:
        if not line:
            blank += 1
            if blank <= 1:
                collapsed.append("")
            continue
        blank = 0
        collapsed.append(line)
    return "\n".join(collapsed).strip()
