"""Benchmark the scoring pipeline against a human-labelled gold set (review plan, Phase 0).

    python -m eval.benchmark eval/gold/pairs.jsonl [--light] [--out eval/results/run.json]

Gold file: one JSON object per line, written by two annotators and adjudicated (see eval/gold/README.md):
    {"id": "p001", "job": "j1", "requirement": "Python", "resume": "Wrote automation scripts in Perl", "grade": 0}
grade 0 = not shown, 1 = partly shown, 2 = clearly shown. `kind` is optional. Split development and test BY JOB
(never by pair); report the test split once, at the end.

Reports quadratic-weighted kappa per requirement kind and overall, nDCG@5 (candidate order within a job-requirement
group), and Brier / ECE of the score as a probability of "clearly shown", each with a 95% bootstrap interval. No target
number is claimed here: the first run is the v2 baseline.
"""
import argparse
import json
import os
import sys
from collections import defaultdict

import numpy as np

from app.config import Settings
from app.services.models import build_models
from eval.metrics import bootstrap_ci, brier, expected_calibration_error, ndcg_at_k, quadratic_weighted_kappa
from eval.paraphrase import run_case


def load(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def predict(rows, models, settings):
    out = []
    for r in rows:
        got = run_case(r["requirement"], r["resume"], models, settings)
        if got["status"] == "unscored":
            continue  # soft skills and duties are not graded by the system
        score = got["score"]
        grade = 2 if score >= settings.met_threshold else (1 if score >= settings.partial_threshold else 0)
        out.append({**r, "kind": got["kind"], "score": score, "pred": grade})
    return out


def report(pred, settings):
    res = {"n": len(pred), "pipeline_version": settings.pipeline_version, "backend": settings.model_backend, "kappa": {}}
    groups = defaultdict(list)
    for p in pred:
        groups["all"].append(p)
        groups[p["kind"]].append(p)
    for name, g in groups.items():
        y, yh = np.array([p["grade"] for p in g]), np.array([p["pred"] for p in g])
        v, lo, hi = bootstrap_ci(quadratic_weighted_kappa, y, yh)
        res["kappa"][name] = {"n": len(g), "qwk": v, "ci95": [lo, hi]}
    y2 = np.array([int(p["grade"] == 2) for p in pred])
    sc = np.array([p["score"] for p in pred])
    res["brier"] = dict(zip(("value", "low", "high"), bootstrap_ci(brier, y2, sc)))
    res["ece"] = dict(zip(("value", "low", "high"), bootstrap_ci(expected_calibration_error, y2, sc)))
    by_req = defaultdict(list)
    for p in pred:
        by_req[(p.get("job"), p["requirement"])].append(p)
    nd = [ndcg_at_k([p["grade"] for p in g], [p["score"] for p in g], 5) for g in by_req.values() if len(g) > 1]
    res["ndcg_at_5"] = {"value": float(np.nanmean(nd)) if nd else None, "groups": len(nd)}
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("gold")
    ap.add_argument("--light", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()
    settings = Settings(model_backend="light" if args.light else "real")
    rows = load(args.gold)
    res = report(predict(rows, build_models(settings), settings), settings)
    res["gold_file"], res["gold_pairs"] = os.path.basename(args.gold), len(rows)
    print(json.dumps(res, indent=2))
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump(res, fh, indent=2)
        try:  # optional experiment tracking: logged to MLflow when it is installed
            import mlflow
            with mlflow.start_run(run_name="benchmark-%s" % settings.pipeline_version):
                mlflow.log_params({"pipeline": settings.pipeline_version, "backend": settings.model_backend, "pairs": len(rows)})
                mlflow.log_metric("qwk_all", res["kappa"]["all"]["qwk"])
                mlflow.log_artifact(args.out)
        except ImportError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
