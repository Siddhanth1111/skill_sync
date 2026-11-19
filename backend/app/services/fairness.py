"""Stage 14: fairness audits. Protected characteristics are never inferred: audits only transform text
(blind, name/pronoun swaps) or use group labels the auditor supplies (synthetic in this project)."""
import re
from itertools import combinations
from typing import Dict, List, Optional, Sequence

import numpy as np

from ..config import Settings
from .chunking import chunk_resume, heading_section
from .fallback import EMAIL_RE, PHONE_RE
from .ranking import final_score
from .retrieval import ChunkView
from .scoring import ReqView, candidate_total, score_candidate

LIMITS = ("These tests use synthetic group labels and simple text transformations. They do not cover proxies "
          "such as school, address or employment gaps, and they do not prove that a system is fair. Treat flags "
          "as prompts for human review.")

URL_RE = re.compile(r"(?:https?://|www\.)\S+|\b(?:linkedin|github|gitlab|twitter|medium)\.com/\S*", re.I)
POSTCODE_RE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2}\b|\b\d{5}(?:-\d{4})?\b|\b\d{6}\b")
SCHOOL_RE = re.compile(
    r"\b(?:[A-Z][\w&.'-]*\s+){0,4}(?:University|College|Institute|Polytechnic|Academy|School)(?:\s+of(?:\s+[A-Z][\w&.'-]*){1,4})?"
    r"|\b(?:University|Institute|College|School)\s+of(?:\s+[A-Z][\w&.'-]*){1,4}", re.UNICODE)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

NEUTRAL = {"he": "they", "she": "they", "him": "them", "her": "them", "his": "their", "hers": "theirs",
           "himself": "themself", "herself": "themself", "mr": "", "mrs": "", "ms": "", "miss": ""}
TO_MALE = {"she": "he", "her": "his", "hers": "his", "herself": "himself", "he": "he", "him": "him", "his": "his", "himself": "himself"}
TO_FEMALE = {"he": "she", "him": "her", "his": "her", "himself": "herself", "she": "she", "her": "her", "hers": "hers", "herself": "herself"}
NAMES_MALE = ["James", "Michael", "Robert", "David", "William", "Daniel", "Thomas", "Mark"]
NAMES_FEMALE = ["Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Susan", "Karen", "Nancy"]


_NOT_POSSESSIVE_NEXT = {"to", "for", "with", "and", "in", "on", "at", "by", "from", "that", "as", "when", "while", "or",
                        "but", "about", "if", "so", "than", "because", "after", "before", "of"}


def _swap_words(text: str, mapping: Dict[str, str]) -> str:
    if mapping is NEUTRAL:
        # "her" is ambiguous: "her work" (possessive, -> their) vs "told her" (object, -> them)
        def her(m):
            nxt = (m.group(2) or "").lower()
            word = "their" if nxt and nxt not in _NOT_POSSESSIVE_NEXT else "them"
            return word.capitalize() if m.group(1)[0].isupper() else word
        text = re.sub(r"\b(her)\b(?:\s+([A-Za-z]+))?", lambda m: her(m) + (m.group(0)[len(m.group(1)):] if m.group(2) else ""), text, flags=re.I)

    def repl(m):
        w = m.group(0)
        new = mapping.get(w.lower())
        if new is None:
            return w
        return new.capitalize() if w[0].isupper() else new
    return re.sub(r"\b[A-Za-z]+\b", repl, text)


def _name_parts(name: Optional[str]) -> List[str]:
    return [p for p in re.split(r"\s+", name or "") if len(p) >= 2]


def blind_text(text: str, profile: dict) -> str:
    """Remove name, contact details, links, postcode, school names and education years; make pronouns neutral."""
    t = URL_RE.sub("", text)
    t = EMAIL_RE.sub("", t)

    def drop_phone(m):
        digits = re.sub(r"\D", "", m.group(0))
        return "" if 8 <= len(digits) <= 15 and not re.fullmatch(r"(19|20)\d{2}(19|20)?\d{0,2}", digits) else m.group(0)

    t = PHONE_RE.sub(drop_phone, t)
    name = (profile or {}).get("name")
    if name:
        t = re.sub(re.escape(name), "", t, flags=re.I)
        for part in _name_parts(name):
            t = re.sub(r"\b%s\b" % re.escape(part), "", t, flags=re.I)
    t = POSTCODE_RE.sub("", t)
    schools = [e.get("institution") for e in (profile or {}).get("education", []) if e.get("institution")]
    for s in sorted(schools, key=len, reverse=True):
        t = re.sub(re.escape(s), "", t, flags=re.I)
    t = SCHOOL_RE.sub("", t)
    out, section = [], None
    for line in t.split("\n"):
        h = heading_section(line)
        if h:
            section = h
        elif section == "education":
            line = YEAR_RE.sub("", line)
        out.append(line)
    return _swap_words("\n".join(out), NEUTRAL)


def blind_profile(profile: dict) -> dict:
    p = dict(profile or {})
    p.update(name=None, email=None, phone=None)
    p["education"] = [{**e, "institution": None, "year": None} for e in p.get("education", [])]
    return p


def swap_variant(text: str, profile: dict, target: str, i: int) -> str:
    """Counterfactual copy: first name replaced by one from the target list, pronouns switched to the target."""
    name = (profile or {}).get("name")
    parts = _name_parts(name)
    t = text
    if parts:
        pool = NAMES_MALE if target == "male" else NAMES_FEMALE
        new_first = pool[i % len(pool)]
        t = re.sub(r"\b%s\b" % re.escape(parts[0]), new_first, t)
    return _swap_words(t, TO_MALE if target == "male" else TO_FEMALE)


def rescore_text(text: str, profile: dict, reqs: Sequence[ReqView], qvecs: np.ndarray, models,
                 settings: Settings, db=None) -> float:
    """Chunk, embed and score a temporary text. Nothing is stored. Returns the 0..1 final score."""
    chunks = chunk_resume(text, settings.chunk_max_chars)
    vecs = models.embedder.encode_docs([c.text for c in chunks])
    views = [ChunkView(None, c.idx, c.section, c.text, v) for c, v in zip(chunks, vecs)]
    return candidate_total(score_candidate(reqs, qvecs, views, text, profile, models, settings, db), reqs, settings)


def _ranks(scores: Dict[int, float]) -> Dict[int, int]:
    order = sorted(scores, key=lambda c: (-scores[c], c))
    return {c: i + 1 for i, c in enumerate(order)}


def blind_audit(cands: Sequence[dict], reqs, qvecs, models, settings, db=None) -> dict:
    """cands: dicts with id, name, text, profile, baseline (0..1 stored score)."""
    normal = {c["id"]: c["baseline"] for c in cands}
    blind = {c["id"]: rescore_text(blind_text(c["text"], c["profile"]), blind_profile(c["profile"]), reqs, qvecs,
                                   models, settings, db) for c in cands}
    r0, r1 = _ranks(normal), _ranks(blind)
    rows = [{"candidate_id": c["id"], "name": c["name"], "normal": normal[c["id"]] * 100, "blind": blind[c["id"]] * 100,
             "change": (blind[c["id"]] - normal[c["id"]]) * 100, "rank_normal": r0[c["id"]], "rank_blind": r1[c["id"]]}
            for c in cands]
    changes = [r["change"] for r in rows]
    return {"candidates": rows, "avg_change": float(np.mean(changes)), "avg_abs_change": float(np.mean(np.abs(changes))),
            "rank_changes": sum(1 for r in rows if r["rank_normal"] != r["rank_blind"]),
            "headline": {"label": "candidates whose rank changed", "value": sum(1 for r in rows if r["rank_normal"] != r["rank_blind"])},
            "limits": LIMITS}


def counterfactual_audit(cands: Sequence[dict], reqs, qvecs, models, settings, db=None) -> dict:
    threshold = settings.counterfactual_threshold_points
    rows = []
    for i, c in enumerate(cands):
        deltas = {}
        for target in ("male", "female"):
            s = rescore_text(swap_variant(c["text"], c["profile"], target, i), c["profile"], reqs, qvecs, models, settings, db)
            deltas[target] = (s - c["baseline"]) * 100
        worst = max(deltas.values(), key=abs)
        rows.append({"candidate_id": c["id"], "name": c["name"], "change_male_variant": deltas["male"],
                     "change_female_variant": deltas["female"], "max_abs_change": abs(worst), "flagged": abs(worst) > threshold})
    flagged = sum(1 for r in rows if r["flagged"])
    return {"candidates": rows, "threshold_points": threshold, "flagged_count": flagged,
            "max_abs_change": max((r["max_abs_change"] for r in rows), default=0.0),
            "headline": {"label": "candidates flagged", "value": flagged}, "limits": LIMITS}


def impact_audit(finals: Dict[int, float], groups: Dict[int, str], top_n: int, settings: Settings) -> dict:
    """Selection = in the top N by rule-based score. Impact ratio = group rate / highest group rate."""
    ids = [c for c in finals if c in groups]
    order = sorted(ids, key=lambda c: (-finals[c], c))
    selected = {c: int(i < top_n) for i, c in enumerate(order)}
    labels = sorted({groups[c] for c in ids})
    stats = {}
    for g in labels:
        members = [c for c in ids if groups[c] == g]
        stats[g] = {"n": len(members), "selected": sum(selected[c] for c in members),
                    "rate": sum(selected[c] for c in members) / len(members)}
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
            "headline": {"label": "lowest impact ratio", "value": min(ratios) if ratios else None}, "limits": LIMITS}


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
