import pytest

from app.config import Settings
from app.services import fairness as fx
from app.services.embeddings import HashEmbedder
from tests.conftest import RESUME, run_scoring

PROFILE = {"name": "Jane Doe", "education": [{"degree": "B.Tech", "institution": "IIT Delhi", "level": 1, "year": "2017"}]}
TEXT = """Jane Doe
jane.doe@example.com
+91 98765 43210
https://linkedin.com/in/janedoe
Bangalore 560001

SUMMARY
She is a backend engineer. Her work is great and he praised her.

EDUCATION
B.Tech in Computer Science, IIT Delhi, 2013 - 2017
Stanford University, 2018

SKILLS
Python, SQL
"""


def test_blind_text_removes_identifying_details():
    b = fx.blind_text(TEXT, PROFILE)
    for gone in ("Jane", "Doe", "jane.doe@example.com", "98765", "linkedin", "560001", "IIT Delhi", "Stanford", "2013", "2017", "2018"):
        assert gone not in b, gone
    low = b.lower()
    assert " she " not in low and " her " not in low and " he " not in low
    assert "they" in low and "their" in low
    assert "Python, SQL" in b and "backend engineer" in b  # job-relevant content survives


def test_blind_keeps_non_education_years():
    t = "EXPERIENCE\nDev   Jan 2018 - Dec 2020\n\nEDUCATION\nBSc 2012 - 2016\n"
    b = fx.blind_text(t, {})
    assert "2018" in b and "2020" in b and "2012" not in b


def test_swap_variant_changes_name_and_pronouns():
    t = fx.swap_variant("Jane Doe. She said her team trusts him.", {"name": "Jane Doe"}, "male", 0)
    assert "Jane" not in t and t.startswith("James Doe") and "He said his team trusts him" in t
    f = fx.swap_variant("Jane Doe. He said his team.", {"name": "Jane Doe"}, "female", 1)
    assert f.startswith("Patricia Doe") and "She said her team" in f


def test_impact_ratio_exact_numbers():
    s = Settings()
    finals = {i: 1.0 - i / 100 for i in range(1, 11)}          # candidate 1 is best
    groups = {i: ("A" if i in (1, 2, 3, 4, 5, 9) else "B") for i in range(1, 11)}
    r = fx.impact_audit(finals, groups, 5, s)                    # top 5 = ids 1..5, all group A
    assert r["groups"]["A"]["rate"] == 5 / 6 and r["groups"]["B"]["rate"] == 0.0
    assert r["groups"]["B"]["impact_ratio"] == 0.0 and r["groups"]["B"]["flagged"] is True
    assert r["groups"]["A"]["impact_ratio"] == 1.0 and r["flagged_groups"] == ["B"]
    assert abs(r["demographic_parity_difference"] - 5 / 6) < 1e-9


def test_impact_ratio_not_flagged_when_balanced():
    finals = {i: 1.0 - i / 100 for i in range(1, 9)}
    groups = {i: ("A" if i % 2 else "B") for i in range(1, 9)}
    r = fx.impact_audit(finals, groups, 4, Settings())
    assert r["flagged_groups"] == [] and r["groups"]["A"]["impact_ratio"] == 1.0


def test_weat_returns_valid_statistics_and_is_seeded():
    s = Settings(weat_permutations=500)
    a = fx.weat_probe(HashEmbedder(), "gender", s)
    b = fx.weat_probe(HashEmbedder(), "gender", s)
    assert a == b and 0 <= a["p_value"] <= 1 and -2.5 <= a["effect_size"] <= 2.5 and a["limits"]
    assert fx.weat_probe(HashEmbedder(), "origin", s)["group_y"] == "Indian first names"


def test_weat_identical_groups_has_zero_effect():
    class Same(HashEmbedder):
        def encode_docs(self, texts):
            return super().encode_docs(["token"] * len(texts)) if len(texts) == 8 else super().encode_docs(texts)
    r = fx.weat_probe(Same(), "gender", Settings(weat_permutations=200))
    assert abs(r["effect_size"]) < 1e-6


def test_audit_endpoints_and_history(pipeline):
    jid = pipeline.job_id
    assert pipeline.post("/jobs/%d/audit/blind" % jid).status_code == 409  # not scored
    run_scoring(pipeline)

    blind = pipeline.post("/jobs/%d/audit/blind" % jid).json()
    assert len(blind["candidates"]) == 3 and "avg_abs_change" in blind and blind["limits"]
    assert all(set(c) >= {"normal", "blind", "change", "rank_normal", "rank_blind"} for c in blind["candidates"])

    cf = pipeline.post("/jobs/%d/audit/counterfactual" % jid).json()
    assert cf["threshold_points"] == 2.0 and len(cf["candidates"]) == 3
    assert all(abs(c["max_abs_change"]) < 2.0 and not c["flagged"] for c in cf["candidates"])  # names/pronouns do not move lexical scores

    groups = {str(cid): ("G1" if i % 2 else "G2") for i, cid in enumerate(pipeline.cands.values())}
    # F1: labels must be consented or marked as a demo; they are never made up silently
    assert pipeline.post("/jobs/%d/audit/impact" % jid, json={"groups": groups, "top_n": 1}).status_code == 400
    imp = pipeline.post("/jobs/%d/audit/impact" % jid, json={"groups": groups, "top_n": 1, "consent": True}).json()
    assert set(imp["groups"]) == {"G1", "G2"} and imp["top_n"] == 1 and imp["labels_source"] == "consented"
    assert imp["small_groups"] and "rate_ci_low" in imp["groups"]["G1"]  # tiny groups are flagged with intervals
    demo = pipeline.post("/jobs/%d/audit/impact" % jid, json={"groups": groups, "top_n": 1, "demo": True}).json()
    assert demo["labels_source"] == "demo" and demo["warning"].startswith("DEMO")
    assert pipeline.post("/jobs/%d/audit/impact" % jid, json={"groups": {str(k): "same" for k in pipeline.cands.values()}, "top_n": 1, "consent": True}).status_code == 400

    weat = pipeline.post("/jobs/%d/audit/weat" % jid, json={"groups": "gender"}).json()
    assert 0 <= weat["p_value"] <= 1

    hist = pipeline.get("/jobs/%d/audit/history" % jid).json()
    assert [h["kind"] for h in hist] == ["blind", "counterfactual", "impact", "impact", "weat"]
    assert all(h["headline"] is not None for h in hist[:2]) and hist[0]["audit_id"] < hist[1]["audit_id"]


def test_audits_do_not_change_stored_scores(pipeline):
    run_scoring(pipeline)
    before = pipeline.get("/jobs/%d/matrix" % pipeline.job_id).json()
    pipeline.post("/jobs/%d/audit/blind" % pipeline.job_id)
    pipeline.post("/jobs/%d/audit/counterfactual" % pipeline.job_id)
    assert pipeline.get("/jobs/%d/matrix" % pipeline.job_id).json() == before
