import json
from typing import Callable, List

import fitz
import docx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.llm import LLMUnavailable

RESUME = """Jane Doe
jane.doe@example.com
+91 98765 43210

SUMMARY
Backend engineer who builds data pipelines.

EXPERIENCE
Senior Engineer, Acme Corp   Jan 2018 - Dec 2020
- Built Python and PostgreSQL services on AWS.
Data Engineer, Beta Ltd   Jun 2020 - Present
- Ran Kafka and Spark jobs; led a team of 4.

EDUCATION
B.Tech in Computer Science, IIT Delhi, 2017

SKILLS
Python, SQL, Docker, Kafka, Spark, AWS
"""

JD = """Backend Engineer

About us
We are a friendly company with great snacks.

Requirements
- 3+ years of experience building backend services
- Strong Python and SQL skills
- Bachelor's degree in Computer Science

Nice to have
- Experience with Kafka

Benefits
- Free lunch and health insurance
"""


class MockLLM:
    """Replays queued replies. A reply that is an Exception instance is raised instead."""

    def __init__(self, replies: List):
        self.replies, self.calls = list(replies), []

    def chat(self, messages, schema):
        self.calls.append(messages)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, str) else json.dumps(r)


class DownLLM:
    def chat(self, messages, schema):
        raise LLMUnavailable("connection refused")


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url="sqlite:///%s/test.db" % tmp_path, ocr_min_chars=50, model_backend="light")


def make_pdf(path, text: str):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(40, 40, 560, 800), text, fontsize=10)
    doc.save(str(path))
    doc.close()


def make_docx(path, text: str):
    d = docx.Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    d.save(str(path))


class AuthClient(TestClient):
    """TestClient that can sign in as a recruiter, student or admin. .use(role) switches the signed-in account."""

    def use(self, role: str = "recruiter", n: int = 1) -> "AuthClient":
        email = "%s%d@example.com" % (role, n)
        body = {"email": email, "password": "correct-horse-1", "full_name": role.title(), "role": role}
        if role == "admin":
            from app.db import User
            from app.security import hash_password
            with self.app.state.session_factory() as db:
                if not db.query(User).filter_by(email=email).first():
                    db.add(User(email=email, password_hash=hash_password(body["password"]), role="admin"))
                    db.commit()
            r = self.post("/auth/login", json={"email": email, "password": body["password"]}, headers={"Authorization": ""})
        else:
            r = self.post("/auth/register", json=body, headers={"Authorization": ""})
            if r.status_code == 409:
                r = self.post("/auth/login", json={"email": email, "password": body["password"]}, headers={"Authorization": ""})
        assert r.status_code in (200, 201), r.text
        self.headers["Authorization"] = "Bearer " + r.json()["access_token"]
        self.user = r.json()["user"]
        return self


@pytest.fixture
def client_factory(settings):
    def make(llm, role: str = "recruiter") -> AuthClient:
        return AuthClient(create_app(settings, llm)).use(role)
    return make

WEAK_RESUME = """Sam Lee
sam.lee@example.com

SKILLS
HTML, CSS

EXPERIENCE
Intern, Shop Ltd   Jan 2024 - Jun 2024
- Updated web pages.

EDUCATION
High school diploma, 2023
"""

MID_RESUME = """Alex Roy
alex.roy@example.com

EXPERIENCE
Developer, Gamma Inc   Jan 2021 - Dec 2023
- Wrote Python scripts and SQL reports.

EDUCATION
B.Sc in Mathematics, 2020

SKILLS
Python, SQL
"""


@pytest.fixture
def pipeline(client_factory, tmp_path):
    """A client with a job (rule-extracted requirements) and three parsed resumes: strong, weak, mid."""
    c = client_factory(DownLLM())
    job = c.post("/jobs", json={"title": "Backend", "text": JD}).json()
    files = []
    for name, text in (("strong.pdf", RESUME), ("weak.pdf", WEAK_RESUME), ("mid.pdf", MID_RESUME)):
        p = tmp_path / name
        make_pdf(p, text)
        files.append(("files", (name, p.read_bytes(), "application/pdf")))
    c.post("/jobs/%d/resumes" % job["id"], files=files)
    c.app.state.pool.wait_all()
    status = c.get("/jobs/%d/status" % job["id"]).json()
    assert status["counts"]["done"] == 3, status
    c.job_id = job["id"]
    c.cands = {f["filename"]: f["id"] for f in status["files"]}
    return c


def run_scoring(c, job_id=None):
    jid = job_id or c.job_id
    r = c.post("/jobs/%d/score" % jid)
    assert r.status_code == 202, r.text
    c.app.state.pool.wait_all()
    s = c.get("/jobs/%d/score/status" % jid).json()
    assert s["status"] == "done", s
    return s
