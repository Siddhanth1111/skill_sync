import json

from app.services.extraction import extract_profile, extract_requirements, sanity_check
from app.schemas import ProfileExtraction
from tests.conftest import JD, RESUME, DownLLM, MockLLM

GOOD = {
    "name": "Jane Doe", "email": "jane.doe@example.com", "phone": "+91 98765 43210",
    "skills": ["Python", "Kafka"],
    "roles": [{"title": "Senior Engineer", "company": "Acme Corp", "start": "2018-01", "end": "2020-12"},
              {"title": "Data Engineer", "company": "Beta Ltd", "start": "2020-06", "end": "present"}],
    "education": [{"degree": "B.Tech", "institution": "IIT Delhi", "level": 1, "year": "2017"}],
}


def test_valid_llm_reply_used(settings):
    p = extract_profile(RESUME, MockLLM([GOOD]), settings)
    assert p.source == "llm" and p.name == "Jane Doe" and p.education_level == 1
    assert p.years_experience > 7  # computed by code, overlap merged


def test_invalid_then_valid_retries_with_error_fed_back(settings):
    bad = dict(GOOD, roles=[{"title": "x", "start": "not a date"}])
    llm = MockLLM([bad, GOOD])
    p = extract_profile(RESUME, llm, settings)
    assert p.source == "llm" and len(llm.calls) == 2
    assert "unparseable date" in llm.calls[1][-1]["content"]


def test_never_validates_falls_back_to_rules_after_three_attempts(settings):
    llm = MockLLM(["not json", "{}x", '{"skills": "oops"}'])
    p = extract_profile(RESUME, llm, settings)
    assert p.source == "rules" and len(llm.calls) == 3  # first try + 2 retries
    assert any("rules" in w for w in p.warnings)


def test_llm_down_falls_back_immediately(settings):
    p = extract_profile(RESUME, DownLLM(), settings)
    assert p.source == "rules" and p.email == "jane.doe@example.com"


def test_no_llm_uses_rules(settings):
    assert extract_profile(RESUME, None, settings).source == "rules"


def test_sanity_drops_hallucinated_values():
    raw = ProfileExtraction(email="fake@nowhere.com", phone="+1 555 000 1111",
                            skills=["Python", "Haskell", "python"])
    p = sanity_check(raw, RESUME)
    assert p.email is None and p.phone is None
    assert p.skills == ["Python"]  # Haskell absent from text; duplicate removed
    assert len(p.warnings) == 3


def test_sanity_phone_matches_ignoring_formatting():
    raw = ProfileExtraction(phone="+919876543210")
    assert sanity_check(raw, RESUME).phone == "+919876543210"


def test_java_does_not_match_javascript():
    raw = ProfileExtraction(skills=["Java"])
    assert sanity_check(raw, "I know JavaScript").skills == []


def test_llm_years_claim_is_ignored():
    # years_experience is not part of the LLM schema at all
    assert "years_experience" not in ProfileExtraction.model_json_schema()["properties"]


JD_GOOD = {"requirements": [
    {"text": "5 years Python", "type": "experience", "importance": "must", "skills": ["python"], "years_required": 5},
    {"text": "5 years Python", "type": "experience", "importance": "must"},  # duplicate
    {"text": "Kafka", "type": "skill", "importance": "nice"},
]}


def test_jd_llm_path_dedupes(settings):
    out, source = extract_requirements(JD, MockLLM([JD_GOOD]), settings)
    assert source == "llm" and [r.text for r in out.requirements] == ["5 years Python", "Kafka"]


def test_jd_invalid_type_retried_then_rules(settings):
    bad = {"requirements": [{"text": "x", "type": "other", "importance": "must"}]}
    out, source = extract_requirements(JD, MockLLM([bad, bad, bad]), settings)
    assert source == "rules" and out.requirements


def test_jd_empty_llm_result_falls_back(settings):
    out, source = extract_requirements(JD, MockLLM([{"requirements": []}]), settings)
    assert source == "rules"
