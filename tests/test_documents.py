from pathlib import Path

import pytest

from deskwork.documents import read_document_text

SAMPLE_INBOX = Path(__file__).parent.parent / "sample_inbox"


def test_reads_plain_text_document():
    text = read_document_text(SAMPLE_INBOX / "invoice_overdue.txt")
    assert "INV-2231" in text
    assert "412.50" in text


def test_unsupported_suffix_raises():
    with pytest.raises(ValueError):
        read_document_text(Path("something.docx"))
