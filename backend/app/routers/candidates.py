from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import Candidate, User
from ..deps import get_db, log_activity, owned_candidate, recruiter_or_student
from ..schemas import CandidateDetail

router = APIRouter(tags=["candidates"])


@router.get("/candidates/{candidate_id}", response_model=CandidateDetail)
def get_candidate(cand: Candidate = Depends(owned_candidate)):
    """Parsed profile, parse confidence, labelled chunks and extracted text for one resume (Stages 2-5 output)."""
    return cand


@router.delete("/candidates/{candidate_id}", status_code=204)
def delete_candidate(cand: Candidate = Depends(owned_candidate), user: User = Depends(recruiter_or_student),
                     db: Session = Depends(get_db)):
    """Remove one resume with its chunks, scores and rating."""
    cid = cand.id
    db.delete(cand)
    db.commit()
    log_activity(db, user.id, "candidate_deleted", "candidate_id=%d" % cid)
