"""Identity removal and counterfactual text variants (review items F2, F3).

`blind_text` strips what should never influence a score: name, contact details, links, postcodes, school names,
education years and gendered pronouns. Scoring uses it by default (settings.blind_scoring); the recruiter still sees
the original resume. The variant functions produce the text changes the counterfactual audit tests."""
import re
from typing import Dict, List, Optional

from .chunking import heading_section
from .fallback import EMAIL_RE, PHONE_RE

URL_RE = re.compile(r"(?:https?://|www\.)\S+|\b(?:linkedin|github|gitlab|twitter|medium)\.com/\S*", re.I)
POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}\b|\b\d{5}(?:-\d{4})?\b|\b\d{6}\b")
SCHOOL_RE = re.compile(
    r"\b(?:[A-Z][\w&.'-]*\s+){0,4}(?:University|College|Institute|Polytechnic|Academy|School)(?:\s+of(?:\s+[A-Z][\w&.'-]*){1,4})?"
    r"|\b(?:University|Institute|College|School)\s+of(?:\s+[A-Z][\w&.'-]*){1,4}", re.UNICODE)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
# Well-known institution abbreviations, matched only inside an education section (short capitals are ambiguous
# elsewhere). The profile's own institution names, when extracted, are removed everywhere.
SCHOOL_ABBR_RE = re.compile(r"\b(?:IIT|NIT|IIIT|IIM|BITS|MIT|NUS|NTU|ETH|EPFL|UCLA|NYU|CMU|VIT|SRM|JNU|BHU|ISB|LSE)\b"
                            r"(?:[ -][A-Z][a-z]+)?")

NEUTRAL = {"he": "they", "she": "they", "him": "them", "her": "them", "his": "their", "hers": "theirs",
           "himself": "themself", "herself": "themself", "mr": "", "mrs": "", "ms": "", "miss": ""}
TO_MALE = {"she": "he", "her": "his", "hers": "his", "herself": "himself", "he": "he", "him": "him", "his": "his", "himself": "himself"}
TO_FEMALE = {"he": "she", "him": "her", "his": "her", "himself": "herself", "she": "she", "her": "her", "hers": "hers", "herself": "herself"}
NAMES_MALE = ["James", "Michael", "Robert", "David", "William", "Daniel", "Thomas", "Mark"]
NAMES_FEMALE = ["Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Susan", "Karen", "Nancy"]


_NOT_POSSESSIVE_NEXT = {"to", "for", "with", "and", "in", "on", "at", "by", "from", "that", "as", "when", "while", "or",
                        "but", "about", "if", "so", "than", "because", "after", "before", "of"}


def _swap_words(text: str, mapping: Dict[str, str]) -> str:
    if mapping is NEUTRAL:
        # "her" is ambiguous: "her work" (possessive, -> their) vs "told her" (object, -> them)
        def her(m):
            nxt = (m.group(2) or "").lower()
            word = "their" if nxt and nxt not in _NOT_POSSESSIVE_NEXT else "them"
            return word.capitalize() if m.group(1)[0].isupper() else word
        text = re.sub(r"\b(her)\b(?:\s+([A-Za-z]+))?", lambda m: her(m) + (m.group(0)[len(m.group(1)):] if m.group(2) else ""), text, flags=re.I)

    def repl(m):
        w = m.group(0)
        new = mapping.get(w.lower())
        if new is None:
            return w
        return new.capitalize() if w[0].isupper() else new
    return re.sub(r"\b[A-Za-z]+\b", repl, text)


def _name_parts(name: Optional[str]) -> List[str]:
    return [p for p in re.split(r"\s+", name or "") if len(p) >= 2]


def blind_text(text: str, profile: dict) -> str:
    """Remove name, contact details, links, postcode, school names and education years; make pronouns neutral."""
    t = URL_RE.sub("", text)
    t = EMAIL_RE.sub("", t)

    def drop_phone(m):
        digits = re.sub(r"\D", "", m.group(0))
        return "" if 8 <= len(digits) <= 15 and not re.fullmatch(r"(19|20)\d{2}(19|20)?\d{0,2}", digits) else m.group(0)

    t = PHONE_RE.sub(drop_phone, t)
    name = (profile or {}).get("name")
    if name:
        t = re.sub(re.escape(name), "", t, flags=re.I)
        # Single name parts are removed from the top of the resume only: a person called Ruby or Swift must not
        # lose the skill of that name further down.
        lines = t.split("\n")
        end = next((i for i, l in enumerate(lines) if heading_section(l)), min(len(lines), 6))
        for part in _name_parts(name):
            pattern = re.compile(r"\b%s\b" % re.escape(part), re.I)
            lines[:end] = [pattern.sub("", l) for l in lines[:end]]
        t = "\n".join(lines)
    t = POSTCODE_RE.sub("", t)
    schools = [e.get("institution") for e in (profile or {}).get("education", []) if e.get("institution")]
    for s in sorted(schools, key=len, reverse=True):
        t = re.sub(re.escape(s), "", t, flags=re.I)
    t = SCHOOL_RE.sub("", t)
    out, section = [], None
    for line in t.split("\n"):
        h = heading_section(line)
        if h:
            section = h
        elif section == "education":
            line = SCHOOL_ABBR_RE.sub("", YEAR_RE.sub("", line))
        out.append(line)
    t = "\n".join(out)
    t = re.sub(r"(?:[ \t]*,){2,}", ",", t)           # "B.Tech, , " left by a removed school and year
    t = re.sub(r"[ \t]*,[ \t]*(?=\n|$)", "", t)     # a dangling comma at the end of a line
    t = re.sub(r"\(\s*\)|\[\s*\]", "", t)
    return _swap_words(t, NEUTRAL)


def blind_profile(profile: dict) -> dict:
    p = dict(profile or {})
    p.update(name=None, email=None, phone=None)
    p["education"] = [{**e, "institution": None, "year": None} for e in p.get("education", [])]
    return p


def swap_variant(text: str, profile: dict, target: str, i: int) -> str:
    """Counterfactual copy: first name replaced by one from the target list, pronouns switched to the target."""
    name = (profile or {}).get("name")
    parts = _name_parts(name)
    t = text
    if parts:
        pool = NAMES_MALE if target == "male" else NAMES_FEMALE
        new_first = pool[i % len(pool)]
        t = re.sub(r"\b%s\b" % re.escape(parts[0]), new_first, t)
    return _swap_words(t, TO_MALE if target == "male" else TO_FEMALE)




SCHOOL_POOL = ["Riverbend University", "Northfield Institute of Technology", "Lakeside College"]
CITY_POOL = ["Springfield", "Rivertown", "Lakeside"]


def swap_school(text: str, profile: dict, i: int) -> str:
    """Counterfactual: replace every school name with a different, fictional one."""
    t = text
    schools = [e.get("institution") for e in (profile or {}).get("education", []) if e.get("institution")]
    new = SCHOOL_POOL[i % len(SCHOOL_POOL)]
    for sname in sorted(schools, key=len, reverse=True):
        t = re.sub(re.escape(sname), new, t, flags=re.I)
    return SCHOOL_RE.sub(new, t)


_MONTH_NUM = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}


def swap_date_format(text: str) -> str:
    """Counterfactual: 'Jan 2020' becomes '01/2020'. The dates are the same, only their writing changes."""
    def repl(m):
        n = _MONTH_NUM.get(m.group(1)[:3].lower())
        return "%02d/%s" % (n, m.group(2)) if n else m.group(0)
    return re.sub(r"\b([A-Za-z]{3,9})\.?,?\s+((?:19|20)\d{2})\b", repl, text)
