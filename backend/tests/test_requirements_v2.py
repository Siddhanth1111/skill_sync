"""Review items B1 to B7: requirement kinds, year ranges, any-of lists, weights, duplicates, queries, importance."""
from app.config import Settings
from app.schemas import JDExtraction, JDRequirement
from app.services.extraction import _clean_requirements, extract_requirements, weight_for
from app.services.requirements import (dedupe_requirements, detect_skills_mode, normalize_query, parse_years)

JD = """Senior Backend Engineer

About us
Friendly company.

Responsibilities
- Design and build APIs in Python
- Collaborate with product managers

Requirements
- 2 to 5 years of backend experience
- Strong understanding of RDBMS
- Kafka / RabbitMQ experience
- Excellent communication skills
- Bachelor's degree in Computer Science

Tech stack
- Docker

Nice to have
- Experience with Kubernetes
"""


def by_text(result):
    return {r.text: r for r in result.requirements}


def test_b1_duties_and_soft_skills_get_a_kind_and_are_not_scored():
    got = by_text(extract_requirements(JD, None, Settings())[0])
    assert got["Design and build APIs in Python"].kind == "duty"
    assert got["Collaborate with product managers"].kind == "duty"
    assert got["Excellent communication skills"].kind == "soft_skill"
    assert got["Strong understanding of RDBMS"].kind == "hard_skill"
    assert got["Bachelor's degree in Computer Science"].kind == "education"
    s = Settings()
    assert weight_for("duty", "must", s) == 0 and weight_for("soft_skill", "should", s) == 0
    assert weight_for("hard_skill", "must", s) == 3 and weight_for("hard_skill", "nice", s) == 1


def test_b2_year_range_requires_the_minimum():
    assert parse_years("2 to 5 years of experience") == (2.0, 5.0)
    assert parse_years("2-5 yrs") == (2.0, 5.0)
    assert parse_years("3+ years") == (3.0, None)
    assert parse_years("minimum of 4 years") == (4.0, None)
    assert parse_years("5 or more years") == (5.0, None)
    assert parse_years("no numbers here") == (None, None)
    got = by_text(extract_requirements(JD, None, Settings())[0])
    assert got["2 to 5 years of backend experience"].years_required == 2.0


def test_b2_llm_that_returns_the_larger_number_is_corrected_by_code():
    llm_out = JDExtraction(requirements=[JDRequirement(
        text="2 to 5 years of backend experience", type="experience", importance="must", years_required=5.0)])
    assert _clean_requirements(llm_out).requirements[0].years_required == 2.0


def test_b3_alternatives_are_any_of():
    assert detect_skills_mode("Kafka / RabbitMQ experience", ["kafka", "rabbitmq"]) == "any"
    assert detect_skills_mode("Kafka or RabbitMQ", ["kafka", "rabbitmq"]) == "any"
    assert detect_skills_mode("any of Python, Java, Go", ["python", "java"]) == "any"
    assert detect_skills_mode("Python and SQL", ["python", "sql"]) == "all"
    assert detect_skills_mode("CI/CD pipelines and Docker", ["ci/cd", "docker"]) == "all"  # '/' inside one skill
    assert detect_skills_mode("Python", ["python"]) == "all"
    got = by_text(extract_requirements(JD, None, Settings())[0])
    assert got["Kafka / RabbitMQ experience"].skills_mode == "any"


def test_b4_weights_follow_importance_even_when_the_llm_labels_everything_must():
    """The posting's own headings win over a model that calls every bullet 'must'."""
    llm_out = JDExtraction(requirements=[
        JDRequirement(text="Strong understanding of RDBMS", type="skill", importance="must", skills=["rdbms"]),
        JDRequirement(text="Experience with Kubernetes", type="skill", importance="must", skills=["kubernetes"]),
        JDRequirement(text="Docker", type="skill", importance="must", skills=["docker"])])
    got = by_text(_clean_requirements(llm_out, JD))
    assert got["Strong understanding of RDBMS"].importance == "must"
    assert got["Experience with Kubernetes"].importance == "nice"
    assert got["Docker"].importance == "should"  # under an unknown heading: should, not must (B7)
    s = Settings()
    assert [weight_for(r.kind, r.importance, s) for r in got.values()] == [3, 1, 2]


def test_b5_near_duplicates_merge_and_keep_the_stronger_importance():
    a = JDRequirement(text="Strong Python skills", type="skill", importance="should", skills=["python"], kind="hard_skill")
    b = JDRequirement(text="Python experience", type="skill", importance="must", skills=["python"], kind="hard_skill")
    c = JDRequirement(text="Python and SQL", type="skill", importance="must", skills=["python", "sql"], kind="hard_skill")
    out = dedupe_requirements([a, b, c])
    assert len(out) == 2 and out[0].importance == "must" and out[1].skills == ["python", "sql"]


def test_b6_query_drops_filler_words_and_year_counts():
    assert normalize_query("Strong understanding of RDBMS") == "RDBMS"
    assert normalize_query("Good knowledge of query optimization") == "query optimization"
    assert normalize_query("Experience in Python development") == "Python development"
    assert normalize_query("3+ years of backend experience") == "backend"
    assert normalize_query("Python") == "Python"


def test_b7_rule_fallback_does_not_let_unknown_headings_inherit_must():
    got = by_text(extract_requirements(JD, None, Settings())[0])
    assert got["Docker"].importance == "should" and got["Kubernetes".join(["Experience with ", ""])].importance == "nice"
    assert got["Strong understanding of RDBMS"].importance == "must"


def test_duties_only_posting_still_scores_the_duties_that_name_a_skill():
    jd = "Backend Developer\n\nResponsibilities\n- Build REST services in Python\n- Design PostgreSQL schemas\n- Attend meetings\n"
    reqs = extract_requirements(jd, None, Settings())[0].requirements
    kinds = {r.text: r.kind for r in reqs}
    assert kinds["Build REST services in Python"] == "hard_skill" and kinds["Attend meetings"] == "duty"
