import csv
import io

from tests.conftest import MID_RESUME, RESUME, WEAK_RESUME, make_pdf, run_scoring


def test_job_analytics(pipeline):
    run_scoring(pipeline)
    a = pipeline.get("/jobs/%d/analytics" % pipeline.job_id).json()
    assert a["parsed"] == a["scored"] == 3 and sum(b["count"] for b in a["histogram"]) == 3 and len(a["histogram"]) == 10
    assert sum(a["tiers"].values()) == 3 and a["tiers"]["strong"] >= 1 and a["tiers"]["low"] >= 1
    assert len(a["coverage"]) == 4 and all(0 <= c["share_met"] <= 1 for c in a["coverage"])
    kafka = next(c for c in a["coverage"] if "Kafka" in c["text"])
    assert kafka["met"] == 1 and kafka["not_met"] == 2                         # only the strong resume has Kafka
    assert [o["name"] for o in a["one_away"]] == ["Alex Roy"] and a["one_away"][0]["importance"] == "nice"
    assert 0 < a["mean_score"] < a["top_score"] <= 1


def test_overview_across_jobs(pipeline):
    run_scoring(pipeline)
    o = pipeline.get("/analytics/overview").json()
    assert len(o["jobs"]) == 1 and o["jobs"][0]["scored"] == 3
    assert {s["skill"] for s in o["skill_demand"]} >= {"python", "sql", "kafka"}
    assert o["labelling"] == {"candidates": 3, "rated": 0, "up": 0, "down": 0}
    assert any("Kafka" in g["text"] for g in o["common_gaps"])
    pipeline.post("/candidates/%d/feedback" % pipeline.cands["strong.pdf"], json={"rating": "up"})
    assert pipeline.get("/analytics/overview").json()["labelling"]["up"] == 1


def test_overview_empty_for_new_user(client_factory):
    from tests.conftest import DownLLM
    o = client_factory(DownLLM()).get("/analytics/overview").json()
    assert o["jobs"] == [] and o["common_gaps"] == [] and o["labelling"]["candidates"] == 0


def test_csv_export_ranked_and_formula_safe(client_factory, tmp_path):
    from tests.conftest import DownLLM, JD
    c = client_factory(DownLLM())
    job = c.post("/jobs", json={"title": "B", "text": JD}).json()
    evil = RESUME.replace("Jane Doe", "+Evil Person")
    files = []
    for n, t in (("a.pdf", evil), ("b.pdf", WEAK_RESUME)):
        p = tmp_path / n
        make_pdf(p, t)
        files.append(("files", (n, p.read_bytes(), "application/pdf")))
    c.post("/jobs/%d/resumes" % job["id"], files=files)
    c.app.state.pool.wait_all()
    assert c.get("/jobs/%d/export.csv" % job["id"]).status_code == 409           # nothing scored yet
    run_scoring(c, job["id"])
    r = c.get("/jobs/%d/export.csv" % job["id"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and "attachment" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0][:5] == ["rank", "tier", "name", "file", "score_0_100"] and len(rows) == 3
    assert [x[0] for x in rows[1:]] == ["1", "2"] and float(rows[1][4]) > float(rows[2][4])
    assert all(not cell.startswith(("=", "+", "-", "@")) for row in rows[1:] for cell in row[:4])
    assert rows[1][2] == "'+Evil Person"


def test_semantic_search_scopes_and_ranks(pipeline):
    r = pipeline.get("/search", params={"q": "Kafka and Spark data pipelines"}).json()
    assert r["searched"] > 0 and r["results"]
    top = r["results"][0]
    assert top["name"] == "Jane Doe" and "Kafka" in top["text"] and top["section"] and top["job_title"] == "Backend"
    names = [x["name"] for x in r["results"]]
    assert len(names) == len(set(names))                                          # one best segment per candidate
    assert pipeline.get("/search", params={"q": "x"}).status_code == 422          # too short
    assert pipeline.get("/search", params={"q": "python", "job_id": 9999}).json()["results"] == []
