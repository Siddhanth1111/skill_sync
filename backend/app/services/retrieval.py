"""Stage 7: hybrid retrieval inside one candidate (review items C3, C4).

Dense cosine and BM25 each rank the candidate's units; reciprocal rank fusion merges the two lists, so an exact
phrase surfaces even when the embedding misses it and a paraphrase surfaces even when no word matches. The query
is expanded with ontology aliases for the BM25 side only. The top `k` (default 8) go on to the reranker."""
import math
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

_TOKEN = re.compile(r"[a-z0-9+#.]+")
_STOP = set("a an the and or of to in for with on at by is are be as we our you your their this that from using "
            "use etc including".split())


def lex_tokens(text: str) -> List[str]:
    out = []
    for t in _TOKEN.findall(text.lower()):
        t = t.strip(".")
        if t and t not in _STOP:
            out.append(t[:-1] if len(t) > 3 and t.endswith("s") else t)
    return out


@dataclass
class ChunkView:
    """A unit with its vector in memory. id is None for temporary units (blind audit, what-if)."""
    id: Optional[int]
    idx: int
    section: str
    text: str
    vec: np.ndarray
    context: str = ""
    start: Optional[str] = None
    end: Optional[str] = None

    @property
    def embed_text(self) -> str:
        return "%s. %s" % (self.context, self.text) if self.context else self.text


@dataclass
class Retrieved:
    chunk: ChunkView
    similarity: float  # cosine
    rrf: float
    dense_rank: int
    bm25_rank: Optional[int]


def bm25(query_terms: Sequence[str], docs: Sequence[List[str]], k1: float = 1.5, b: float = 0.75) -> np.ndarray:
    n = len(docs)
    scores = np.zeros(n)
    if not n or not query_terms:
        return scores
    avg = (sum(len(d) for d in docs) / n) or 1.0
    df: Dict[str, int] = {}
    for d in docs:
        for t in set(d):
            df[t] = df.get(t, 0) + 1
    for term in set(query_terms):
        if term not in df:
            continue
        idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
        for i, d in enumerate(docs):
            tf = d.count(term)
            if tf:
                scores[i] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(d) / avg))
    return scores


def top_k(query_vec: np.ndarray, chunks: Sequence[ChunkView], k: int = 8, query_text: str = "",
          expansion: Sequence[str] = (), rrf_k: int = 60) -> List[Retrieved]:
    """Hybrid top-k. With no query_text this is plain dense retrieval (BM25 contributes nothing)."""
    if not chunks:
        return []
    matrix = np.stack([c.vec for c in chunks])
    sim = matrix @ query_vec
    dense_order = np.argsort(-sim, kind="stable")
    dense_rank = {int(i): r + 1 for r, i in enumerate(dense_order)}

    bm_rank: Dict[int, int] = {}
    terms = lex_tokens(" ".join([query_text, *expansion]))
    if terms:
        bm = bm25(terms, [lex_tokens(c.embed_text) for c in chunks])
        order = [int(i) for i in np.argsort(-bm, kind="stable") if bm[i] > 0]
        bm_rank = {i: r + 1 for r, i in enumerate(order)}

    fused = []
    for i in range(len(chunks)):
        score = 1.0 / (rrf_k + dense_rank[i]) + (1.0 / (rrf_k + bm_rank[i]) if i in bm_rank else 0.0)
        fused.append((score, float(sim[i]), i))
    fused.sort(key=lambda t: (-t[0], -t[1], t[2]))
    return [Retrieved(chunks[i], s, f, dense_rank[i], bm_rank.get(i)) for f, s, i in fused[:k]]
