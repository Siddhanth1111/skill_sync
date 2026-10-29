"""SQLAlchemy models and session factory.

Tables follow section 6 of the spec for Stages 1-5. Not yet present (later phases): users, scores, feedback,
audit_runs, gold_labels, experiment_runs, and the pgvector `embedding` column on chunks (Stage 6).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
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
    # Stage 6 adds: embedding = Vector(<dimension of the configured model>)


def make_session_factory(database_url: str) -> sessionmaker:
    kwargs = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}  # worker threads share the engine
        if ":memory:" in database_url or database_url in ("sqlite://", "sqlite:///"):
            kwargs["poolclass"] = StaticPool
    engine = create_engine(database_url, **kwargs)
    if database_url.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _fk_on(conn, _):  # SQLite ignores ON DELETE CASCADE unless asked
            conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
