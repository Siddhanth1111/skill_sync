"""SQLAlchemy models and session factory.

Tables follow section 6 of the spec. Not yet present (later phases): users, gold_labels, experiment_runs.
Embeddings are stored as JSON lists and searched with numpy (the pgvector column is a Postgres-only upgrade).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
                        create_engine, inspect, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.utcnow()


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)  # filled once auth lands (Phase 3)
    title: Mapped[str] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text)
    requirements_source: Mapped[Optional[str]] = mapped_column(String(10))  # llm | rules
    mode: Mapped[str] = mapped_column(String(10), default="recruiter")  # recruiter | student
    scores_stale: Mapped[bool] = mapped_column(Boolean, default=False)  # requirement text edited after scoring
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    requirements = relationship("Requirement", cascade="all, delete-orphan", order_by="Requirement.idx")
    candidates = relationship("Candidate", cascade="all, delete-orphan")


class Requirement(Base):
    __tablename__ = "requirements"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(12))  # skill | experience | education
    importance: Mapped[str] = mapped_column(String(8))  # must | should | nice
    weight: Mapped[float] = mapped_column(Float)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # skills, years_required, degree_level_required


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)  # null in student mode
    filename: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(10), default="queued", index=True)  # queued|parsing|done|failed
    error: Mapped[Optional[str]] = mapped_column(String(300))
    profile: Mapped[Optional[dict]] = mapped_column(JSON)
    raw_text: Mapped[Optional[str]] = mapped_column(Text)  # extracted text; Stage 9 verifies quotes against it
    needs_ocr: Mapped[bool] = mapped_column(Boolean, default=False)
    parse_confidence: Mapped[Optional[dict]] = mapped_column(JSON)
    source: Mapped[Optional[str]] = mapped_column(String(10))  # llm | rules
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    chunks = relationship("Chunk", cascade="all, delete-orphan", order_by="Chunk.idx")


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Optional[list]] = mapped_column(JSON)  # normalised vector; dimension set by the model
    embedding_model: Mapped[Optional[str]] = mapped_column(String(120))


class ScoreRun(Base):
    __tablename__ = "score_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="running")  # running | done | failed
    done: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(String(300))
    config: Mapped[Optional[dict]] = mapped_column(JSON)  # model names and thresholds used, for reproducibility
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class Score(Base):
    """One cell of the requirement-evidence matrix. Latest run only: re-scoring replaces the row."""
    __tablename__ = "scores"
    __table_args__ = (UniqueConstraint("candidate_id", "requirement_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[Optional[int]] = mapped_column(Integer)
    rerank_score: Mapped[float] = mapped_column(Float)
    final_score: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(8))  # met | partial | not_met
    chunk_id: Mapped[Optional[int]] = mapped_column(Integer)
    similarity: Mapped[Optional[float]] = mapped_column(Float)
    quote: Mapped[Optional[str]] = mapped_column(Text)  # only set when verified
    section: Mapped[Optional[str]] = mapped_column(String(20))
    entailment: Mapped[Optional[float]] = mapped_column(Float)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)


class RerankCache(Base):
    """Cache key: requirement hash, segment text hash, reranker model (spec: repeated runs are fast)."""
    __tablename__ = "rerank_cache"
    __table_args__ = (UniqueConstraint("req_hash", "seg_hash", "model"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    req_hash: Mapped[str] = mapped_column(String(40), index=True)
    seg_hash: Mapped[str] = mapped_column(String(40), index=True)
    model: Mapped[str] = mapped_column(String(120))
    score: Mapped[float] = mapped_column(Float)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), unique=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer)
    rating: Mapped[str] = mapped_column(String(4))  # up | down
    features: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class JobModel(Base):
    """The optional learned score for one job (logistic regression over requirement-level features)."""
    __tablename__ = "job_models"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), unique=True)
    params: Mapped[dict] = mapped_column(JSON)
    metrics: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AuditRun(Base):
    __tablename__ = "audit_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # blind | counterfactual | impact | weat
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


def ensure_columns(engine) -> None:
    """Tiny dev-time migration: add columns that newer code expects to tables created by an older version.
    (create_all only creates missing tables.) Use a real migration tool before production."""
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in have:
                ddl = "ALTER TABLE %s ADD COLUMN %s %s" % (table.name, col.name, col.type.compile(engine.dialect))
                if col.default is not None and getattr(col.default, "is_scalar", False):
                    v = col.default.arg
                    ddl += " DEFAULT %s" % (("'%s'" % v) if isinstance(v, str) else int(v))
                with engine.begin() as conn:
                    conn.execute(text(ddl))


def make_session_factory(database_url: str) -> sessionmaker:
    kwargs = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}  # worker threads share the engine; wait for locks
        if ":memory:" in database_url or database_url in ("sqlite://", "sqlite:///"):
            kwargs["poolclass"] = StaticPool
    engine = create_engine(database_url, **kwargs)
    if database_url.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _fk_on(conn, _):  # SQLite ignores ON DELETE CASCADE unless asked
            conn.execute("PRAGMA foreign_keys=ON")
            if "memory" not in str(engine.url):
                conn.execute("PRAGMA journal_mode=WAL")  # readers no longer block the writers (3 ingest workers)

    Base.metadata.create_all(engine)
    ensure_columns(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
