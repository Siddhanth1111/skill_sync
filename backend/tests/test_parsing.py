import pytest

from app.services.parsing import ParseError, extract_text, parse_confidence, validate_upload
from tests.conftest import RESUME, make_docx, make_pdf


def test_pdf_text_extracted_without_ocr(tmp_path, settings):
    p = tmp_path / "r.pdf"
    make_pdf(p, RESUME)
    doc = extract_text(str(p), settings)
    assert not doc.ocr_used and "jane.doe@example.com" in doc.text and doc.pages == 1


def test_docx_text_extracted(tmp_path, settings):
    p = tmp_path / "r.docx"
    make_docx(p, RESUME)
    doc = extract_text(str(p), settings)
    assert "Kafka" in doc.text and not doc.ocr_used


def test_scanned_pdf_triggers_ocr(tmp_path, settings):
    p = tmp_path / "scan.pdf"
    make_pdf(p, "tiny")  # under the 50-char test threshold
    calls = []

    def fake_ocr(page, dpi):
        calls.append(dpi)
        return RESUME

    doc = extract_text(str(p), settings, ocr_page=fake_ocr)
    assert doc.ocr_used and calls == [200] and "Jane Doe" in doc.text
    assert parse_confidence(doc, settings)["low"] is True  # OCR always lowers confidence


def test_ocr_unavailable_gives_clear_error(tmp_path, settings, monkeypatch):
    import pytesseract

    def boom(*a, **k):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "image_to_string", boom)
    p = tmp_path / "scan.pdf"
    make_pdf(p, "tiny")
    with pytest.raises(ParseError, match="OCR"):
        extract_text(str(p), settings)


def test_corrupt_pdf(tmp_path, settings):
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"%PDF-1.4 garbage")
    with pytest.raises(ParseError):
        extract_text(str(p), settings)


def test_confidence_high_for_good_resume(tmp_path, settings):
    p = tmp_path / "r.pdf"
    make_pdf(p, RESUME * 1)
    s2 = settings.model_copy(update={"low_confidence_min_chars": 100})
    conf = parse_confidence(extract_text(str(p), s2), s2)
    assert conf["low"] is False and conf["sections_detected"] >= 4


@pytest.mark.parametrize("name,content,fragment", [
    ("a.txt", b"hello", "unsupported"),
    ("a.pdf", b"", "empty"),
    ("a.pdf", b"x" * 20, "not a valid PDF"),
    ("a.docx", b"x" * 20, "not a valid DOCX"),
    ("a.pdf", b"%PDF" + b"0" * (11 * 1024 * 1024), "larger than"),
])
def test_validate_upload_rejections(settings, name, content, fragment):
    assert fragment in validate_upload(name, content, settings)


def test_validate_upload_accepts_good(settings):
    assert validate_upload("CV.PDF", b"%PDF-1.7 ...", settings) is None
