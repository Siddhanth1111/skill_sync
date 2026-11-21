"""Review items C3 to C5: hybrid retrieval (BM25 plus dense with RRF) and the evidence reuse limit."""
import numpy as np

from app.services.embeddings import HashEmbedder
from app.services.retrieval import ChunkView, bm25, lex_tokens, top_k


def views(texts, vecs):
    return [ChunkView(i, i, "experience", t, v) for i, (t, v) in enumerate(zip(texts, vecs))]


def test_exact_phrase_surfaces_even_when_the_embedding_misses_it():
    texts = ["Built dashboards in Tableau", "Tuned queries with pgBouncer pooling", "Led a team of four engineers"]
    zero = [np.eye(3, dtype=np.float32)[0]] * 3  # every vector identical: dense retrieval cannot tell them apart
    q = np.eye(3, dtype=np.float32)[0]
    dense_only = [r.chunk.id for r in top_k(q, views(texts, zero), 1)]
    hybrid = [r.chunk.id for r in top_k(q, views(texts, zero), 1, "pgbouncer pooling")]
    assert dense_only == [0] and hybrid == [1]


def test_rrf_fuses_both_rankings_and_reports_ranks():
    e = HashEmbedder()
    texts = ["python services", "cooked pasta", "sql tuning and python"]
    q = e.encode_queries(["python sql tuning"])[0]
    out = top_k(q, views(texts, e.encode_docs(texts)), 3, "python sql tuning")
    assert out[0].chunk.id == 2 and out[0].bm25_rank == 1 and out[0].dense_rank == 1
    assert out[-1].chunk.id == 1 and out[-1].bm25_rank is None
    assert out[0].rrf > out[1].rrf > out[2].rrf


def test_k_limits_results_and_empty_input_is_safe():
    e = HashEmbedder()
    t = ["a b", "c d", "e f"]
    assert len(top_k(e.encode_queries(["x"])[0], views(t, e.encode_docs(t)), 2)) == 2
    assert top_k(e.encode_queries(["x"])[0], [], 8) == []
    assert (bm25([], [["a"]]) == 0).all() and lex_tokens("The Python, and SQL!") == ["python", "sql"]
