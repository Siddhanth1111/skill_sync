"""Stage 15: student mode. One resume against several job descriptions, a prioritised roadmap, and a what-if
simulator that rescores a temporary copy and saves nothing."""
import logging
import re
from typing import Dict, List, Optional

from pydantic import BaseModel

from ..config import Settings
from .llm import LLMClient, LLMInvalidOutput, LLMUnavailable, generate_validated
from .ranking import final_score
from .rerank import tokens
from .scoring import candidate_total, score_candidate, units_for_text
from .taxonomy import find_skills

log = logging.getLogger(__name__)

PHASES = {"must": "start_here", "should": "next", "nice": "later"}

ROADMAP_SYSTEM = (
    "You are a career coach. For each unmet job requirement, suggest ONE concrete action that would let the student "
    "show they meet it, such as building a small project or adding a measurable result to an existing resume "
    "bullet. Stay strictly within the requirement text: do not add other skills or topics. Return JSON only."
)


class Step(BaseModel):
    requirement_id: int
    action: str


class RoadmapPlan(BaseModel):
    steps: List[Step]


def template_action(req: dict, status: str) -> str:
    text = req["text"]
    if req["type"] == "experience":
        n = req["meta"].get("years_required")
        return ("Build up relevant experience%s through internships, freelance work or a substantial project, and add "
                "dated entries with measurable results to your Experience section." % (" toward %s years" % n if n else ""))
    if req["type"] == "education":
        return "Plan or complete the required degree or an equivalent certification, and list it under Education."
    if status == "partial":
        return 'Add a measurable result (a number, size or outcome) to an existing bullet that shows "%s".' % text
    return 'Build a small project that demonstrates "%s" and add it to your Projects section with a measurable result.' % text


def _grounded(action: str, req: dict) -> bool:
    """The suggestion must share at least one content word with the requirement (constrained to its text)."""
    allowed = tokens(req["text"]) | {s.lower() for s in req["meta"].get("skills", [])}
    return bool(tokens(action) & allowed)


def draft_actions(unmet: List[dict], llm: Optional[LLMClient], settings: Settings) -> Dict[int, dict]:
    out = {r["id"]: {"action": template_action(r, r["status"]), "source": "template"} for r in unmet}
    if llm is None or not unmet:
        return out
    prompt = "Unmet requirements:\n" + "\n".join("- id %d: %s" % (r["id"], r["text"]) for r in unmet)
    try:
        plan = generate_validated(llm, ROADMAP_SYSTEM, prompt, RoadmapPlan, settings.llm_max_retries)
    except (LLMUnavailable, LLMInvalidOutput) as exc:
        log.warning("roadmap LLM failed (%s); using templates", type(exc).__name__)
        return out
    by_id = {r["id"]: r for r in unmet}
    for step in plan.steps:
        req = by_id.get(step.requirement_id)
        if req and 10 <= len(step.action.strip()) <= 400 and _grounded(step.action, req):
            out[req["id"]] = {"action": step.action.strip(), "source": "llm"}
    return out


def build_roadmap(reqs: List[dict], scores: Dict[int, dict], llm, settings: Settings) -> dict:
    """reqs: dicts (id, text, type, importance, weight, meta). scores: requirement_id -> score dict."""
    def total(sc: Dict[int, float]) -> float:
        return final_score([(r["importance"], float(r["weight"]), sc[r["id"]]) for r in reqs if r["id"] in sc and float(r["weight"]) > 0],
                           settings.met_threshold, settings.partial_threshold, settings.must_not_met_penalty)

    current = {rid: s["score"] for rid, s in scores.items()}
    wsum = sum(float(r["weight"]) for r in reqs if r["id"] in current and float(r["weight"]) > 0) or 1.0
    unmet = [{**r, "status": scores[r["id"]]["status"], "score": scores[r["id"]]["score"]}
             for r in reqs if r["id"] in scores and scores[r["id"]]["status"] != "met" and float(r["weight"]) > 0]
    level = {"must": 0, "should": 1, "nice": 2}
    unmet.sort(key=lambda r: (level[r["importance"]], -float(r["weight"]) * (1 - r["score"]), r["idx"]))
    actions = draft_actions(unmet, llm, settings)

    running, steps = dict(current), []
    start = total(current)
    for r in unmet:
        running[r["id"]] = 1.0
        steps.append({
            "requirement_id": r["id"], "text": r["text"], "type": r["type"], "importance": r["importance"],
            "phase": PHASES[r["importance"]], "status": r["status"], "score": r["score"],
            "points_gain": 100.0 * float(r["weight"]) * (1 - r["score"]) / wsum,
            "projected_score": total(running), "action": actions[r["id"]]["action"],
            "action_source": actions[r["id"]]["source"],
        })
    return {"current_score": start, "final_projected_score": total(running), "steps": steps}


def check_addition(addition: str) -> Optional[str]:
    """A what-if needs an evidence-style statement (what was built or done, ideally with a result). Returns the
    reason it is rejected, or None. This keeps the simulator from rewarding a bare list of keywords (F6)."""
    words = addition.split()
    if len(words) < 6:
        return "describe what you built or did in a full sentence, with a result if you have one"
    acted = re.search(r"\b(built|developed|designed|implemented|created|led|wrote|deployed|automated|migrated|"
                      r"optimi[sz]ed|reduced|improved|launched|trained|analy[sz]ed|managed|delivered|tuned|used)\b",
                      addition, re.I)
    if not acted and not re.search(r"\d", addition):
        return "use an action verb (built, designed, deployed ...) or a number, so the text reads as evidence"
    return None


def whatif_rescore(cand, addition: str, reqs, qvecs, models, settings: Settings, db):
    """Rescore a temporary copy of the resume with the described project added. Returns (text, profile, rows)."""
    text = whatif_text(cand.raw_text or "", addition)
    profile = whatif_profile(cand.profile or {}, addition)
    st, views, profile = units_for_text(text, profile, models, settings)
    rows = score_candidate(reqs, qvecs, views, st, profile, models, settings, db)
    return text, profile, rows


def whatif_text(raw_text: str, addition: str) -> str:
    """A temporary copy of the resume with the described project or skill appended under a Projects heading."""
    return raw_text.rstrip() + "\n\nPROJECTS\n" + addition.strip()


def whatif_profile(profile: dict, addition: str) -> dict:
    p = dict(profile or {})
    known = {s.lower() for s in p.get("skills", [])}
    p["skills"] = list(p.get("skills", [])) + [s for s in find_skills(addition) if s.lower() not in known]
    return p
