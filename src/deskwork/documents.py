"""Turns any file in the inbox into plain text the agent can reason about.

PDFs are tried as real text first (pypdf) since that's free and exact. Some
PDFs -- notably a browser/Gmail "Print to PDF" export -- carry no extractable
text layer at all (confirmed directly: pypdf and poppler's own pdftotext both
return empty on such a file, even though it isn't a scanned image either --
the glyphs are vector-drawn without a Unicode mapping). The only way to
recover that content is to rasterize each page and OCR it, so that path is
the fallback here rather than a hard failure.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pymupdf
import pytesseract
from pypdf import PdfReader

_tesseract_cmd = os.environ.get("TESSERACT_CMD")
if _tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd

# A short OCR'd page ("Mi Gmail", a lone icon caption) is a sign pypdf's text
# layer was actually present but sparse, not that OCR is needed -- only
# escalate to rasterize-and-OCR when the text layer is genuinely empty.
_MIN_TEXT_LAYER_CHARS = 20


def _extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if len(text.strip()) >= _MIN_TEXT_LAYER_CHARS:
        return text
    return _ocr_pdf(path)


def _ocr_pdf(path: Path) -> str:
    doc = pymupdf.open(str(path))
    pages = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=300)
            img_path = Path(tmp_dir) / f"page_{i}.png"
            pix.save(str(img_path))
            pages.append(pytesseract.image_to_string(str(img_path)))
    return "\n".join(pages)


def read_document_text(path: str | Path) -> str:
    """Returns the plain-text content of a document in the inbox.

    Raises ValueError for a file type this agent doesn't know how to read,
    rather than silently returning empty text -- an empty read should never
    be confused with an empty document.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_text(path)
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8")
    raise ValueError(f"Unsupported document type: {suffix} ({path.name})")
