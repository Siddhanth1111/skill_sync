"""Stage 9: evidence verification. A quote is shown only if it is an exact substring of the resume text
(whitespace normalised). An NLI model then checks that it supports the requirement; a low probability only
raises a weak-evidence flag and never changes the stored score."""
import re
import threading
from typing import List, Sequence, Tuple

from ..config import Settings
from .rerank import tokens


def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def quote_in_text(quote: str, text: str) -> bool:
    q = normalize_ws(quote)
    return bool(q) and q in normalize_ws(text)


def requirement_statement(req_text: str) -> str:
    """The requirement written as a statement for the entailment model (the hypothesis)."""
    return "The candidate meets this requirement: %s." % req_text.strip().rstrip(".")


class LexicalNLI:
    """'light' backend: share of hypothesis content words found in the premise."""
    name = "light-lexical-nli"

    def entailment(self, pairs: Sequence[Tuple[str, str]]) -> List[float]:
        out = []
        for premise, hypothesis in pairs:
            h = tokens(hypothesis) - {"candidate", "meets", "requirement"}
            out.append(len(h & tokens(premise)) / len(h) if h else 0.0)
        return out


class DebertaNLI:
    """'real' backend: P(entailment) from a DeBERTa model fine-tuned on MNLI."""

    def __init__(self, model_name: str):
        self.name = model_name
        self._tok = self._model = None
        self._ent = 2
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            self._tok = AutoTokenizer.from_pretrained(self.name)
            self._model = AutoModelForSequenceClassification.from_pretrained(self.name).eval()
            labels = {int(i): str(l).lower() for i, l in self._model.config.id2label.items()}
            self._ent = next(i for i, l in labels.items() if l.startswith("entail"))  # label order differs by model

    def entailment(self, pairs: Sequence[Tuple[str, str]]) -> List[float]:
        import torch
        out: List[float] = []
        with self._lock:
            self._load()
            for i in range(0, len(pairs), 16):
                batch = pairs[i:i + 16]
                enc = self._tok([p[0] for p in batch], [p[1] for p in batch], padding=True, truncation=True,
                                max_length=512, return_tensors="pt")
                with torch.no_grad():
                    probs = torch.softmax(self._model(**enc).logits, dim=-1)[:, self._ent]
                out.extend(float(p) for p in probs)
        return out


def build_nli(settings: Settings):
    return LexicalNLI() if settings.model_backend == "light" else DebertaNLI(settings.nli_model)
