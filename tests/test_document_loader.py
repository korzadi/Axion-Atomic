import io
import zipfile

import pytest

from rag.document_loader import DocumentLoadError, extract_document


def test_extracts_utf8_text_and_markdown():
    assert extract_document("notes.txt", b"\xef\xbb\xbfHola") == ("Hola", "notes.txt")
    assert extract_document("guide.MD", b"# AXION") == ("# AXION", "guide.MD")


def test_rejects_unsupported_empty_oversized_and_non_utf8_files():
    for name, data in [("image.png", b"x"), ("empty.txt", b""), ("bad.txt", b"\xff")]:
        with pytest.raises(DocumentLoadError):
            extract_document(name, data)
    with pytest.raises(DocumentLoadError):
        extract_document("large.md", b"x" * (5 * 1024 * 1024 + 1))


def test_extracts_docx_without_trusting_client_mime_type():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>AXION documento</w:t></w:r></w:p></w:body></w:document>',
        )
    assert extract_document("manual.docx", stream.getvalue())[0] == "AXION documento"


def test_rejects_invalid_docx_and_pdf():
    with pytest.raises(DocumentLoadError):
        extract_document("broken.docx", b"not a zip")
    with pytest.raises(DocumentLoadError):
        extract_document("broken.pdf", b"not a pdf")
