from app.db import Score
from tests.conftest import JD, RESUME, MID_RESUME, WEAK_RESUME, DownLLM, MockLLM, make_pdf

JD2 = """Data Analyst

Requirements
- 2+ years of experience with data analysis
- Strong Tableau and Excel skills
- Master's degree in Statistics

Nice to have
- Experience with Spark
"""


def _student(client_factory, tmp_path, resume=MID_RESUME, llm=None):
    c = client_factory(llm or DownLLM(), role="student")
    p = tmp_path / "me.pdf"
    make_pdf(p, resume)
    cid = c.post("/student/resume", files={"file": ("me.pdf", p.read_bytes(), "application/pdf")}).json()["id"]
    c.app.state.pool.wait_all()
    jobs = [c.post("/jobs", json={"title": t, "text": txt, "mode": "student"}).json()["id"] for t, txt in (("Backend", JD), ("Analyst", JD2))]
    return c, cid, jobs


def test_students_and_recruiters_see_only_their_own_jobs(client_factory, tmp_path):
    c, _, jobs = _student(client_factory, tmp_path)
    c.use("recruiter").post("/jobs", json={"title": "Recruiter job", "text": JD})
    assert [j["title"] for j in c.get("/jobs").json()] == ["Recruiter job"]
    assert all(j["mode"] == "recruiter" for j in c.get("/jobs").json())
    assert [j["title"] for j in c.use("student").get("/jobs").json()] == ["Analyst", "Backend"]
    assert all(j["mode"] == "student" for j in c.get("/jobs").json())


def test_match_lists_best_first_and_stores_scores(client_factory, tmp_path):
    c, cid, jobs = _student(client_factory, tmp_path)
    r = c.post("/student/match", json={"candidate_id": cid, "job_ids": jobs}).json()
    assert [x["title"] for x in r] == ["Backend", "Analyst"]  # mid resume knows Python/SQL, lacks Tableau and a master's
    assert r[0]["final_score"] > r[1]["final_score"] and r[0]["met"] + r[0]["partial"] + r[0]["not_met"] == 4
    with c.app.state.session_factory() as db:
        assert db.query(Score).count() == 4 + 4


def test_match_rejects_recruiters_and_unknown_resumes(client_factory, tmp_path, pipeline):
    body = {"candidate_id": pipeline.cands["strong.pdf"], "job_ids": [pipeline.job_id]}
    assert pipeline.post("/student/match", json=body).status_code == 403          # recruiter account
    s = pipeline.use("student")
    assert s.post("/student/match", json=body).status_code == 404                 # someone else's resume
    assert s.post("/student/match", json={"candidate_id": 999, "job_ids": [1]}).status_code == 404
    assert s.post("/student/match", json={"candidate_id": 1, "job_ids": []}).status_code == 422


def test_roadmap_phases_points_and_projection(client_factory, tmp_path):
    c, cid, jobs = _student(client_factory, tmp_path)
    assert c.get("/student/roadmap", params={"candidate_id": cid, "job_id": jobs[1]}).status_code == 409
    c.post("/student/match", json={"candidate_id": cid, "job_ids": jobs})
    rm = c.get("/student/roadmap", params={"candidate_id": cid, "job_id": jobs[1]}).json()
    steps = rm["steps"]
    assert steps and [s["phase"] for s in steps] == sorted((s["phase"] for s in steps), key=["start_here", "next", "later"].index)
    assert all(s["importance"] == {"start_here": "must", "next": "should", "later": "nice"}[s["phase"]] for s in steps)
    proj = [s["projected_score"] for s in steps]
    assert proj == sorted(proj) and proj[-1] == rm["final_projected_score"] > rm["current_score"]
    assert abs(rm["final_projected_score"] - 1.0) < 1e-9  # closing every gap reaches a full match
    assert all(s["points_gain"] > 0 and s["action"] and s["action_source"] == "template" for s in steps)
    musts = [s for s in steps if s["phase"] == "start_here"]
    assert musts == sorted(musts, key=lambda s: -s["points_gain"])


def test_roadmap_llm_action_kept_only_when_tied_to_requirement(client_factory, tmp_path):
    c, cid, jobs = _student(client_factory, tmp_path)
    c.post("/student/match", json={"candidate_id": cid, "job_ids": jobs})
    steps = c.get("/student/roadmap", params={"candidate_id": cid, "job_id": jobs[1]}).json()["steps"]
    tableau = next(s for s in steps if "Tableau" in s["text"])
    other = next(s for s in steps if s is not tableau)
    c.app.state.llm = MockLLM([{"steps": [
        {"requirement_id": tableau["requirement_id"], "action": "Build a Tableau dashboard of public sales data and publish it."},
        {"requirement_id": other["requirement_id"], "action": "Learn to bake sourdough bread at home on weekends."}]}])
    out = {s["requirement_id"]: s for s in c.get("/student/roadmap", params={"candidate_id": cid, "job_id": jobs[1]}).json()["steps"]}
    assert out[tableau["requirement_id"]]["action_source"] == "llm" and "Tableau dashboard" in out[tableau["requirement_id"]]["action"]
    assert out[other["requirement_id"]]["action_source"] == "template"  # off-topic suggestion rejected


def test_whatif_raises_score_and_saves_nothing(client_factory, tmp_path):
    c, cid, jobs = _student(client_factory, tmp_path)
    c.post("/student/match", json={"candidate_id": cid, "job_ids": jobs})
    with c.app.state.session_factory() as db:
        scores_before = sorted((s.candidate_id, s.requirement_id, s.final_score) for s in db.query(Score))
        from app.db import Candidate, Chunk
        text_before, chunks_before = db.get(Candidate, cid).raw_text, db.query(Chunk).count()
    w = c.post("/student/whatif", json={"candidate_id": cid, "job_id": jobs[1],
                                        "addition": "Built a Tableau dashboard and Excel model analysing 5 years of sales data."}).json()
    assert w["saved"] is False and w["after"] > w["before"] and w["delta_points"] > 0
    assert any("Tableau" in ch["text"] for ch in w["changes"])
    with c.app.state.session_factory() as db:
        assert sorted((s.candidate_id, s.requirement_id, s.final_score) for s in db.query(Score)) == scores_before
        assert db.get(Candidate, cid).raw_text == text_before and db.query(Chunk).count() == chunks_before
    again = c.post("/student/whatif", json={"candidate_id": cid, "job_id": jobs[1], "addition": "Studied cooking and gardening for fun."}).json()
    assert again["delta_points"] <= 1e-9 and again["after"] <= w["after"]
    assert c.post("/student/whatif", json={"candidate_id": cid, "job_id": 999, "addition": "something here"}).status_code == 404


def test_current_resume_is_null_until_uploaded_then_latest(client_factory, tmp_path):
    c = client_factory(DownLLM(), role="student")
    assert c.get("/student/resume").status_code == 200 and c.get("/student/resume").json() is None
    for name in ("first.pdf", "second.pdf"):
        p = tmp_path / name
        make_pdf(p, MID_RESUME)
        c.post("/student/resume", files={"file": (name, p.read_bytes(), "application/pdf")})
        c.app.state.pool.wait_all()
    assert c.get("/student/resume").json()["filename"] == "second.pdf"
    from app.db import Candidate
    with c.app.state.session_factory() as db:
        assert db.query(Candidate).count() == 1          # a new upload replaces the old resume
