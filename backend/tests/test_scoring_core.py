import numpy as np

from app.config import Settings
from app.services.embeddings import HashEmbedder
from app.services.ranking import final_score, gaps, rank_candidates, status_of
from app.services.rerank import CachedReranker, LexicalReranker
from app.services.retrieval import ChunkView, Retrieved, top_k
from app.services.scoring import ReqView, score_education, score_experience, score_skill

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
    top = top_k(q, chunks, 3)  # no query text: dense only
    assert [t.chunk.id for t in top][0] == 2 and top[0].similarity >= top[1].similarity >= top[2].similarity
    assert len(top_k(q, chunks, 2)) == 2 and top_k(q, [], 3) == []


def _cands(*items):
    """(unit text, section, rerank) -> the (Retrieved, rerank) pairs score_skill reads."""
    out = []
    for i, (text, section, rr) in enumerate(items):
        cv = ChunkView(i, i, section, text, np.zeros(2, dtype=np.float32))
        out.append((Retrieved(cv, 0.5, 0.03, i + 1, None), rr))
    return out


def test_skill_is_scored_from_evidence_not_from_the_profile_list():
    """D1: the old rule gave 0.85 whenever the skill was in the profile, whatever the quote said."""
    r = req("skill", "Python and SQL", {"skills": ["python", "sql"]})
    both, show, _ = score_skill(r, _cands(("Built Python and SQL services", "experience", 0.1)), S)
    none, _, _ = score_skill(r, _cands(("cooked pasta", "experience", 0.9)), S)
    some, _, _ = score_skill(r, _cands(("Built Python services", "experience", 0.2)), S)
    assert abs(both - S.skill_present_score) < 1e-9 and show == 0
    assert abs(none - S.skill_absent_cap) < 1e-9  # reranker 0.9 is capped when the skill is not in any evidence
    assert none < some < both


def test_listed_skill_scores_below_a_skill_shown_in_work():
    r = req("skill", "Kafka", {"skills": ["kafka"]})
    listed, _, t1 = score_skill(r, _cands(("Python, Kafka, Spark", "skills", 0.3)), S)
    shown, _, t2 = score_skill(r, _cands(("Ran Kafka jobs", "experience", 0.3)), S)
    assert listed == S.skill_listed_score < shown == S.skill_present_score
    assert t1["skills"]["kafka"] == "listed" and t2["skills"]["kafka"] == "evidence"


def test_any_of_takes_the_best_alternative_and_all_of_the_average():
    units = _cands(("Ran Kafka jobs", "experience", 0.3))
    any_r = req("skill", "Kafka or RabbitMQ", {"skills": ["kafka", "rabbitmq"], "skills_mode": "any"})
    all_r = req("skill", "Kafka and RabbitMQ", {"skills": ["kafka", "rabbitmq"], "skills_mode": "all"})
    assert score_skill(any_r, units, S)[0] == S.skill_present_score  # B3
    assert score_skill(all_r, units, S)[0] < S.skill_present_score


def test_related_tool_is_partial_at_most_and_other_language_is_not_met():
    """From the plan's paraphrase table: RabbitMQ for Kafka is partial at most; Perl for Python is not met."""
    kafka = req("skill", "Kafka", {"skills": ["kafka"]})
    s, _, t = score_skill(kafka, _cands(("Built streaming ingestion with RabbitMQ", "experience", 0.1)), S)
    assert t["skills"]["kafka"] == "related_only" and S.partial_threshold <= s < S.met_threshold
    py = req("skill", "Python", {"skills": ["python"]})
    s, _, t = score_skill(py, _cands(("Wrote automation scripts in Perl", "experience", 0.1)), S)
    assert t["skills"]["python"] == "not_found" and s < S.partial_threshold


def test_a_named_technique_is_partial_not_met():
    ml = req("skill", "Machine learning", {"skills": ["machine learning"]})
    s, show, t = score_skill(ml, _cands(("Trained a logistic regression model to predict churn", "experience", 0.0)), S)
    assert t["skills"]["machine learning"] == "technique_only" and show == 0
    assert S.partial_threshold <= s < S.met_threshold


def test_skill_without_ontology_entry_uses_reranker_score():
    r = req("skill", "Zorblax mastery", {"skills": []})
    assert score_skill(r, _cands(("something", "experience", 0.7)), S)[0] == 0.7


def test_experience_uses_years_with_the_skill_and_education_level_and_field():
    e = req("experience", "4 years of Python", {"skills": ["python"], "years_required": 4, "years_min": 4})
    assert score_experience(e, {"years_experience": 10, "skill_years": {"python": 2}}, 1, S)[0] == 0.5  # D6
    assert score_experience(e, {"years_experience": 10, "skill_years": {"python": 9}}, 1, S)[0] == 1.0
    # skill shown but no dated role links to it: years cannot be verified, so at most partial
    assert score_experience(e, {"years_experience": 10, "skill_years": {}}, 1, S)[0] <= S.skill_absent_cap
    total_only = req("experience", "4 years of backend experience", {"years_min": 4})
    assert score_experience(total_only, {"years_experience": 2}, 0, S)[0] == 0.5
    d = req("education", "Master's in Computer Science", {"degree_level_required": 2})
    assert score_education(d, {"education_level": 1, "education": [{"degree": "B.Tech Computer Science"}]}, S)[0] == 0.5
    assert score_education(d, {"education_level": 3, "education": [{"degree": "PhD Computer Science"}]}, S)[0] == 1.0
    # D7: right level, wrong field, and the equivalence rule
    wrong = score_education(d, {"education_level": 2, "education": [{"degree": "MA History"}]}, S)
    assert abs(wrong[0] - S.field_mismatch_factor) < 1e-9 and wrong[1]["field_mismatch"]
    eq = req("education", "Bachelor's degree or equivalent experience", {"degree_level_required": 1})
    assert score_education(eq, {"education_level": 0, "years_experience": 6}, S)[0] == 0.8


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


def test_experience_requirement_without_years_scores_by_skill_mention():
    """Found with real Llama: 'Experience with Kafka' came back typed as experience, with no years."""
    r = req("experience", "Experience with Kafka", {"skills": ["kafka"], "years_required": None})
    assert r.years_required is None
    assert score_skill(r, _cands(("Ran Kafka jobs", "experience", 0.1)), S)[0] == S.skill_present_score
    assert score_skill(r, _cands(("nothing relevant", "experience", 0.9)), S)[0] <= S.skill_absent_cap + 1e-9


def test_tiers_group_close_scores_and_never_split_on_a_point():
    reqs = [{"id": 1, "importance": "must", "weight": 1}]
    m = {1: {1: 0.90}, 2: {1: 0.89}, 3: {1: 0.60}, 4: {1: 0.595}}
    ranked = rank_candidates(reqs, m, {**TH, "tier_band": 0.02})
    assert [r["tier"] for r in ranked] == [1, 1, 2, 2] and all(r["tied"] for r in ranked)
    assert [r["rank"] for r in ranked] == [1, 2, 3, 4]  # order stays deterministic, the tier says it is not meaningful


def test_unverifiable_must_is_not_penalised_and_zero_weight_is_ignored():
    items = [("must", 3, 0.0, True), ("should", 3, 1.0, False)]
    assert abs(final_score(items, 0.6, 0.3, 0.9) - 0.5) < 1e-12  # E1: no 0.9 penalty when evidence was unreadable
    reqs = [{"id": 1, "importance": "must", "weight": 3}, {"id": 2, "importance": "must", "weight": 0}]
    r = rank_candidates(reqs, {1: {1: 1.0, 2: 0.0}}, TH)[0]
    assert (r["musts"], r["musts_met"], r["not_met"]) == (1, 1, 0) and r["final_score"] == 1.0  # B1/E3
    assert gaps(reqs, {1: 1.0, 2: 0.0}) == []


