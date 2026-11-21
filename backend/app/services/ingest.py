"""Stages 1-5 orchestration: process one uploaded file end to end, and the worker pool that runs them."""
import logging
import os
import shutil
import tempfile
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Callable, List, Optional

from sqlalchemy.orm import sessionmaker

from ..config import Settings
from ..db import Candidate, Chunk
from .chunking import chunk_resume
from .embeddings import embed_chunks
from .extraction import extract_profile
from .llm import LLMClient
from .parsing import ParseError, extract_text, ocr_pdf_page, parse_confidence
from .scoring import make_chunk_rows, scoring_text_for
from .skillgraph import link_skills, undated_roles

log = logging.getLogger(__name__)  # only ids and error classes are logged, never resume content


def process_candidate(
    session_factory: sessionmaker,
    candidate_id: int,
    path: str,
    settings: Settings,
    llm: Optional[LLMClient],
    ocr_page: Callable = ocr_pdf_page,
    embedder=None,
) -> None:
    """Run Stages 2-5 for one file. Never raises: any failure is stored on the row so the batch continues.
    The temporary file is always deleted afterwards."""
    with session_factory() as db:
        cand = db.get(Candidate, candidate_id)
        try:
            cand.status = "parsing"
            db.commit()

            doc = extract_text(path, settings, ocr_page)                      # Stage 2
            profile = extract_profile(doc.text, llm, settings)                # Stage 3
            # Stage 5: the scorer reads identity-free text (blind by default); units are bullets with context.
            scoring_text = scoring_text_for(doc.text, profile.model_dump(), settings)
            units = chunk_resume(scoring_text, settings.chunk_max_chars)
            profile.skill_links, profile.skill_years = link_skills(units)     # evidence links and years per skill
            gaps = undated_roles(units)
            if gaps:
                profile.warnings.append("%d role(s) have no dates and count as 0 years of experience" % gaps)

            # Stage 6 runs BEFORE any row is modified: the first embedding call can take minutes (model download),
            # and a half-written transaction would hold the database write lock for all that time.
            rows = make_chunk_rows(units)
            if embedder is not None:
                embed_chunks(rows, embedder)

            cand.raw_text = doc.text
            cand.scoring_text = scoring_text
            cand.chunk_version = 2
            cand.needs_ocr = doc.ocr_used
            cand.parse_confidence = parse_confidence(doc, settings)
            cand.profile = profile.model_dump()
            cand.source = profile.source
            cand.chunks = rows
            cand.status, cand.error = "done", None
        except ParseError as exc:
            db.rollback()
            cand = db.get(Candidate, candidate_id)
            cand.status, cand.error = "failed", str(exc)[:300]
        except Exception as exc:  # unexpected: record the class only, so no resume text can leak into the DB/logs
            log.exception("unexpected failure processing candidate %s", candidate_id)
            db.rollback()
            cand = db.get(Candidate, candidate_id)
            cand.status, cand.error = "failed", "internal error (%s)" % type(exc).__name__
        finally:
            try:
                db.commit()
            finally:  # the upload must be deleted even if the final commit fails
                folder = os.path.dirname(path)
                if os.path.basename(folder).startswith("skillsync_"):  # the private folder made by save_temp
                    shutil.rmtree(folder, ignore_errors=True)
                else:
                    try:
                        os.remove(path)
                    except OSError:
                        pass


class IngestPool:
    """Three worker threads by default. submit() returns immediately; the API polls candidate status."""

    def __init__(self, session_factory: sessionmaker, settings: Settings, llm: Optional[LLMClient], models=None):
        self.session_factory, self.settings, self.llm, self.models = session_factory, settings, llm, models
        self.executor = ThreadPoolExecutor(max_workers=settings.worker_threads, thread_name_prefix="ingest")
        self._futures: List[Future] = []

    def submit(self, candidate_id: int, path: str) -> None:
        self._futures = [f for f in self._futures if not f.done()]
        embedder = self.models.embedder if self.models else None
        self._futures.append(self.executor.submit(
            process_candidate, self.session_factory, candidate_id, path, self.settings, self.llm,
            ocr_pdf_page, embedder))

    def submit_task(self, fn, *args) -> Future:
        """Run any background job (e.g. a scoring run) on the same worker threads."""
        self._futures = [f for f in self._futures if not f.done()]
        fut = self.executor.submit(fn, *args)
        self._futures.append(fut)
        return fut

    def wait_all(self, timeout: float = 60.0) -> None:
        """Block until queued work is done (used by tests)."""
        wait(self._futures, timeout=timeout)


def save_temp(content: bytes, filename: str) -> str:
    """Write an upload to private temp storage; the worker deletes it after parsing."""
    folder = tempfile.mkdtemp(prefix="skillsync_")
    ext = os.path.splitext(filename)[1].lower()
    path = os.path.join(folder, "upload" + ext)  # original name is never used on disk
    with open(path, "wb") as fh:
        fh.write(content)
    return path
