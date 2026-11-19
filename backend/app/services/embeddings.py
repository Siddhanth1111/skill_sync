"""Stage 6: embeddings. bge-base by default (MiniLM baseline, bge-m3 ablation), chosen in config only."""
import re
import threading
import zlib
from typing import List

import numpy as np

from ..config import Settings


class HashEmbedder:
    """'light' backend: signed hashing of word unigrams and bigrams. Deterministic, no downloads, lexical only."""

    def __init__(self, dim: int = 384):
        self.dim = dim
        self.name = "light-hash-%d" % dim

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        toks = re.findall(r"[a-z0-9+#.]+", text.lower())
        for gram in toks + [a + " " + b for a, b in zip(toks, toks[1:])]:
            h = zlib.crc32(gram.encode())
            v[h % self.dim] += 1.0 if (h >> 16) & 1 else -1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def encode_docs(self, texts: List[str]) -> np.ndarray:
        return np.stack([self._vec(t) for t in texts]) if texts else np.zeros((0, self.dim), dtype=np.float32)

    encode_queries = encode_docs


class SentenceTransformerEmbedder:
    """'real' backend. The model loads on first use; vectors are L2-normalised so dot product is cosine."""

    def __init__(self, model_name: str, query_prefix: str):
        self.name = model_name
        low = model_name.lower()
        # bge English models want an instruction on queries; bge-m3 and others do not.
        self.prefix = query_prefix if ("bge" in low and "m3" not in low) else ""
        self._model = None
        self._lock = threading.RLock()

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.name)
        return self._model

    @property
    def dim(self) -> int:
        with self._lock:
            return int(self._load().get_sentence_embedding_dimension())

    def _encode(self, texts: List[str]) -> np.ndarray:
        with self._lock:  # one forward pass at a time; ingest worker threads share the model
            model = self._load()
            if not texts:
                return np.zeros((0, int(model.get_sentence_embedding_dimension())), dtype=np.float32)
            return np.asarray(model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False),
                              dtype=np.float32)

    def encode_docs(self, texts: List[str]) -> np.ndarray:
        return self._encode(texts)

    def encode_queries(self, texts: List[str]) -> np.ndarray:
        return self._encode([self.prefix + t for t in texts])


def build_embedder(settings: Settings):
    if settings.model_backend == "light":
        return HashEmbedder()
    return SentenceTransformerEmbedder(settings.embedding_model, settings.query_prefix)


def embed_chunks(chunks, embedder) -> None:
    """Embed Chunk rows (documents, no query prefix) and store the vectors on them."""
    if not chunks:
        return
    vecs = embedder.encode_docs([c.text for c in chunks])
    for c, v in zip(chunks, vecs):
        c.embedding = [float(x) for x in v]
        c.embedding_model = embedder.name
