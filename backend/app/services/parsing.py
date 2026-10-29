"""Stages 1-2: upload validation and text extraction (PyMuPDF, python-docx, Tesseract OCR fallback)."""
import io
from dataclasses import dataclass
from typing import Callable, List, Optional

from ..config import Settings
from .chunking import sections_detected


class ParseError(Exception):
    """A file could not be read. The message is safe to show to the user (it never contains resume text)."""


class OCRUnavailable(ParseError):
    pass


@dataclass
class ExtractedDocument:
    text: str
    ocr_used: bool
    pages: int
    char_count: int


def validate_upload(filename: str, content: bytes, settings: Settings) -> Optional[str]:
    """Return a rejection reason, or None if the file is acceptable."""
    name = filename.lower()
    ext = next((e for e in settings.allowed_extensions if name.endswith(e)), None)
    if ext is None:
        return "unsupported file type (only %s allowed)" % ", ".join(settings.allowed_extensions)
    if len(content) == 0:
        return "file is empty"
    if len(content) > settings.max_file_bytes:
        return "file larger than %d MB" % (settings.max_file_bytes // (1024 * 1024))
    # Cheap content check so a renamed file cannot slip through on extension alone.
    if ext == ".pdf" and not content[:5].startswith(b"%PDF"):
        return "file is not a valid PDF"
    if ext == ".docx" and not content[:2] == b"PK":
        return "file is not a valid DOCX"
    return None


def ocr_pdf_page(page, dpi: int) -> str:
    """Render one PDF page at `dpi` and read it with Tesseract."""
    try:
        import pytesseract
        from PIL import Image
        pix = page.get_pixmap(dpi=dpi)
        image = Image.open(io.BytesIO(pix.tobytes("png")))
        return pytesseract.image_to_string(image)
    except Exception as exc:  # TesseractNotFoundError, missing pytesseract, bad image ...
        raise OCRUnavailable("scanned PDF but OCR failed (%s)" % type(exc).__name__)


def extract_pdf(path: str, settings: Settings, ocr_page: Callable = ocr_pdf_page) -> ExtractedDocument:
    import fitz  # PyMuPDF

    try:
        doc = fitz.open(path)
    except Exception:
        raise ParseError("could not open PDF (corrupt or password protected)")
    try:
        if doc.needs_pass:
            raise ParseError("PDF is password protected")
        # "blocks" sort keeps reading order for multi-column layouts better than raw order.
        text = "\n".join(page.get_text("text", sort=True) for page in doc).strip()
        pages, ocr_used = doc.page_count, False
        if len(text) < settings.ocr_min_chars:
            text = "\n".join(ocr_page(page, settings.ocr_dpi) for page in doc).strip()
            ocr_used = True
    finally:
        doc.close()
    return ExtractedDocument(text=text, ocr_used=ocr_used, pages=pages, char_count=len(text))


def extract_docx(path: str) -> ExtractedDocument:
    import docx

    try:
        document = docx.Document(path)
    except Exception:
        raise ParseError("could not open DOCX (corrupt file)")
    lines: List[str] = [p.text for p in document.paragraphs]
    # Resumes often put skills or dates in tables; read them in row order.
    for table in document.tables:
        for row in table.rows:
            cells = []
            for cell in row.cells:
                if cell.text not in cells:  # merged cells repeat
                    cells.append(cell.text)
            lines.append("  ".join(c for c in cells if c.strip()))
    text = "\n".join(lines).strip()
    return ExtractedDocument(text=text, ocr_used=False, pages=1, char_count=len(text))


def extract_text(path: str, settings: Settings, ocr_page: Callable = ocr_pdf_page) -> ExtractedDocument:
    if path.lower().endswith(".pdf"):
        doc = extract_pdf(path, settings, ocr_page)
    elif path.lower().endswith(".docx"):
        doc = extract_docx(path)
    else:
        raise ParseError("unsupported file type")
    if not doc.text.strip():
        raise ParseError("no readable text found in file")
    return doc


def parse_confidence(doc: ExtractedDocument, settings: Settings) -> dict:
    """The parse-confidence flag: whether OCR was used, how much text, how many sections. The UI warns on low."""
    sections = sections_detected(doc.text)
    reasons = []
    if doc.ocr_used:
        reasons.append("OCR was used")
    if doc.char_count < settings.low_confidence_min_chars:
        reasons.append("very little text found")
    if len(sections) < settings.low_confidence_min_sections:
        reasons.append("few resume sections detected")
    return {
        "ocr_used": doc.ocr_used,
        "char_count": doc.char_count,
        "sections_detected": len(sections),
        "section_names": sections,
        "low": bool(reasons),
        "reasons": reasons,
    }
