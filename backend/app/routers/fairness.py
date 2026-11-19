"""Stage 14 over HTTP. Every run is saved to audit_runs so the trend can be shown."""
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import AuditRun, Candidate, Job
from ..deps import get_db
from ..schemas import ImpactIn, WeatIn
from ..services import fairness as fx
from ..services.matrix import job_candidates
from ..services.ranking import final_score
from ..services.scoring import load_scores, req_views
from .scoring import get_job_or_404

router = APIRouter(prefix="/jobs", tags=["fairness"])


def _inputs(db: Session, job: Job, request: Request):
    """Scored candidates with their stored baseline, plus the requirement views and query vectors."""
    state = request.app.state
    reqs = req_views(job.requirements)
    loaded = load_scores(db, [c.id for c in job_candidates(db, job)])
    cands = []
    for c in job_candidates(db, job):
        rows = loaded[c.id]
        if not rows:
            continue
        baseline = final_score([(q.importance, q.weight, rows[q.id].final_score) for q in reqs if q.id in rows],
                               state.settings.met_threshold, state.settings.partial_threshold,
                               state.settings.must_not_met_penalty)
        cands.append({"id": c.id, "name": (c.profile or {}).get("name") or c.filename, "text": c.raw_text or "",
                      "profile": c.profile or {}, "baseline": baseline})
    if not cands:
        raise HTTPException(409, "score this job first; audits compare against stored scores")
    qvecs = state.models.embedder.encode_queries([r.text for r in reqs])
    return state, reqs, qvecs, cands


def _save(db: Session, job_id: int, kind: str, params: dict, metrics: dict) -> dict:
    run = AuditRun(job_id=job_id, kind=kind, params=params, metrics=metrics)
    db.add(run)
    db.commit()
    return {"audit_id": run.id, "kind": kind, "created_at": run.created_at.isoformat(), **metrics}


@router.post("/{job_id}/audit/blind")
def audit_blind(job_id: int, request: Request, db: Session = Depends(get_db)):
    job = get_job_or_404(db, job_id)
    state, reqs, qvecs, cands = _inputs(db, job, request)
    return _save(db, job_id, "blind", {}, fx.blind_audit(cands, reqs, qvecs, state.models, state.settings, db))


@router.post("/{job_id}/audit/counterfactual")
def audit_counterfactual(job_id: int, request: Request, db: Session = Depends(get_db)):
    job = get_job_or_404(db, job_id)
    state, reqs, qvecs, cands = _inputs(db, job, request)
    return _save(db, job_id, "counterfactual", {}, fx.counterfactual_audit(cands, reqs, qvecs, state.models, state.settings, db))


@router.post("/{job_id}/audit/impact")
def audit_impact(job_id: int, body: ImpactIn, request: Request, db: Session = Depends(get_db)):
    job = get_job_or_404(db, job_id)
    _, _, _, cands = _inputs(db, job, request)
    groups = {int(k): v for k, v in body.groups.items()}
    finals = {c["id"]: c["baseline"] for c in cands if c["id"] in groups}
    if len(finals) < 2 or len(set(groups[c] for c in finals)) < 2:
        raise HTTPException(400, "provide group labels for at least two scored candidates and two distinct groups")
    result = fx.impact_audit(finals, groups, body.top_n, request.app.state.settings)
    return _save(db, job_id, "impact", {"top_n": body.top_n}, result)


@router.post("/{job_id}/audit/weat")
def audit_weat(job_id: int, body: WeatIn, request: Request, db: Session = Depends(get_db)):
    get_job_or_404(db, job_id)
    state = request.app.state
    result = fx.weat_probe(state.models.embedder, body.groups, state.settings)
    return _save(db, job_id, "weat", {"groups": body.groups}, result)


@router.get("/{job_id}/audit/history")
def audit_history(job_id: int, db: Session = Depends(get_db)):
    """Monitoring over time: every saved run with its headline number."""
    get_job_or_404(db, job_id)
    runs = db.scalars(select(AuditRun).where(AuditRun.job_id == job_id).order_by(AuditRun.id)).all()
    return [{"audit_id": r.id, "kind": r.kind, "created_at": r.created_at.isoformat(), "params": r.params,
             "headline": (r.metrics or {}).get("headline")} for r in runs]
