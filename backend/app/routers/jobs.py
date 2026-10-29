from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Job, Requirement
from ..deps import get_db
from ..schemas import JobCreate, JobOut, RequirementPatch
from ..services.extraction import default_weight, extract_requirements

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _get_job(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@router.post("", response_model=JobOut, status_code=201)
def create_job(body: JobCreate, request: Request, db: Session = Depends(get_db)):
    """Stage 4: turn the pasted job description into typed, weighted requirements the recruiter can edit."""
    settings = request.app.state.settings
    extraction, source = extract_requirements(body.text, request.app.state.llm, settings)
    job = Job(title=body.title, text=body.text, requirements_source=source)
    for i, r in enumerate(extraction.requirements):
        job.requirements.append(Requirement(
            idx=i, text=r.text, type=r.type, importance=r.importance,
            weight=default_weight(r.importance, settings),
            meta={"skills": r.skills, "years_required": r.years_required,
                  "degree_level_required": r.degree_level_required},
        ))
    db.add(job)
    db.commit()
    return job


@router.get("", response_model=List[JobOut])
def list_jobs(db: Session = Depends(get_db)):
    return db.scalars(select(Job).order_by(Job.id.desc())).all()


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    return _get_job(db, job_id)


@router.patch("/{job_id}/requirements", response_model=JobOut)
def patch_requirements(job_id: int, patches: List[RequirementPatch], request: Request, db: Session = Depends(get_db)):
    """Recruiter edits text and importance before scoring. Changing importance resets the weight to that
    level's default unless an explicit weight is sent in the same patch."""
    settings = request.app.state.settings
    job = _get_job(db, job_id)
    by_id = {r.id: r for r in job.requirements}
    for p in patches:
        req = by_id.get(p.id)
        if req is None:
            raise HTTPException(404, "requirement %d not in this job" % p.id)
        if p.text is not None:
            req.text = p.text.strip()
        if p.importance is not None:
            req.importance = p.importance
            req.weight = default_weight(p.importance, settings)
        if p.weight is not None:
            req.weight = p.weight
    db.commit()
    return job
