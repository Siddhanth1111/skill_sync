"""Single place for model names, thresholds, limits and weights (spec rule: swap without code changes).

Every field can be overridden with an environment variable prefixed SKILLSYNC_.
"""
from typing import Dict

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SKILLSYNC_", env_file=".env", extra="ignore")

    # Database
    database_url: str = "sqlite:///./skillsync.db"

    # Auth. If jwt_secret is empty a random secret is created once and kept in backend/.jwt_secret (git-ignored).
    jwt_secret: str = ""
    jwt_expire_minutes: int = 480
    admin_email: str = ""  # optional: seed an admin account at start-up (with admin_password)
    admin_password: str = ""
    login_max_failures: int = 8  # per email, within login_window_s, then 429
    login_window_s: int = 900

    # LLM (Ollama)
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "llama3.1:8b"
    llm_timeout_s: float = 120.0
    llm_max_retries: int = 2  # validation retries after the first attempt
    llm_max_input_chars: int = 12000

    # Stage 1: upload limits
    max_files_per_job: int = 200
    max_file_bytes: int = 10 * 1024 * 1024
    allowed_extensions: tuple = (".pdf", ".docx")
    worker_threads: int = 3

    # Stage 2: extraction / OCR
    ocr_min_chars: int = 200  # PDFs with fewer characters are treated as scanned
    ocr_dpi: int = 200
    low_confidence_min_chars: int = 400
    low_confidence_min_sections: int = 2

    # Stage 4: default requirement weights by importance
    weights: Dict[str, int] = {"must": 3, "should": 2, "nice": 1}

    # Stage 5: chunking
    chunk_max_chars: int = 500

    # Models. "real" loads the HuggingFace models below (downloaded on first use, about 2 GB in total).
    # "light" uses small deterministic stand-ins (hashing embedder, lexical reranker and entailment): no downloads,
    # meant for tests and quick demos. Their scores say nothing about real model quality.
    model_backend: str = "real"
    embedding_model: str = "BAAI/bge-base-en-v1.5"  # baseline: sentence-transformers/all-MiniLM-L6-v2, ablation: BAAI/bge-m3
    query_prefix: str = "Represent this sentence for searching relevant passages: "  # bge models only
    reranker_model: str = "BAAI/bge-reranker-base"  # compare with BAAI/bge-reranker-v2-m3
    nli_model: str = "microsoft/deberta-base-mnli"

    # Stages 7-11: retrieval, scoring, ranking (starting values, to be tuned on development data only)
    retrieval_top_k: int = 3
    met_threshold: float = 0.6
    partial_threshold: float = 0.3
    skill_present_score: float = 0.85
    skill_absent_cap: float = 0.45
    must_not_met_penalty: float = 0.9
    # Below this a verified quote is flagged as weak evidence. deberta-base-mnli gives low probabilities even for
    # supported quotes, so 0.5 flagged everything. 0.05 comes from an 8-pair sanity probe (unsupported <= 0.03,
    # supported >= 0.07) and has NOT been tuned on a development set. Tune it before trusting the flag.
    entailment_threshold: float = 0.05

    # Stage 13: learning from feedback
    min_ratings: int = 10
    min_ratings_each_kind: int = 3

    # Stage 14: fairness
    counterfactual_threshold_points: float = 2.0  # on a 0 to 100 scale
    impact_ratio_threshold: float = 0.8
    weat_permutations: int = 5000


def get_settings() -> Settings:
    return Settings()
