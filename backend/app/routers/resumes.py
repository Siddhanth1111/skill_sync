from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import Candidate, Job
from ..deps import get_db
from ..schemas import CandidateStatus, JobStatus
from ..services.ingest import save_temp
from ..services.parsing import validate_upload

router = APIRouter(prefix="/jobs", tags=["resumes"])


@router.post("/{job_id}/resumes", response_model=List[CandidateStatus], status_code=202)
async def upload_resumes(job_id: int, files: List[UploadFile], request: Request, db: Session = Depends(get_db)):
    """Stage 1: validate each file (type, size, content), create a row per file, and queue valid ones.
    Invalid files become 'failed' rows with a reason. They never stop the rest of the batch."""
    settings = request.app.state.settings
    if db.get(Job, job_id) is None:
        raise HTTPException(404, "job not found")

    existing = db.scalar(select(func.count()).select_from(Candidate).where(Candidate.job_id == job_id)) or 0
    if existing + len(files) > settings.max_files_per_job:
        raise HTTPException(413, "a job can hold at most %d resumes (%d already uploaded)"
                            % (settings.max_files_per_job, existing))

    rows, queue = [], []
    for f in files:
        content = await f.read(settings.max_file_bytes + 1)  # read one byte past the limit, never the whole oversize file
        name = (f.filename or "unnamed")[:300]
        reason = validate_upload(name, content, settings)
        cand = Candidate(job_id=job_id, filename=name, status="failed" if reason else "queued", error=reason)
        db.add(cand)
        rows.append(cand)
        if reason is None:
            queue.append((cand, content))
    db.commit()  # assigns ids

    for cand, content in queue:
        request.app.state.pool.submit(cand.id, save_temp(content, cand.filename))
    return rows


@router.get("/{job_id}/status", response_model=JobStatus)
def job_status(job_id: int, db: Session = Depends(get_db)):
    """Polled by the interface: per-file status plus counts."""
    if db.get(Job, job_id) is None:
        raise HTTPException(404, "job not found")
    rows = db.scalars(select(Candidate).where(Candidate.job_id == job_id).order_by(Candidate.id)).all()
    counts = {s: 0 for s in ("queued", "parsing", "done", "failed")}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    return JobStatus(job_id=job_id, total=len(rows), counts=counts, files=rows)
