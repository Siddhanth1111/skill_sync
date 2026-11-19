"""Admin: users, activity log, removal of a user and their data. Admins never see resumes or candidates."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import ActivityLog, Candidate, Job, User
from ..deps import admin_only, get_db, log_activity
from .auth import delete_user_data

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
def list_users(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    jobs = dict(db.execute(select(Job.user_id, func.count()).group_by(Job.user_id)).all())
    cands = dict(db.execute(select(Candidate.user_id, func.count()).group_by(Candidate.user_id)).all())
    last = dict(db.execute(select(ActivityLog.user_id, func.max(ActivityLog.created_at))
                           .where(ActivityLog.action == "login").group_by(ActivityLog.user_id)).all())
    users = db.scalars(select(User).order_by(User.id)).all()
    return [{"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role, "created_at": u.created_at.isoformat(),
             "last_login": last[u.id].isoformat() if last.get(u.id) else None,
             "jobs": jobs.get(u.id, 0), "candidates": cands.get(u.id, 0)} for u in users]


@router.get("/stats")
def stats(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    by_role = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
    return {"users": sum(by_role.values()), "by_role": by_role,
            "jobs": db.scalar(select(func.count()).select_from(Job)) or 0,
            "candidates": db.scalar(select(func.count()).select_from(Candidate)) or 0}


@router.get("/activity")
def activity(limit: int = 100, action: Optional[str] = None, _: User = Depends(admin_only), db: Session = Depends(get_db)):
    q = select(ActivityLog).order_by(ActivityLog.id.desc()).limit(min(max(limit, 1), 500))
    if action:
        q = q.where(ActivityLog.action == action)
    emails = dict(db.execute(select(User.id, User.email)).all())
    return [{"id": a.id, "user_id": a.user_id, "email": emails.get(a.user_id), "action": a.action, "detail": a.detail,
             "created_at": a.created_at.isoformat()} for a in db.scalars(q)]


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    """Delete a user and all of their data (cascade). An admin cannot delete themselves."""
    if user_id == admin.id:
        raise HTTPException(400, "You cannot delete your own admin account.")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found.")
    removed = delete_user_data(db, user_id)
    db.delete(user)
    db.commit()
    log_activity(db, admin.id, "user_deleted", "user_id=%d role=%s jobs=%d candidates=%d" % (user_id, user.role, removed["jobs"], removed["candidates"]))
    return {"deleted_user": user_id, **removed}
