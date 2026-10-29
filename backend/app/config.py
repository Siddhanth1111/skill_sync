"""Single place for model names, thresholds, limits and weights (spec rule: swap without code changes).

Every field can be overridden with an environment variable prefixed SKILLSYNC_.
"""
from typing import Dict

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SKILLSYNC_", env_file=".env", extra="ignore")

    # Database
    database_url: str = "sqlite:///./skillsync.db"

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


def get_settings() -> Settings:
    return Settings()
