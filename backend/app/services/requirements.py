"""Requirement understanding (review items B1 to B7): kinds, year ranges, any-of lists, normalised queries,
near-duplicate merging. Pure functions over text so the LLM path and the rule path share one definition.

Only hard skills, experience and education are scored. Soft skills and duties are kept and shown, never scored.
"""
import re
from typing import Dict, List, Optional, Tuple

from ..schemas import JDRequirement, SCORED_KINDS
from .taxonomy import ENTRIES, find_skills

NUM = r"(\d+(?:\.\d+)?)"
RANGE_RE = re.compile(NUM + r"\s*(?:-|–|—|to)\s*" + NUM + r"\s*\+?\s*(?:years?|yrs?)", re.I)
YEARS_RE = re.compile(NUM + r"\s*\+?\s*(?:years?|yrs?)", re.I)
# "minimum of 3 years", "at least 3 years" and "3 or more years" all mean 3.
MIN_RE = re.compile(r"(?:minimum(?: of)?|at least|min\.?)\s*" + NUM + r"\s*\+?\s*(?:years?|yrs?)|" + NUM + r"\s+or\s+more\s+(?:years?|yrs?)", re.I)

SOFT_RE = re.compile(
    r"\b(communicat\w*|team ?work|collaborat\w*|leadership|stakeholder\w*|interpersonal|problem[- ]solving|"
    r"self[- ]motivated|attention to detail|time management|adaptab\w*|work ethic|fast[- ]paced|proactive|ownership|"
    r"critical thinking|presentation skills|negotiat\w*|team player|multi-?task\w*|organi[sz]ational|"
    r"curious\w*|passion\w*|positive attitude|work independently|self[- ]starter)\b", re.I)
DUTY_RE = re.compile(
    r"^(?:you will\s+)?(?:design|build|develop|implement|maintain|own|lead|manage|write|deliver|collaborate|"
    r"work with|work closely|participate|support|create|drive|review|ensure|monitor|deploy|architect|mentor|"
    r"partner|contribute|define|analy[sz]e|investigate|troubleshoot|document|coordinate|help|run|operate)\b", re.I)

FILLER_PREFIX = re.compile(
    r"^(?:(?:we(?:'re| are) looking for|you (?:have|will have|bring|are|should have|possess)|must have|should have|"
    r"required|preferred|strong|good|solid|deep|proven|excellent|extensive|hands[- ]on|working|demonstrated|"
    r"in-depth|basic|advanced|sound|thorough|understanding of|knowledge of|experience (?:in|with|of|using)|"
    r"proficiency (?:in|with)|proficient (?:in|with)|familiarity with|familiar with|ability to|expertise in|"
    r"background in|exposure to|competence in|an?|the)\s+)+", re.I)
FILLER_SUFFIX = re.compile(r"\s*(?:skills?|experience|knowledge|is a plus|a plus|preferred|required)\s*$", re.I)
YEARS_PHRASE = re.compile(NUM + r"(?:\s*(?:-|–|—|to)\s*" + NUM + r")?\s*\+?\s*(?:years?|yrs?)\s*(?:of\s+)?", re.I)
WORD = re.compile(r"[a-z0-9+#.]+")
STOP = set("a an the and or of to in for with on at by is are be as we our you your their this that from using use "
           "etc including such like".split())
RANK = {"must": 3, "should": 2, "nice": 1}
# phrases containing '/' that are one skill, not an either-or
_SLASH_SKILLS = sorted((a for e in ENTRIES for a in [e] + ENTRIES[e].get("aliases", []) if "/" in a), key=len, reverse=True)


def parse_years(text: str) -> Tuple[Optional[float], Optional[float]]:
    """(minimum, maximum) years stated in the text. '2 to 5 years' -> (2, 5); '3+ years' -> (3, None)."""
    m = RANGE_RE.search(text)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return (min(lo, hi), max(lo, hi))
    m = MIN_RE.search(text)
    if m:
        return (float(m.group(1) or m.group(2)), None)
    m = YEARS_RE.search(text)
    return (float(m.group(1)), None) if m else (None, None)


def normalize_query(text: str) -> str:
    """The requirement without filler ('Strong understanding of X' -> 'X') and without the year count."""
    t = YEARS_PHRASE.sub("", " ".join(text.split()))
    for _ in range(3):
        before = t
        t = FILLER_PREFIX.sub("", t.strip(" -:;,."))
        t = FILLER_SUFFIX.sub("", t)
        if t == before:
            break
    t = t.strip(" -:;,.")
    return t if len(t) >= 2 else " ".join(text.split())


def detect_skills_mode(text: str, skills: List[str]) -> str:
    """'any' for 'A / B / C', 'A or B', 'any of ...', 'one of ...'; otherwise 'all'. Needs two or more skills."""
    if len(skills) < 2:
        return "all"
    t = text.lower()
    for phrase in _SLASH_SKILLS:  # 'CI/CD' is one skill
        t = t.replace(phrase, " ")
    if re.search(r"\b(any of|one of|either|at least one|or similar|or equivalent|and/or)\b", t):
        return "any"
    if re.search(r"\w\s*/\s*\w", t):
        return "any"
    # 'X, Y or Z' (or) without an 'and' joining skills
    return "any" if re.search(r"\bor\b", t) and not re.search(r"\band\b", t) else "all"


def derive_kind(text: str, skills: List[str], type_: str, years: Optional[float], degree: Optional[int],
                duty_hint: bool = False) -> str:
    if type_ == "education" or degree:
        return "education"
    if type_ == "experience" or years:
        return "experience"
    if duty_hint and DUTY_RE.match(text.strip()):
        return "duty"  # "Build services with Python" under Responsibilities is a duty, not a skill requirement
    if skills or find_skills(text):
        return "hard_skill"
    if SOFT_RE.search(text):
        return "soft_skill"
    if duty_hint or DUTY_RE.match(text.strip()):
        return "duty"
    return "hard_skill"  # a concept the ontology does not know (e.g. "RDBMS design"); the reranker judges it


def finalize_requirement(r: JDRequirement, duty_hint: bool = False) -> JDRequirement:
    """Make one requirement consistent: years range -> minimum, skills list, kind, any-of mode."""
    years_min, _ = parse_years(r.text)
    years = years_min if years_min is not None else r.years_required
    skills, seen = [], set()
    for s in (r.skills or []) or find_skills(r.text):
        if s.strip() and s.strip().lower() not in seen:
            seen.add(s.strip().lower())
            skills.append(s.strip())
    degree = r.degree_level_required
    kind = r.kind
    derived = derive_kind(r.text, skills, r.type, years, degree, duty_hint)
    if kind is None or kind not in SCORED_KINDS + ("soft_skill", "duty"):
        kind = derived
    elif derived in ("education", "experience"):
        kind = derived  # numbers and degrees in the text outrank the model's label
    elif kind == "hard_skill" and derived in ("soft_skill", "duty") and not skills:
        kind = derived  # the model called a soft skill or duty a hard skill but no skill is named
    elif kind in ("soft_skill", "duty") and derived == "hard_skill" and skills:
        kind = "hard_skill"
    type_ = {"education": "education", "experience": "experience"}.get(kind, "skill")
    mode = detect_skills_mode(r.text, skills) if r.skills_mode == "all" else r.skills_mode
    return r.model_copy(update={"kind": kind, "type": type_, "skills": skills, "years_required": years,
                                "skills_mode": mode})


def requirement_meta(r: JDRequirement) -> Dict:
    """What is stored in Requirement.meta."""
    years_min, years_max = parse_years(r.text)
    return {
        "skills": r.skills, "skills_mode": r.skills_mode, "kind": r.kind,
        "years_required": r.years_required, "years_min": years_min if years_min is not None else r.years_required,
        "years_max": years_max, "degree_level_required": r.degree_level_required,
        "query": normalize_query(r.text), "weight_source": "default",
    }


def is_scored(kind: Optional[str]) -> bool:
    return kind in SCORED_KINDS or kind is None  # old rows without a kind are scored as before


def _toks(text: str) -> set:
    out = set()
    for t in WORD.findall(text.lower()):
        t = t.strip(".")
        if t and t not in STOP:
            out.add(t[:-1] if len(t) > 3 and t.endswith("s") else t)
    return out


def dedupe_requirements(reqs: List[JDRequirement]) -> List[JDRequirement]:
    """Merge near-duplicates of the same kind: the one that reads as the same query once filler is removed.
    The stronger importance wins and skills are unioned. (Token overlap, not embeddings: no model is needed here.)"""
    out: List[JDRequirement] = []
    sigs: List[set] = []
    for r in reqs:
        sig = _toks(normalize_query(r.text)) | {s.lower() for s in r.skills}
        hit = None
        for i, (o, osig) in enumerate(zip(out, sigs)):
            if o.kind != r.kind or o.years_required != r.years_required or o.degree_level_required != r.degree_level_required:
                continue
            inter = len(sig & osig)
            if inter and inter / len(sig | osig) >= 0.8:  # "Python" and "Python and SQL" are different requirements
                hit = i
                break
        if hit is None:
            out.append(r)
            sigs.append(sig)
            continue
        keep = out[hit]
        imp = keep.importance if RANK[keep.importance] >= RANK[r.importance] else r.importance
        out[hit] = keep.model_copy(update={"importance": imp, "skills": list(dict.fromkeys(keep.skills + r.skills))})
        sigs[hit] = sigs[hit] | sig
    return out


def promote_if_nothing_scored(reqs: List[JDRequirement]) -> List[JDRequirement]:
    """A posting that lists only duties would score nothing. Duties that name a skill then count as skills."""
    if any(r.kind in SCORED_KINDS for r in reqs):
        return reqs
    return [r.model_copy(update={"kind": "hard_skill", "type": "skill"}) if r.kind == "duty" and r.skills else r
            for r in reqs]
