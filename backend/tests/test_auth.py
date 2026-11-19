import time

import jwt
import pytest

from app.config import Settings
from app.db import ActivityLog, Candidate, Chunk, Job, Score, User
from app.main import create_app
from tests.conftest import JD, RESUME, AuthClient, DownLLM, make_pdf, run_scoring


def anon(client_factory):
    c = client_factory(DownLLM())
    c.headers.pop("Authorization")
    return c


def test_register_login_me_roundtrip(client_factory):
    c = anon(client_factory)
    r = c.post("/auth/register", json={"email": "  Pat@Example.COM ", "password": "longenough1", "full_name": "Pat", "role": "student"})
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["email"] == "pat@example.com" and body["user"]["role"] == "student" and "password" not in str(body)
    me = c.get("/auth/me", headers={"Authorization": "Bearer " + body["access_token"]}).json()
    assert me["email"] == "pat@example.com" and me["full_name"] == "Pat"
    ok = c.post("/auth/login", json={"email": "PAT@example.com", "password": "longenough1"})
    assert ok.status_code == 200 and ok.json()["user"]["id"] == me["id"]


def test_passwords_are_hashed_never_stored_plain(client_factory):
    c = client_factory(DownLLM())
    with c.app.state.session_factory() as db:
        u = db.query(User).one()
        assert u.password_hash.startswith("$2") and "correct-horse-1" not in u.password_hash


@pytest.mark.parametrize("payload,status", [
    ({"email": "nope", "password": "longenough1"}, 422),
    ({"email": "a@b.co", "password": "short"}, 422),
    ({"email": "a@b.co", "password": "x" * 73}, 422),
    ({"email": "a@b.co", "password": "longenough1", "role": "admin"}, 422),     # no self-service admin
])
def test_register_validation(client_factory, payload, status):
    assert anon(client_factory).post("/auth/register", json=payload).status_code == status


def test_duplicate_email_conflict(client_factory):
    c = anon(client_factory)
    p = {"email": "dup@example.com", "password": "longenough1"}
    assert c.post("/auth/register", json=p).status_code == 201
    assert c.post("/auth/register", json=p).status_code == 409


def test_login_failures_do_not_reveal_which_part_was_wrong(client_factory):
    c = anon(client_factory)
    c.post("/auth/register", json={"email": "who@example.com", "password": "longenough1"})
    wrong_pw = c.post("/auth/login", json={"email": "who@example.com", "password": "bad-password"})
    unknown = c.post("/auth/login", json={"email": "ghost@example.com", "password": "longenough1"})
    assert wrong_pw.status_code == unknown.status_code == 401 and wrong_pw.json() == unknown.json()


def test_login_throttle_after_repeated_failures(tmp_path):
    s = Settings(database_url="sqlite:///%s/t.db" % tmp_path, model_backend="light", login_max_failures=3)
    c = AuthClient(create_app(s, DownLLM()))
    c.post("/auth/register", json={"email": "t@example.com", "password": "longenough1"})
    for _ in range(3):
        assert c.post("/auth/login", json={"email": "t@example.com", "password": "wrong-pass"}).status_code == 401
    assert c.post("/auth/login", json={"email": "t@example.com", "password": "longenough1"}).status_code == 429


def test_requests_without_valid_token_are_rejected(client_factory):
    c = anon(client_factory)
    for method, path in (("get", "/jobs"), ("post", "/jobs"), ("get", "/auth/me"), ("get", "/admin/users"),
                         ("get", "/jobs/1/matrix"), ("post", "/student/match"), ("get", "/analytics/overview"), ("delete", "/me/data")):
        assert getattr(c, method)(path).status_code == 401, (method, path)
    assert c.get("/jobs", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert c.get("/health").status_code == 200   # health stays public


def test_expired_and_tampered_tokens_rejected(client_factory):
    c = client_factory(DownLLM())
    secret = c.app.state.jwt_secret
    uid = c.user["id"]
    expired = jwt.encode({"sub": str(uid), "exp": int(time.time()) - 10}, secret, algorithm="HS256")
    forged = jwt.encode({"sub": str(uid), "exp": int(time.time()) + 600}, "another-secret", algorithm="HS256")
    none_alg = jwt.encode({"sub": str(uid), "exp": int(time.time()) + 600}, "", algorithm="none")
    for tok in (expired, forged, none_alg):
        assert c.get("/auth/me", headers={"Authorization": "Bearer " + tok}).status_code == 401


def test_token_for_deleted_user_stops_working(client_factory):
    c = client_factory(DownLLM())
    assert c.get("/auth/me").status_code == 200
    c.delete("/me/data", params={"delete_account": "true"})
    assert c.get("/auth/me").status_code == 401


def test_roles_are_enforced_on_every_route_group(pipeline, tmp_path):
    jid = pipeline.job_id
    student = pipeline.use("student")
    for method, path in (("get", f"/jobs/{jid}/status"), ("post", f"/jobs/{jid}/score"), ("get", f"/jobs/{jid}/matrix"),
                         ("get", f"/jobs/{jid}/ranking"), ("post", f"/jobs/{jid}/audit/blind"), ("get", f"/jobs/{jid}/model"),
                         ("get", f"/jobs/{jid}/analytics"), ("get", "/search?q=python"), ("get", "/analytics/overview"),
                         ("get", "/admin/users")):
        assert getattr(student, method)(path).status_code in (403, 404), (method, path)
    rec = pipeline.use("recruiter")
    for path in ("/student/matches", "/student/resume"):
        assert rec.get(path).status_code == 403
    assert rec.post("/student/match", json={"candidate_id": 1, "job_ids": [1]}).status_code == 403
    for path in ("/admin/users", "/admin/activity", "/admin/stats"):
        assert rec.get(path).status_code == 403
    admin = pipeline.use("admin")
    assert admin.get("/jobs").status_code == 403           # admins have no access to recruiter data
    assert admin.get(f"/jobs/{jid}").status_code == 403


def test_users_cannot_see_each_others_records(pipeline):
    run_scoring(pipeline)
    jid, cid = pipeline.job_id, pipeline.cands["strong.pdf"]
    other = pipeline.use("recruiter", n=2)
    probes = [("get", f"/jobs/{jid}"), ("patch", f"/jobs/{jid}/requirements"), ("get", f"/jobs/{jid}/status"),
              ("post", f"/jobs/{jid}/score"), ("get", f"/jobs/{jid}/matrix"), ("get", f"/jobs/{jid}/ranking"),
              ("get", f"/jobs/{jid}/model"), ("post", f"/jobs/{jid}/model/train"), ("post", f"/jobs/{jid}/audit/blind"),
              ("get", f"/jobs/{jid}/audit/history"), ("get", f"/jobs/{jid}/analytics"), ("get", f"/jobs/{jid}/export.csv"),
              ("get", f"/candidates/{cid}"), ("get", f"/candidates/{cid}/explanation"), ("delete", f"/candidates/{cid}"),
              ("delete", f"/jobs/{jid}")]
    for method, path in probes:
        kw = {"json": []} if method == "patch" else {}
        assert getattr(other, method)(path, **kw).status_code == 404, (method, path)
    assert other.post(f"/candidates/{cid}/feedback", json={"rating": "up"}).status_code == 404
    assert other.get("/jobs").json() == []
    assert other.get("/search?q=python").json()["results"] == []
    # and the owner is unaffected
    owner = pipeline.use("recruiter")
    assert owner.get(f"/jobs/{jid}").status_code == 200 and owner.get(f"/candidates/{cid}").status_code == 200


def test_upload_to_someone_elses_job_is_404(pipeline, tmp_path):
    other = pipeline.use("recruiter", n=2)
    p = tmp_path / "x.pdf"
    make_pdf(p, RESUME)
    r = other.post(f"/jobs/{pipeline.job_id}/resumes", files=[("files", ("x.pdf", p.read_bytes(), "application/pdf"))])
    assert r.status_code == 404


def test_activity_is_logged_without_personal_data(pipeline):
    run_scoring(pipeline)
    with pipeline.app.state.session_factory() as db:
        rows = db.query(ActivityLog).all()
        actions = {r.action for r in rows}
        assert {"register", "job_created", "resumes_uploaded", "scoring_started"} <= actions
        blob = " ".join((r.detail or "") for r in rows)
        assert "@" not in blob and "Jane" not in blob and "example.com" not in blob


def test_admin_user_list_activity_and_delete(pipeline):
    pipeline.use("student")
    admin = pipeline.use("admin")
    users = admin.get("/admin/users").json()
    roles = {u["role"] for u in users}
    assert roles == {"recruiter", "student", "admin"}
    rec = next(u for u in users if u["role"] == "recruiter")
    assert rec["jobs"] == 1 and rec["candidates"] == 3 and "password" not in str(users)
    assert admin.get("/admin/stats").json()["by_role"]["recruiter"] == 1
    assert admin.get("/admin/activity", params={"action": "register"}).json()
    assert admin.delete("/admin/users/%d" % admin.user["id"]).status_code == 400      # not yourself
    assert admin.delete("/admin/users/9999").status_code == 404
    out = admin.delete("/admin/users/%d" % rec["id"]).json()
    assert out["jobs"] == 1 and out["candidates"] == 3
    with pipeline.app.state.session_factory() as db:
        assert db.query(Job).count() == 0 and db.query(Candidate).count() == 0 and db.query(Chunk).count() == 0
        assert db.query(User).filter_by(email="recruiter1@example.com").count() == 0


def test_delete_my_data_removes_everything_but_keeps_account(pipeline):
    run_scoring(pipeline)
    pipeline.post("/candidates/%d/feedback" % pipeline.cands["strong.pdf"], json={"rating": "up"})
    pipeline.post("/jobs/%d/audit/blind" % pipeline.job_id)
    other = pipeline.use("recruiter", n=2)
    other.post("/jobs", json={"title": "Keep me", "text": JD})
    pipeline.use("recruiter")
    r = pipeline.delete("/me/data").json()
    assert r == {"jobs": 1, "candidates": 3, "account_deleted": False}
    with pipeline.app.state.session_factory() as db:
        assert db.query(Score).count() == 0 and db.query(Chunk).count() == 0
        assert db.query(Job).count() == 1                       # the other user's job is untouched
    assert pipeline.get("/auth/me").status_code == 200 and pipeline.get("/jobs").json() == []


def test_admin_seeded_from_settings(tmp_path):
    s = Settings(database_url="sqlite:///%s/t.db" % tmp_path, model_backend="light", admin_email="Boss@Example.com", admin_password="seeded-pass-1")
    c = AuthClient(create_app(s, DownLLM()))
    r = c.post("/auth/login", json={"email": "boss@example.com", "password": "seeded-pass-1"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
