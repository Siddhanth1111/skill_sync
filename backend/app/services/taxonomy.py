"""A small skill taxonomy used by the rule extractor and the sanity checks.

Deliberately conservative: ambiguous one-letter names (R, C, Go) are left out because plain word matching
would produce false hits. Extend this list for a real deployment.
"""
import re
from typing import List

SKILLS = sorted({
    "python", "java", "javascript", "typescript", "c++", "c#", "golang", "rust", "scala", "kotlin", "swift",
    "ruby", "php", "sql", "nosql", "bash", "matlab", "html", "css", "react", "angular", "vue", "node.js",
    "django", "flask", "fastapi", "spring", "spring boot", ".net", "graphql", "rest", "grpc",
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "cassandra", "kafka", "rabbitmq", "spark",
    "hadoop", "airflow", "dbt", "snowflake", "bigquery", "aws", "azure", "gcp", "docker", "kubernetes",
    "terraform", "ansible", "jenkins", "github actions", "ci/cd", "linux", "git",
    "machine learning", "deep learning", "nlp", "computer vision", "pytorch", "tensorflow", "keras",
    "scikit-learn", "pandas", "numpy", "mlflow", "langchain", "llm", "pgvector", "tableau", "power bi",
    "excel", "data analysis", "data engineering", "statistics", "a/b testing", "etl", "microservices",
    "system design", "agile", "scrum", "jira", "figma", "selenium", "pytest", "junit", "unit testing",
}, key=lambda s: (-len(s), s))


def _pattern(skill: str) -> "re.Pattern":
    return re.compile(r"(?<![\w+#.])" + re.escape(skill) + r"(?![\w+#])", re.IGNORECASE)


_PATTERNS = {s: _pattern(s) for s in SKILLS}


def contains_skill(text: str, skill: str) -> bool:
    """Whole-token, case-insensitive match (so 'java' does not match 'javascript')."""
    return bool(_pattern(skill.strip()).search(text)) if skill.strip() else False


def find_skills(text: str) -> List[str]:
    """Taxonomy skills mentioned in the text, in taxonomy order."""
    return [s for s, p in _PATTERNS.items() if p.search(text)]
