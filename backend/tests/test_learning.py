import numpy as np
import pytest

from app.config import Settings
from app.services import feedback as fb
from tests.conftest import MockLLM, run_scoring, make_pdf, RESUME, WEAK_RESUME, MID_RESUME


def test_can_train_rules():
    s = Settings()
    assert not fb.can_train(5, 4, s)       # 9 < 10
    assert not fb.can_train(9, 2, s)       # only 2 of one kind
    assert fb.can_train(7, 3, s) and fb.can_train(5, 5, s)


def test_ece_perfect_and_bad():
    y = np.array([0, 0, 1, 1])
    assert fb.expected_calibration_error(y, np.array([0.0, 0.0, 1.0, 1.0])) == 0.0
    assert fb.expected_calibration_error(y, np.array([1.0, 1.0, 0.0, 0.0])) == 1.0


def test_train_learns_clear_signal_and_reports_metrics():
    rng = np.random.default_rng(0)
    X, y = [], []
    for i in range(30):
        good = i % 2
        base = 0.8 if good else 0.2
        X.append([base + rng.normal(0, .03)] * 4 + [base, 1 - base, 0.0])
        y.append(good)
    out = fb.train(X, y)
    m = out["metrics"]
    assert m["cv_auc"] > 0.9 and 0 <= m["brier"] < 0.25 and 0 <= m["ece"] <= 1 and m["n"] == 30
    f_good = dict(zip(fb.FEATURES, [0.8] * 4 + [0.8, 0.2, 0.0]))
    f_bad = dict(zip(fb.FEATURES, [0.2] * 4 + [0.2, 0.8, 0.0]))
    assert fb.predict(out["params"], f_good)["probability"] > 0.8 > 0.2 > fb.predict(out["params"], f_bad)["probability"]


def test_shap_contributions_sum_to_logit_minus_intercept():
    out = fb.train([[i / 10] * 7 for i in range(10)], [0, 0, 0, 1, 0, 1, 1, 1, 1, 0])
    f = dict(zip(fb.FEATURES, [0.4] * 7))
    p = fb.predict(out["params"], f)
    logit = np.log(p["probability"] / (1 - p["probability"]))
    assert abs(sum(p["shap"].values()) + out["params"]["intercept"] - logit) < 1e-9
    assert set(p["shap"]) == set(fb.FEATURES)


def test_random_labels_give_auc_near_chance():
    rng = np.random.default_rng(1)
    X = rng.random((40, 7))
    y = rng.integers(0, 2, 40)
    assert 0.2 < fb.train(X, y)["metrics"]["cv_auc"] < 0.8


def _many_candidates(c, tmp_path, n):
    texts = [RESUME, WEAK_RESUME, MID_RESUME]
    files = []
    for i in range(n):
        p = tmp_path / ("x%d.pdf" % i)
        make_pdf(p, texts[i % 3].replace("Jane Doe", "Person %d" % i).replace("Sam Lee", "Person %d" % i).replace("Alex Roy", "Person %d" % i))
        files.append(("files", ("x%d.pdf" % i, p.read_bytes(), "application/pdf")))
    c.post("/jobs/%d/resumes" % c.job_id, files=files)
    c.app.state.pool.wait_all()


def test_feedback_workflow_end_to_end(pipeline, tmp_path):
    cid = pipeline.cands["strong.pdf"]
    assert pipeline.post("/candidates/%d/feedback" % cid, json={"rating": "up"}).status_code == 409  # not scored yet
    _many_candidates(pipeline, tmp_path, 9)
    run_scoring(pipeline)
    ids = [f["id"] for f in pipeline.get("/jobs/%d/status" % pipeline.job_id).json()["files"]]
    assert len(ids) == 12
    assert pipeline.post("/candidates/%d/feedback" % cid, json={"rating": "maybe"}).status_code == 422
    m = pipeline.get("/jobs/%d/model" % pipeline.job_id).json()
    assert m["trained"] is False and m["can_train"] is False
    assert pipeline.post("/jobs/%d/model/train" % pipeline.job_id).status_code == 409

    ranking = pipeline.get("/jobs/%d/ranking" % pipeline.job_id).json()["ranking"]
    for i, r in enumerate(ranking):          # top half liked, bottom half disliked
        rating = "up" if i < len(ranking) // 2 else "down"
        resp = pipeline.post("/candidates/%d/feedback" % r["candidate_id"], json={"rating": rating})
        assert resp.status_code == 200
    # re-rating the same candidate replaces, not duplicates
    again = pipeline.post("/candidates/%d/feedback" % ranking[0]["candidate_id"], json={"rating": "up"}).json()
    assert again["up"] + again["down"] == 12

    t = pipeline.post("/jobs/%d/model/train" % pipeline.job_id)
    assert t.status_code == 200
    body = t.json()
    assert body["trained"] and set(body["metrics"]) >= {"cv_auc", "brier", "ece", "cv_folds"}
    assert len(body["learned"]) == 12 and all(0 <= v["probability"] <= 1 for v in body["learned"].values())
    r = pipeline.get("/jobs/%d/ranking" % pipeline.job_id).json()["ranking"]
    assert all("learned_probability" in x and "final_score" in x for x in r)  # learned shown beside, rule score kept
    assert [x["candidate_id"] for x in r] == [x["candidate_id"] for x in ranking]  # learned score does not reorder
