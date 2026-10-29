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
from .extraction import extract_profile
from .llm import LLMClient
from .parsing import ParseError, extract_text, ocr_pdf_page, parse_confidence

log = logging.getLogger(__name__)  # only ids and error classes are logged, never resume content


def process_candidate(
    session_factory: sessionmaker,
    candidate_id: int,
    path: str,
    settings: Settings,
    llm: Optional[LLMClient],
    ocr_page: Callable = ocr_pdf_page,
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
            chunks = chunk_resume(doc.text, settings.chunk_max_chars)         # Stage 5

            cand.raw_text = doc.text
            cand.needs_ocr = doc.ocr_used
            cand.parse_confidence = parse_confidence(doc, settings)
            cand.profile = profile.model_dump()
            cand.source = profile.source
            cand.chunks = [Chunk(idx=c.idx, section=c.section, text=c.text) for c in chunks]
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
            db.commit()
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

    def __init__(self, session_factory: sessionmaker, settings: Settings, llm: Optional[LLMClient]):
        self.session_factory, self.settings, self.llm = session_factory, settings, llm
        self.executor = ThreadPoolExecutor(max_workers=settings.worker_threads, thread_name_prefix="ingest")
        self._futures: List[Future] = []

    def submit(self, candidate_id: int, path: str) -> None:
        self._futures = [f for f in self._futures if not f.done()]
        self._futures.append(self.executor.submit(
            process_candidate, self.session_factory, candidate_id, path, self.settings, self.llm))

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
