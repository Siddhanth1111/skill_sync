import json

from tests.conftest import JD, RESUME, DownLLM, MockLLM, make_docx, make_pdf
from tests.test_extraction import GOOD


def _upload(client, job_id, files):
    return client.post("/jobs/%d/resumes" % job_id,
                       files=[("files", (n, c, "application/octet-stream")) for n, c in files])


def test_create_job_and_edit_requirements(client_factory):
    c = client_factory(DownLLM())  # LLM down: rules answer
    r = c.post("/jobs", json={"title": "Backend", "text": JD})
    assert r.status_code == 201
    job = r.json()
    assert job["requirements_source"] == "rules" and len(job["requirements"]) == 4
    weights = {q["importance"]: q["weight"] for q in job["requirements"]}
    assert weights == {"must": 3.0, "nice": 1.0}

    kafka = next(q for q in job["requirements"] if q["importance"] == "nice")
    r = c.patch("/jobs/%d/requirements" % job["id"], json=[{"id": kafka["id"], "importance": "should"}])
    edited = next(q for q in r.json()["requirements"] if q["id"] == kafka["id"])
    assert edited["importance"] == "should" and edited["weight"] == 2.0
    r = c.patch("/jobs/%d/requirements" % job["id"], json=[{"id": kafka["id"], "weight": 5}])
    assert r.json()["requirements"][3]["weight"] == 5.0
    assert c.patch("/jobs/%d/requirements" % job["id"], json=[{"id": 9999, "weight": 1}]).status_code == 404


def test_full_batch_with_bad_file_does_not_stop_others(client_factory, tmp_path):
    # job creation also uses the LLM: three invalid replies force the rule fallback, then two good resume replies
    c2 = client_factory(MockLLM(["x", "x", "x", GOOD, GOOD]))
    job = c2.post("/jobs", json={"title": "Backend", "text": JD}).json()
    assert job["requirements_source"] == "rules"

    pdf, dx = tmp_path / "a.pdf", tmp_path / "b.docx"
    make_pdf(pdf, RESUME)
    make_docx(dx, RESUME)
    r = _upload(c2, job["id"], [("a.pdf", pdf.read_bytes()), ("b.docx", dx.read_bytes()),
                                ("notes.txt", b"hello"), ("fake.pdf", b"not a pdf at all")])
    assert r.status_code == 202
    assert [x["status"] for x in r.json()] == ["queued", "queued", "failed", "failed"]

    c2.app.state.pool.wait_all()
    s = c2.get("/jobs/%d/status" % job["id"]).json()
    assert s["total"] == 4 and s["counts"] == {"queued": 0, "parsing": 0, "done": 2, "failed": 2}
    done = [f for f in s["files"] if f["status"] == "done"]
    assert all(f["source"] == "llm" and f["parse_confidence"]["ocr_used"] is False for f in done)
    assert "unsupported" in s["files"][2]["error"]


def test_corrupt_pdf_marked_failed_batch_continues(client_factory, tmp_path):
    c = client_factory(DownLLM())
    job = c.post("/jobs", json={"title": "B", "text": JD}).json()
    good = tmp_path / "g.pdf"
    make_pdf(good, RESUME)
    _upload(c, job["id"], [("bad.pdf", b"%PDF-1.4 garbage"), ("g.pdf", good.read_bytes())])
    c.app.state.pool.wait_all()
    s = c.get("/jobs/%d/status" % job["id"]).json()
    assert [f["status"] for f in s["files"]] == ["failed", "done"]
    assert s["files"][1]["source"] == "rules"  # LLM down -> rule fallback recorded


def test_chunks_and_text_stored_and_temp_file_deleted(client_factory, tmp_path):
    import glob, tempfile, os
    c = client_factory(DownLLM())
    job = c.post("/jobs", json={"title": "B", "text": JD}).json()
    f = tmp_path / "g.pdf"
    make_pdf(f, RESUME)
    _upload(c, job["id"], [("g.pdf", f.read_bytes())])
    c.app.state.pool.wait_all()
    from app.db import Candidate
    with c.app.state.session_factory() as db:
        cand = db.query(Candidate).one()
        assert cand.status == "done" and cand.chunks
        assert all(ch.text in cand.raw_text or " ".join(ch.text.split()) in " ".join(cand.raw_text.split())
                   for ch in cand.chunks)
        assert {ch.section for ch in cand.chunks} >= {"experience", "skills"}
        assert all(len(ch.text) <= 500 for ch in cand.chunks)
    assert not glob.glob(os.path.join(tempfile.gettempdir(), "skillsync_*", "upload.pdf"))


def test_file_count_limit(client_factory):
    c = client_factory(DownLLM())
    c.app.state.settings.max_files_per_job = 2
    job = c.post("/jobs", json={"title": "B", "text": JD}).json()
    r = _upload(c, job["id"], [("a.txt", b"x"), ("b.txt", b"x"), ("c.txt", b"x")])
    assert r.status_code == 413


def test_unknown_job_404(client_factory):
    c = client_factory(DownLLM())
    assert c.get("/jobs/42").status_code == 404
    assert _upload(c, 42, [("a.pdf", b"%PDF")]).status_code == 404
    assert c.get("/jobs/42/status").status_code == 404


def test_deleting_job_cascades(client_factory, tmp_path):
    c = client_factory(DownLLM())
    job = c.post("/jobs", json={"title": "B", "text": JD}).json()
    f = tmp_path / "g.pdf"
    make_pdf(f, RESUME)
    _upload(c, job["id"], [("g.pdf", f.read_bytes())])
    c.app.state.pool.wait_all()
    from app.db import Candidate, Chunk, Job, Requirement
    with c.app.state.session_factory() as db:
        db.delete(db.get(Job, job["id"]))
        db.commit()
        assert db.query(Candidate).count() == db.query(Chunk).count() == db.query(Requirement).count() == 0


def test_candidate_detail_and_student_upload(client_factory, tmp_path):
    c = client_factory(DownLLM())
    f = tmp_path / "s.pdf"
    make_pdf(f, RESUME)
    r = c.post("/student/resume", files={"file": ("s.pdf", f.read_bytes(), "application/pdf")})
    assert r.status_code == 202
    cid = r.json()["id"]
    c.app.state.pool.wait_all()
    d = c.get("/candidates/%d" % cid).json()
    assert d["status"] == "done" and d["job_id"] is None
    assert d["profile"]["email"] == "jane.doe@example.com" and d["chunks"] and d["raw_text"]
    assert c.get("/candidates/999").status_code == 404
    bad = c.post("/student/resume", files={"file": ("x.txt", b"hi", "text/plain")})
    assert bad.json()["status"] == "failed"
