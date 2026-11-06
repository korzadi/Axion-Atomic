"""Extracción segura y acotada de documentos para la base de conocimiento."""
from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath

from pypdf import PdfReader

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 100_000
MAX_PDF_PAGES = 250
MAX_DOCX_ENTRIES = 1_000
MAX_DOCX_UNCOMPRESSED = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


class DocumentLoadError(ValueError):
    """El archivo no es compatible o excede límites seguros."""


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise DocumentLoadError("El documento debe estar codificado en UTF-8.") from None


def _extract_pdf(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise DocumentLoadError("No se admiten documentos PDF cifrados.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise DocumentLoadError("El PDF supera el límite de 250 páginas.")
        parts = []
        total = 0
        for page in reader.pages:
            value = page.extract_text() or ""
            total += len(value)
            if total > MAX_TEXT_CHARS:
                raise DocumentLoadError("El texto extraído supera 100000 caracteres.")
            parts.append(value)
        return "\n\n".join(parts)
    except DocumentLoadError:
        raise
    except Exception:
        raise DocumentLoadError("No se pudo leer el documento PDF.") from None


def _extract_docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_DOCX_ENTRIES:
                raise DocumentLoadError("El documento DOCX contiene demasiados componentes.")
            if sum(item.file_size for item in entries) > MAX_DOCX_UNCOMPRESSED:
                raise DocumentLoadError("El documento DOCX supera el límite interno permitido.")
            names = {item.filename for item in entries}
            if "word/document.xml" not in names:
                raise DocumentLoadError("El archivo no contiene un documento DOCX válido.")
            xml = archive.read("word/document.xml")
        root = ET.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = []
        total = 0
        for paragraph in root.findall(".//w:p", ns):
            value = "".join(node.text or "" for node in paragraph.findall(".//w:t", ns))
            total += len(value)
            if total > MAX_TEXT_CHARS:
                raise DocumentLoadError("El texto extraído supera 100000 caracteres.")
            if value:
                paragraphs.append(value)
        return "\n".join(paragraphs)
    except DocumentLoadError:
        raise
    except (zipfile.BadZipFile, ET.ParseError, KeyError, OSError):
        raise DocumentLoadError("No se pudo leer el documento DOCX.") from None
    except Exception:
        raise DocumentLoadError("No se pudo leer el documento DOCX.") from None


def extract_document(filename: str, data: bytes) -> tuple[str, str]:
    """Extrae texto de TXT, Markdown, PDF o DOCX sin confiar en el MIME del cliente."""
    if not isinstance(filename, str) or not filename.strip():
        raise DocumentLoadError("El archivo debe tener un nombre válido.")
    suffix = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise DocumentLoadError("Formato no admitido. Usa TXT, MD, PDF o DOCX.")
    if not isinstance(data, bytes) or not data:
        raise DocumentLoadError("El archivo está vacío.")
    if len(data) > MAX_FILE_BYTES:
        raise DocumentLoadError("El archivo supera el límite de 5 MB.")
    if suffix in {".txt", ".md"}:
        extracted = _decode_text(data)
    elif suffix == ".pdf":
        extracted = _extract_pdf(data)
    else:
        extracted = _extract_docx(data)
    extracted = extracted.replace("\x00", "").strip()
    if not extracted:
        raise DocumentLoadError("No se encontró texto extraíble en el documento.")
    if len(extracted) > MAX_TEXT_CHARS:
        raise DocumentLoadError("El texto extraído supera 100000 caracteres.")
    return extracted, PurePosixPath(filename.replace("\\", "/")).name[:500]
