from app.services.chunking import chunk_resume, chunk_section, heading_section, split_sections, sections_detected
from tests.conftest import RESUME


def test_heading_detection():
    assert heading_section("EXPERIENCE") == "experience"
    assert heading_section("Work Experience:") == "experience"
    assert heading_section("Skills & Tools") == "skills"
    assert heading_section("I have experience in many things and projects") is None
    assert heading_section("") is None


def test_sections_and_header():
    secs = dict(split_sections(RESUME))
    assert "Jane Doe" in secs["header"]
    assert set(secs) == {"header", "summary", "experience", "education", "skills"}
    assert "EXPERIENCE" not in secs["experience"]


def test_chunk_limit_and_label_kept():
    chunks = chunk_resume(RESUME, 120)
    assert chunks and all(len(c.text) <= 120 for c in chunks)
    assert {c.section for c in chunks} >= {"experience", "education", "skills"}
    assert [c.idx for c in chunks] == list(range(len(chunks)))


def test_chunks_are_exact_substrings_of_source():
    for c in chunk_resume(RESUME, 500):
        assert c.text in RESUME


def test_cuts_on_line_boundaries():
    body = "\n".join("line number %02d" % i for i in range(20))
    for piece in chunk_section(body, 60):
        assert all(l.startswith("line number") for l in piece.split("\n"))


def test_overlong_line_is_split_on_words_and_respects_limit():
    body = "word " * 300
    pieces = chunk_section(body.strip(), 500)
    assert len(pieces) >= 3 and all(len(p) <= 500 for p in pieces)


def test_unbroken_token_longer_than_limit():
    assert all(len(p) <= 100 for p in chunk_section("x" * 450, 100))


def test_sections_detected_excludes_header():
    assert "header" not in sections_detected(RESUME)
