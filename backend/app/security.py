"""Password hashing (bcrypt), signed expiring JWTs, a login throttle, and the signing-secret loader."""
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import bcrypt
import jwt

from .config import Settings

ALGORITHM = "HS256"
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(rounds=10)).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    """Always does one bcrypt comparison, even for unknown users, so response time does not reveal which emails exist."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), (password_hash or _DUMMY_HASH).encode()) and password_hash is not None
    except ValueError:
        return False


def load_secret(settings: Settings) -> str:
    """SKILLSYNC_JWT_SECRET if set, else a random secret generated once and stored in a git-ignored file (mode 600)."""
    if settings.jwt_secret:
        return settings.jwt_secret
    path = Path(__file__).resolve().parent.parent / ".jwt_secret"
    if path.exists():
        return path.read_text().strip()
    value = secrets.token_urlsafe(48)
    path.write_text(value)
    os.chmod(path, 0o600)
    return value


def create_token(user_id: int, role: str, secret: str, minutes: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user_id), "role": role, "iat": now, "exp": now + timedelta(minutes=minutes)},
                      secret, algorithm=ALGORITHM)


def decode_token(token: str, secret: str) -> Optional[dict]:
    try:
        return jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        return None


class LoginThrottle:
    """Blocks an email after too many failed logins in a window (in memory, per process)."""

    def __init__(self, max_failures: int, window_s: int):
        self.max, self.window = max_failures, window_s
        self._fails: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> List[float]:
        cutoff = time.time() - self.window
        self._fails[key] = [t for t in self._fails.get(key, []) if t > cutoff]
        return self._fails[key]

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self.max

    def fail(self, key: str) -> None:
        with self._lock:
            self._recent(key).append(time.time())

    def clear(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)
