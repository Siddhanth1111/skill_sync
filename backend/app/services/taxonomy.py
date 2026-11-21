"""Skill ontology: canonical skills with aliases, parents (implied skills) and related families.

Replaces the old flat word list (review items D2, A6). A mention of PostgreSQL implies SQL and RDBMS, "tuned slow
SQL using execution plans" is an alias of query optimisation, and RabbitMQ is related to Kafka but is not Kafka.
Extend ENTRIES for a real deployment (ESCO or O*NET can be merged in the same shape).

Match kinds returned by `skill_match`:
  direct   the skill or one of its aliases appears
  implied   a more specific skill appears (PostgreSQL for SQL)
  technique a named method that is one instance of the skill appears (logistic regression for machine learning):
            partial credit, never met on its own
  related   a sibling tool from the same family appears (RabbitMQ for Kafka); never counts as met
"""
import re
from typing import Dict, FrozenSet, Iterable, List, Optional, Set

# canonical id -> (aliases, parents, family)
# parents: broader skills that this skill implies. family: sibling group used for "related" matches.
ENTRIES: Dict[str, dict] = {
    # languages
    "python": {"aliases": ["python3"]},
    "java": {},
    "javascript": {"aliases": ["js", "ecmascript", "es6"]},
    "typescript": {"parents": ["javascript"]},
    "c++": {"aliases": ["cpp"]},
    "c#": {"aliases": ["csharp", "c sharp"]},
    "golang": {"aliases": ["go lang", "go language"]},
    "rust": {}, "scala": {}, "kotlin": {},
    "swift": {}, "ruby": {}, "php": {},
    "perl": {},
    "bash": {"aliases": ["shell scripting", "shell script"]},
    "matlab": {},
    "sql": {"aliases": ["structured query language", "t-sql", "pl/sql", "plsql"]},
    "nosql": {"aliases": ["no-sql", "non-relational database"]},
    "html": {"aliases": ["html5"]}, "css": {"aliases": ["css3"]},
    # web
    "react": {"aliases": ["reactjs", "react.js"], "parents": ["javascript"], "family": "frontend-framework"},
    "angular": {"aliases": ["angularjs"], "parents": ["javascript"], "family": "frontend-framework"},
    "vue": {"aliases": ["vuejs", "vue.js"], "parents": ["javascript"], "family": "frontend-framework"},
    "node.js": {"aliases": ["nodejs", "node js"], "parents": ["javascript"]},
    "django": {"parents": ["python"], "family": "python-web"}, "flask": {"parents": ["python"], "family": "python-web"},
    "fastapi": {"parents": ["python"], "family": "python-web"},
    "spring": {"aliases": ["spring framework"], "parents": ["java"]},
    "spring boot": {"aliases": ["springboot"], "parents": ["spring"]},
    ".net": {"aliases": ["dotnet", "asp.net", ".net core"], "parents": ["c#"]},
    "graphql": {"family": "api"}, "rest": {"aliases": ["restful", "rest api", "rest apis", "restful api", "restful apis"], "family": "api"},
    "grpc": {"family": "api"},
    # data stores
    "rdbms": {"aliases": ["relational database", "relational databases", "relational database management system"]},
    "postgresql": {"aliases": ["postgres", "psql"], "parents": ["sql", "rdbms"], "family": "rdbms"},
    "mysql": {"aliases": ["mariadb"], "parents": ["sql", "rdbms"], "family": "rdbms"},
    "oracle": {"aliases": ["oracle db", "oracle database"], "parents": ["sql", "rdbms"], "family": "rdbms"},
    "sql server": {"aliases": ["mssql", "ms sql", "microsoft sql server"], "parents": ["sql", "rdbms"], "family": "rdbms"},
    "sqlite": {"parents": ["sql", "rdbms"], "family": "rdbms"},
    "mongodb": {"aliases": ["mongo"], "parents": ["nosql"], "family": "nosql-store"},
    "redis": {"parents": ["nosql"], "family": "nosql-store"},
    "cassandra": {"parents": ["nosql"], "family": "nosql-store"},
    "dynamodb": {"parents": ["nosql", "aws"], "family": "nosql-store"},
    "elasticsearch": {"aliases": ["elastic search", "opensearch"], "family": "search"},
    "query optimization": {"aliases": [
        "query optimisation", "query tuning", "performance tuning", "sql tuning", "tuned slow sql", "tuned slow queries",
        "slow query", "slow queries", "execution plan", "execution plans", "explain analyze", "query plan", "query plans",
        "index tuning", "database tuning", "optimized queries", "optimised queries", "optimizing queries"]},
    "database design": {"aliases": ["schema design", "designed schemas", "data modeling", "data modelling",
                                    "database schema", "database schemas", "er diagram", "normalization"]},
    # data / messaging
    "kafka": {"aliases": ["apache kafka"], "family": "message-broker"},
    "rabbitmq": {"aliases": ["rabbit mq"], "family": "message-broker"},
    "sqs": {"aliases": ["amazon sqs"], "family": "message-broker"},
    "spark": {"aliases": ["apache spark", "pyspark"], "family": "big-data"},
    "hadoop": {"aliases": ["hdfs", "mapreduce"], "family": "big-data"},
    "airflow": {"aliases": ["apache airflow"], "family": "orchestrator"},
    "dbt": {"aliases": ["data build tool"]},
    "snowflake": {"family": "warehouse"}, "bigquery": {"aliases": ["big query"], "family": "warehouse"},
    "etl": {"aliases": ["elt", "data pipelines", "data pipeline", "etl pipelines", "streaming ingestion"]},
    "data engineering": {"aliases": ["data engineer"]},
    "data analysis": {"aliases": ["data analytics", "analyzed data", "analysed data"]},
    "statistics": {"aliases": ["statistical analysis", "statistical modeling", "statistical modelling"]},
    "a/b testing": {"aliases": ["ab testing", "a/b tests", "split testing", "controlled experiments"]},
    # cloud / devops
    "aws": {"aliases": ["amazon web services", "ec2", "amazon s3", "aws lambda", "amazon aws"], "family": "cloud"},
    "azure": {"aliases": ["microsoft azure"], "family": "cloud"},
    "gcp": {"aliases": ["google cloud", "google cloud platform"], "family": "cloud"},
    "docker": {"aliases": ["containerization", "containerisation", "containerized", "containerised"], "family": "containers"},
    "kubernetes": {"aliases": ["k8s", "eks", "gke", "aks"], "parents": ["docker"], "family": "containers"},
    "terraform": {"aliases": ["infrastructure as code", "iac"], "family": "iac"},
    "ansible": {"family": "iac"},
    "ci/cd": {"aliases": [
        "cicd", "ci cd", "continuous integration", "continuous delivery", "continuous deployment",
        "ci/cd pipeline", "ci/cd pipelines", "automated builds", "automated deployments", "build pipelines",
        "deployment pipelines", "jenkins", "github actions", "gitlab ci", "circleci", "travis ci"]},
    "jenkins": {"parents": ["ci/cd"], "family": "ci-tool"},
    "github actions": {"parents": ["ci/cd"], "family": "ci-tool"},
    "linux": {"aliases": ["unix", "ubuntu"]},
    "git": {"aliases": ["github", "gitlab", "version control"]},
    # ML
    "machine learning": {"aliases": ["ml", "predictive modeling", "predictive modelling", "supervised learning",
                                     "unsupervised learning", "model training", "ml models"],
                         "techniques": ["logistic regression", "linear regression", "random forest", "gradient boosting",
                                        "xgboost", "lightgbm", "decision tree", "decision trees", "k-means", "svm",
                                        "support vector machine", "naive bayes", "classification model",
                                        "regression model", "churn model", "recommendation model", "recommender system"]},
    "deep learning": {"aliases": ["neural network", "neural networks", "cnn", "rnn", "lstm", "transformer models"],
                      "parents": ["machine learning"]},
    "nlp": {"aliases": ["natural language processing", "text mining", "text classification"], "parents": ["machine learning"]},
    "computer vision": {"aliases": ["image recognition", "object detection", "image classification"],
                        "parents": ["machine learning"]},
    "pytorch": {"parents": ["deep learning"], "family": "dl-framework"},
    "tensorflow": {"parents": ["deep learning"], "family": "dl-framework"},
    "keras": {"parents": ["deep learning"], "family": "dl-framework"},
    "scikit-learn": {"aliases": ["sklearn", "scikit learn"], "parents": ["machine learning"]},
    "pandas": {"parents": ["python"]}, "numpy": {"parents": ["python"]},
    "mlflow": {}, "langchain": {"parents": ["llm"]},
    "llm": {"aliases": ["large language model", "large language models", "llms", "generative ai"]},
    "pgvector": {"parents": ["postgresql"]},
    # BI / misc
    "tableau": {"family": "bi"}, "power bi": {"aliases": ["powerbi"], "family": "bi"}, "excel": {"aliases": ["microsoft excel"]},
    "microservices": {"aliases": ["micro-services", "microservice"]},
    "system design": {"aliases": ["distributed systems", "scalable systems", "software architecture", "architecture design"]},
    "agile": {"aliases": ["agile methodology"]}, "scrum": {"parents": ["agile"]},
    "jira": {}, "figma": {},
    "selenium": {"family": "test-tool"}, "pytest": {"parents": ["unit testing"], "family": "test-tool"},
    "junit": {"parents": ["unit testing"], "family": "test-tool"},
    "unit testing": {"aliases": ["unit tests", "test automation", "automated tests", "tdd", "test-driven development"]},
}

CANON: List[str] = sorted(ENTRIES, key=lambda s: (-len(s), s))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _phrase_pattern(phrase: str) -> "re.Pattern":
    return re.compile(r"(?<![\w+#.])" + re.escape(phrase) + r"(?![\w+#])", re.IGNORECASE)


# alias (normalised) -> canonical id
ALIAS_TO_CANON: Dict[str, str] = {}
for _c, _e in ENTRIES.items():
    ALIAS_TO_CANON.setdefault(_c, _c)
    for _a in _e.get("aliases", []):
        ALIAS_TO_CANON.setdefault(_norm(_a), _c)

_PATTERNS: Dict[str, "re.Pattern"] = {}
_ALIAS_PATTERNS: Dict[str, List["re.Pattern"]] = {}
_TECHNIQUE_PATTERNS: Dict[str, List["re.Pattern"]] = {}
for _c, _e in ENTRIES.items():
    _PATTERNS[_c] = _phrase_pattern(_c)
    _ALIAS_PATTERNS[_c] = [_phrase_pattern(a) for a in _e.get("aliases", [])]
    _TECHNIQUE_PATTERNS[_c] = [_phrase_pattern(a) for a in _e.get("techniques", [])]

# descendants[c] = skills that imply c (PostgreSQL implies SQL, so SQL's descendants include postgresql)
_DESCENDANTS: Dict[str, Set[str]] = {c: set() for c in ENTRIES}


def _ancestors(c: str, seen: Optional[Set[str]] = None) -> Set[str]:
    seen = seen if seen is not None else set()
    for p in ENTRIES.get(c, {}).get("parents", []):
        if p not in seen:
            seen.add(p)
            _ancestors(p, seen)
    return seen


for _c in ENTRIES:
    for _p in _ancestors(_c):
        if _p in _DESCENDANTS:
            _DESCENDANTS[_p].add(_c)

# Old public name, kept because other modules import it.
SKILLS = CANON


def canonical(skill: str) -> Optional[str]:
    """Canonical id for a skill name or alias, or None when the ontology does not know it."""
    return ALIAS_TO_CANON.get(_norm(skill))


def aliases_of(skill: str) -> List[str]:
    c = canonical(skill)
    return [c] + list(ENTRIES[c].get("aliases", [])) if c else [skill.strip()]


def _literal_pattern(phrase: str) -> "re.Pattern":
    """For a skill the ontology does not know: whole-token match that tolerates a plural ('view' and 'views')."""
    words = phrase.strip().split()
    last = words[-1]
    stem = last[:-1] if len(last) > 3 and last.endswith("s") else last
    body = " ".join(re.escape(w) for w in words[:-1] + [stem])
    return re.compile(r"(?<![\w+#.])" + body + r"(?:s|es)?(?![\w+#])", re.IGNORECASE)


def mentions(text: str, c: str) -> bool:
    """True when canonical skill `c` or one of its aliases appears in the text."""
    return bool(_PATTERNS[c].search(text) or any(p.search(text) for p in _ALIAS_PATTERNS[c]))


def skill_match(text: str, skill: str) -> Optional[str]:
    """'direct', 'implied', 'technique', 'related' or None for one skill against a piece of text."""
    c = canonical(skill)
    if c is None:  # not in the ontology: literal whole-token match only
        return "direct" if skill.strip() and _literal_pattern(skill).search(text) else None
    if mentions(text, c):
        return "direct"
    if any(mentions(text, d) for d in _DESCENDANTS.get(c, ())):
        return "implied"
    if any(p.search(text) for p in _TECHNIQUE_PATTERNS[c]):
        return "technique"
    fam = ENTRIES[c].get("family")
    if fam and any(mentions(text, s) for s, e in ENTRIES.items() if e.get("family") == fam and s != c):
        return "related"
    return None


def contains_skill(text: str, skill: str) -> bool:
    """Alias-aware presence check (direct or implied mentions). Related tools do not count."""
    return skill_match(text, skill) in ("direct", "implied")


def find_skills(text: str) -> List[str]:
    """Canonical skills directly mentioned in the text (aliases resolve to the canonical id), longest first."""
    return [c for c in CANON if mentions(text, c)]


def expand_query_terms(skills: Iterable[str]) -> List[str]:
    """Aliases and more specific skills to add to a lexical query so exact phrases surface."""
    out: List[str] = []
    for s in skills:
        c = canonical(s)
        if not c:
            out.append(s)
            continue
        out.extend([c] + list(ENTRIES[c].get("aliases", [])))
        out.extend(sorted(_DESCENDANTS.get(c, ())))
    seen, res = set(), []
    for t in out:
        k = _norm(t)
        if k not in seen:
            seen.add(k)
            res.append(t)
    return res


def related_family(skill: str) -> FrozenSet[str]:
    c = canonical(skill)
    fam = ENTRIES.get(c, {}).get("family") if c else None
    return frozenset(s for s, e in ENTRIES.items() if fam and e.get("family") == fam and s != c)
