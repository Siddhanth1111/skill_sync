"""Stages 7 to 10 for one candidate: retrieve, rerank, verify, score. Pure in-memory core plus DB helpers.

v2 (review plan, section 5): scoring is evidence-first. A skill counts only when the ontology finds it in a unit
the retriever and reranker selected (never from the profile's skill list alone); experience is years with the skill
computed from dated roles; education is level times field of study with an explicit equivalence rule. The LLM is
never involved here. Every row carries a trace of the steps that produced it.
"""
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import Candidate, Chunk, Requirement, Score
from .chunking import SENTENCE, chunk_resume
from .embeddings import embed_chunks
from .ranking import final_score, status_of
from .requirements import is_scored, normalize_query
from .rerank import CachedReranker, tokens
from .retrieval import ChunkView, Retrieved, top_k
from .taxonomy import canonical, expand_query_terms, find_skills, skill_match
from .verify import quote_in_text, requirement_statement

FIELD_WORDS = {
    "computer science": ["computer science", "computing", "software engineering", "computer engineering",
                         "information technology", "information systems", "cse", "b.tech", "btech", "mca", "bca"],
    "engineering": ["engineering", "b.tech", "btech", "b.e", "m.tech", "mtech"],
    "mathematics": ["mathematics", "maths", "statistics", "applied mathematics"],
    "statistics": ["statistics", "mathematics", "data science", "econometrics"],
    "data science": ["data science", "statistics", "computer science", "analytics", "machine learning"],
    "information technology": ["information technology", "computer science", "information systems", "software"],
    "business": ["business", "management", "mba", "commerce", "economics"],
    "physics": ["physics"], "electronics": ["electronics", "electrical", "ece", "eee"],
}


@dataclass
class ReqView:
    id: int
    idx: int
    text: str
    type: str
    importance: str
    weight: float
    meta: dict

    @property
    def kind(self) -> str:
        return self.meta.get("kind") or {"education": "education", "experience": "experience"}.get(self.type, "hard_skill")

    @property
    def scored(self) -> bool:
        return is_scored(self.meta.get("kind"))

    @property
    def query(self) -> str:
        return self.meta.get("query") or normalize_query(self.text)

    @property
    def skills(self) -> List[str]:
        return [s for s in (self.meta.get("skills") or []) if s] or find_skills(self.query)

    @property
    def mode(self) -> str:
        return self.meta.get("skills_mode") or "all"

    @property
    def years_required(self) -> Optional[float]:
        v = self.meta.get("years_min")
        v = v if v is not None else self.meta.get("years_required")
        return float(v) if v else None


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
    sentence: Optional[str] = None
    hub: bool = False
    trace: Optional[dict] = None
    pipeline_version: Optional[str] = None


def req_views(requirements: Sequence[Requirement]) -> List[ReqView]:
    return [ReqView(r.id, r.idx, r.text, r.type, r.importance, r.weight, r.meta or {}) for r in requirements]


def query_texts(reqs: Sequence[ReqView]) -> List[str]:
    return [r.query for r in reqs]


def embed_queries(reqs: Sequence[ReqView], models) -> np.ndarray:
    return models.embedder.encode_queries(query_texts(reqs))


# ---- per-kind scoring -----------------------------------------------------------------------------

def _unit_text(c: ChunkView) -> str:
    """Text the ontology reads: the unit itself plus, under a role or project, its header (e.g. 'Python Developer')."""
    return c.text + (" " + c.context if c.section in ("experience", "projects") and c.context else "")


def best_sentence(unit: ChunkView, terms: Sequence[str]) -> str:
    """The single sentence of the unit that best supports the requirement (most overlap with its terms)."""
    parts = [p.strip() for piece in SENTENCE.split(unit.text) for p in piece.split("\n") if p.strip()]
    if len(parts) <= 1:
        return unit.text.strip()
    want = set()
    for t in terms:
        want |= tokens(t)
    return max(parts, key=lambda p: (len(tokens(p) & want), -parts.index(p)))


def score_skill(req: ReqView, cands: List[Tuple[Retrieved, float]], settings: Settings) -> Tuple[float, Optional[int], dict]:
    """Evidence-first skill score. Returns (score, index into cands of the unit to show, trace)."""
    best_rr = max((rr for _, rr in cands), default=0.0)
    skills = req.skills
    trace: dict = {"rule": "skill_evidence", "skills": {}}
    if not cands:
        return 0.0, None, trace
    if not skills:  # a concept the ontology does not know: the reranker's judgement is all there is
        trace["rule"] = "rerank_only"
        top = max(range(len(cands)), key=lambda i: (cands[i][1], -i))
        return best_rr, top, trace
    per, show = [], []
    for skill in skills:
        hit, related, technique = None, False, None
        for i, (rt, rr) in enumerate(cands):
            m = skill_match(_unit_text(rt.chunk), skill)
            if m == "technique" and (technique is None or rr > cands[technique][1]):
                technique = i
            if m in ("direct", "implied"):
                listed = rt.chunk.section == "skills"
                key = (0 if listed else 1, rr)  # a hit in running text beats a bare list entry
                if hit is None or key > hit[0]:
                    hit = (key, i, listed)
            elif m == "related":
                related = True
        if hit:
            s = settings.skill_listed_score if hit[2] else settings.skill_present_score
            show.append((hit[0], hit[1]))
            trace["skills"][skill] = "listed" if hit[2] else "evidence"
        elif technique is not None:
            s = max(min(best_rr, settings.skill_absent_cap), settings.skill_technique_score)
            show.append(((0, cands[technique][1]), technique))
            trace["skills"][skill] = "technique_only"
        elif related:
            s = max(min(best_rr, settings.skill_absent_cap), settings.skill_related_score)
            trace["skills"][skill] = "related_only"
        else:
            s = min(best_rr, settings.skill_absent_cap)
            trace["skills"][skill] = "not_found"
        per.append(s)
    score = max(per) if req.mode == "any" else float(np.mean(per))
    if show:
        idx = max(show)[1]
    else:
        idx = max(range(len(cands)), key=lambda i: (cands[i][1], -i))
    return score, idx, trace


def score_experience(req: ReqView, profile: dict, hit_units: int, settings: Settings) -> Tuple[float, dict]:
    """Years with the skill (from dated roles that mention it) over years required, capped at 1."""
    need = req.years_required
    total = float(profile.get("years_experience") or 0)
    skills = [s for s in req.skills if canonical(s)]
    trace: dict = {"rule": "years", "years_required": need, "years_total": total}
    if not need:  # "Experience with Kafka": no years stated, so the skill must be shown
        return -1.0, trace
    if not skills:
        trace["years_used"] = total
        return min(1.0, total / need), trace
    sy = profile.get("skill_years") or {}
    ys = [float(sy.get(canonical(s), 0.0)) for s in skills]
    used = max(ys) if req.mode == "any" else min(ys)
    trace.update(years_with_skill={canonical(s): y for s, y in zip(skills, ys)}, years_used=used)
    if used > 0:
        return min(1.0, used / need), trace
    if hit_units:  # skill is shown but no dated role links to it: years cannot be verified
        trace["note"] = "skill found, but no dated role mentions it; years not verifiable"
        return min(min(1.0, total / need), settings.skill_absent_cap), trace
    return 0.0, trace


def score_education(req: ReqView, profile: dict, settings: Settings) -> Tuple[float, dict]:
    need = req.meta.get("degree_level_required")
    level = int(profile.get("education_level") or 0)
    trace: dict = {"rule": "education", "level_required": need, "level_found": level}
    if not need:
        return -1.0, trace
    score = min(1.0, level / float(need))
    low = req.text.lower()
    if score > 0 and not re.search(r"related|similar|any (?:discipline|field)|or equivalent", low):
        wanted = [f for f in FIELD_WORDS if f in low]
        if wanted:
            have = " ".join(((e.get("degree") or "") for e in profile.get("education", []))).lower()
            if not any(w in have for f in wanted for w in FIELD_WORDS[f]):
                score *= settings.field_mismatch_factor
                trace["field_mismatch"] = wanted
    if "equivalent" in low and float(profile.get("years_experience") or 0) >= settings.equivalent_experience_years:
        if score < 0.8:
            score = 0.8
            trace["equivalence_rule"] = "experience >= %.0f years" % settings.equivalent_experience_years
    return score, trace


def requirement_score(req: ReqView, profile: dict, rerank: float, settings: Settings) -> float:
    """Kept for callers and tests that score without retrieval: profile-based numeric rules only."""
    if req.kind == "experience" and req.years_required:
        return score_experience(req, profile, 0, settings)[0]
    if req.kind == "education":
        s = score_education(req, profile, settings)[0]
        return s if s >= 0 else rerank
    return rerank


def score_candidate(reqs: Sequence[ReqView], qvecs: np.ndarray, chunks: Sequence[ChunkView], text: str,
                    profile: dict, models, settings: Settings, db: Optional[Session] = None,
                    low_confidence: bool = False) -> List[ScoreRow]:
    """Hybrid-retrieve per requirement, rerank (cached when db given), score by kind, pick one evidence unit per
    requirement with a reuse limit, verify the quote against `text`, check entailment. Returns rows for scored
    requirements only (soft skills and duties are never scored)."""
    reranker = CachedReranker(models.reranker, db, settings.pipeline_version)
    active = [i for i, r in enumerate(reqs) if r.scored]
    retrieved: Dict[int, List[Retrieved]] = {}
    for i in active:
        r = reqs[i]
        retrieved[i] = top_k(qvecs[i], chunks, settings.retrieval_top_k, r.query, expand_query_terms(r.skills))
    pairs, owner = [], []
    for i in active:
        for j, rt in enumerate(retrieved[i]):
            pairs.append((reqs[i].query, rt.chunk.embed_text))
            owner.append((i, j))
    scores = reranker.score(pairs) if pairs else []
    rr: Dict[int, List[float]] = {i: [0.0] * len(retrieved[i]) for i in active}
    for (i, j), sc in zip(owner, scores):
        rr[i][j] = sc

    results: Dict[int, dict] = {}
    for i in active:
        r = reqs[i]
        cands = list(zip(retrieved[i], rr[i]))
        trace: dict = {"query": r.query, "kind": r.kind, "mode": r.mode, "version": settings.pipeline_version}
        show: Optional[int] = None
        if r.kind == "experience" and r.years_required:
            skill_score, show, st = score_skill(r, cands, settings) if r.skills else (0.0, None, {})
            hits = sum(1 for v in st.get("skills", {}).values() if v in ("evidence", "listed"))
            sc, t = score_experience(r, profile, hits, settings)
            trace.update(t)
        elif r.kind == "education" and r.meta.get("degree_level_required"):
            sc, t = score_education(r, profile, settings)
            trace.update(t)
            edu = [k for k, (rt, _) in enumerate(cands) if rt.chunk.section == "education"]
            show = max(edu, key=lambda k: cands[k][1]) if edu else None
        else:  # hard skills, and experience without a year count ("Experience with Kafka")
            sc, show, t = score_skill(r, cands, settings)
            trace.update(t)
        if show is None and cands:
            pool = range(len(cands))
            if r.kind == "experience":  # years are shown by a role entry, not by the summary line
                pool = [k for k in pool if cands[k][0].chunk.section == "experience"] or pool
            show = max(pool, key=lambda k: (cands[k][1], -k))
        results[i] = {"score": sc, "show": show, "cands": cands, "trace": trace}

    # One evidence unit may back at most hub_max_reuse requirements; heavier requirements choose first (C5).
    usage: Counter = Counter()
    for i in sorted(active, key=lambda k: (-reqs[k].weight, k)):
        res = results[i]
        cands, show = res["cands"], res["show"]
        if show is None:
            continue
        order = sorted(range(len(cands)), key=lambda k: (k != show, -cands[k][1]))
        skills = reqs[i].skills
        usable = [k for k in order if k == show or not skills or any(
            skill_match(_unit_text(cands[k][0].chunk), s) in ("direct", "implied") for s in skills)]
        pick = next((k for k in usable if usage[cands[k][0].chunk.idx] < settings.hub_max_reuse), show)
        res["show"] = pick
        usage[cands[pick][0].chunk.idx] += 1

    verified, shown = {}, {}
    for i in active:
        res = results[i]
        if res["show"] is None:
            verified[i], shown[i] = False, None
            continue
        rt, rerank_v = res["cands"][res["show"]]
        shown[i] = (rt, rerank_v)
        verified[i] = quote_in_text(rt.chunk.text, text)
    sentences = {i: best_sentence(shown[i][0].chunk, [reqs[i].query, *reqs[i].skills]) for i in active if shown[i]}
    ent_idx = [i for i in active if verified[i] and reqs[i].kind == "hard_skill"]
    ent = models.nli.entailment([(sentences[i], requirement_statement(reqs[i].query)) for i in ent_idx]) if ent_idx else []
    entailment = dict(zip(ent_idx, ent))

    rows = []
    for i in active:
        r, res = reqs[i], results[i]
        sc = max(0.0, min(1.0, res["score"]))
        trace = res["trace"]
        rt, rerank_v = shown[i] if shown[i] else (None, 0.0)
        if res["score"] < 0:  # a numeric rule had nothing to go on: fall back to the reranker
            sc = max(0.0, min(1.0, rerank_v))
        ent_v = entailment.get(i)
        sentence = sentences.get(i)
        # D5: weak evidence cannot make a requirement "met" unless the ontology finds the skill in that sentence.
        if ent_v is not None and ent_v < settings.entailment_threshold and sc >= settings.met_threshold:
            direct = any(skill_match(sentence or "", s) in ("direct", "implied") for s in r.skills)
            if not direct:
                sc = min(sc, settings.weak_evidence_cap)
                trace["weak_evidence_cap"] = True
        status = status_of(sc, settings.met_threshold, settings.partial_threshold)
        if status == "not_met" and low_confidence:
            status = "not_verifiable"  # the resume was read poorly: absence cannot be trusted (D8)
        trace["retrieved"] = [{"unit": c.chunk.idx, "section": c.chunk.section, "rrf": round(c.rrf, 4),
                               "dense_rank": c.dense_rank, "bm25_rank": c.bm25_rank, "rerank": round(s, 3)}
                              for c, s in res["cands"]]
        trace["reuse"] = usage[rt.chunk.idx] if rt is not None else 0
        hub = rt is not None and usage[rt.chunk.idx] > settings.hub_max_reuse
        rows.append(ScoreRow(
            requirement_id=r.id, rerank_score=rerank_v, final_score=sc, status=status,
            chunk_id=rt.chunk.id if rt else None, similarity=rt.similarity if rt else None,
            quote=rt.chunk.text if rt is not None and verified[i] else None,
            section=rt.chunk.section if rt is not None and verified[i] else None,
            entailment=ent_v, verified=bool(verified[i]), sentence=sentence if verified[i] else None, hub=hub,
            trace=trace, pipeline_version=settings.pipeline_version))
    return rows


def candidate_total(rows: Sequence[ScoreRow], reqs: Sequence[ReqView], settings: Settings) -> float:
    by_id = {r.requirement_id: r for r in rows}
    return final_score([(q.importance, q.weight, by_id[q.id].final_score, by_id[q.id].status == "not_verifiable")
                        for q in reqs if q.id in by_id],
                       settings.met_threshold, settings.partial_threshold, settings.must_not_met_penalty)


# ---- DB helpers ------------------------------------------------------------------------------

def make_chunk_rows(units) -> List[Chunk]:
    return [Chunk(idx=u.idx, section=u.section, text=u.text, context=u.context, meta={"start": u.start, "end": u.end})
            for u in units]


def scoring_text_for(raw_text: str, profile: dict, settings: Settings) -> str:
    """The text the scorer reads: identity details removed unless blind scoring is switched off."""
    from .blind import blind_text
    return blind_text(raw_text, profile) if settings.blind_scoring else raw_text


def chunk_views(db: Session, cand: Candidate, embedder, settings: Optional[Settings] = None) -> List[ChunkView]:
    """Units with vectors. Rebuilds the units when the candidate was ingested by an older pipeline, and re-embeds
    lazily when a unit has no vector or was embedded by another model (swapping the model in config just works)."""
    if settings is not None and (cand.chunk_version or 1) < 2 and cand.raw_text:
        text = scoring_text_for(cand.raw_text, cand.profile or {}, settings)
        cand.scoring_text = text
        cand.chunks = make_chunk_rows(chunk_resume(text, settings.chunk_max_chars))
        cand.chunk_version = 2
        db.flush()
    stale = [c for c in cand.chunks if c.embedding is None or c.embedding_model != embedder.name]
    if stale:
        embed_chunks(stale, embedder)
    db.commit()
    return [ChunkView(c.id, c.idx, c.section, c.text, np.asarray(c.embedding, dtype=np.float32), c.context or "",
                      (c.meta or {}).get("start"), (c.meta or {}).get("end")) for c in cand.chunks]


def score_candidate_to_db(db: Session, cand: Candidate, reqs: Sequence[ReqView], qvecs: np.ndarray, models,
                          settings: Settings, run_id: Optional[int] = None) -> List[ScoreRow]:
    views = chunk_views(db, cand, models.embedder, settings)
    text = cand.scoring_text if cand.scoring_text else scoring_text_for(cand.raw_text or "", cand.profile or {}, settings)
    low = bool((cand.parse_confidence or {}).get("low_ocr") or (cand.parse_confidence or {}).get("unreadable"))
    rows = score_candidate(reqs, qvecs, views, text, cand.profile or {}, models, settings, db, low)
    db.execute(delete(Score).where(Score.candidate_id == cand.id, Score.requirement_id.in_([r.id for r in reqs])))
    for r in rows:
        db.add(Score(candidate_id=cand.id, run_id=run_id, **r.__dict__))
    db.commit()
    return rows


def units_for_text(text: str, profile: dict, models, settings: Settings) -> Tuple[str, List[ChunkView], dict]:
    """Units and vectors for a temporary text (what-if, audits). Nothing is stored. Returns the scoring text, the
    views, and a copy of the profile with skill years and links recomputed for this text."""
    from .skillgraph import link_skills
    st = scoring_text_for(text, profile, settings)
    units = chunk_resume(st, settings.chunk_max_chars)
    vecs = models.embedder.encode_docs([u.embed_text for u in units])
    views = [ChunkView(None, u.idx, u.section, u.text, v, u.context, u.start, u.end) for u, v in zip(units, vecs)]
    links, years = link_skills(units)
    return st, views, {**(profile or {}), "skill_links": links, "skill_years": years}


def row_from_score(s: Score) -> ScoreRow:
    return ScoreRow(s.requirement_id, s.rerank_score, s.final_score, s.status, s.chunk_id, s.similarity, s.quote,
                    s.section, s.entailment, s.verified, s.sentence, bool(s.hub), s.trace, s.pipeline_version)


def load_scores(db: Session, candidate_ids: Sequence[int]) -> Dict[int, Dict[int, Score]]:
    out: Dict[int, Dict[int, Score]] = {cid: {} for cid in candidate_ids}
    if candidate_ids:
        for s in db.scalars(select(Score).where(Score.candidate_id.in_(list(candidate_ids)))):
            out[s.candidate_id][s.requirement_id] = s
    return out


def config_snapshot(models, settings: Settings) -> dict:
    return {**models.describe(), "met": settings.met_threshold, "partial": settings.partial_threshold,
            "top_k": settings.retrieval_top_k, "entailment_threshold": settings.entailment_threshold,
            "must_penalty": settings.must_not_met_penalty, "pipeline_version": settings.pipeline_version,
            "blind_scoring": settings.blind_scoring, "hub_max_reuse": settings.hub_max_reuse,
            "tier_band_points": settings.tier_band_points}
