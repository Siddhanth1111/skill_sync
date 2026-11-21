"""Stage 14: fairness audits. Protected characteristics are never inferred: audits only transform text
(blind, name/pronoun swaps) or use group labels the auditor supplies (synthetic in this project)."""
import re
from itertools import combinations
from typing import Dict, List, Optional, Sequence

import numpy as np

from ..config import Settings
from .blind import (NEUTRAL, TO_FEMALE, TO_MALE, _name_parts, _swap_words, blind_profile, blind_text,  # noqa: F401
                    swap_date_format, swap_school, swap_variant)
from .ranking import final_score  # noqa: F401
from .scoring import ReqView, candidate_total, score_candidate, units_for_text

LIMITS = ("These tests use consented or demo group labels and simple text transformations. They do not cover proxies "
          "such as school, address or employment gaps, and they do not prove that a system is fair. Treat flags "
          "as prompts for human review.")

def rescore_text(text: str, profile: dict, reqs: Sequence[ReqView], qvecs: np.ndarray, models,
                 settings: Settings, db=None, blind: Optional[bool] = None) -> float:
    """Build units for a temporary text and score it through the live pipeline. Nothing is stored. `blind` forces
    blind scoring on or off; None follows settings.blind_scoring. Returns the 0..1 final score."""
    cfg = settings if blind is None else settings.model_copy(update={"blind_scoring": blind})
    st, views, prof = units_for_text(text, profile, models, cfg)
    return candidate_total(score_candidate(reqs, qvecs, views, st, prof, models, cfg, db), reqs, cfg)


def _ranks(scores: Dict[int, float]) -> Dict[int, int]:
    order = sorted(scores, key=lambda c: (-scores[c], c))
    return {c: i + 1 for i, c in enumerate(order)}


def blind_audit(cands: Sequence[dict], reqs, qvecs, models, settings, db=None) -> dict:
    """cands: dicts with id, name, text (original resume), profile. Scores every resume twice through the same
    pipeline, once with identity details present and once with them removed, and compares the order."""
    normal = {c["id"]: rescore_text(c["text"], c["profile"], reqs, qvecs, models, settings, db, blind=False) for c in cands}
    blind = {c["id"]: rescore_text(c["text"], c["profile"], reqs, qvecs, models, settings, db, blind=True) for c in cands}
    r0, r1 = _ranks(normal), _ranks(blind)
    rows = [{"candidate_id": c["id"], "name": c["name"], "normal": normal[c["id"]] * 100, "blind": blind[c["id"]] * 100,
             "change": (blind[c["id"]] - normal[c["id"]]) * 100, "rank_normal": r0[c["id"]], "rank_blind": r1[c["id"]]}
            for c in cands]
    changes = [r["change"] for r in rows]
    return {"candidates": rows, "avg_change": float(np.mean(changes)), "avg_abs_change": float(np.mean(np.abs(changes))),
            "rank_changes": sum(1 for r in rows if r["rank_normal"] != r["rank_blind"]),
            "scoring_mode": "blind" if settings.blind_scoring else "identity",
            "headline": {"label": "candidates whose rank changed", "value": sum(1 for r in rows if r["rank_normal"] != r["rank_blind"])},
            "limits": LIMITS}


VARIANTS = ("male", "female", "school", "date_format")


def _variant_text(c: dict, name: str, i: int) -> str:
    if name in ("male", "female"):
        return swap_variant(c["text"], c["profile"], name, i)
    if name == "school":
        return swap_school(c["text"], c["profile"], i)
    return swap_date_format(c["text"])


def counterfactual_audit(cands: Sequence[dict], reqs, qvecs, models, settings, db=None) -> dict:
    """Change one thing that should not matter (name and pronouns, school, date format) and report the score change
    through the live pipeline. With blind scoring on, name, pronoun and school changes should give zero change."""
    threshold = settings.counterfactual_threshold_points
    rows = []
    for i, c in enumerate(cands):
        deltas = {}
        for v in VARIANTS:
            s = rescore_text(_variant_text(c, v, i), c["profile"], reqs, qvecs, models, settings, db)
            deltas[v] = (s - c["baseline"]) * 100
        worst = max(deltas.values(), key=abs)
        rows.append({"candidate_id": c["id"], "name": c["name"], "change_male_variant": deltas["male"],
                     "change_female_variant": deltas["female"], "change_school_variant": deltas["school"],
                     "change_date_format_variant": deltas["date_format"], "max_abs_change": abs(worst),
                     "flagged": abs(worst) > threshold})
    flagged = sum(1 for r in rows if r["flagged"])
    return {"candidates": rows, "threshold_points": threshold, "flagged_count": flagged,
            "variants": list(VARIANTS), "scoring_mode": "blind" if settings.blind_scoring else "identity",
            "max_abs_change": max((r["max_abs_change"] for r in rows), default=0.0),
            "headline": {"label": "candidates flagged", "value": flagged}, "limits": LIMITS}


def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    """95% Wilson interval for a selection rate (small groups give wide intervals, which is the point)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, float(centre - half)), min(1.0, float(centre + half)))


MIN_GROUP_SIZE = 10


def impact_audit(finals: Dict[int, float], groups: Dict[int, str], top_n: int, settings: Settings,
                 demo: bool = False) -> dict:
    """Selection = in the top N by rule-based score. Impact ratio = group rate / highest group rate. Group labels
    must be consented and self-reported, or the run is marked as a demo (F1)."""
    ids = [c for c in finals if c in groups]
    order = sorted(ids, key=lambda c: (-finals[c], c))
    selected = {c: int(i < top_n) for i, c in enumerate(order)}
    labels = sorted({groups[c] for c in ids})
    stats = {}
    for g in labels:
        members = [c for c in ids if groups[c] == g]
        k = sum(selected[c] for c in members)
        lo, hi = wilson(k, len(members))
        stats[g] = {"n": len(members), "selected": k, "rate": k / len(members), "rate_ci_low": lo, "rate_ci_high": hi,
                    "small_group": len(members) < MIN_GROUP_SIZE}
    top = max((s["rate"] for s in stats.values()), default=0.0)
    for s in stats.values():
        s["impact_ratio"] = (s["rate"] / top) if top > 0 else None
        s["flagged"] = s["impact_ratio"] is not None and s["impact_ratio"] < settings.impact_ratio_threshold
    y = [selected[c] for c in ids]
    dpd = _fairlearn_dpd(y, [groups[c] for c in ids])
    ratios = [s["impact_ratio"] for s in stats.values() if s["impact_ratio"] is not None]
    return {"top_n": top_n, "groups": stats, "ratio_threshold": settings.impact_ratio_threshold,
            "demographic_parity_difference": dpd, "n_candidates": len(ids),
            "flagged_groups": [g for g, s in stats.items() if s["flagged"]],
            "small_groups": [g for g, s in stats.items() if s["small_group"]],
            "labels_source": "demo" if demo else "consented",
            "warning": ("DEMO: these group labels are not real data. The numbers show how the audit works, nothing more."
                        if demo else ("Some groups have fewer than %d candidates; their rates carry wide intervals and "
                                      "should not be read as findings." % MIN_GROUP_SIZE
                                      if any(s["small_group"] for s in stats.values()) else None)),
            "headline": {"label": "lowest impact ratio" + (" (demo)" if demo else ""), "value": min(ratios) if ratios else None},
            "limits": LIMITS}


def _fairlearn_dpd(y: Sequence[int], groups: Sequence[str]) -> Optional[float]:
    """Fairlearn's demographic parity difference (max minus min selection rate across groups)."""
    if len(set(groups)) < 2:
        return None
    try:
        from fairlearn.metrics import demographic_parity_difference
        return float(demographic_parity_difference(y, y, sensitive_features=groups))
    except ImportError:  # same definition computed directly
        rates = [np.mean([yy for yy, g in zip(y, groups) if g == lab]) for lab in set(groups)]
        return float(max(rates) - min(rates))


# ---- WEAT probe -----------------------------------------------------------------------------

NAME_GROUPS = {
    "gender": ("male-coded first names", ["John", "Paul", "Mike", "Kevin", "Steve", "Greg", "Jeff", "Bill"],
               "female-coded first names", ["Amy", "Joan", "Lisa", "Sarah", "Diana", "Kate", "Ann", "Donna"]),
    "origin": ("Anglo first names", ["Adam", "Harry", "Josh", "Roger", "Alan", "Frank", "Justin", "Ryan"],
               "Indian first names", ["Rahul", "Amit", "Priya", "Anil", "Sunita", "Vikram", "Deepa", "Rajesh"]),
}
PLEASANT = ["freedom", "health", "love", "peace", "cheer", "friend", "heaven", "loyal", "pleasure", "honest",
            "lucky", "gift"]
UNPLEASANT = ["abuse", "crash", "filth", "murder", "sickness", "accident", "death", "grief", "poison", "assault",
              "disaster", "hatred"]


def weat_probe(embedder, groups: str, settings: Settings, seed: int = 0) -> dict:
    """WEAT (Caliskan et al.): do two name groups associate differently with pleasant vs unpleasant words in
    this embedding model? Returns effect size d and a permutation p-value."""
    label_x, X_words, label_y, Y_words = NAME_GROUPS[groups]
    # float64: numpy's float32 matmul on macOS Accelerate emits spurious overflow warnings
    X, Y = (np.asarray(embedder.encode_docs(w), dtype=np.float64) for w in (X_words, Y_words))
    A, B = (np.asarray(embedder.encode_docs(w), dtype=np.float64) for w in (PLEASANT, UNPLEASANT))

    def assoc(W):  # s(w, A, B) for each row
        with np.errstate(all="ignore"):  # numpy 2.x on macOS Accelerate emits spurious FP warnings here
            out = (W @ A.T).mean(axis=1) - (W @ B.T).mean(axis=1)
        if not np.all(np.isfinite(out)):  # ...so check the result instead of trusting the warnings either way
            raise ValueError("WEAT produced non-finite values; the embeddings are invalid")
        return out

    sx, sy = assoc(X), assoc(Y)
    pooled = np.concatenate([X, Y])
    s_all = assoc(pooled)
    sd = float(s_all.std(ddof=1))
    effect = float((sx.mean() - sy.mean()) / sd) if sd > 0 else 0.0
    observed = float(sx.sum() - sy.sum())
    n, rng = len(X), np.random.default_rng(seed)
    total_combos = len(list(combinations(range(len(pooled)), n))) if len(pooled) <= 16 else None
    if total_combos is not None and total_combos <= settings.weat_permutations:
        perms = [np.array(c) for c in combinations(range(len(pooled)), n)]
    else:
        perms = [rng.permutation(len(pooled))[:n] for _ in range(settings.weat_permutations)]
    count = 0
    for idx in perms:
        mask = np.zeros(len(pooled), dtype=bool)
        mask[idx] = True
        if s_all[mask].sum() - s_all[~mask].sum() >= observed - 1e-12:
            count += 1
    p = count / len(perms)
    return {"groups": groups, "group_x": label_x, "group_y": label_y, "effect_size": effect, "p_value": p,
            "permutations": len(perms), "embedder": embedder.name,
            "interpretation": "Positive effect size: group X is closer to pleasant words than group Y.",
            "headline": {"label": "effect size", "value": effect},
            "limits": LIMITS + " WEAT probes the embedding model only, not the ranking."}
