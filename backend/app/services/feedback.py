"""Stage 13: learn from thumbs up/down. An optional logistic regression shown beside, never replacing, the rule score.

Features (7): overall score, mean score on must / should / nice requirements, share met, share partial, share not met.
SHAP for a linear model on standardised features has a closed form, coef * (x - mean) / scale (log-odds relative
to the average rated candidate), which is what is returned. No shap package is needed.
"""
from typing import Dict, List, Optional, Sequence

import numpy as np

from ..config import Settings
from .ranking import final_score, status_of

FEATURES = ["overall_score", "mean_must", "mean_should", "mean_nice", "share_met", "share_partial", "share_not_met"]


def features_for(reqs: Sequence[dict], scores: Dict[int, float], settings: Settings) -> Dict[str, float]:
    items = [(r["importance"], float(r["weight"]), scores[r["id"]]) for r in reqs if r["id"] in scores]
    n = len(items) or 1

    def mean(level: str) -> float:
        vals = [s for imp, _, s in items if imp == level]
        return float(np.mean(vals)) if vals else 0.0

    st = [status_of(s, settings.met_threshold, settings.partial_threshold) for _, _, s in items]
    return {
        "overall_score": final_score(items, settings.met_threshold, settings.partial_threshold, settings.must_not_met_penalty),
        "mean_must": mean("must"), "mean_should": mean("should"), "mean_nice": mean("nice"),
        "share_met": st.count("met") / n, "share_partial": st.count("partial") / n, "share_not_met": st.count("not_met") / n,
    }


def vector(f: Dict[str, float]) -> List[float]:
    return [float(f[k]) for k in FEATURES]


def can_train(up: int, down: int, settings: Settings) -> bool:
    return (up + down) >= settings.min_ratings and min(up, down) >= settings.min_ratings_each_kind


def expected_calibration_error(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for i in range(bins):
        mask = (p >= edges[i]) & ((p < edges[i + 1]) if i < bins - 1 else (p <= edges[i + 1]))
        if mask.any():
            ece += mask.mean() * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(ece)


def train(X: Sequence[Sequence[float]], y: Sequence[int]) -> dict:
    """Fit on all ratings and report cross-validated metrics. AUC near 0.5 means no signal."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import brier_score_loss, roc_auc_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    X, y = np.asarray(X, dtype=float), np.asarray(y, dtype=int)
    pipe = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))
    folds = max(2, min(5, int(np.bincount(y).min())))
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=0)
    p = cross_val_predict(pipe, X, y, cv=cv, method="predict_proba")[:, 1]
    pipe.fit(X, y)
    scaler, clf = pipe.named_steps["standardscaler"], pipe.named_steps["logisticregression"]
    return {
        "params": {"mean": scaler.mean_.tolist(), "scale": np.where(scaler.scale_ == 0, 1.0, scaler.scale_).tolist(),
                   "coef": clf.coef_[0].tolist(), "intercept": float(clf.intercept_[0]), "features": FEATURES},
        "metrics": {"n": int(len(y)), "up": int(y.sum()), "down": int(len(y) - y.sum()), "cv_folds": folds,
                    "cv_auc": float(roc_auc_score(y, p)), "brier": float(brier_score_loss(y, p)),
                    "ece": expected_calibration_error(y, p)},
    }


def predict(params: dict, f: Dict[str, float]) -> dict:
    x = (np.asarray(vector(f)) - np.asarray(params["mean"])) / np.asarray(params["scale"])
    contrib = np.asarray(params["coef"]) * x
    logit = float(contrib.sum() + params["intercept"])
    return {"probability": float(1 / (1 + np.exp(-logit))),
            "shap": {k: float(v) for k, v in zip(params["features"], contrib)}}
