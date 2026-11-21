"""Skill-to-evidence links and years per skill (review items A7, D6). Computed by code from the resume units:
a skill gets the dated periods of every role entry that mentions it (overlaps merged), plus the skills it implies
(a PostgreSQL role counts toward SQL and RDBMS)."""
from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

from .dates import parse_date, total_years
from .taxonomy import CANON, ENTRIES, _ancestors, mentions


def skills_in(text: str) -> List[str]:
    return [c for c in CANON if mentions(text, c)]


def link_skills(units: Sequence) -> Tuple[Dict[str, List[int]], Dict[str, float]]:
    """units: objects with idx, text, context, start, end. Returns (skill -> unit indexes, skill -> years)."""
    links: Dict[str, List[int]] = defaultdict(list)
    periods: Dict[str, Dict[Tuple[str, str], tuple]] = defaultdict(dict)  # skill -> {(start, end): (d0, d1)}
    entry_skills: Dict[Tuple[str, str, str], set] = defaultdict(set)
    for u in units:
        found = set(skills_in(u.text))
        if u.start:
            found |= set(skills_in(u.context))  # "Python Developer, Acme" names the skill in the header
        expanded = set(found)
        for s in found:
            expanded |= _ancestors(s)
        for s in expanded:
            links[s].append(u.idx)
        if u.start:
            entry_skills[(u.context, u.start, u.end or "present")] |= expanded
    for (ctx, s, e), skills in entry_skills.items():
        d0, d1 = parse_date(s), parse_date(e, is_end=True)
        if d0 and d1 and d0 <= d1:
            for skill in skills:
                periods[skill][(s, e)] = (d0, d1)
    years = {skill: total_years(p.values()) for skill, p in periods.items()}
    return dict(links), years


def undated_roles(units: Sequence) -> int:
    """Experience entries (by context) that have no parseable dates: their years count as zero (item A8)."""
    seen = {}
    for u in units:
        if u.section == "experience":
            seen[u.context] = seen.get(u.context, False) or bool(u.start)
    return sum(1 for dated in seen.values() if not dated)
