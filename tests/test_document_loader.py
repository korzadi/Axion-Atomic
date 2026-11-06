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


def _pdf_bytes(*, pages=1, password=None):
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    if password:
        writer.encrypt(password)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_rejects_encrypted_and_excessive_page_documents():
    with pytest.raises(DocumentLoadError, match="cifrados"):
        extract_document("private.pdf", _pdf_bytes(password="secret"))
    with pytest.raises(DocumentLoadError, match="250 páginas"):
        extract_document("too-many.pdf", _pdf_bytes(pages=251))


def test_pdf_with_no_extractable_text_is_rejected():
    with pytest.raises(DocumentLoadError, match="No se encontró texto"):
        extract_document("blank.pdf", _pdf_bytes())


def test_docx_rejects_archive_with_too_many_entries():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Texto válido</w:t></w:r></w:p></w:body></w:document>',
        )
        for index in range(1_000):
            archive.writestr(f"extra/{index}.txt", "")
    with pytest.raises(DocumentLoadError, match="demasiados componentes"):
        extract_document("many.docx", stream.getvalue())


def test_document_loader_sanitizes_windows_path_and_bounds_display_name():
    text, name = extract_document(r"C:\\private\\manual.txt", b"Contenido seguro")
    assert text == "Contenido seguro"
    assert name == "manual.txt"
    _, long_name = extract_document(("a" * 600) + ".txt", b"ok")
    assert len(long_name) == 500


def test_docx_rejects_excessive_uncompressed_archive_size():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Texto válido</w:t></w:r></w:p></w:body></w:document>',
        )
        archive.writestr("word/media/payload.bin", b"x" * (20 * 1024 * 1024 + 1))
    # El archivo comprimido cabe en el límite HTTP, pero su contenido expandido no.
    assert len(stream.getvalue()) < 5 * 1024 * 1024
    with pytest.raises(DocumentLoadError, match="límite interno"):
        extract_document("bomb.docx", stream.getvalue())


def test_docx_rejects_extracted_text_over_limit():
    stream = io.BytesIO()
    oversized = "x" * 100_001
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t>' + oversized + '</w:t></w:r></w:p></w:body></w:document>'
    )
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", xml)
    with pytest.raises(DocumentLoadError, match="100000 caracteres"):
        extract_document("oversized.docx", stream.getvalue())



def test_document_loader_normalizes_untrusted_paths_without_exposing_directories():
    cases = [
        ("../../private/notes.txt", "notes.txt"),
        (r"..\\..\\private\\notes.MD", "notes.MD"),
        ("/etc/axion/guide.PDF", "guide.PDF"),
    ]
    for supplied_name, expected_name in cases:
        _, safe_name = extract_document(supplied_name, b"Contenido")
        assert safe_name == expected_name


@pytest.mark.parametrize("filename", ["", "   ", None, 123])
def test_document_loader_rejects_invalid_filename_types(filename):
    with pytest.raises(DocumentLoadError, match="nombre válido"):
        extract_document(filename, b"Contenido")
