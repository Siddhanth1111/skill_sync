from typing import Optional

from fastapi import FastAPI

from .config import Settings, get_settings
from .db import make_session_factory
from .routers import candidates, fairness, jobs, learning, resumes, scoring, student
from .services.ingest import IngestPool
from .services.llm import LLMClient, OllamaClient
from .services.models import Models, build_models


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
