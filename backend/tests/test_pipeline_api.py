from app.services.verify import normalize_ws, quote_in_text
from tests.conftest import JD, RESUME, MockLLM, run_scoring


def test_score_requires_requirements_and_resumes(client_factory):
    from tests.conftest import DownLLM
    c = client_factory(DownLLM())
    job = c.post("/jobs", json={"title": "B", "text": JD}).json()
    assert c.post("/jobs/%d/score" % job["id"]).status_code == 400  # no resumes yet
    assert c.post("/jobs/999/score").status_code == 404


def test_matrix_ranking_and_verified_quotes(pipeline):
    run_scoring(pipeline)
    m = pipeline.get("/jobs/%d/matrix" % pipeline.job_id).json()
    reqs = {r["id"]: r for r in m["requirements"]}
    assert len(m["requirements"]) == 4 and len(m["candidates"]) == 3 and all(c["scored"] for c in m["candidates"])

    texts = {}
    from app.db import Candidate
    with pipeline.app.state.session_factory() as db:
        texts = {c.id: c.raw_text for c in db.query(Candidate)}
    shown = 0
    for cand in m["candidates"]:
        assert set(cand["scores"]) == {str(i) for i in reqs}
        for s in cand["scores"].values():
            assert 0 <= s["score"] <= 1 and s["status"] in ("met", "partial", "not_met")
            if s["quote"] is not None:   # every displayed quotation is an exact substring of the resume
                shown += 1
                assert s["verified"] and quote_in_text(s["quote"], texts[cand["id"]])
            else:
                assert not s["verified"]
    assert shown > 0

    r = pipeline.get("/jobs/%d/ranking" % pipeline.job_id).json()["ranking"]
    names = [x["filename"] for x in r]
    assert names[0] == "strong.pdf" and names[-1] == "weak.pdf"
    assert r[0]["final_score"] > r[1]["final_score"] > r[2]["final_score"]
    assert r[0]["met"] == 4 and r[2]["not_met"] >= 3


def test_experience_and_education_scores_use_profile(pipeline):
    run_scoring(pipeline)
    m = pipeline.get("/jobs/%d/matrix" % pipeline.job_id).json()
    by_type = {r["type"]: r["id"] for r in m["requirements"]}
    cand = {c["filename"]: c for c in m["candidates"]}
    assert cand["strong.pdf"]["scores"][str(by_type["experience"])]["score"] == 1.0
    assert abs(cand["mid.pdf"]["scores"][str(by_type["experience"])]["score"] - 1.0) < 1e-9  # 3 years of 3
    assert cand["weak.pdf"]["scores"][str(by_type["education"])]["score"] == 0.0


def test_rerun_is_idempotent_and_replaces_rows(pipeline):
    run_scoring(pipeline)
    first = pipeline.get("/jobs/%d/matrix" % pipeline.job_id).json()
    run_scoring(pipeline)
    second = pipeline.get("/jobs/%d/matrix" % pipeline.job_id).json()
    assert first["candidates"] == second["candidates"]
    from app.db import Score
    with pipeline.app.state.session_factory() as db:
        assert db.query(Score).count() == 12  # 3 candidates x 4 requirements, not doubled


def test_weight_change_needs_no_new_scoring_and_changes_scores(pipeline):
    from app.db import Score
    run_scoring(pipeline)
    before = {r["filename"]: r["final_score"] for r in pipeline.get("/jobs/%d/ranking" % pipeline.job_id).json()["ranking"]}
    with pipeline.app.state.session_factory() as db:
        rows_before = db.query(Score).count()
    job = pipeline.get("/jobs/%d" % pipeline.job_id).json()
    nice = next(r for r in job["requirements"] if r["importance"] == "nice")
    pipeline.patch("/jobs/%d/requirements" % pipeline.job_id, json=[{"id": nice["id"], "weight": 50}])
    after_resp = pipeline.get("/jobs/%d/ranking" % pipeline.job_id).json()
    after = {r["filename"]: r["final_score"] for r in after_resp["ranking"]}
    assert not after_resp["stale"]  # weights only: stored scores are still valid
    assert after != before and after["mid.pdf"] != before["mid.pdf"]  # mid lacks Kafka, so the heavy nice weight hurts it
    with pipeline.app.state.session_factory() as db:
        assert db.query(Score).count() == rows_before  # no new model work


def test_text_edit_marks_scores_stale_until_rerun(pipeline):
    run_scoring(pipeline)
    job = pipeline.get("/jobs/%d" % pipeline.job_id).json()
    rid = job["requirements"][0]["id"]
    pipeline.patch("/jobs/%d/requirements" % pipeline.job_id, json=[{"id": rid, "text": "5+ years of Python"}])
    assert pipeline.get("/jobs/%d/ranking" % pipeline.job_id).json()["stale"] is True
    run_scoring(pipeline)
    assert pipeline.get("/jobs/%d/ranking" % pipeline.job_id).json()["stale"] is False


def test_unscored_candidates_listed_separately(pipeline, tmp_path):
    from tests.conftest import make_pdf
    run_scoring(pipeline)
    p = tmp_path / "late.pdf"
    make_pdf(p, RESUME)
    pipeline.post("/jobs/%d/resumes" % pipeline.job_id, files=[("files", ("late.pdf", p.read_bytes(), "application/pdf"))])
    pipeline.app.state.pool.wait_all()
    r = pipeline.get("/jobs/%d/ranking" % pipeline.job_id).json()
    assert [u["filename"] for u in r["unscored"]] == ["late.pdf"] and len(r["ranking"]) == 3


def test_second_scoring_run_conflicts_while_running(pipeline):
    from app.db import ScoreRun
    with pipeline.app.state.session_factory() as db:
        db.add(ScoreRun(job_id=pipeline.job_id, status="running", total=3))
        db.commit()
    assert pipeline.post("/jobs/%d/score" % pipeline.job_id).status_code == 409


def test_scoring_failure_is_reported_not_raised(pipeline):
    class Boom:
        name = "boom"
        def encode_queries(self, t): raise OSError("model download failed")
        encode_docs = encode_queries
    pipeline.app.state.models.embedder = Boom()
    pipeline.post("/jobs/%d/score" % pipeline.job_id)
    pipeline.app.state.pool.wait_all()
    s = pipeline.get("/jobs/%d/score/status" % pipeline.job_id).json()
    assert s["status"] == "failed" and "model download failed" in s["error"]


def test_explanation_orders_unmet_first_and_gaps(pipeline):
    run_scoring(pipeline)
    cid = pipeline.cands["weak.pdf"]
    e = pipeline.get("/candidates/%d/explanation" % cid).json()
    statuses = [r["status"] for r in e["requirements"]]
    order = {"not_met": 0, "partial": 1, "met": 2}
    assert statuses == sorted(statuses, key=order.get)
    pts = [g["points_gain"] for g in e["gaps"]]
    assert pts == sorted(pts, reverse=True) and pts[0] > 0
    assert e["narrative"]["source"] == "template"  # LLM down in this fixture


def test_explanation_requires_scores(pipeline):
    assert pipeline.get("/candidates/%d/explanation" % pipeline.cands["weak.pdf"]).status_code == 409


def _narrative_client(client_factory, tmp_path, reply):
    from tests.conftest import DownLLM, make_pdf
    c = client_factory(DownLLM())
    job = c.post("/jobs", json={"title": "B", "text": JD}).json()
    p = tmp_path / "s.pdf"
    make_pdf(p, RESUME)
    c.post("/jobs/%d/resumes" % job["id"], files=[("files", ("s.pdf", p.read_bytes(), "application/pdf"))])
    c.app.state.pool.wait_all()
    c.post("/jobs/%d/score" % job["id"])
    c.app.state.pool.wait_all()
    cid = c.get("/jobs/%d/status" % job["id"]).json()["files"][0]["id"]
    c.app.state.llm = MockLLM([reply])
    return c, cid


def test_narrative_with_verified_quote_is_kept(client_factory, tmp_path):
    c, cid = _narrative_client(client_factory, tmp_path, {"narrative": 'Works on data. Resume says "Ran Kafka and Spark jobs" so Kafka is covered.'})
    n = c.get("/candidates/%d/explanation" % cid).json()["narrative"]
    assert n["source"] == "llm" and "Ran Kafka and Spark jobs" in n["text"]


def test_narrative_with_fabricated_quote_replaced_by_template(client_factory, tmp_path):
    c, cid = _narrative_client(client_factory, tmp_path, {"narrative": 'Led a team at "Google Brain for ten years".'})
    n = c.get("/candidates/%d/explanation" % cid).json()["narrative"]
    assert n["source"] == "template" and "Google" not in n["text"]
