"""Stage 7: top-k nearest segments within one candidate, by cosine distance."""
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np


@dataclass
class ChunkView:
    """A chunk with its vector in memory. id is None for temporary chunks (blind audit, what-if)."""
    id: Optional[int]
    idx: int
    section: str
    text: str
    vec: np.ndarray


def top_k(query_vec: np.ndarray, chunks: Sequence[ChunkView], k: int = 3) -> List[Tuple[ChunkView, float]]:
    """Vectors are normalised, so cosine distance = 1 - dot. Similarity is reported as 1 - distance."""
    if not chunks:
        return []
    matrix = np.stack([c.vec for c in chunks])
    distance = 1.0 - matrix @ query_vec
    order = np.argsort(distance, kind="stable")[:k]
    return [(chunks[i], float(1.0 - distance[i])) for i in order]
