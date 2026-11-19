"""Operator commands. Create the first admin:  python -m app.cli create-admin you@example.com"""
import getpass
import sys

from sqlalchemy import select

from .config import get_settings
from .db import User, make_session_factory
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


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "create-admin":
        sys.exit("usage: python -m app.cli create-admin EMAIL")
    pw = getpass.getpass("Password (8 to 72 characters): ")
    if not 8 <= len(pw) <= 72:
        sys.exit("password must be 8 to 72 characters")
    print(create_admin(sys.argv[2], pw))
