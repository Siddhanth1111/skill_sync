"""Stage 11: the ranking formula. frontend/src/lib/rank.js implements the identical formula; a test checks parity.

final = weighted mean of requirement scores, times 0.9 for every 'must' that is confidently not met
(not for one that could not be verified). Tiers group scores within a band of the tier leader.
Ties are broken by the number of met musts, then by candidate id (so order is deterministic).
"""
from typing import Dict, Iterable, List, Optional, Sequence

from ..config import Settings


def status_of(score: float, met: float, partial: float) -> str:
    return "met" if score >= met else ("partial" if score >= partial else "not_met")


def final_score(items: Iterable[tuple], met: float, partial: float, penalty: float) -> float:
    """items: (importance, weight, score) or (importance, weight, score, unverifiable) per requirement.
    The must-have penalty applies only to a requirement that is confidently not met: one whose evidence could not
    be read (unverifiable) is never penalised (E1)."""
    items = list(items)
    total = sum(it[1] for it in items)
    if total <= 0:
        return 0.0
    value = sum(it[1] * it[2] for it in items) / total
    for it in items:
        unverifiable = len(it) > 3 and bool(it[3])
        if it[0] == "must" and it[1] > 0 and not unverifiable and status_of(it[2], met, partial) == "not_met":
            value *= penalty
    return value


def thresholds(settings: Settings) -> Dict[str, float]:
    return {"met": settings.met_threshold, "partial": settings.partial_threshold,
            "must_penalty": settings.must_not_met_penalty, "tier_band": settings.tier_band_points / 100.0}


def assign_tiers(rows: List[dict], band: float) -> None:
    """Candidates within `band` of the leader of their tier share that tier, so a one-point difference never
    decides a ranking on its own (E2). rows must already be sorted best first."""
    tier, leader = 0, None
    for r in rows:
        if leader is None or leader - r["final_score"] >= band:
            tier += 1
            leader = r["final_score"]
        r["tier"] = tier
    sizes: Dict[int, int] = {}
    for r in rows:
        sizes[r["tier"]] = sizes.get(r["tier"], 0) + 1
    for r in rows:
        r["tied"] = sizes[r["tier"]] > 1


def rank_candidates(requirements: Sequence[dict], matrix: Dict[int, Dict[int, float]], th: Dict[str, float],
                    flags: Optional[Dict[int, Dict[int, bool]]] = None) -> List[dict]:
    """requirements: dicts with id, importance, weight. matrix: candidate_id -> requirement_id -> score.
    flags: candidate_id -> requirement_id -> True when the requirement could not be verified.
    Requirements a candidate has no score for are skipped for that candidate, and so are weight-0 requirements."""
    flags = flags or {}
    rows = []
    for cid, scores in matrix.items():
        cf = flags.get(cid, {})
        items = [(r["importance"], float(r["weight"]), scores[r["id"]], bool(cf.get(r["id"])))
                 for r in requirements if r["id"] in scores and float(r["weight"]) > 0]
        counts = {"met": 0, "partial": 0, "not_met": 0, "not_verifiable": 0}
        musts_met = musts = 0
        for r in requirements:
            if r["id"] not in scores or float(r["weight"]) <= 0:
                continue
            st = "not_verifiable" if cf.get(r["id"]) else status_of(scores[r["id"]], th["met"], th["partial"])
            counts[st] += 1
            if r["importance"] == "must":
                musts += 1
                musts_met += st == "met"
        rows.append({"candidate_id": cid, "final_score": final_score(items, th["met"], th["partial"], th["must_penalty"]),
                     "met": counts["met"], "partial": counts["partial"], "not_met": counts["not_met"],
                     "not_verifiable": counts["not_verifiable"], "musts_met": musts_met, "musts": musts})
    rows.sort(key=lambda r: (-r["final_score"], -r["musts_met"], r["candidate_id"]))
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    assign_tiers(rows, th.get("tier_band", 0.02))
    return rows


def gaps(requirements: Sequence[dict], scores: Dict[int, float]) -> List[dict]:
    """Stage 12: points a candidate would gain by fully meeting each requirement = weight*(1-score)/total weight.
    Requirements with weight 0 (soft skills, duties) are not scored and never listed as gaps (E3)."""
    present = [r for r in requirements if r["id"] in scores and float(r["weight"]) > 0]
    total = sum(float(r["weight"]) for r in present) or 1.0
    out = [{"requirement_id": r["id"], "points_gain": 100.0 * float(r["weight"]) * (1 - scores[r["id"]]) / total}
           for r in present if scores[r["id"]] < 1.0]
    return sorted(out, key=lambda g: -g["points_gain"])
