"""Builds the requirement-evidence matrix payload and the plain dicts the ranking code works on."""
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import Candidate, Job, Score
from .ranking import thresholds
from .scoring import load_scores


def req_dicts(job: Job) -> List[dict]:
    return [{"id": r.id, "idx": r.idx, "text": r.text, "type": r.type, "importance": r.importance,
             "weight": r.weight, "meta": r.meta or {}} for r in job.requirements]


def score_dict(s: Score, settings: Settings) -> dict:
    t = s.trace or {}
    # Same rule as scoring (see score_candidate): weak means the model doubts it and the ontology cannot vouch for it.
    weak = bool(t["weak"]) if "weak" in t else bool(s.verified and s.entailment is not None and s.entailment < settings.entailment_threshold)
    return {"score": s.final_score, "rerank_score": s.rerank_score, "status": s.status, "quote": s.quote,
            "section": s.section, "entailment": s.entailment, "verified": s.verified, "weak": weak,
            "similarity": s.similarity, "sentence": s.sentence, "hub": bool(s.hub),
            "unverifiable": s.status == "not_verifiable", "skills": t.get("skills"), "parts": t.get("parts"), "below_minimum": t.get("below_minimum", False), "rule": t.get("rule"),
            "pipeline_version": s.pipeline_version}


def job_candidates(db: Session, job: Job) -> List[Candidate]:
    return list(db.scalars(select(Candidate).where(Candidate.job_id == job.id, Candidate.status == "done")
                           .order_by(Candidate.id)))


def score_matrix(db: Session, job: Job) -> Dict[int, Dict[int, float]]:
    """candidate_id -> requirement_id -> score, for candidates that have been scored."""
    cands = job_candidates(db, job)
    loaded = load_scores(db, [c.id for c in cands])
    return {cid: {rid: s.final_score for rid, s in rows.items()} for cid, rows in loaded.items() if rows}


def unverifiable_flags(loaded: Dict[int, Dict[int, Score]]) -> Dict[int, Dict[int, bool]]:
    """candidate_id -> requirement_id -> True where the evidence could not be read (excluded from the must penalty)."""
    return {cid: {rid: True for rid, s in rows.items() if s.status == "not_verifiable"} for cid, rows in loaded.items()}


def job_matrix(db: Session, job: Job, settings: Settings) -> dict:
    cands = job_candidates(db, job)
    loaded = load_scores(db, [c.id for c in cands])
    return {
        "job_id": job.id,
        "stale": bool(job.scores_stale),
        "thresholds": thresholds(settings),
        "entailment_threshold": settings.entailment_threshold,
        "hub_max_reuse": settings.hub_max_reuse,
        "requirements": req_dicts(job),
        "candidates": [{
            "id": c.id,
            "filename": c.filename,
            "name": (c.profile or {}).get("name"),
            "scored": bool(loaded[c.id]),
            "scores": {str(rid): score_dict(s, settings) for rid, s in loaded[c.id].items()},
        } for c in cands],
    }
