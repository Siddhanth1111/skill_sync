"""The three swappable models (embedder, reranker, entailment) built from config in one place."""
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from .embeddings import build_embedder
from .rerank import build_reranker
from .verify import build_nli


@dataclass
class Models:
    embedder: Any
    reranker: Any
    nli: Any

    def describe(self) -> dict:
        return {"embedder": self.embedder.name, "reranker": self.reranker.name, "nli": self.nli.name}


def build_models(settings: Settings) -> Models:
    return Models(build_embedder(settings), build_reranker(settings), build_nli(settings))
