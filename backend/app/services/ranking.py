"""Stage 11: the ranking formula. frontend/src/lib/rank.js implements the identical formula; a test checks parity.

final = weighted mean of requirement scores, times 0.9 for every 'must' requirement that is not met.
Ties are broken by the number of met musts, then by candidate id (so order is deterministic).
"""
from typing import Dict, Iterable, List, Sequence

from ..config import Settings


def status_of(score: float, met: float, partial: float) -> str:
    return "met" if score >= met else ("partial" if score >= partial else "not_met")


def final_score(items: Iterable[tuple], met: float, partial: float, penalty: float) -> float:
    """items: (importance, weight, score) per requirement."""
    items = list(items)
    total = sum(w for _, w, _ in items)
    if total <= 0:
        return 0.0
    value = sum(w * s for _, w, s in items) / total
    for importance, _, s in items:
        if importance == "must" and status_of(s, met, partial) == "not_met":
            value *= penalty
    return value


def thresholds(settings: Settings) -> Dict[str, float]:
    return {"met": settings.met_threshold, "partial": settings.partial_threshold,
            "must_penalty": settings.must_not_met_penalty}


def rank_candidates(requirements: Sequence[dict], matrix: Dict[int, Dict[int, float]], th: Dict[str, float]) -> List[dict]:
    """requirements: dicts with id, importance, weight. matrix: candidate_id -> requirement_id -> score.
    Requirements a candidate has no score for are skipped for that candidate."""
    rows = []
    for cid, scores in matrix.items():
        items = [(r["importance"], float(r["weight"]), scores[r["id"]]) for r in requirements if r["id"] in scores]
        counts = {"met": 0, "partial": 0, "not_met": 0}
        musts_met = 0
        for r in requirements:
            if r["id"] not in scores:
                continue
            st = status_of(scores[r["id"]], th["met"], th["partial"])
            counts[st] += 1
            if r["importance"] == "must" and st == "met":
                musts_met += 1
        rows.append({"candidate_id": cid, "final_score": final_score(items, th["met"], th["partial"], th["must_penalty"]),
                     "met": counts["met"], "partial": counts["partial"], "not_met": counts["not_met"],
                     "musts_met": musts_met})
    rows.sort(key=lambda r: (-r["final_score"], -r["musts_met"], r["candidate_id"]))
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows


def gaps(requirements: Sequence[dict], scores: Dict[int, float]) -> List[dict]:
    """Stage 12: points a candidate would gain by fully meeting each requirement = weight*(1-score)/total weight."""
    total = sum(float(r["weight"]) for r in requirements if r["id"] in scores) or 1.0
    out = [{"requirement_id": r["id"], "points_gain": 100.0 * float(r["weight"]) * (1 - scores[r["id"]]) / total}
           for r in requirements if r["id"] in scores and scores[r["id"]] < 1.0]
    return sorted(out, key=lambda g: -g["points_gain"])
