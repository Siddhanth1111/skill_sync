"""Stage 8: cross-encoder reranking with a sigmoid to 0..1, cached by requirement hash, segment hash and model."""
import hashlib
import math
import re
import threading
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import RerankCache

STOP = set("a an the and or of to in for with on at by is are be as we our you your their this that from "
           "experience skills skill strong good knowledge proficiency ability years year work working plus "
           "etc including using use".split())


def tokens(text: str) -> set:
    out = set()
    for t in re.findall(r"[a-z0-9+#.]+", text.lower()):
        t = t.strip(".")
        if t and t not in STOP:
            out.add(t[:-1] if len(t) > 3 and t.endswith("s") else t)
    return out


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x)) if x >= 0 else math.exp(x) / (1.0 + math.exp(x))


class LexicalReranker:
    """'light' backend: share of requirement words found in the segment."""
    name = "light-lexical"

    def score(self, pairs: Sequence[Tuple[str, str]]) -> List[float]:
        out = []
        for req, seg in pairs:
            r = tokens(req)
            out.append(len(r & tokens(seg)) / len(r) if r else 0.0)
        return out


class CrossEncoderReranker:
    """'real' backend: reads each (requirement, segment) pair together; logits go through a sigmoid."""

    def __init__(self, model_name: str):
        self.name = model_name
        self._tok = self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            self._tok = AutoTokenizer.from_pretrained(self.name)
            self._model = AutoModelForSequenceClassification.from_pretrained(self.name).eval()

    def score(self, pairs: Sequence[Tuple[str, str]]) -> List[float]:
        import torch
        out: List[float] = []
        with self._lock:
            self._load()
            for i in range(0, len(pairs), 16):
                batch = pairs[i:i + 16]
                enc = self._tok([p[0] for p in batch], [p[1] for p in batch], padding=True, truncation=True,
                                max_length=512, return_tensors="pt")
                with torch.no_grad():
                    logits = self._model(**enc).logits.reshape(len(batch), -1)[:, 0]
                out.extend(float(sigmoid(float(x))) for x in logits)
        return out


def build_reranker(settings: Settings):
    return LexicalReranker() if settings.model_backend == "light" else CrossEncoderReranker(settings.reranker_model)


def _h(s: str) -> str:
    return hashlib.sha1(" ".join(s.split()).encode()).hexdigest()


class CachedReranker:
    """Wraps a reranker with the DB cache. Without a session it just passes through."""

    def __init__(self, reranker, db: Optional[Session] = None):
        self.reranker, self.db = reranker, db

    def score(self, pairs: Sequence[Tuple[str, str]]) -> List[float]:
        if self.db is None or not pairs:
            return self.reranker.score(pairs)
        keys = [(_h(r), _h(s)) for r, s in pairs]
        have: Dict[Tuple[str, str], float] = {}
        rows = self.db.scalars(select(RerankCache).where(
            RerankCache.model == self.reranker.name, RerankCache.req_hash.in_({k[0] for k in keys}),
            RerankCache.seg_hash.in_({k[1] for k in keys})))
        for row in rows:
            have[(row.req_hash, row.seg_hash)] = row.score
        missing = [i for i, k in enumerate(keys) if k not in have]
        if missing:
            fresh = self.reranker.score([pairs[i] for i in missing])
            for i, sc in zip(missing, fresh):
                if keys[i] not in have:
                    have[keys[i]] = sc
                    self.db.add(RerankCache(req_hash=keys[i][0], seg_hash=keys[i][1], model=self.reranker.name, score=sc))
            self.db.commit()
        return [have[k] for k in keys]
