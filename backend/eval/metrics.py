"""Evaluation metrics from the review plan (section 10), with bootstrap confidence intervals. Pure numpy."""
from typing import Callable, Sequence, Tuple

import numpy as np


def quadratic_weighted_kappa(y_true: Sequence[int], y_pred: Sequence[int], n_classes: int = 3) -> float:
    """Agreement between two graders on an ordinal scale, 1 = perfect, 0 = chance, negative = worse than chance."""
    a, b = np.asarray(y_true, dtype=int), np.asarray(y_pred, dtype=int)
    if len(a) == 0:
        return float("nan")
    obs = np.zeros((n_classes, n_classes))
    for i, j in zip(a, b):
        obs[i, j] += 1
    exp = np.outer(obs.sum(axis=1), obs.sum(axis=0)) / len(a)
    w = np.array([[(i - j) ** 2 for j in range(n_classes)] for i in range(n_classes)], dtype=float) / (n_classes - 1) ** 2
    denom = (w * exp).sum()
    return float(1.0 - (w * obs).sum() / denom) if denom > 0 else float("nan")


def ndcg_at_k(relevance: Sequence[float], scores: Sequence[float], k: int = 10) -> float:
    """Ranking quality for one list: relevance by the human grade, order by the system score."""
    rel, sc = np.asarray(relevance, dtype=float), np.asarray(scores, dtype=float)
    order = np.argsort(-sc, kind="stable")[:k]
    disc = 1.0 / np.log2(np.arange(2, len(order) + 2))
    dcg = float(((2 ** rel[order] - 1) * disc).sum())
    ideal = np.sort(rel)[::-1][:k]
    idcg = float(((2 ** ideal - 1) * (1.0 / np.log2(np.arange(2, len(ideal) + 2)))).sum())
    return dcg / idcg if idcg > 0 else float("nan")


def brier(y: Sequence[int], p: Sequence[float]) -> float:
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    return float(np.mean((p - y) ** 2)) if len(y) else float("nan")


def expected_calibration_error(y: Sequence[int], p: Sequence[float], bins: int = 10) -> float:
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    if not len(y):
        return float("nan")
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for i in range(bins):
        mask = (p >= edges[i]) & ((p < edges[i + 1]) if i < bins - 1 else (p <= edges[i + 1]))
        if mask.any():
            ece += mask.mean() * abs(y[mask].mean() - p[mask].mean())
    return float(ece)


def bootstrap_ci(metric: Callable[..., float], *arrays: Sequence, n: int = 1000, seed: int = 0,
                 alpha: float = 0.05) -> Tuple[float, float, float]:
    """(value, low, high): the metric on all data and a percentile bootstrap interval from resampled rows."""
    arrs = [np.asarray(a) for a in arrays]
    value = float(metric(*arrs))
    if len(arrs[0]) < 2:
        return value, float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        idx = rng.integers(0, len(arrs[0]), len(arrs[0]))
        v = metric(*[a[idx] for a in arrs])
        if np.isfinite(v):
            vals.append(v)
    if not vals:
        return value, float("nan"), float("nan")
    return value, float(np.quantile(vals, alpha / 2)), float(np.quantile(vals, 1 - alpha / 2))
