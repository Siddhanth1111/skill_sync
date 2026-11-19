import numpy as np

from app.config import Settings
from app.services.embeddings import HashEmbedder
from app.services.ranking import final_score, gaps, rank_candidates, status_of
from app.services.rerank import CachedReranker, LexicalReranker
from app.services.retrieval import ChunkView, top_k
from app.services.scoring import ReqView, requirement_score

S = Settings(model_backend="light")
TH = {"met": 0.6, "partial": 0.3, "must_penalty": 0.9}


def req(type_, text="x", meta=None, importance="must", weight=3.0, id_=1):
    return ReqView(id_, 0, text, type_, importance, weight, meta or {})


def test_hash_embedder_normalised_and_deterministic():
    e = HashEmbedder()
    v = e.encode_docs(["python sql", "python sql"])
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0) and np.allclose(v[0], v[1])


def test_top_k_orders_by_cosine_and_reports_similarity():
    e = HashEmbedder()
    texts = ["built python services", "cooked pasta at home", "python and sql pipelines"]
    chunks = [ChunkView(i, i, "experience", t, v) for i, (t, v) in enumerate(zip(texts, e.encode_docs(texts)))]
    q = e.encode_queries(["python sql"])[0]
    top = top_k(q, chunks, 3)
    assert [c.id for c, _ in top][0] == 2 and top[0][1] >= top[1][1] >= top[2][1]
    assert len(top_k(q, chunks, 2)) == 2 and top_k(q, [], 3) == []


def test_skill_score_all_none_some():
    profile = {"skills": ["python"]}
    r = req("skill", "Python and SQL", {"skills": ["python", "sql"]})
    both = requirement_score(r, {"skills": ["python", "sql"]}, "", 0.1, S)
    none = requirement_score(r, {"skills": []}, "no relevant words", 0.9, S)
    some = requirement_score(r, profile, "", 0.2, S)
    assert abs(both - 0.85) < 1e-9
    assert none <= 0.45 + 1e-9 and abs(none - 0.45) < 1e-9  # reranker 0.9 capped at 0.45
    assert none < some < both


def test_skill_without_taxonomy_uses_reranker_score():
    assert requirement_score(req("skill", "Strong communication"), {}, "", 0.7, S) == 0.7


def test_experience_and_education_ratios_capped():
    e = req("experience", meta={"years_required": 4})
    assert requirement_score(e, {"years_experience": 2}, "", 0, S) == 0.5
    assert requirement_score(e, {"years_experience": 10}, "", 0, S) == 1.0
    d = req("education", meta={"degree_level_required": 2})
    assert requirement_score(d, {"education_level": 1}, "", 0, S) == 0.5
    assert requirement_score(d, {"education_level": 3}, "", 0, S) == 1.0
    assert requirement_score(req("experience"), {"years_experience": 9}, "", 0.33, S) == 0.33  # no years stated


def test_status_thresholds():
    assert [status_of(s, 0.6, 0.3) for s in (0.6, 0.59, 0.3, 0.29)] == ["met", "partial", "partial", "not_met"]


def test_final_score_and_must_penalty():
    items = [("must", 3, 1.0), ("should", 2, 0.5), ("nice", 1, 0.0)]
    assert abs(final_score(items, 0.6, 0.3, 0.9) - (3 + 1 + 0) / 6) < 1e-12
    items = [("must", 3, 0.0), ("should", 3, 1.0)]
    assert abs(final_score(items, 0.6, 0.3, 0.9) - 0.5 * 0.9) < 1e-12  # one unmet must
    two = [("must", 1, 0.0), ("must", 1, 0.0)]
    assert final_score(two, 0.6, 0.3, 0.9) == 0.0
    assert final_score([("must", 1, 0.5), ("nice", 1, 0.0)], 0.6, 0.3, 0.9) == 0.25  # partial must: no penalty
    assert final_score([], 0.6, 0.3, 0.9) == 0.0


def test_rank_tiebreak_by_met_musts_then_id():
    reqs = [{"id": 1, "importance": "must", "weight": 1}, {"id": 2, "importance": "nice", "weight": 1}]
    m = {10: {1: 1.0, 2: 0.0}, 11: {1: 0.0, 2: 1.0}, 12: {1: 1.0, 2: 0.0}}
    ranked = rank_candidates(reqs, m, TH)
    assert [r["candidate_id"] for r in ranked][0] in (10, 12)
    assert [r["candidate_id"] for r in ranked] == [10, 12, 11]  # 11 is penalised; 10 before 12 by id


def test_gaps_formula_and_order():
    reqs = [{"id": 1, "weight": 3}, {"id": 2, "weight": 1}]
    g = gaps(reqs, {1: 0.5, 2: 0.0})
    assert [x["requirement_id"] for x in g] == [1, 2]
    assert abs(g[0]["points_gain"] - 100 * 3 * 0.5 / 4) < 1e-9 and abs(g[1]["points_gain"] - 25.0) < 1e-9
    assert gaps(reqs, {1: 1.0, 2: 1.0}) == []


def test_rerank_cache_avoids_repeat_model_calls(settings):
    from app.db import make_session_factory
    calls = []

    class Counting(LexicalReranker):
        def score(self, pairs):
            calls.append(len(pairs))
            return super().score(pairs)

    sf = make_session_factory(settings.database_url)
    with sf() as db:
        r = CachedReranker(Counting(), db)
        pairs = [("python sql", "wrote python and sql"), ("kafka", "cooked pasta")]
        first = r.score(pairs)
        second = r.score(pairs + [("python", "python dev")])
    assert calls == [2, 1]  # second call only scores the one new pair
    assert second[:2] == first
