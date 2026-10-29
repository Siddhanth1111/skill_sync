from app.services.fallback import (degree_level, extract_jd_rules, extract_profile_rules, find_email,
                                   find_name, find_phone)
from tests.conftest import JD, RESUME


def test_contact_fields():
    assert find_email(RESUME) == "jane.doe@example.com"
    assert find_phone(RESUME) == "+91 98765 43210"
    assert find_name(RESUME) == "Jane Doe"


def test_years_not_mistaken_for_phone():
    assert find_phone("Worked 2015-2019 at Acme") is None


def test_degree_levels():
    assert degree_level("PhD in Physics") == 3
    assert degree_level("M.Tech, IIT") == 2
    assert degree_level("MBA") == 2
    assert degree_level("B.Tech in CS") == 1
    assert degree_level("High school diploma") == 0


def test_profile_rules():
    p = extract_profile_rules(RESUME)
    assert p.source == "rules"
    assert len(p.roles) == 2
    assert p.roles[0].start == "Jan 2018"
    assert {"python", "kafka", "spark", "aws"} <= set(p.skills)
    assert p.education_level == 1
    assert p.years_experience > 7  # 2018 to now, overlapping roles merged


def test_jd_rules_ignore_benefits_and_set_importance():
    reqs = extract_jd_rules(JD).requirements
    texts = [r.text for r in reqs]
    assert not any("lunch" in t.lower() for t in texts)
    assert not any("snacks" in t.lower() for t in texts)
    by = {r.text: r for r in reqs}
    exp = by["3+ years of experience building backend services"]
    assert exp.type == "experience" and exp.years_required == 3 and exp.importance == "must"
    edu = by["Bachelor's degree in Computer Science"]
    assert edu.type == "education" and edu.degree_level_required == 1
    kafka = by["Experience with Kafka"]
    assert kafka.importance == "nice" and kafka.skills == ["kafka"]
    py = by["Strong Python and SQL skills"]
    assert py.type == "skill" and set(py.skills) == {"python", "sql"}
