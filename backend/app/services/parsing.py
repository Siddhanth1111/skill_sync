"""Stages 1-2: upload validation and text extraction (PyMuPDF, python-docx, Tesseract OCR fallback).

v2 (review items A1 to A5):
  * the OCR decision is made per page (little text, mostly images, or garbled text), and the page texts are merged;
  * OCR renders at 300 dpi and preprocesses the image (grayscale, contrast, denoise, threshold, deskew), uses page
    mode 4 and records the mean word confidence per page;
  * two-column pages are read column by column;
  * DOCX text boxes, headers and footers are read;
  * extracted text is normalised (ligatures, bullets, soft hyphens, line-break hyphenation, odd spacing). The
    normalised text is what is stored and what quotes are verified against.
"""
import functools
import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from ..config import Settings
from .chunking import sections_detected


class ParseError(Exception):
    """A file could not be read. The message is safe to show to the user (it never contains resume text)."""


class OCRUnavailable(ParseError):
    pass


@dataclass
class OcrResult:
    text: str
    confidence: Optional[float] = None  # mean word confidence 0..100


@dataclass
class ExtractedDocument:
    text: str
    ocr_used: bool
    pages: int
    char_count: int
    ocr_pages: int = 0
    page_confidence: List[Optional[float]] = field(default_factory=list)  # per OCRed page
    mean_confidence: Optional[float] = None
    ocr_failed_pages: int = 0


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


# ---- text normalisation (A5) ------------------------------------------------------------------------

_BULLET_GLYPHS = "•●○▪■➢➤⁃‣◦∙·"
_BULLET_LINE = re.compile(r"^[ \t]*[%s][ \t]*" % re.escape(_BULLET_GLYPHS), re.M)
_INVISIBLE = re.compile("[­​‌‍⁠﻿]")


def normalize_text(text: str) -> str:
    """Make extracted text uniform without changing its meaning. Applied once at extraction, so everything
    downstream (units, quotes, verification) sees the same text."""
    t = unicodedata.normalize("NFKC", text)  # ligatures (fi, fl), non-breaking spaces, full-width forms
    t = _INVISIBLE.sub("", t)
    t = _BULLET_LINE.sub("• ", t)
    t = re.sub(r"([a-z])-[ \t]*\n[ \t]*([a-z])", r"\1\2", t)  # "optimi-\nzation" -> "optimization"
    t = re.sub(r"[ \t]+", " ", t)
    t = "\n".join(line.strip() for line in t.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", t).strip()


# ---- OCR (A1, A2) -----------------------------------------------------------------------------------

def preprocess_for_ocr(image):
    """Grayscale, stretch contrast, denoise, deskew, then binarise (Otsu). Returns a PIL 'L' image."""
    import numpy as np
    from PIL import ImageFilter, ImageOps

    img = ImageOps.autocontrast(image.convert("L"))
    img = img.filter(ImageFilter.MedianFilter(3))
    img = _deskew(img)
    arr = np.asarray(img)
    hist = np.bincount(arr.ravel(), minlength=256).astype(float)
    total, sum_all = hist.sum(), float((np.arange(256) * hist).sum())
    best_t, best_var, w0, sum0 = 127, -1.0, 0.0, 0.0
    for t in range(256):
        w0 += hist[t]
        if w0 == 0 or w0 == total:
            continue
        sum0 += t * hist[t]
        m0, m1 = sum0 / w0, (sum_all - sum0) / (total - w0)
        var = w0 * (total - w0) * (m0 - m1) ** 2
        if var > best_var:
            best_var, best_t = var, t
    return img.point(lambda p: 255 if p > best_t else 0)


def _deskew(img, max_angle: float = 5.0):
    """Rotate by the angle (within +-5 degrees) that makes text rows line up best (projection-profile search)."""
    import numpy as np

    small = img.copy()
    small.thumbnail((700, 700))
    inv = small.point(lambda p: 255 - p)
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_angle, max_angle + 0.01, 0.5):
        rows = np.asarray(inv.rotate(float(angle), fillcolor=0), dtype=float).sum(axis=1)
        score = float(np.var(rows))
        if score > best_score:
            best_angle, best_score = float(angle), score
    return img if abs(best_angle) < 0.5 else img.rotate(best_angle, expand=True, fillcolor=255)


def ocr_pdf_page(page, dpi: int, psm: int = 4) -> OcrResult:
    """Render one PDF page at `dpi`, preprocess it, and read it with Tesseract. Returns text and the mean word
    confidence (0 to 100)."""
    try:
        import fitz
        import pytesseract
        from PIL import Image

        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        image = preprocess_for_ocr(Image.frombytes("L", (pix.width, pix.height), pix.samples))
        data = pytesseract.image_to_data(image, config="--psm %d" % psm, output_type=pytesseract.Output.DICT)
    except Exception as exc:  # TesseractNotFoundError, missing pytesseract, bad image ...
        raise OCRUnavailable("scanned PDF but OCR failed (%s)" % type(exc).__name__)
    lines, confs, last_block = {}, [], None
    for i, word in enumerate(data["text"]):
        if not str(word).strip():
            continue
        conf = float(data["conf"][i])
        if conf < 0:
            continue
        confs.append(conf)
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(str(word))
    out = []
    for key, words in lines.items():
        if last_block is not None and key[0] != last_block:
            out.append("")
        last_block = key[0]
        out.append(" ".join(words))
    return OcrResult("\n".join(out), (sum(confs) / len(confs)) if confs else None)


def _as_result(value) -> OcrResult:
    return value if isinstance(value, OcrResult) else OcrResult(str(value))


# ---- PDF ---------------------------------------------------------------------------------------------

def _page_text(page) -> str:
    """Native text in reading order. A page with two text columns is read left column first, then right (A3)."""
    blocks = [b for b in page.get_text("blocks") if b[6] == 0 and b[4].strip()]
    width = page.rect.width
    left = [b for b in blocks if b[2] <= width * 0.56]
    right = [b for b in blocks if b[0] >= width * 0.44]
    wide = [b for b in blocks if b not in left and b not in right]
    if len(left) >= 2 and len(right) >= 2 and len(wide) <= max(2, len(blocks) // 4):
        keyed, band = [], 0
        for b in sorted(blocks, key=lambda b: (b[1], b[0])):
            if b in wide:
                band += 1
                keyed.append((band, 0, b[1], b))
                band += 1
            else:
                keyed.append((band, 0 if b in left else 1, b[1], b))
        return "\n".join(k[3][4].strip() for k in sorted(keyed, key=lambda k: k[:3]))
    return page.get_text("text", sort=True)


def _garbage_ratio(text: str) -> float:
    s = re.sub(r"\s", "", text)
    if not s:
        return 0.0
    bad = sum(1 for ch in s if ch == "�" or "" <= ch <= "" or (not ch.isalnum() and ch in "¤§¶¿"))
    bad += 3 * len(re.findall(r"\(cid:\d+\)", text))
    return min(1.0, bad / len(s))


def _image_ratio(page) -> float:
    try:
        area = page.rect.width * page.rect.height
        covered = sum(abs((i["bbox"][2] - i["bbox"][0]) * (i["bbox"][3] - i["bbox"][1])) for i in page.get_image_info())
        return covered / area if area else 0.0
    except Exception:
        return 0.0


def _page_needs_ocr(text: str, page, settings: Settings) -> bool:
    n = len(text.strip())
    return (n < settings.ocr_page_min_chars or _garbage_ratio(text) > settings.ocr_garbage_ratio
            or (_image_ratio(page) > settings.ocr_image_area_ratio and n < 300))


def extract_pdf(path: str, settings: Settings, ocr_page: Callable = ocr_pdf_page) -> ExtractedDocument:
    import fitz  # PyMuPDF

    try:
        doc = fitz.open(path)
    except Exception:
        raise ParseError("could not open PDF (corrupt or password protected)")
    try:
        if doc.needs_pass:
            raise ParseError("PDF is password protected")
        pages = doc.page_count
        native = [_page_text(p) for p in doc]
        total = sum(len(t.strip()) for t in native)
        # A document with almost no text is OCRed in full; otherwise only the pages that need it.
        wanted = [i for i, p in enumerate(doc) if total < settings.ocr_min_chars or _page_needs_ocr(native[i], p, settings)]
        reader = functools.partial(ocr_page, psm=settings.ocr_psm) if ocr_page is ocr_pdf_page else ocr_page
        texts, confs, failed = list(native), [], 0
        for i in wanted:
            try:
                res = _as_result(reader(doc[i], settings.ocr_dpi))
            except OCRUnavailable:
                if total < settings.ocr_min_chars or not native[i].strip():
                    raise  # a scanned document (or page with no text) has nothing to fall back on
                failed += 1
                continue
            # keep whichever reading has more text (a mostly-native page with one logo image stays native)
            if len(res.text.strip()) >= len(native[i].strip()):
                texts[i] = res.text
                confs.append(res.confidence)
        text = normalize_text("\n".join(texts))
    finally:
        doc.close()
    known = [c for c in confs if c is not None]
    return ExtractedDocument(
        text=text, ocr_used=len(confs) > 0, pages=pages, char_count=len(text), ocr_pages=len(confs),
        page_confidence=confs, mean_confidence=(sum(known) / len(known)) if known else None, ocr_failed_pages=failed)


# ---- DOCX --------------------------------------------------------------------------------------------

def extract_docx(path: str) -> ExtractedDocument:
    import docx
    from docx.oxml.ns import qn

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
    # Text boxes (A4): their paragraphs are not in document.paragraphs. A box is stored twice (Choice and Fallback).
    seen = {l.strip() for l in lines if l.strip()}
    for box in document.element.body.iter(qn("w:txbxContent")):
        for p in box.iter(qn("w:p")):
            t = "".join(n.text or "" for n in p.iter(qn("w:t"))).strip()
            if t and t not in seen:
                seen.add(t)
                lines.append(t)
    # Headers and footers often hold the name and contact line.
    extra = []
    for section in document.sections:
        for part in (section.header, section.footer):
            for p in part.paragraphs:
                t = p.text.strip()
                if t and t not in seen:
                    seen.add(t)
                    extra.append(t)
    text = normalize_text("\n".join(extra + lines))
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
    """The parse-confidence flag: whether OCR was used and how well, how much text, how many sections.
    The UI warns on low."""
    sections = sections_detected(doc.text)
    reasons = []
    low_ocr = False
    if doc.ocr_used:
        reasons.append("OCR was used on %d page(s)" % doc.ocr_pages)
        if doc.mean_confidence is not None and doc.mean_confidence < settings.ocr_min_confidence:
            low_ocr = True
            reasons.append("OCR confidence is low (%.0f out of 100)" % doc.mean_confidence)
    if doc.ocr_failed_pages:
        reasons.append("%d page(s) needed OCR but it failed" % doc.ocr_failed_pages)
    if doc.char_count < settings.low_confidence_min_chars:
        reasons.append("very little text found")
    if len(sections) < settings.low_confidence_min_sections:
        reasons.append("few resume sections detected")
    return {
        "ocr_used": doc.ocr_used,
        "ocr_pages": doc.ocr_pages,
        "ocr_confidence": doc.mean_confidence,
        "ocr_page_confidence": doc.page_confidence,
        "low_ocr": low_ocr,
        "char_count": doc.char_count,
        "sections_detected": len(sections),
        "section_names": sections,
        "low": bool(reasons),
        "reasons": reasons,
    }
