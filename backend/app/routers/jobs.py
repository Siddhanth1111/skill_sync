from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import Candidate, Job, Requirement, User
from ..deps import get_db, log_activity, owned_job, recruiter_or_student
from ..schemas import JobCreate, JobOut, RequirementPatch
from ..services.extraction import extract_requirements, weight_for
from ..services.requirements import normalize_query, requirement_meta

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _with_counts(db: Session, jobs: List[Job]) -> List[Job]:
    """Attach resume counts (transient attributes read by JobOut)."""
    ids = [j.id for j in jobs]
    total = dict(db.execute(select(Candidate.job_id, func.count()).where(Candidate.job_id.in_(ids)).group_by(Candidate.job_id)).all()) if ids else {}
    parsed = dict(db.execute(select(Candidate.job_id, func.count()).where(Candidate.job_id.in_(ids), Candidate.status == "done")
                             .group_by(Candidate.job_id)).all()) if ids else {}
    for j in jobs:
        j.candidate_count, j.parsed_count = total.get(j.id, 0), parsed.get(j.id, 0)
    return jobs


@router.post("", response_model=JobOut, status_code=201)
def create_job(body: JobCreate, request: Request, user: User = Depends(recruiter_or_student), db: Session = Depends(get_db)):
    """Stage 4: turn the pasted job description into typed, weighted requirements the user can edit.
    A student's jobs are kept apart from recruiter jobs: the mode follows the account role."""
    settings = request.app.state.settings
    extraction, source = extract_requirements(body.text, request.app.state.llm, settings)
    job = Job(user_id=user.id, title=body.title, text=body.text, requirements_source=source,
              mode="student" if user.role == "student" else "recruiter")
    for i, r in enumerate(extraction.requirements):
        job.requirements.append(Requirement(
            idx=i, text=r.text, type=r.type, importance=r.importance,
            weight=weight_for(r.kind, r.importance, settings), meta=requirement_meta(r),
        ))
    db.add(job)
    db.commit()
    log_activity(db, user.id, "job_created", "job_id=%d requirements=%d source=%s" % (job.id, len(job.requirements), source))
    return job


@router.get("", response_model=List[JobOut])
def list_jobs(user: User = Depends(recruiter_or_student), db: Session = Depends(get_db)):
    return _with_counts(db, list(db.scalars(select(Job).where(Job.user_id == user.id).order_by(Job.id.desc())).all()))


@router.get("/{job_id}", response_model=JobOut)
def get_job(job: Job = Depends(owned_job), db: Session = Depends(get_db)):
    return _with_counts(db, [job])[0]


@router.delete("/{job_id}", status_code=204)
def delete_job(job: Job = Depends(owned_job), user: User = Depends(recruiter_or_student), db: Session = Depends(get_db)):
    """Delete a job with its candidates, chunks, scores, feedback, audits and learned model."""
    for c in db.scalars(select(Candidate).where(Candidate.job_id == job.id)).all():
        db.delete(c)
    db.flush()
    db.delete(job)
    db.commit()
    log_activity(db, user.id, "job_deleted", "job_id=%d" % job.id)


@router.patch("/{job_id}/requirements", response_model=JobOut)
def patch_requirements(patches: List[RequirementPatch], request: Request, job: Job = Depends(owned_job),
                       db: Session = Depends(get_db)):
    """Edit wording, importance, kind and any-of mode before scoring. Changing importance or kind resets the weight
    to that level's default (0 for soft skills and duties) unless an explicit weight is sent in the same patch.
    Changing wording, kind or mode marks stored scores stale. meta.weight_source says where the weight came from."""
    settings = request.app.state.settings
    by_id = {r.id: r for r in job.requirements}
    for p in patches:
        req = by_id.get(p.id)
        if req is None:
            raise HTTPException(404, "requirement %d not in this job" % p.id)
        meta = dict(req.meta or {})
        if p.text is not None and p.text.strip() != req.text:
            req.text = p.text.strip()
            meta["query"] = normalize_query(req.text)
            job.scores_stale = True  # stored evidence was found for the old wording; re-run scoring
        if p.skills_mode is not None and p.skills_mode != meta.get("skills_mode"):
            meta["skills_mode"] = p.skills_mode
            job.scores_stale = True
        if p.kind is not None and p.kind != meta.get("kind"):
            meta["kind"] = p.kind
            req.type = {"education": "education", "experience": "experience"}.get(p.kind, "skill")
            job.scores_stale = True
        if p.importance is not None:
            req.importance = p.importance
        if p.importance is not None or p.kind is not None:
            req.weight, meta["weight_source"] = weight_for(meta.get("kind"), req.importance, settings), "default"
        if p.weight is not None:
            req.weight, meta["weight_source"] = p.weight, "manual"
        req.meta = meta
    db.commit()
    return _with_counts(db, [job])[0]
