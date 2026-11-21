"""Review items D2, A6: the ontology, and the plan's paraphrase table at the matching level."""
import pytest

from app.services.taxonomy import canonical, contains_skill, expand_query_terms, find_skills, skill_match


@pytest.mark.parametrize("requirement_skill,resume_text,expected", [
    ("query optimization", "Tuned slow SQL using execution plans and indexes", "direct"),
    ("rdbms", "Designed schemas in PostgreSQL and MySQL", "implied"),
    ("ci/cd", "Automated builds and deployments with Jenkins", "direct"),
    ("machine learning", "Trained a logistic regression model to predict churn", "technique"),  # partial, not met
    ("machine learning", "Built supervised learning models for fraud", "direct"),
    ("kafka", "Built streaming ingestion with RabbitMQ", "related"),   # partial at most, never met
    ("python", "Wrote automation scripts in Perl", None),               # not met
    ("sql", "Maintained PostgreSQL databases", "implied"),
    ("kafka", "Cooked pasta", None),
])
def test_paraphrase_table_matching_level(requirement_skill, resume_text, expected):
    assert skill_match(resume_text, requirement_skill) == expected


def test_aliases_resolve_to_one_canonical_id():
    assert canonical("Postgres") == canonical("PostgreSQL") == "postgresql"
    assert canonical("k8s") == "kubernetes" and canonical("Node JS") == "node.js"
    assert canonical("not a skill") is None


def test_whole_word_matching_and_implication_only_goes_one_way():
    assert not contains_skill("I know javascript", "java")
    assert contains_skill("PostgreSQL admin", "sql") and not contains_skill("SQL admin", "postgresql")
    assert "c++" in find_skills("Wrote C++ and Python") and "python" in find_skills("wrote Python3 code")


def test_query_expansion_adds_aliases_and_more_specific_tools():
    terms = [t.lower() for t in expand_query_terms(["rdbms"])]
    assert "postgresql" in terms and "relational database" in terms
