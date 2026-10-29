"""Stage 5: heading-based sectioning and chunking into segments of at most N characters."""
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

SECTION_ALIASES: Dict[str, List[str]] = {
    "experience": ["experience", "work experience", "professional experience", "employment history",
                   "employment", "work history", "career history", "relevant experience", "internships"],
    "education": ["education", "academic background", "academics", "qualifications", "education & training",
                  "academic qualifications"],
    "skills": ["skills", "technical skills", "core competencies", "key skills", "skills & tools",
               "skills and tools", "technologies", "tech stack"],
    "projects": ["projects", "personal projects", "academic projects", "selected projects", "key projects"],
    "certifications": ["certifications", "certificates", "licenses", "licenses & certifications",
                       "certifications & licenses", "courses"],
    "summary": ["summary", "profile", "professional summary", "objective", "career objective", "about me",
                "about", "executive summary"],
    "achievements": ["achievements", "awards", "honors", "accomplishments", "awards & honors",
                     "honors & awards", "publications"],
}
_HEADING_LOOKUP = {alias: sec for sec, aliases in SECTION_ALIASES.items() for alias in aliases}
MAX_HEADING_LEN = 40


@dataclass
class Chunk:
    section: str
    text: str
    idx: int


def heading_section(line: str) -> Optional[str]:
    """Return the section label if the line is a heading, else None."""
    s = line.strip()
    if not s or len(s) > MAX_HEADING_LEN:
        return None
    norm = re.sub(r"[^a-z& ]", "", s.lower()).strip()
    norm = re.sub(r"\s+", " ", norm)
    return _HEADING_LOOKUP.get(norm)


def split_sections(text: str) -> List[Tuple[str, str]]:
    """Split text into (section, body) pairs in document order. Text before the first heading is 'header'.
    Heading lines are dropped from the body. Repeated headings produce separate entries."""
    sections: List[Tuple[str, List[str]]] = [("header", [])]
    for line in text.splitlines():
        sec = heading_section(line)
        if sec:
            sections.append((sec, []))
        else:
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
    Segments are contiguous substrings of the original text, which Stage 9 relies on."""
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


def chunk_resume(text: str, max_chars: int = 500) -> List[Chunk]:
    chunks: List[Chunk] = []
    for section, body in split_sections(text):
        for piece in chunk_section(body, max_chars):
            chunks.append(Chunk(section=section, text=piece, idx=len(chunks)))
    return chunks


def sections_detected(text: str) -> List[str]:
    """Distinct non-header section labels found, used for the parse-confidence flag."""
    return sorted({sec for sec, _ in split_sections(text) if sec != "header"})
