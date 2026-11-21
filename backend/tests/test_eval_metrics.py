import math

import numpy as np

from eval.benchmark import report
from eval.metrics import bootstrap_ci, brier, expected_calibration_error, ndcg_at_k, quadratic_weighted_kappa


def test_kappa_perfect_chance_and_opposite():
    assert quadratic_weighted_kappa([0, 1, 2, 1], [0, 1, 2, 1]) == 1.0
    assert quadratic_weighted_kappa([0, 0, 2, 2], [2, 2, 0, 0]) < -0.9
    assert abs(quadratic_weighted_kappa([0, 1, 2, 0, 1, 2], [1, 2, 0, 2, 0, 1])) < 0.6
    assert math.isnan(quadratic_weighted_kappa([1, 1, 1], [1, 1, 1]))  # one class only: undefined, never reported as 1


def test_kappa_penalises_far_misses_more_than_near_misses():
    y = [0, 0, 1, 1, 2, 2, 0, 1, 2, 1]
    near = [0, 1, 1, 2, 2, 1, 0, 1, 2, 1]
    far = [2, 0, 1, 1, 0, 2, 0, 1, 2, 1]
    assert quadratic_weighted_kappa(y, near) > quadratic_weighted_kappa(y, far)


def test_ndcg_best_order_is_one_and_worst_is_lower():
    rel = [2, 1, 0]
    assert ndcg_at_k(rel, [0.9, 0.5, 0.1]) == 1.0
    assert ndcg_at_k(rel, [0.1, 0.5, 0.9]) < 0.8
    assert math.isnan(ndcg_at_k([0, 0], [0.5, 0.4]))


def test_brier_and_ece_reward_calibrated_probabilities():
    y = np.array([1, 1, 1, 0, 0, 0, 1, 0])
    good = np.array([0.9, 0.8, 0.7, 0.2, 0.1, 0.3, 0.8, 0.2])
    bad = 1.0 - good
    assert brier(y, good) < brier(y, bad)
    assert expected_calibration_error(y, good) < expected_calibration_error(y, bad)


def test_bootstrap_interval_contains_the_value_and_is_reproducible():
    rng = np.random.default_rng(1)
    y = rng.integers(0, 3, 60)
    yh = np.clip(y + rng.integers(-1, 2, 60), 0, 2)
    v, lo, hi = bootstrap_ci(quadratic_weighted_kappa, y, yh, n=200)
    assert lo <= v <= hi and (v, lo, hi) == bootstrap_ci(quadratic_weighted_kappa, y, yh, n=200)


def test_report_runs_on_predictions():
    from app.config import Settings
    pred = [{"requirement": "Python", "job": "j", "kind": "hard_skill", "grade": g, "pred": p, "score": s}
            for g, p, s in [(2, 2, 0.85), (0, 0, 0.1), (1, 1, 0.4), (2, 1, 0.5), (0, 0, 0.0), (2, 2, 0.9)]]
    r = report(pred, Settings(model_backend="light"))
    assert r["n"] == 6 and r["kappa"]["all"]["qwk"] > 0.5 and r["ndcg_at_5"]["groups"] == 1
