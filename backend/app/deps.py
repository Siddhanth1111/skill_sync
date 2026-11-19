"""Request dependencies: DB session, the signed-in user, role checks, and ownership checks.

Every query on user data goes through owned_job / owned_candidate, so one user can never read another's records
(a record that belongs to someone else looks exactly like a missing one: 404)."""
from typing import Iterator, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import ActivityLog, Candidate, Job, User
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as db:
        yield db


def current_user(request: Request, creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(401, "Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})
    if creds is None:
        raise unauthorized
    payload = decode_token(creds.credentials, request.app.state.jwt_secret)
    if payload is None:
        raise HTTPException(401, "Session expired. Sign in again.", headers={"WWW-Authenticate": "Bearer"})
    user = db.get(User, int(payload["sub"]))
    if user is None:  # deleted after the token was issued
        raise unauthorized
    return user


def require_roles(*roles: str):
    def check(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "This action is not available for %s accounts." % user.role)
        return user
    return check


recruiter_only = require_roles("recruiter")
student_only = require_roles("student")
admin_only = require_roles("admin")
recruiter_or_student = require_roles("recruiter", "student")


def owned_job(job_id: int, user: User = Depends(recruiter_or_student), db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(404, "Job not found.")
    return job


def owned_candidate(candidate_id: int, user: User = Depends(recruiter_or_student), db: Session = Depends(get_db)) -> Candidate:
    cand = db.get(Candidate, candidate_id)
    if cand is None or cand.user_id != user.id:
        raise HTTPException(404, "Candidate not found.")
    return cand


def log_activity(db: Session, user_id: Optional[int], action: str, detail: str = "") -> None:
    """Record an event for the admin activity log. detail must be ids or counts, never resume or personal text."""
    db.add(ActivityLog(user_id=user_id, action=action, detail=detail[:200]))
    db.commit()
