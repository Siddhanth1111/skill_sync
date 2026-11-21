"""Choose the met and partial thresholds from human-graded pairs (review item D3 / point 8).

    python -m eval.tune eval/gold/pairs.jsonl [--light] [--report-test]

The gold file is the one `eval.benchmark` reads. Pairs are split BY JOB: jobs listed in a "split" field, otherwise every
third job (sorted) is held out as test. Thresholds are searched on the development jobs only, by quadratic-weighted
kappa between the human grade and the grade the thresholds give. The test jobs are scored once, only with
--report-test, so the number is not tuned on. Nothing is written to config: copy the result into SKILLSYNC_MET_THRESHOLD
and SKILLSYNC_PARTIAL_THRESHOLD yourself after reading it.
"""
import argparse
import sys
from typing import Dict, List, Sequence, Tuple

import numpy as np

from app.config import Settings
from app.services.models import build_models
from eval.benchmark import load, predict
from eval.metrics import bootstrap_ci, quadratic_weighted_kappa


def split_by_job(rows: Sequence[dict]) -> Tuple[List[dict], List[dict]]:
    if any("split" in r for r in rows):
        return [r for r in rows if r.get("split") != "test"], [r for r in rows if r.get("split") == "test"]
    jobs = sorted({str(r.get("job")) for r in rows})
    test_jobs = set(jobs[2::3])
    return [r for r in rows if str(r.get("job")) not in test_jobs], [r for r in rows if str(r.get("job")) in test_jobs]


def grade(score: float, met: float, partial: float) -> int:
    return 2 if score >= met else (1 if score >= partial else 0)


def choose_thresholds(scores: Sequence[float], grades: Sequence[int], step: float = 0.05) -> Dict:
    """Grid search over met in [0.3, 0.9] and partial in [0.05, met - step]. Ties keep the thresholds closest to the
    current defaults, so noise does not move them."""
    best = None
    sc, y = np.asarray(scores, dtype=float), np.asarray(grades, dtype=int)
    for met in np.arange(0.30, 0.901, step):
        for partial in np.arange(0.05, met - step + 1e-9, step):
            pred = [grade(s, met, partial) for s in sc]
            k = quadratic_weighted_kappa(y, pred)
            if np.isnan(k):
                continue
            key = (round(k, 6), -abs(met - 0.6) - abs(partial - 0.3))
            if best is None or key > best[0]:
                best = (key, float(round(met, 2)), float(round(partial, 2)), float(k))
    if best is None:
        raise ValueError("not enough graded pairs to tune on (need at least two different grades)")
    return {"met": best[1], "partial": best[2], "qwk": best[3]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("gold")
    ap.add_argument("--light", action="store_true")
    ap.add_argument("--report-test", action="store_true")
    args = ap.parse_args()
    settings = Settings(model_backend="light" if args.light else "real")
    dev, test = split_by_job(load(args.gold))
    models = build_models(settings)
    pd = predict(dev, models, settings)
    cur = quadratic_weighted_kappa([p["grade"] for p in pd], [grade(p["score"], settings.met_threshold, settings.partial_threshold) for p in pd])
    best = choose_thresholds([p["score"] for p in pd], [p["grade"] for p in pd])
    print("development pairs: %d (jobs held out for test: %d pairs)" % (len(pd), len(test)))
    print("current thresholds met=%.2f partial=%.2f: QWK %.3f" % (settings.met_threshold, settings.partial_threshold, cur))
    print("best on development  met=%.2f partial=%.2f: QWK %.3f" % (best["met"], best["partial"], best["qwk"]))
    if args.report_test:
        pt = predict(test, models, settings)
        y = np.array([p["grade"] for p in pt])
        for name, (m, pa) in {"current": (settings.met_threshold, settings.partial_threshold), "tuned": (best["met"], best["partial"])}.items():
            v, lo, hi = bootstrap_ci(quadratic_weighted_kappa, y, np.array([grade(p["score"], m, pa) for p in pt]))
            print("test (%s): QWK %.3f  95%% CI %.3f to %.3f  (n=%d)" % (name, v, lo, hi, len(pt)))
    else:
        print("test jobs not scored. Add --report-test once, when you are done tuning.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
