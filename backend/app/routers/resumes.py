from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import Candidate, Job, User
from ..deps import get_db, log_activity, owned_job, recruiter_only
from ..schemas import CandidateStatus, JobStatus
from ..services.ingest import save_temp
from ..services.parsing import validate_upload

router = APIRouter(prefix="/jobs", tags=["resumes"])


@router.post("/{job_id}/resumes", response_model=List[CandidateStatus], status_code=202)
async def upload_resumes(files: List[UploadFile], request: Request, job: Job = Depends(owned_job),
                         user: User = Depends(recruiter_only), db: Session = Depends(get_db)):
    """Stage 1: validate each file (type, size, content), create a row per file, and queue valid ones.
    Invalid files become 'failed' rows with a reason. They never stop the rest of the batch."""
    settings = request.app.state.settings
    existing = db.scalar(select(func.count()).select_from(Candidate).where(Candidate.job_id == job.id)) or 0
    if existing + len(files) > settings.max_files_per_job:
        raise HTTPException(413, "A job can hold at most %d resumes (%d already uploaded)."
                            % (settings.max_files_per_job, existing))

    rows, queue = [], []
    for f in files:
        content = await f.read(settings.max_file_bytes + 1)  # read one byte past the limit, never the whole oversize file
        name = (f.filename or "unnamed")[:300]
        reason = validate_upload(name, content, settings)
        cand = Candidate(job_id=job.id, user_id=user.id, filename=name, status="failed" if reason else "queued", error=reason)
        db.add(cand)
        rows.append(cand)
        if reason is None:
            queue.append((cand, content))
    db.commit()  # assigns ids

    for cand, content in queue:
        request.app.state.pool.submit(cand.id, save_temp(content, cand.filename))
    log_activity(db, user.id, "resumes_uploaded", "job_id=%d files=%d accepted=%d" % (job.id, len(files), len(queue)))
    return rows


@router.get("/{job_id}/status", response_model=JobStatus)
def job_status(job: Job = Depends(owned_job), _: User = Depends(recruiter_only), db: Session = Depends(get_db)):
    """Polled by the interface: per-file status plus counts."""
    rows = db.scalars(select(Candidate).where(Candidate.job_id == job.id).order_by(Candidate.id)).all()
    counts = {s: 0 for s in ("queued", "parsing", "done", "failed")}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    return JobStatus(job_id=job.id, total=len(rows), counts=counts, files=rows)
