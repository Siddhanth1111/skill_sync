"""Stage 12: per-candidate explanation, ranked gaps, and a narrative that may only quote verified text."""
import logging
import re
from typing import Dict, List, Optional

from pydantic import BaseModel

from ..config import Settings
from .llm import LLMClient, LLMInvalidOutput, LLMUnavailable, generate_validated
from .ranking import final_score, gaps
from .verify import quote_in_text

log = logging.getLogger(__name__)

STATUS_ORDER = {"not_met": 0, "partial": 1, "met": 2}
QUOTED = re.compile(r'["“]([^"“”]{6,})["”]')

NARRATIVE_SYSTEM = (
    "You write a short, neutral summary (3 to 5 sentences) of how a candidate matches a job, for a recruiter who "
    "makes the decision. Use ONLY the evidence given. When you quote the resume, copy the quote exactly, inside "
    "double quotes. Never invent facts, never give a hire or reject recommendation, never mention scores you were "
    "not given."
)


class Narrative(BaseModel):
    narrative: str


def ordered_rows(reqs: List[dict], scores: Dict[int, dict]) -> List[dict]:
    """Every requirement with its score row, unmet first (then partial, then met), heavier weights first."""
    rows = [{**r, **scores[r["id"]], "requirement_id": r["id"]} for r in reqs if r["id"] in scores]
    return sorted(rows, key=lambda x: (STATUS_ORDER[x["status"]], -float(x["weight"]), x["idx"]))


def _first_line(quote: str, limit: int = 160) -> Optional[str]:
    line = next((l.strip() for l in quote.splitlines() if l.strip()), "")
    return line if 6 <= len(line) <= limit else None


def template_narrative(name: str, total: float, rows: List[dict], gap_list: List[dict]) -> str:
    met = [r for r in rows if r["status"] == "met"]
    musts = [r for r in rows if r["importance"] == "must"]
    musts_met = [r for r in musts if r["status"] == "met"]
    parts = ["%s scores %.0f out of 100 on this job. %d of %d requirements are met, including %d of %d must-haves."
             % (name, total * 100, len(met), len(rows), len(musts_met), len(musts))]
    for r in sorted(met, key=lambda x: -float(x["weight"]))[:2]:
        line = _first_line(r["quote"]) if r.get("verified") and r.get("quote") else None
        if line:
            parts.append('Evidence for "%s" (%s section): "%s".' % (r["text"], r["section"], line))
    by_id = {r["id"]: r for r in rows}
    missing = [by_id[g["requirement_id"]]["text"] for g in gap_list[:3] if g["requirement_id"] in by_id]
    if missing:
        parts.append("Largest gaps: %s." % "; ".join(missing))
    return " ".join(parts)


def narrative_is_grounded(text: str, resume_text: str) -> bool:
    """Every quoted string must appear in the resume. Anything else returns False and the template is used."""
    return bool(text.strip()) and all(quote_in_text(q, resume_text) for q in QUOTED.findall(text))


def build_narrative(name: str, rows: List[dict], total: float, gap_list: List[dict], resume_text: str,
                    llm: Optional[LLMClient], settings: Settings) -> Dict[str, str]:
    template = template_narrative(name, total, rows, gap_list)
    evidence = [r for r in rows if r.get("verified") and r.get("quote")]
    if llm is None or not evidence:
        return {"text": template, "source": "template"}
    lines = ["Job requirements and verified resume evidence:"]
    for r in rows:
        q = ("\n  evidence: \"%s\"" % " ".join(r["quote"].split())[:300]) if r.get("verified") and r.get("quote") else ""
        lines.append("- [%s, %s] %s%s" % (r["importance"], r["status"], r["text"], q))
    try:
        out = generate_validated(llm, NARRATIVE_SYSTEM, "\n".join(lines), Narrative, settings.llm_max_retries)
    except (LLMUnavailable, LLMInvalidOutput) as exc:
        log.warning("narrative LLM failed (%s); using template", type(exc).__name__)
        return {"text": template, "source": "template"}
    if narrative_is_grounded(out.narrative, resume_text):
        return {"text": out.narrative.strip(), "source": "llm"}
    log.warning("narrative contained an unverifiable quote; using template")
    return {"text": template, "source": "template"}


def explanation(cand, reqs: List[dict], scores: Dict[int, dict], llm, settings: Settings) -> dict:
    total = final_score([(r["importance"], float(r["weight"]), scores[r["id"]]["score"]) for r in reqs if r["id"] in scores],
                        settings.met_threshold, settings.partial_threshold, settings.must_not_met_penalty)
    rows = ordered_rows(reqs, scores)
    for r in rows:
        r["final_score"] = r["score"]
    gap_list = gaps(reqs, {rid: s["score"] for rid, s in scores.items()})
    for g in gap_list:
        g["text"] = next(r["text"] for r in reqs if r["id"] == g["requirement_id"])
    name = (cand.profile or {}).get("name") or cand.filename
    return {"candidate_id": cand.id, "name": name, "final_score": total, "requirements": rows, "gaps": gap_list,
            "narrative": build_narrative(name, rows, total, gap_list, cand.raw_text or "", llm, settings)}
