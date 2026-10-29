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
    return Settings(database_url="sqlite:///%s/test.db" % tmp_path, ocr_min_chars=50)


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


@pytest.fixture
def client_factory(settings):
    def make(llm) -> TestClient:
        return TestClient(create_app(settings, llm))
    return make
