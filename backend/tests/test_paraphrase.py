"""The paraphrase table from the review plan, run through the full scoring path."""
import os

import pytest

from app.config import Settings
from app.services.models import build_models
from eval.paraphrase import CASES, run


def test_paraphrase_set_with_light_models():
    s = Settings(model_backend="light")
    rows = run(build_models(s), s, light=True)
    assert len(rows) == len([c for c in CASES if not c[3]])
    bad = [(r["requirement"], r["status"]) for r in rows if not r["ok"]]
    assert not bad, bad


@pytest.mark.skipif(not os.environ.get("SKILLSYNC_REAL_TESTS"), reason="set SKILLSYNC_REAL_TESTS=1 to run with the real models")
def test_paraphrase_set_with_real_models():
    s = Settings(model_backend="real")
    rows = run(build_models(s), s)
    bad = [(r["requirement"], r["status"], r["score"]) for r in rows if not r["ok"]]
    assert not bad, bad
