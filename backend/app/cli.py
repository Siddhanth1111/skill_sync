"""Operator commands.

    python -m app.cli create-admin you@example.com      create the first admin
    python -m app.cli export-gold gold.jsonl             write reviewers' evidence verdicts as gold-set seeds
"""
import getpass
import json
import sys

from sqlalchemy import select

from .config import get_settings
from .db import Candidate, GoldLabel, Requirement, Score, User, make_session_factory
from .security import hash_password


def create_admin(email: str, password: str) -> str:
    sf = make_session_factory(get_settings().database_url)
    with sf() as db:
        email = email.strip().lower()
        user = db.scalar(select(User).where(User.email == email))
        if user:
            user.role, user.password_hash = "admin", hash_password(password)
            msg = "updated existing user to admin"
        else:
            db.add(User(email=email, password_hash=hash_password(password), full_name="Administrator", role="admin"))
            msg = "created admin"
        db.commit()
    return msg


def export_gold(path: str) -> int:
    """One JSON line per reviewer verdict: requirement text, the supporting sentence the system showed (from the
    identity-free text), what the system said, and the reviewer's judgement and grade. This is the only place a
    verdict is joined to resume text, so run it deliberately and keep the file out of version control."""
    sf = make_session_factory(get_settings().database_url)
    n = 0
    with sf() as db, open(path, "w", encoding="utf-8") as out:
        for g in db.scalars(select(GoldLabel).order_by(GoldLabel.id)):
            req, cand = db.get(Requirement, g.requirement_id), db.get(Candidate, g.candidate_id)
            sc = db.scalar(select(Score).where(Score.candidate_id == g.candidate_id, Score.requirement_id == g.requirement_id))
            out.write(json.dumps({
                "requirement": req.text, "kind": (req.meta or {}).get("kind"), "sentence": sc.sentence if sc else None,
                "quote": sc.quote if sc else None, "model_status": g.model_status, "model_score": g.model_score,
                "judgement": g.judgement, "grade": g.grade, "pipeline_version": g.pipeline_version,
                "job_id": cand.job_id if cand else None}) + "\n")
            n += 1
    return n


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "export-gold":
        print("wrote %d verdicts to %s" % (export_gold(sys.argv[2]), sys.argv[2]))
        sys.exit(0)
    if len(sys.argv) != 3 or sys.argv[1] != "create-admin":
        sys.exit("usage: python -m app.cli create-admin EMAIL | python -m app.cli export-gold FILE")
    pw = getpass.getpass("Password (8 to 72 characters): ")
    if not 8 <= len(pw) <= 72:
        sys.exit("password must be 8 to 72 characters")
    print(create_admin(sys.argv[2], pw))
