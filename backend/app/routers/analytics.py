"""Stage 16 analytics, CSV export and semantic search. Recruiter accounts only; every query is limited to the user's jobs."""
import csv
import io
from collections import Counter, defaultdict
from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Candidate, Chunk, Feedback, Job, User
from ..deps import get_db, owned_job, recruiter_only
from ..services.matrix import job_candidates, req_dicts
from ..services.ranking import rank_candidates, status_of, thresholds
from ..services.scoring import load_scores

router = APIRouter(tags=["analytics"])

TIERS = [("strong", 0.75), ("moderate", 0.5), ("low", 0.0)]  # lower bound of each tier on the 0..1 final score


def _tier(score: float) -> str:
    return next(name for name, lo in TIERS if score >= lo)


def _job_stats(db: Session, job: Job, settings) -> Optional[dict]:
    reqs = req_dicts(job)
    cands = {c.id: c for c in job_candidates(db, job)}
    loaded = load_scores(db, list(cands))
    matrix = {cid: {rid: s.final_score for rid, s in rows.items()} for cid, rows in loaded.items() if rows}
    th = thresholds(settings)
    ranked = rank_candidates(reqs, matrix, th)
    finals = [r["final_score"] for r in ranked]
    bins = [0] * 10
    for f in finals:
        bins[min(int(f * 10), 9)] += 1
    tiers = Counter(_tier(f) for f in finals)
    coverage = []
    for r in reqs:
        scored = [m[r["id"]] for m in matrix.values() if r["id"] in m]
        met = sum(1 for s in scored if status_of(s, th["met"], th["partial"]) == "met")
        coverage.append({"requirement_id": r["id"], "text": r["text"], "importance": r["importance"], "type": r["type"],
                         "met": met, "partial": sum(1 for s in scored if status_of(s, th["met"], th["partial"]) == "partial"),
                         "not_met": len(scored) - met - sum(1 for s in scored if status_of(s, th["met"], th["partial"]) == "partial"),
                         "share_met": (met / len(scored)) if scored else 0.0})
    one_away = []
    for cid, m in matrix.items():
        sts = {rid: status_of(s, th["met"], th["partial"]) for rid, s in m.items()}
        unmet = [rid for rid, st in sts.items() if st != "met"]
        if len(unmet) == 1 and len(sts) == len(reqs):
            req = next(r for r in reqs if r["id"] == unmet[0])
            c = cands[cid]
            one_away.append({"candidate_id": cid, "name": (c.profile or {}).get("name") or c.filename, "missing": req["text"],
                             "importance": req["importance"]})
    return {"job_id": job.id, "title": job.title, "parsed": len(cands), "scored": len(matrix),
            "mean_score": float(np.mean(finals)) if finals else None, "top_score": max(finals) if finals else None,
            "histogram": [{"from": i / 10, "to": (i + 1) / 10, "count": c} for i, c in enumerate(bins)],
            "tiers": {name: tiers.get(name, 0) for name, _ in TIERS}, "coverage": coverage, "one_away": one_away}


@router.get("/jobs/{job_id}/analytics")
def job_analytics(request: Request, job: Job = Depends(owned_job), _: User = Depends(recruiter_only), db: Session = Depends(get_db)):
    """Score distribution, tier breakdown, requirement coverage, and candidates one requirement away from a full match."""
    return _job_stats(db, job, request.app.state.settings)


@router.get("/analytics/overview")
def overview(request: Request, user: User = Depends(recruiter_only), db: Session = Depends(get_db)):
    """Across all of the user's jobs: scores, most common gaps and strengths, labelling progress, skill demand."""
    settings = request.app.state.settings
    jobs = db.scalars(select(Job).where(Job.user_id == user.id, Job.mode == "recruiter").order_by(Job.id.desc())).all()
    per_job, gaps, strengths, skills, display = [], Counter(), Counter(), Counter(), {}
    for job in jobs:
        stats = _job_stats(db, job, settings)
        per_job.append({k: stats[k] for k in ("job_id", "title", "parsed", "scored", "mean_score", "top_score")})
        for cov in stats["coverage"]:
            key = " ".join(cov["text"].lower().split())  # same requirement across jobs is grouped case-insensitively
            display.setdefault(key, " ".join(cov["text"].split()))
            if cov["share_met"] < 0.5:
                gaps[key] += cov["partial"] + cov["not_met"]   # every candidate who did not fully meet it
            else:
                strengths[key] += cov["met"]
        for r in job.requirements:
            for s in (r.meta or {}).get("skills", []) or []:
                skills[s.lower()] += 1
    cand_ids = [c.id for c in db.scalars(select(Candidate).where(Candidate.user_id == user.id, Candidate.job_id.isnot(None))).all()]
    rated = db.scalars(select(Feedback).where(Feedback.candidate_id.in_(cand_ids))).all() if cand_ids else []
    top = lambda c: [{"text": display[t], "count": n} for t, n in c.most_common(8) if n > 0]
    return {"jobs": per_job, "common_gaps": top(gaps), "common_strengths": top(strengths),
            "skill_demand": [{"skill": s, "jobs": n} for s, n in skills.most_common(12)],
            "labelling": {"candidates": len(cand_ids), "rated": len(rated), "up": sum(r.rating == "up" for r in rated),
                          "down": sum(r.rating == "down" for r in rated)}}


def _safe(cell) -> str:
    """Neutralise spreadsheet formula injection: a resume-derived value must not start with = + - @."""
    s = "" if cell is None else str(cell)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


@router.get("/jobs/{job_id}/export.csv")
def export_csv(request: Request, job: Job = Depends(owned_job), _: User = Depends(recruiter_only), db: Session = Depends(get_db)):
    """Ranking with per-requirement scores, using the job's stored weights."""
    settings = request.app.state.settings
    reqs = req_dicts(job)
    cands = {c.id: c for c in job_candidates(db, job)}
    loaded = load_scores(db, list(cands))
    matrix = {cid: {rid: s.final_score for rid, s in rows.items()} for cid, rows in loaded.items() if rows}
    ranked = rank_candidates(reqs, matrix, thresholds(settings))
    if not ranked:
        raise HTTPException(409, "Score this job before exporting.")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["rank", "name", "file", "score_0_100", "met", "partial", "not_met", "musts_met"] + ["req_%d: %s" % (r["idx"] + 1, r["text"][:60]) for r in reqs])
    for r in ranked:
        c = cands[r["candidate_id"]]
        w.writerow([r["rank"], _safe((c.profile or {}).get("name")), _safe(c.filename), "%.1f" % (r["final_score"] * 100), r["met"],
                    r["partial"], r["not_met"], r["musts_met"]] + ["%.2f" % matrix[c.id][q["id"]] if q["id"] in matrix[c.id] else "" for q in reqs])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="skillsync-job-%d-ranking.csv"' % job.id})


@router.get("/search")
def search(request: Request, q: str = Query(min_length=2, max_length=300), job_id: Optional[int] = None,
           limit: int = Query(15, ge=1, le=50), user: User = Depends(recruiter_only), db: Session = Depends(get_db)):
    """Semantic search over the user's own resume segments. Returns the best segments with their candidate and section."""
    state = request.app.state
    embedder = state.models.embedder
    query = db.query(Chunk, Candidate).join(Candidate, Chunk.candidate_id == Candidate.id).filter(
        Candidate.user_id == user.id, Candidate.job_id.isnot(None), Chunk.embedding.isnot(None),
        Chunk.embedding_model == embedder.name)
    if job_id is not None:
        query = query.filter(Candidate.job_id == job_id)
    rows = query.all()
    if not rows:
        return {"query": q, "results": [], "searched": 0}
    qv = embedder.encode_queries([q])[0]
    mat = np.asarray([c.embedding for c, _ in rows], dtype=np.float32)
    sims = mat @ qv
    best = {}
    for i in np.argsort(-sims):  # keep each candidate's best segment so one resume cannot fill the page
        cand = rows[i][1]
        if cand.id not in best:
            best[cand.id] = (rows[i][0], cand, float(sims[i]))
        if len(best) >= limit:
            break
    titles = dict(db.execute(select(Job.id, Job.title).where(Job.user_id == user.id)).all())
    return {"query": q, "searched": len(rows), "results": [
        {"candidate_id": cand.id, "job_id": cand.job_id, "job_title": titles.get(cand.job_id), "name": (cand.profile or {}).get("name") or cand.filename,
         "filename": cand.filename, "section": ch.section, "text": ch.text, "similarity": sim} for ch, cand, sim in best.values()]}
