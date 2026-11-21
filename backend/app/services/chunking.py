"""Stages 5-6 input: sectioning and retrieval units.

v2 (review items C1, C2, A9): units are single bullets or sentences, each carrying a context line (role title,
company and dates) so a short generic bullet is never searched without knowing where it came from. Headings are
matched with wider aliases, fuzzy matching and inline forms ("Education: B.Tech ..."). Contact lines and personal
details are never indexed.

Every unit's `text` is a contiguous piece of the resume text (whitespace aside), which Stage 9 relies on.
`context` is separate and is only used to help retrieval and reranking; it is never shown as a quote.
"""
import difflib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

SECTION_ALIASES: Dict[str, List[str]] = {
    "experience": ["experience", "work experience", "professional experience", "employment history", "employment",
                   "work history", "career history", "relevant experience", "internships", "internship experience",
                   "career details", "employment details", "professional background", "experience summary",
                   "work experience details", "industry experience", "internship", "positions held"],
    "education": ["education", "academic background", "academics", "qualifications", "education & training",
                  "academic qualifications", "education details", "educational qualification",
                  "educational qualifications", "academic details", "academic profile", "scholastic record",
                  "educational background", "education and training"],
    "skills": ["skills", "technical skills", "core competencies", "key skills", "skills & tools", "skills and tools",
               "technologies", "tech stack", "technical proficiency", "technical expertise", "areas of expertise",
               "tools & technologies", "tools and technologies", "technical summary", "it skills", "skill set",
               "technical skill set", "competencies", "expertise", "skills summary", "technical competencies"],
    "projects": ["projects", "personal projects", "academic projects", "selected projects", "key projects",
                 "project experience", "projects undertaken", "project details", "major projects", "side projects"],
    "certifications": ["certifications", "certificates", "licenses", "licenses & certifications",
                       "certifications & licenses", "courses", "training", "training & certifications",
                       "certifications and training", "professional certifications", "courses & certifications"],
    "summary": ["summary", "profile", "professional summary", "objective", "career objective", "about me", "about",
                "executive summary", "professional profile", "career summary", "profile summary",
                "summary of qualifications", "personal summary", "overview", "career profile", "highlights"],
    "achievements": ["achievements", "awards", "honors", "accomplishments", "awards & honors", "honors & awards",
                     "publications", "key achievements", "awards and achievements", "achievements & awards"],
    # personal and interest sections are recognised so they do not leak into other sections, but are never indexed
    "personal": ["personal details", "personal information", "personal profile", "declaration", "personal data",
                 "personal particulars"],
    "interests": ["interests", "hobbies", "hobbies & interests", "hobbies and interests", "extracurricular activities",
                  "extra curricular activities", "extracurricular", "languages", "references", "volunteering",
                  "volunteer experience", "activities"],
}
NOT_INDEXED = {"personal", "interests"}
_HEADING_LOOKUP = {alias: sec for sec, aliases in SECTION_ALIASES.items() for alias in aliases}
_ALIAS_LIST = list(_HEADING_LOOKUP)
MAX_HEADING_LEN = 40
BULLET = re.compile(r"^\s*(?:[-*•▪◦–·●○■▶►✓✔]|\d{1,2}[.)])\s+")
CONTACT = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|(?:https?://|www\.)\S+|\b(?:linkedin|github|gitlab)\.com\S*|"
                     r"(?<!\d)\+?\d[\d\s().-]{8,}\d(?!\d)", re.I)
_DATE = r"(?:[A-Za-z]{3,9}\.?,?\s+\d{4}|\d{1,2}/\d{4}|\d{4}-\d{1,2}|\d{4})"
DATE_RANGE = re.compile(r"(?P<s>%s)\s*(?:-|–|—|to)\s*(?P<e>(?:present|current|now|ongoing|till date|to date|%s))" % (_DATE, _DATE),
                        re.I)
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(])")


@dataclass
class Chunk:
    section: str
    text: str
    idx: int
    context: str = ""  # role title, company, dates (experience) or the section name; helps retrieval only
    start: Optional[str] = None  # role dates, when the unit sits under a dated role
    end: Optional[str] = None

    @property
    def embed_text(self) -> str:
        return "%s. %s" % (self.context, self.text) if self.context else self.text


def _norm_heading(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z& ]", "", s.lower())).strip()


def heading_section(line: str) -> Optional[str]:
    """Return the section label if the whole line is a heading, else None. Exact alias match first, then a fuzzy
    match for typos and decorated headings, allowed only for short upper-case, title-case or colon-ended lines."""
    s = line.strip()
    if not s or len(s) > MAX_HEADING_LEN or BULLET.match(line):
        return None
    norm = _norm_heading(s)
    if norm in _HEADING_LOOKUP:
        return _HEADING_LOOKUP[norm]
    if len(norm) >= 6 and len(norm.split()) <= 4 and (s.isupper() or s.rstrip().endswith(":") or s.istitle()):
        close = difflib.get_close_matches(norm, _ALIAS_LIST, n=1, cutoff=0.9)
        if close:
            return _HEADING_LOOKUP[close[0]]
    return None


def inline_heading(line: str) -> Optional[Tuple[str, str]]:
    """'Education: B.Tech in CS, 2017' -> ('education', 'B.Tech in CS, 2017'). Only when the text before the colon
    is a known heading and something follows it."""
    if ":" not in line or BULLET.match(line):
        return None
    head, rest = line.split(":", 1)
    if len(head) > MAX_HEADING_LEN or not rest.strip():
        return None
    sec = _HEADING_LOOKUP.get(_norm_heading(head))
    return (sec, rest.strip()) if sec else None


def split_sections(text: str) -> List[Tuple[str, str]]:
    """Split text into (section, body) pairs in document order. Text before the first heading is 'header'.
    Heading lines are dropped from the body (an inline heading keeps the text after the colon). Repeated headings
    produce separate entries."""
    sections: List[Tuple[str, List[str]]] = [("header", [])]
    for line in text.splitlines():
        sec = heading_section(line)
        if sec:
            sections.append((sec, []))
            continue
        inl = inline_heading(line)
        if inl and sec is None:
            sections.append((inl[0], [inl[1]]))
            continue
        sections[-1][1].append(line)
    out = []
    for sec, lines in sections:
        body = "\n".join(lines).strip("\n")
        if body.strip():
            out.append((sec, body))
    return out


def _split_long_line(line: str, max_chars: int) -> List[str]:
    """A single line over the limit is cut on word boundaries (the only case that is not line-aligned)."""
    parts, cur = [], ""
    for word in line.split(" "):
        while len(word) > max_chars:  # an unbroken token longer than the limit
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(word[:max_chars])
            word = word[max_chars:]
        candidate = word if not cur else cur + " " + word
        if len(candidate) > max_chars:
            parts.append(cur)
            cur = word
        else:
            cur = candidate
    if cur:
        parts.append(cur)
    return parts


def chunk_section(body: str, max_chars: int) -> List[str]:
    """Pack consecutive lines into segments of at most max_chars, cutting only on line boundaries.
    (Used for sections without bullet structure; kept from v1.)"""
    pieces: List[str] = []
    for line in body.split("\n"):
        pieces.extend(_split_long_line(line, max_chars) if len(line) > max_chars else [line])
    chunks, cur = [], ""
    for piece in pieces:
        candidate = piece if not cur else cur + "\n" + piece
        if len(candidate) > max_chars and cur.strip():
            chunks.append(cur.strip())
            cur = piece
        else:
            cur = candidate
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


def _sentences(text: str, max_chars: int) -> List[str]:
    out: List[str] = []
    for part in SENTENCE.split(text):
        part = part.strip()
        if not part:
            continue
        out.extend(_split_long_line(part, max_chars) if len(part) > max_chars else [part])
    return out


def _is_contact(line: str) -> bool:
    return bool(CONTACT.search(line))


def _entries(body: str) -> List[Tuple[str, List[str]]]:
    """Split an experience or projects body into (header, bullets). A non-bullet line right after a bullet that
    does not look like a new header (no date range, bullet not finished) continues that bullet."""
    entries: List[Tuple[List[str], List[str]]] = []
    head: List[str] = []
    bullets: List[str] = []
    for raw in body.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            continue
        if BULLET.match(line):
            bullets.append(BULLET.sub("", line, count=1).strip())
            continue
        if bullets and not DATE_RANGE.search(line):
            last = bullets[-1]
            if not re.search(r"[.!?:]$", last) or line[:1].islower():
                bullets[-1] = last + "\n" + line.strip()  # a wrapped bullet
                continue
        if bullets:  # a new header starts: close the previous entry
            entries.append((head, bullets))
            head, bullets = [], []
        head.append(line.strip())
    entries.append((head, bullets))
    return [(" ".join(h)[:240], b) for h, b in entries if h or b]


def chunk_resume(text: str, max_chars: int = 500) -> List[Chunk]:
    """Retrieval units: one per bullet or sentence, each with a context line. See the module docstring."""
    units: List[Chunk] = []
    sections = split_sections(text)
    has_sections = any(sec != "header" for sec, _ in sections)

    def add(section: str, piece: str, context: str, start=None, end=None) -> None:
        piece = piece.strip()
        if len(piece) < 3 or not re.search(r"[A-Za-z0-9]", piece):
            return
        units.append(Chunk(section=section, text=piece, idx=len(units), context=context, start=start, end=end))

    for section, body in sections:
        if section in NOT_INDEXED:
            continue
        label = section.capitalize()
        if section in ("experience", "projects"):
            for header, bullets in _entries(body):
                m = DATE_RANGE.search(header)
                s, e = (m.group("s"), m.group("e")) if m else (None, None)
                ctx = header if header else label
                if bullets:
                    for b in bullets:
                        for piece in _sentences(b, max_chars) if len(b) > max_chars else [b]:
                            add(section, piece, ctx, s, e)
                elif header:  # a role with no bullets: its header line is the evidence
                    add(section, header, label, s, e)
            continue
        for raw in body.split("\n"):
            line = BULLET.sub("", raw, count=1).strip()
            if not line or _is_contact(line):
                continue
            # Before the first heading ("header"): keep only summary-like lines, never a name, address or phone line.
            if section == "header" and has_sections and len(line.split()) < 7:
                continue
            for piece in (_sentences(line, max_chars) if len(line) > max_chars else [line]):
                add(section, piece, label)
    return units


def sections_detected(text: str) -> List[str]:
    """Distinct non-header section labels found, used for the parse-confidence flag."""
    return sorted({sec for sec, _ in split_sections(text) if sec != "header"})


def date_span(header: str) -> Tuple[Optional[str], Optional[str]]:
    m = DATE_RANGE.search(header or "")
    return (m.group("s"), m.group("e")) if m else (None, None)
