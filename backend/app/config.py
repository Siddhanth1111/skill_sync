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
    ocr_min_chars: int = 200  # a whole document under this many characters is OCRed page by page
    ocr_page_min_chars: int = 60  # a single page with fewer characters than this is OCRed (A1)
    ocr_garbage_ratio: float = 0.35  # a page whose text is mostly symbols or replacement characters is OCRed
    ocr_image_area_ratio: float = 0.5  # a page mostly covered by images, with little text, is OCRed
    ocr_dpi: int = 300
    ocr_psm: int = 4  # Tesseract page segmentation: 4 = one column of variable sizes, 6 = one uniform block
    ocr_min_confidence: float = 60.0  # mean word confidence under this flags the parse as low confidence
    low_confidence_min_chars: int = 400
    low_confidence_min_sections: int = 2

    # Stage 4: default requirement weights by importance
    weights: Dict[str, int] = {"must": 3, "should": 2, "nice": 1}

    # Stage 5: chunking. Units are bullets or sentences, so this is only a cap on one unit.
    chunk_max_chars: int = 500
    max_scored_requirements_warning: int = 15  # the editor warns above this many scored requirements (B8)

    # Models. "real" loads the HuggingFace models below (downloaded on first use, about 2 GB in total).
    # "light" uses small deterministic stand-ins (hashing embedder, lexical reranker and entailment): no downloads,
    # meant for tests and quick demos. Their scores say nothing about real model quality.
    model_backend: str = "real"
    embedding_model: str = "BAAI/bge-base-en-v1.5"  # baseline: sentence-transformers/all-MiniLM-L6-v2, ablation: BAAI/bge-m3
    query_prefix: str = "Represent this sentence for searching relevant passages: "  # bge models only
    reranker_model: str = "BAAI/bge-reranker-base"  # compare with BAAI/bge-reranker-v2-m3
    nli_model: str = "microsoft/deberta-base-mnli"

    # Stages 7-11: retrieval, scoring, ranking (starting values, to be tuned on development data only)
    pipeline_version: str = "v2"  # part of the rerank cache key and stored on every score (D9)
    retrieval_top_k: int = 8  # hybrid retrieval keeps this many units per requirement; the reranker picks among them
    hub_max_reuse: int = 3  # one unit may be the evidence for at most this many requirements before it is flagged
    blind_scoring: bool = True  # score on text with identity details removed (F2)
    skill_listed_score: float = 0.65  # skill found only in a bare skills list
    skill_related_score: float = 0.35  # a sibling tool (RabbitMQ for Kafka) is found: partial at most
    skill_technique_score: float = 0.5  # a named method that is one instance of the skill (logistic regression for ML)
    equivalent_experience_years: float = 5.0  # "or equivalent experience" satisfies a degree requirement at this level
    field_mismatch_factor: float = 0.7  # degree level fine but the required field of study is not found
    tier_band_points: float = 2.0  # candidates within this many points of a tier's leader share the tier (E2)
    met_threshold: float = 0.6
    partial_threshold: float = 0.3
    skill_present_score: float = 0.85
    skill_absent_cap: float = 0.45
    must_not_met_penalty: float = 0.9
    # Below this a verified quote is flagged as weak evidence. deberta-base-mnli gives low probabilities even for
    # supported quotes, so 0.5 flagged everything. 0.05 comes from an 8-pair sanity probe (unsupported <= 0.03,
    # supported >= 0.07) and has NOT been tuned on a development set. Tune it before trusting the flag.
    entailment_threshold: float = 0.05
    # A verified quote flagged as weak evidence (entailment below the threshold) cannot score above this, unless the
    # ontology finds the requirement's skill in the quote itself.
    weak_evidence_cap: float = 0.59

    # Stage 13: learning from feedback
    min_ratings: int = 10
    min_ratings_each_kind: int = 3

    # Stage 14: fairness
    counterfactual_threshold_points: float = 2.0  # on a 0 to 100 scale
    impact_ratio_threshold: float = 0.8
    weat_permutations: int = 5000


def get_settings() -> Settings:
    return Settings()
