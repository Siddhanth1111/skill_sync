from typing import Optional

from fastapi import FastAPI

from .config import Settings, get_settings
from .db import User, make_session_factory
from .security import LoginThrottle, hash_password, load_secret
from .routers import admin, analytics, auth, candidates, fairness, jobs, learning, resumes, scoring, student
from .services.ingest import IngestPool
from .services.llm import LLMClient, OllamaClient
from .services.models import Models, build_models


def _seed_admin(app: FastAPI, settings: Settings) -> None:
    """Optional: create an admin from SKILLSYNC_ADMIN_EMAIL / SKILLSYNC_ADMIN_PASSWORD if it does not exist."""
    if not (settings.admin_email and settings.admin_password):
        return
    from sqlalchemy import select
    with app.state.session_factory() as db:
        email = settings.admin_email.strip().lower()
        if not db.scalar(select(User).where(User.email == email)):
            db.add(User(email=email, password_hash=hash_password(settings.admin_password), full_name="Administrator", role="admin"))
            db.commit()


def create_app(settings: Optional[Settings] = None, llm: Optional[LLMClient] = None,
               models: Optional[Models] = None) -> FastAPI:
    """App factory. Tests pass their own settings and a mock LLM."""
    settings = settings or get_settings()
    app = FastAPI(title="SkillSync", version="0.1.0")
    app.state.settings = settings
    app.state.session_factory = make_session_factory(settings.database_url)
    app.state.llm = llm if llm is not None else OllamaClient(settings)
    app.state.models = models if models is not None else build_models(settings)
    app.state.pool = IngestPool(app.state.session_factory, settings, app.state.llm, app.state.models)
    app.state.jwt_secret = load_secret(settings)
    app.state.throttle = LoginThrottle(settings.login_max_failures, settings.login_window_s)
    _seed_admin(app, settings)
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(analytics.router)
    app.include_router(jobs.router)
    app.include_router(resumes.router)
    app.include_router(candidates.router)
    app.include_router(scoring.router)
    app.include_router(learning.router)
    app.include_router(fairness.router)
    app.include_router(student.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


# Run with: uvicorn app.main:create_app --factory
