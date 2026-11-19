from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import Candidate, Job, Requirement, User
from ..deps import get_db, log_activity, owned_job, recruiter_or_student
from ..schemas import JobCreate, JobOut, RequirementPatch
from ..services.extraction import default_weight, extract_requirements

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
            weight=default_weight(r.importance, settings),
            meta={"skills": r.skills, "years_required": r.years_required,
                  "degree_level_required": r.degree_level_required},
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
    from sqlalchemy import select as _s
    from ..db import Candidate
    for c in db.scalars(_s(Candidate).where(Candidate.job_id == job.id)).all():
        db.delete(c)
    db.flush()
    db.delete(job)
    db.commit()
    log_activity(db, user.id, "job_deleted", "job_id=%d" % job.id)


@router.patch("/{job_id}/requirements", response_model=JobOut)
def patch_requirements(patches: List[RequirementPatch], request: Request, job: Job = Depends(owned_job),
                       db: Session = Depends(get_db)):
    """Edit text and importance before scoring. Changing importance resets the weight to that level's default
    unless an explicit weight is sent in the same patch. Changing the wording marks stored scores stale."""
    settings = request.app.state.settings
    by_id = {r.id: r for r in job.requirements}
    for p in patches:
        req = by_id.get(p.id)
        if req is None:
            raise HTTPException(404, "requirement %d not in this job" % p.id)
        if p.text is not None and p.text.strip() != req.text:
            req.text = p.text.strip()
            job.scores_stale = True  # stored evidence was found for the old wording; re-run scoring
        if p.importance is not None:
            req.importance = p.importance
            req.weight = default_weight(p.importance, settings)
        if p.weight is not None:
            req.weight = p.weight
    db.commit()
    return _with_counts(db, [job])[0]
