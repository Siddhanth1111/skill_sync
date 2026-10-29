"""Rule-based extractors (regex and heading rules). They answer when the LLM fails and cross-check it."""
import re
from typing import List, Optional

from ..schemas import CandidateProfile, Education, JDExtraction, JDRequirement, Role
from .chunking import split_sections
from .dates import parse_date, years_of_experience
from .taxonomy import find_skills

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{3,5}[\s.-]?\d{3,5}(?:[\s.-]?\d{2,4})?(?!\d)")

_DATE = r"(?:[A-Za-z]{3,9}\.?,?\s+\d{4}|\d{1,2}/\d{4}|\d{4}-\d{1,2}|\d{4})"
_END = r"(?:present|current|now|ongoing|till date|to date|" + _DATE + ")"
DATE_RANGE_RE = re.compile(r"(?P<s>%s)\s*(?:-|–|—|to)\s*(?P<e>%s)" % (_DATE, _END), re.IGNORECASE)

# Order matters: check the highest level first.
DEGREE_PATTERNS = [
    (3, re.compile(r"\b(ph\.?\s?d|doctorate|doctor of philosophy)\b", re.I)),
    (2, re.compile(r"\b(master'?s?|m\.?\s?sc|m\.?\s?s\b|m\.?\s?tech|m\.?\s?e\b|mba|m\.?\s?a\b|mca)\b", re.I)),
    (1, re.compile(r"\b(bachelor'?s?|b\.?\s?sc|b\.?\s?s\b|b\.?\s?tech|b\.?\s?e\b|b\.?\s?a\b|bca|b\.?\s?com)\b", re.I)),
]


def degree_level(text: str) -> int:
    for level, pattern in DEGREE_PATTERNS:
        if pattern.search(text):
            return level
    return 0


def find_email(text: str) -> Optional[str]:
    m = EMAIL_RE.search(text)
    return m.group(0) if m else None


def find_phone(text: str) -> Optional[str]:
    for m in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 8 <= len(digits) <= 15 and not re.fullmatch(r"(19|20)\d{2}(19|20)?\d{0,2}", digits):
            return m.group(0).strip()
    return None


def find_name(text: str) -> Optional[str]:
    """First short line near the top with no digits, '@' or heading words (a heuristic, often right)."""
    for line in text.splitlines()[:6]:
        s = line.strip()
        if 2 <= len(s) <= 40 and not re.search(r"[\d@:/|]", s) and 1 <= len(s.split()) <= 4:
            if not any(w in s.lower() for w in ("resume", "curriculum", "vitae")):
                return s
    return None


def extract_roles(experience_text: str) -> List[Role]:
    roles = []
    lines = experience_text.splitlines()
    for i, line in enumerate(lines):
        m = DATE_RANGE_RE.search(line)
        if not m or parse_date(m.group("s")) is None or parse_date(m.group("e"), is_end=True) is None:
            continue
        title = (line[:m.start()] + " " + line[m.end():]).strip(" \t-–—|,()")
        if not title and i > 0:
            title = lines[i - 1].strip()  # date on its own line, title just above
        roles.append(Role(title=title[:120] or "Unspecified role", start=m.group("s"), end=m.group("e")))
    return roles


def extract_education(education_text: str) -> List[Education]:
    out = []
    for line in education_text.splitlines():
        level = degree_level(line)
        if level:
            year = re.search(r"\b(19|20)\d{2}\b", line)
            out.append(Education(degree=line.strip()[:120], level=level, year=year.group(0) if year else None))
    return out


def extract_profile_rules(text: str) -> CandidateProfile:
    sections = split_sections(text)
    by_name = {}
    for name, body in sections:
        by_name[name] = by_name.get(name, "") + "\n" + body
    roles = extract_roles(by_name.get("experience", ""))
    education = extract_education(by_name.get("education", ""))
    return CandidateProfile(
        name=find_name(text),
        email=find_email(text),
        phone=find_phone(text),
        skills=find_skills(text),
        roles=roles,
        education=education,
        years_experience=years_of_experience(roles),
        education_level=max([e.level for e in education], default=0),
        source="rules",
    )


# ---- Job descriptions ----------------------------------------------------------------------

# Heading text -> importance of the bullets below it. None means ignore the block.
JD_HEADINGS = [
    (None, ("benefits", "perks", "what we offer", "we offer", "compensation", "salary", "equal opportunity",
            "about us", "about the company", "who we are", "our company", "how to apply", "legal")),
    ("nice", ("nice to have", "preferred", "bonus", "good to have", "plus", "desirable", "pluses")),
    ("must", ("requirements", "qualifications", "must have", "what you need", "what you'll need",
              "what we're looking for", "required", "minimum qualifications", "skills required", "you have")),
    ("should", ("responsibilities", "what you'll do", "what you will do", "the role", "your role", "duties")),
]
BULLET_RE = re.compile(r"^\s*(?:[-*•▪◦–·]|\d+[.)])\s+(.*\S)")
YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", re.I)


def _heading_importance(line: str):
    """(is_heading, importance). Headings are short lines without bullets, optionally ending with ':'."""
    s = line.strip().rstrip(":").strip().lower()
    if not s or len(s) > 50 or BULLET_RE.match(line):
        return False, None
    for importance, keys in JD_HEADINGS:
        if any(s == k or s.startswith(k + " ") or s.endswith(" " + k) for k in keys):
            return True, importance if importance is not None else "ignore"
    return False, None


def _inline_importance(text: str, default: str) -> str:
    low = text.lower()
    if re.search(r"\b(nice to have|preferred|bonus|a plus|is a plus|desirable|good to have)\b", low):
        return "nice"
    if re.search(r"\b(must|required|mandatory)\b", low):
        return "must"
    return default


def _classify(text: str) -> JDRequirement:
    skills = find_skills(text)
    years = YEARS_RE.search(text)
    level = degree_level(text) if re.search(r"\b(degree|bachelor|master|ph\.?d|b\.?tech|m\.?tech|mba|doctorate)", text, re.I) else 0
    if level and not years:
        return JDRequirement(text=text, type="education", importance="must", skills=skills, degree_level_required=level)
    if years:
        return JDRequirement(text=text, type="experience", importance="must", skills=skills, years_required=float(years.group(1)))
    return JDRequirement(text=text, type="skill", importance="must", skills=skills)


def extract_jd_rules(text: str) -> JDExtraction:
    """Heading and bullet based requirement extraction. Bullets under unknown or ignored headings are skipped
    unless they look like requirements (mention a taxonomy skill, years, or a degree)."""
    current: Optional[str] = "should"
    reqs: List[JDRequirement] = []
    for line in text.splitlines():
        is_heading, importance = _heading_importance(line)
        if is_heading:
            current = importance
            continue
        m = BULLET_RE.match(line)
        if not m or current == "ignore":
            continue
        body = m.group(1).strip()
        req = _classify(body)
        if current is None and not (req.skills or req.type != "skill"):
            continue
        req.importance = _inline_importance(body, current or "should")
        reqs.append(req)
    return JDExtraction(requirements=reqs)
