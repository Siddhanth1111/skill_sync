from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from ..db import Candidate
from ..deps import get_db
from ..schemas import CandidateDetail, CandidateStatus
from ..services.ingest import save_temp
from ..services.parsing import validate_upload

router = APIRouter(tags=["candidates"])


@router.get("/candidates/{candidate_id}", response_model=CandidateDetail)
def get_candidate(candidate_id: int, db: Session = Depends(get_db)):
    """Parsed profile, parse confidence and labelled chunks for one resume (what Stages 2-5 produced)."""
    cand = db.get(Candidate, candidate_id)
    if cand is None:
        raise HTTPException(404, "candidate not found")
    return cand


@router.post("/student/resume", response_model=CandidateStatus, status_code=202)
async def upload_student_resume(file: UploadFile, request: Request, db: Session = Depends(get_db)):
    """Student mode: one resume with no job attached (job_id is null). Same Stages 2-5 as recruiter uploads."""
    settings = request.app.state.settings
    content = await file.read(settings.max_file_bytes + 1)
    name = (file.filename or "unnamed")[:300]
    reason = validate_upload(name, content, settings)
    cand = Candidate(job_id=None, filename=name, status="failed" if reason else "queued", error=reason)
    db.add(cand)
    db.commit()
    if reason is None:
        request.app.state.pool.submit(cand.id, save_temp(content, name))
    return cand
