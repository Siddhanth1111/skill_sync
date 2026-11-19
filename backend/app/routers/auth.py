"""Register, sign in, who am I, and 'delete my data' (spec section 8: Auth, Admin and privacy)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Candidate, Job, User
from ..deps import current_user, get_db, log_activity
from ..schemas import LoginIn, RegisterIn, TokenOut, UserOut
from ..security import create_token, hash_password, verify_password

router = APIRouter(tags=["auth"])


def _token(request: Request, user: User) -> TokenOut:
    s = request.app.state
    return TokenOut(access_token=create_token(user.id, user.role, s.jwt_secret, s.settings.jwt_expire_minutes),
                    user=UserOut.model_validate(user))


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "An account with this email already exists.")
    user = User(email=body.email, password_hash=hash_password(body.password), full_name=body.full_name.strip() or None,
                role=body.role)
    db.add(user)
    db.commit()
    log_activity(db, user.id, "register", user.role)
    return _token(request, user)


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    throttle = request.app.state.throttle
    if throttle.blocked(email):
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    user = db.scalar(select(User).where(User.email == email))
    if not verify_password(body.password, user.password_hash if user else None):
        throttle.fail(email)
        raise HTTPException(401, "Incorrect email or password.")  # same message for unknown email and wrong password
    throttle.clear(email)
    log_activity(db, user.id, "login")
    return _token(request, user)


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


def delete_user_data(db: Session, user_id: int) -> dict:
    """Remove every job, candidate and everything hanging off them (chunks, scores, feedback, audits, models)."""
    jobs = db.scalars(select(Job).where(Job.user_id == user_id)).all()
    cands = db.scalars(select(Candidate).where(Candidate.user_id == user_id)).all()
    for c in cands:  # ORM cascade removes chunks; the database cascades scores and feedback
        db.delete(c)
    db.flush()
    for j in jobs:
        db.delete(j)
    db.commit()
    return {"jobs": len(jobs), "candidates": len(cands)}


@router.delete("/me/data")
def delete_my_data(delete_account: bool = False, request: Request = None, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    """Privacy: delete all of the signed-in user's records. With ?delete_account=true the account goes too."""
    removed = delete_user_data(db, user.id)
    log_activity(db, user.id, "data_deleted", "jobs=%d candidates=%d" % (removed["jobs"], removed["candidates"]))
    if delete_account:
        db.delete(db.get(User, user.id))
        db.commit()
    return {**removed, "account_deleted": delete_account}
