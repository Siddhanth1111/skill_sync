"""Stage 15 over HTTP: match one resume to several jobs, roadmap, what-if."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Candidate, Job
from ..deps import get_db
from ..schemas import MatchIn, WhatIfIn
from ..services import student as st
from ..services.matrix import req_dicts, score_dict
from ..services.ranking import final_score
from ..services.retrieval import ChunkView
from ..services.chunking import chunk_resume
from ..services.scoring import (candidate_total, load_scores, req_views, score_candidate,
                                score_candidate_to_db)

router = APIRouter(prefix="/student", tags=["student"])


def _candidate(db: Session, cid: int) -> Candidate:
    cand = db.get(Candidate, cid)
    if cand is None or cand.job_id is not None:
        raise HTTPException(404, "student resume not found")
    if cand.status != "done":
        raise HTTPException(409, "resume is not parsed yet (status: %s)" % cand.status)
    return cand


def _job(db: Session, jid: int) -> Job:
    job = db.get(Job, jid)
    if job is None:
        raise HTTPException(404, "job %d not found" % jid)
    return job


def _summary(job: Job, rows, settings) -> dict:
    reqs = req_views(job.requirements)
    by_id = {r.requirement_id: r for r in rows}
    return {"job_id": job.id, "title": job.title, "final_score": candidate_total(rows, reqs, settings),
            "met": sum(r.status == "met" for r in rows), "partial": sum(r.status == "partial" for r in rows),
            "not_met": sum(r.status == "not_met" for r in rows),
            "musts_met": sum(1 for q in reqs if q.importance == "must" and q.id in by_id and by_id[q.id].status == "met"),
            "musts": sum(1 for q in reqs if q.importance == "must")}


@router.post("/match")
def match(body: MatchIn, request: Request, db: Session = Depends(get_db)):
    """Stages 2-11 for each job (the resume is already parsed and embedded). Jobs come back best match first."""
    state = request.app.state
    cand = _candidate(db, body.candidate_id)
    out = []
    for jid in body.job_ids:
        job = _job(db, jid)
        if not job.requirements:
            continue
        reqs = req_views(job.requirements)
        qvecs = state.models.embedder.encode_queries([r.text for r in reqs])
        rows = score_candidate_to_db(db, cand, reqs, qvecs, state.models, state.settings)
        out.append(_summary(job, rows, state.settings))
    out.sort(key=lambda r: (-r["final_score"], -r["musts_met"], r["job_id"]))
    return out


@router.get("/roadmap")
def roadmap(candidate_id: int, job_id: int, request: Request, db: Session = Depends(get_db)):
    state = request.app.state
    cand, job = _candidate(db, candidate_id), _job(db, job_id)
    reqs = req_dicts(job)
    scores = {rid: score_dict(s, state.settings) for rid, s in load_scores(db, [cand.id])[cand.id].items()
              if rid in {r["id"] for r in reqs}}
    if not scores:
        raise HTTPException(409, "run /student/match for this job first")
    return {"job_id": job.id, "title": job.title, **st.build_roadmap(reqs, scores, state.llm, state.settings)}


@router.post("/whatif")
def whatif(body: WhatIfIn, request: Request, db: Session = Depends(get_db)):
    """Rescore a temporary copy of the resume with a described project or skill added. Saves nothing."""
    state = request.app.state
    cand, job = _candidate(db, body.candidate_id), _job(db, body.job_id)
    reqs = req_views(job.requirements)
    stored = load_scores(db, [cand.id])[cand.id]
    if not all(r.id in stored for r in reqs):
        raise HTTPException(409, "run /student/match for this job first")
    text = st.whatif_text(cand.raw_text or "", body.addition)
    profile = st.whatif_profile(cand.profile or {}, body.addition)
    chunks = chunk_resume(text, state.settings.chunk_max_chars)
    vecs = state.models.embedder.encode_docs([c.text for c in chunks])
    views = [ChunkView(None, c.idx, c.section, c.text, v) for c, v in zip(chunks, vecs)]
    qvecs = state.models.embedder.encode_queries([r.text for r in reqs])
    new_rows = score_candidate(reqs, qvecs, views, text, profile, state.models, state.settings, db)
    before = final_score([(r.importance, r.weight, stored[r.id].final_score) for r in reqs],
                         state.settings.met_threshold, state.settings.partial_threshold, state.settings.must_not_met_penalty)
    after = candidate_total(new_rows, reqs, state.settings)
    changes = [{"requirement_id": r.id, "text": r.text, "before": stored[r.id].final_score, "after": n.final_score,
                "status_before": stored[r.id].status, "status_after": n.status}
               for r, n in zip(reqs, new_rows) if abs(n.final_score - stored[r.id].final_score) > 1e-9]
    return {"job_id": job.id, "before": before, "after": after, "delta_points": (after - before) * 100,
            "changes": changes, "saved": False}
