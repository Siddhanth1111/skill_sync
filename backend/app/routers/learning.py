"""Stage 13 over HTTP: ratings, training the optional learned score, reading it back."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Candidate, Feedback, GoldLabel, Job, JobModel, User
from ..deps import get_db, log_activity, owned_candidate, owned_job, recruiter_only
from ..schemas import EvidenceFeedbackIn, FeedbackIn
from ..services import feedback as fb
from ..services.matrix import job_candidates, req_dicts, score_matrix
from ..services.scoring import load_scores

router = APIRouter(tags=["learning"])


def _counts(db: Session, job: Job) -> dict:
    ids = [c.id for c in db.scalars(select(Candidate).where(Candidate.job_id == job.id))]
    rows = db.scalars(select(Feedback).where(Feedback.candidate_id.in_(ids))).all() if ids else []
    return {"up": sum(r.rating == "up" for r in rows), "down": sum(r.rating == "down" for r in rows)}


@router.post("/candidates/{candidate_id}/feedback")
def rate_candidate(body: FeedbackIn, request: Request, cand: Candidate = Depends(owned_candidate),
                   user: User = Depends(recruiter_only), db: Session = Depends(get_db)):
    """Store a thumbs up or down with the candidate's requirement-level features (one rating per candidate)."""
    settings = request.app.state.settings
    if cand.job_id is None:
        raise HTTPException(404, "Candidate not found in a job.")
    job = db.get(Job, cand.job_id)
    scores = score_matrix(db, job).get(cand.id)
    if not scores:
        raise HTTPException(409, "Score this job before rating candidates.")
    features = fb.features_for(req_dicts(job), scores, settings)
    row = db.scalar(select(Feedback).where(Feedback.candidate_id == cand.id))
    if row:
        row.rating, row.features = body.rating, features
    else:
        db.add(Feedback(candidate_id=cand.id, rating=body.rating, features=features))
    db.commit()
    return {"candidate_id": cand.id, "rating": body.rating, **_counts(db, job)}


@router.post("/jobs/{job_id}/model/train")
def train_model(request: Request, job: Job = Depends(owned_job), user: User = Depends(recruiter_only),
                db: Session = Depends(get_db)):
    settings = request.app.state.settings
    job_id = job.id
    ids = [c.id for c in job_candidates(db, job)]
    rows = db.scalars(select(Feedback).where(Feedback.candidate_id.in_(ids))).all() if ids else []
    up, down = sum(r.rating == "up" for r in rows), sum(r.rating == "down" for r in rows)
    if not fb.can_train(up, down, settings):
        raise HTTPException(409, "need at least %d ratings with at least %d of each kind (have %d up, %d down)"
                            % (settings.min_ratings, settings.min_ratings_each_kind, up, down))
    result = fb.train([fb.vector(r.features) for r in rows], [1 if r.rating == "up" else 0 for r in rows])
    existing = db.scalar(select(JobModel).where(JobModel.job_id == job_id))
    if existing:
        existing.params, existing.metrics = result["params"], result["metrics"]
    else:
        db.add(JobModel(job_id=job_id, params=result["params"], metrics=result["metrics"]))
    db.commit()
    log_activity(db, user.id, "model_trained", "job_id=%d n=%d" % (job_id, len(rows)))
    return get_model(request, job, user, db)


@router.get("/jobs/{job_id}/model")
def get_model(request: Request, job: Job = Depends(owned_job), _: User = Depends(recruiter_only), db: Session = Depends(get_db)):
    settings = request.app.state.settings
    job_id = job.id
    counts = _counts(db, job)
    model = db.scalar(select(JobModel).where(JobModel.job_id == job_id))
    out = {"job_id": job_id, **counts, "can_train": fb.can_train(counts["up"], counts["down"], settings),
           "min_ratings": settings.min_ratings, "min_each": settings.min_ratings_each_kind,
           "trained": model is not None, "metrics": model.metrics if model else None, "learned": {}}
    if model:
        reqs = req_dicts(job)
        for cid, scores in score_matrix(db, job).items():
            out["learned"][str(cid)] = fb.predict(model.params, fb.features_for(reqs, scores, settings))
        out["note"] = ("Cross-validated AUC near 0.5 means the ratings carry no learnable signal. The learned score "
                       "is shown beside the rule-based score and never replaces it.")
    return out


@router.post("/candidates/{candidate_id}/evidence-feedback", status_code=201)
def evidence_feedback(body: EvidenceFeedbackIn, cand: Candidate = Depends(owned_candidate),
                      user: User = Depends(recruiter_only), db: Session = Depends(get_db)):
    """The wrong-evidence button: record that the evidence for one requirement is wrong (or right, or missing).
    Stores ids, the system's status and the reviewer's grade: these rows seed the gold set. One verdict per
    reviewer, candidate and requirement; sending it again replaces it."""
    if cand.job_id is None:
        raise HTTPException(404, "Candidate not found in a job.")
    job = db.get(Job, cand.job_id)
    if body.requirement_id not in {r.id for r in job.requirements}:
        raise HTTPException(404, "Requirement not found in this job.")
    stored = load_scores(db, [cand.id])[cand.id].get(body.requirement_id)
    if stored is None:
        raise HTTPException(409, "This requirement was not scored for this candidate.")
    row = db.scalar(select(GoldLabel).where(GoldLabel.candidate_id == cand.id, GoldLabel.requirement_id == body.requirement_id,
                                            GoldLabel.user_id == user.id))
    if row is None:
        row = GoldLabel(candidate_id=cand.id, requirement_id=body.requirement_id, user_id=user.id)
        db.add(row)
    row.judgement, row.grade = body.judgement, body.grade
    row.model_status, row.model_score, row.pipeline_version = stored.status, stored.final_score, stored.pipeline_version
    db.commit()
    log_activity(db, user.id, "evidence_flag", "candidate_id=%d requirement_id=%d %s" % (cand.id, body.requirement_id, body.judgement))
    return {"saved": True, "judgement": row.judgement, "grade": row.grade}


@router.get("/candidates/{candidate_id}/evidence-feedback")
def my_evidence_feedback(cand: Candidate = Depends(owned_candidate), user: User = Depends(recruiter_only),
                         db: Session = Depends(get_db)):
    rows = db.scalars(select(GoldLabel).where(GoldLabel.candidate_id == cand.id, GoldLabel.user_id == user.id)).all()
    return {str(r.requirement_id): {"judgement": r.judgement, "grade": r.grade} for r in rows}
