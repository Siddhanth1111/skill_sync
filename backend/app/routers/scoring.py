"""Stages 7-12 over HTTP: run scoring, read the matrix and ranking, open a candidate's explanation."""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..db import Candidate, Feedback, Job, JobModel, ScoreRun, User
from ..deps import get_db, log_activity, owned_candidate, owned_job, recruiter_only
from ..services import feedback as fb
from ..services.explain import explanation
from ..services.matrix import job_candidates, job_matrix, req_dicts, score_dict
from ..services.ranking import rank_candidates, thresholds
from ..services.scoring import config_snapshot, load_scores, req_views, score_candidate_to_db

log = logging.getLogger(__name__)
router = APIRouter(tags=["scoring"])


def run_scoring(session_factory: sessionmaker, run_id: int, models, settings: Settings) -> None:
    """Background task: Stages 7-10 for every parsed candidate of the job. Progress is saved after each one."""
    with session_factory() as db:
        run = db.get(ScoreRun, run_id)
        try:
            job = db.get(Job, run.job_id)
            reqs = req_views(job.requirements)
            qvecs = models.embedder.encode_queries([r.text for r in reqs])
            for cand in job_candidates(db, job):
                score_candidate_to_db(db, cand, reqs, qvecs, models, settings, run_id)
                run.done += 1
                db.commit()
            job.scores_stale = False
            run.status, run.finished_at = "done", datetime.utcnow()
        except Exception as exc:  # model download or load problems land here; the message is shown to the user
            log.exception("scoring run %s failed", run_id)
            db.rollback()
            run = db.get(ScoreRun, run_id)
            run.status, run.error = "failed", ("%s: %s" % (type(exc).__name__, exc))[:300]
        finally:
            db.commit()


def _run_out(run: ScoreRun) -> dict:
    return {"run_id": run.id, "job_id": run.job_id, "status": run.status, "done": run.done, "total": run.total,
            "error": run.error, "config": run.config}


@router.post("/jobs/{job_id}/score", status_code=202)
def start_scoring(request: Request, job: Job = Depends(owned_job), user: User = Depends(recruiter_only),
                  db: Session = Depends(get_db)):
    job_id = job.id
    state = request.app.state
    if not job.requirements:
        raise HTTPException(400, "job has no requirements")
    cands = job_candidates(db, job)
    if not cands:
        raise HTTPException(400, "no parsed resumes yet; upload resumes and wait for them to finish")
    running = db.scalar(select(ScoreRun).where(ScoreRun.job_id == job_id, ScoreRun.status == "running"))
    if running:
        raise HTTPException(409, "a scoring run is already in progress")
    run = ScoreRun(job_id=job_id, total=len(cands), config=config_snapshot(state.models, state.settings))
    db.add(run)
    db.commit()
    log_activity(db, user.id, "scoring_started", "job_id=%d candidates=%d" % (job_id, len(cands)))
    state.pool.submit_task(run_scoring, state.session_factory, run.id, state.models, state.settings)
    return _run_out(run)


@router.get("/jobs/{job_id}/score/status")
def scoring_status(job: Job = Depends(owned_job), _: User = Depends(recruiter_only), db: Session = Depends(get_db)):
    job_id = job.id
    run = db.scalar(select(ScoreRun).where(ScoreRun.job_id == job_id).order_by(ScoreRun.id.desc()))
    return _run_out(run) if run else {"status": "none", "done": 0, "total": 0}


@router.get("/jobs/{job_id}/matrix")
def matrix(request: Request, job: Job = Depends(owned_job), _: User = Depends(recruiter_only), db: Session = Depends(get_db)):
    """The requirement-evidence matrix. The browser re-ranks from this with no further server calls."""
    return job_matrix(db, job, request.app.state.settings)


@router.get("/jobs/{job_id}/ranking")
def ranking(request: Request, job: Job = Depends(owned_job), _: User = Depends(recruiter_only), db: Session = Depends(get_db)):
    """Server-side ranking with the stored weights (the browser computes the identical formula)."""
    settings = request.app.state.settings
    job_id = job.id
    cands = {c.id: c for c in job_candidates(db, job)}
    loaded = load_scores(db, list(cands))
    reqs = req_dicts(job)
    matrix_ = {cid: {rid: s.final_score for rid, s in rows.items()} for cid, rows in loaded.items() if rows}
    ranked = rank_candidates(reqs, matrix_, thresholds(settings))
    model = db.scalar(select(JobModel).where(JobModel.job_id == job_id))
    ratings = {f.candidate_id: f.rating for f in db.scalars(select(Feedback).where(Feedback.candidate_id.in_(list(cands))))}
    for r in ranked:
        c = cands[r["candidate_id"]]
        r.update(filename=c.filename, name=(c.profile or {}).get("name"), rating=ratings.get(c.id))
        if model:
            r["learned_probability"] = fb.predict(model.params, fb.features_for(reqs, matrix_[c.id], settings))["probability"]
    return {"job_id": job_id, "stale": job.scores_stale, "ranking": ranked,
            "unscored": [{"candidate_id": cid, "filename": cands[cid].filename} for cid in cands if cid not in matrix_]}


@router.get("/candidates/{candidate_id}/explanation")
def candidate_explanation(request: Request, cand: Candidate = Depends(owned_candidate), _: User = Depends(recruiter_only),
                          db: Session = Depends(get_db)):
    """Stage 12: requirements (unmet first), gaps by points gained, and a narrative limited to verified quotes."""
    state = request.app.state
    if cand.job_id is None:
        raise HTTPException(404, "Candidate not found in a job.")
    job = db.get(Job, cand.job_id)
    scores = {rid: score_dict(s, state.settings) for rid, s in load_scores(db, [cand.id])[cand.id].items()}
    if not scores:
        raise HTTPException(409, "this candidate has not been scored yet")
    return explanation(cand, req_dicts(job), scores, state.llm, state.settings)
