"""Stages 7 to 10 for one candidate: retrieve, rerank, verify, score. Pure in-memory core plus DB helpers.

The LLM is never involved here. Scores come from the reranker, the profile and fixed formulas.
"""
import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import Candidate, Chunk, Requirement, Score
from .embeddings import embed_chunks
from .ranking import final_score, status_of
from .rerank import CachedReranker
from .retrieval import ChunkView, top_k
from .taxonomy import contains_skill, find_skills
from .verify import quote_in_text, requirement_statement


@dataclass
class ReqView:
    id: int
    idx: int
    text: str
    type: str
    importance: str
    weight: float
    meta: dict


@dataclass
class ScoreRow:
    requirement_id: int
    rerank_score: float
    final_score: float
    status: str
    chunk_id: Optional[int]
    similarity: Optional[float]
    quote: Optional[str]
    section: Optional[str]
    entailment: Optional[float]
    verified: bool


def req_views(requirements: Sequence[Requirement]) -> List[ReqView]:
    return [ReqView(r.id, r.idx, r.text, r.type, r.importance, r.weight, r.meta or {}) for r in requirements]


def requirement_score(req: ReqView, profile: dict, text: str, rerank: float, settings: Settings) -> float:
    """Stage 10 formulas, 0 to 1."""
    meta = req.meta
    if req.type == "experience" and meta.get("years_required"):
        return min(1.0, float(profile.get("years_experience") or 0) / float(meta["years_required"]))
    if req.type == "education" and meta.get("degree_level_required"):
        return min(1.0, float(profile.get("education_level") or 0) / float(meta["degree_level_required"]))
    if req.type == "skill":
        skills = [s for s in (meta.get("skills") or []) if s] or find_skills(req.text)
        if skills:
            known = {s.lower() for s in profile.get("skills") or []}
            mentioned = sum(1 for s in skills if s.lower() in known or contains_skill(text, s))
            share = mentioned / len(skills)
            low = min(rerank, settings.skill_absent_cap)
            # all mentioned -> 0.85, none mentioned -> at most 0.45, in between interpolated
            return low + (settings.skill_present_score - low) * share
    return rerank


def score_candidate(reqs: Sequence[ReqView], qvecs: np.ndarray, chunks: Sequence[ChunkView], text: str,
                    profile: dict, models, settings: Settings, db: Optional[Session] = None) -> List[ScoreRow]:
    """Retrieve top-k per requirement, rerank (cached when db given), pick the best segment, verify the
    quote against `text`, check entailment, and compute the requirement score."""
    reranker = CachedReranker(models.reranker, db)
    tops = [top_k(qvecs[i], chunks, settings.retrieval_top_k) for i in range(len(reqs))]
    pairs, owner = [], []
    for ri, top in enumerate(tops):
        for j, (chunk, _) in enumerate(top):
            pairs.append((reqs[ri].text, chunk.text))
            owner.append((ri, j))
    scores = reranker.score(pairs) if pairs else []
    by_req: Dict[int, List[float]] = {ri: [] for ri in range(len(reqs))}
    for (ri, _), sc in zip(owner, scores):
        by_req[ri].append(sc)

    best: Dict[int, Optional[tuple]] = {}
    for ri, top in enumerate(tops):
        if not top:
            best[ri] = None
            continue
        j = int(np.argmax(by_req[ri]))  # first maximum wins on ties
        best[ri] = (top[j][0], top[j][1], by_req[ri][j])

    # Stage 9: exact-substring check, then entailment for the quotes that survived.
    verified = {ri: b is not None and quote_in_text(b[0].text, text) for ri, b in best.items()}
    ent_idx = [ri for ri in best if verified[ri]]
    ent = models.nli.entailment([(best[ri][0].text, requirement_statement(reqs[ri].text)) for ri in ent_idx]) if ent_idx else []
    entailment = dict(zip(ent_idx, ent))

    rows = []
    for ri, req in enumerate(reqs):
        b = best[ri]
        rerank = b[2] if b else 0.0
        sc = requirement_score(req, profile, text, rerank, settings)
        rows.append(ScoreRow(
            requirement_id=req.id, rerank_score=rerank, final_score=sc,
            status=status_of(sc, settings.met_threshold, settings.partial_threshold),
            chunk_id=b[0].id if b else None, similarity=b[1] if b else None,
            quote=b[0].text if verified[ri] else None, section=b[0].section if verified[ri] else None,
            entailment=entailment.get(ri), verified=verified[ri],
        ))
    return rows


def candidate_total(rows: Sequence[ScoreRow], reqs: Sequence[ReqView], settings: Settings) -> float:
    by_id = {r.requirement_id: r for r in rows}
    return final_score([(q.importance, q.weight, by_id[q.id].final_score) for q in reqs if q.id in by_id],
                       settings.met_threshold, settings.partial_threshold, settings.must_not_met_penalty)


# ---- DB helpers ------------------------------------------------------------------------------

def chunk_views(db: Session, cand: Candidate, embedder) -> List[ChunkView]:
    """Chunks with vectors. (Re-)embeds lazily when a chunk has no vector or was embedded by another model, so
    swapping the embedding model in config just works."""
    stale = [c for c in cand.chunks if c.embedding is None or c.embedding_model != embedder.name]
    if stale:
        embed_chunks(stale, embedder)
        db.commit()
    return [ChunkView(c.id, c.idx, c.section, c.text, np.asarray(c.embedding, dtype=np.float32)) for c in cand.chunks]


def score_candidate_to_db(db: Session, cand: Candidate, reqs: Sequence[ReqView], qvecs: np.ndarray, models,
                          settings: Settings, run_id: Optional[int] = None) -> List[ScoreRow]:
    rows = score_candidate(reqs, qvecs, chunk_views(db, cand, models.embedder), cand.raw_text or "",
                           cand.profile or {}, models, settings, db)
    db.execute(delete(Score).where(Score.candidate_id == cand.id, Score.requirement_id.in_([r.id for r in reqs])))
    for r in rows:
        db.add(Score(candidate_id=cand.id, run_id=run_id, **r.__dict__))
    db.commit()
    return rows


def load_scores(db: Session, candidate_ids: Sequence[int]) -> Dict[int, Dict[int, Score]]:
    out: Dict[int, Dict[int, Score]] = {cid: {} for cid in candidate_ids}
    if candidate_ids:
        for s in db.scalars(select(Score).where(Score.candidate_id.in_(list(candidate_ids)))):
            out[s.candidate_id][s.requirement_id] = s
    return out


def config_snapshot(models, settings: Settings) -> dict:
    return {**models.describe(), "met": settings.met_threshold, "partial": settings.partial_threshold,
            "top_k": settings.retrieval_top_k, "entailment_threshold": settings.entailment_threshold,
            "must_penalty": settings.must_not_met_penalty}
