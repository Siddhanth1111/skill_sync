"""Second QA round (SQL Developer review): minimum years, wrapped lines, soft skills, listed-only skills, combined
requirements, warning versus verdict, generic evidence lines."""
from app.config import Settings
from app.services.chunking import chunk_resume
from app.services.embeddings import HashEmbedder
from app.services.extraction import weight_for
from app.services.matrix import score_dict
from app.services.requirements import finalize_requirement
from app.services.retrieval import ChunkView
from app.services.scoring import ReqView, embed_queries, score_candidate, score_experience
from app.services.verify import LexicalNLI
from app.services.rerank import LexicalReranker
from app.schemas import JDRequirement

S = Settings(model_backend="light")


class Models:
    embedder, reranker, nli = HashEmbedder(), LexicalReranker(), LexicalNLI()


def req(id_, text, kind="hard_skill", skills=None, importance="must", weight=3.0, **meta):
    return ReqView(id_, id_, text, {"education": "education", "experience": "experience"}.get(kind, "skill"),
                   importance, weight, {"kind": kind, "skills": skills or [], **meta})


def views(items):
    e = HashEmbedder()
    vecs = e.encode_docs([t for t, _, _ in items])
    return [ChunkView(i, i, sec, t, v, ctx) for i, ((t, sec, ctx), v) in enumerate(zip(items, vecs))]


def run(reqs, units, profile=None, models=Models):
    return score_candidate(reqs, embed_queries(reqs, Models), units, "\n".join(u.text for u in units), profile or {}, models, S)


# 1 -----------------------------------------------------------------------------------------------------
def test_1_two_years_does_not_meet_a_three_year_minimum():
    r = req(1, "3 to 5 years of SQL development", kind="experience", skills=["sql"], years_min=3, years_required=3, years_max=5)
    two, t = score_experience(r, {"years_experience": 2, "skill_years": {"sql": 2.0}}, 1, S)
    assert two < S.met_threshold and S.partial_threshold <= two and t["below_minimum"]
    three, t = score_experience(r, {"years_experience": 3, "skill_years": {"sql": 3.0}}, 1, S)
    assert three == 1.0 and "below_minimum" not in t
    total_only = req(2, "3+ years of backend experience", kind="experience", years_min=3, years_required=3)
    assert score_experience(total_only, {"years_experience": 2.9}, 0, S)[0] < S.met_threshold


def test_1_a_musts_met_count_stays_honest_for_the_two_year_candidate():
    units = views([("Wrote SQL reports for two years", "experience", "Developer, Acme Jan 2023 - Dec 2024")])
    r = req(1, "3 to 5 years of SQL", kind="experience", skills=["sql"], years_min=3, years_required=3)
    row = run([r], units, {"years_experience": 2, "skill_years": {"sql": 2.0}})[0]
    assert row.status == "partial"


# 2 -----------------------------------------------------------------------------------------------------
def test_2_wrapped_lines_become_whole_sentences():
    text = """EDUCATION
B.Tech -
Computer Science, 2017
SKILLS
SQL, PL/SQL,
Oracle and MySQL
EXPERIENCE
Developer, Acme  Jan 2020 - Dec 2022
- Designed stored procedures and
triggers for the billing system
- Tuned queries
"""
    texts = [u.text for u in chunk_resume(text)]
    assert "B.Tech - Computer Science, 2017" in texts
    assert "SQL, PL/SQL, Oracle and MySQL" in texts
    assert "Designed stored procedures and triggers for the billing system" in texts and "Tuned queries" in texts
    assert not any(t in ("B.Tech -", "Computer Science, 2017") for t in texts)


# 3 -----------------------------------------------------------------------------------------------------
def test_3_abstract_traits_are_soft_skills_and_carry_no_weight():
    for text in ("Strong debugging skills", "Communication and teamwork", "Good analytical skills", "Excellent interpersonal skills"):
        r = finalize_requirement(JDRequirement(text=text, type="skill", importance="must", kind="hard_skill"))
        assert r.kind == "soft_skill", text
        assert weight_for(r.kind, r.importance, S) == 0
    for text in ("Strong SQL skills", "Strong knowledge of RDBMS", "Experience with stored procedures"):
        assert finalize_requirement(JDRequirement(text=text, type="skill", importance="must")).kind == "hard_skill", text


# 4 -----------------------------------------------------------------------------------------------------
def test_4_a_skill_only_listed_is_partial_and_work_evidence_is_met():
    r = req(1, "Oracle", skills=["oracle"])
    listed = run([r], views([("SQL, Oracle, MySQL", "skills", "Skills")]))[0]
    worked = run([r], views([("Administered Oracle databases for billing", "experience", "DBA, Acme")]))[0]
    assert listed.status == "partial" and listed.final_score < S.met_threshold
    assert worked.status == "met" and worked.final_score > listed.final_score


def test_4_listed_plus_demonstrated_counts_as_demonstrated():
    r = req(1, "Oracle", skills=["oracle"])
    both = run([r], views([("SQL, Oracle", "skills", "Skills"), ("Administered Oracle databases", "experience", "DBA, Acme")]))[0]
    assert both.status == "met" and both.section == "experience"


# 5 -----------------------------------------------------------------------------------------------------
def test_5_combined_requirement_shows_which_parts_were_found_and_which_were_missing():
    r = finalize_requirement(JDRequirement(text="Experience writing stored procedures, functions, views, and triggers",
                                           type="skill", importance="must", kind="hard_skill"))
    assert r.skills == ["stored procedures", "functions", "views", "triggers"]
    rv = req(1, r.text, skills=r.skills, query="stored procedures, functions, views, and triggers", skills_mode=r.skills_mode)
    units = views([("Wrote stored procedures and database views for reporting", "experience", "Developer, Acme"),
                   ("Created triggers to audit changes", "experience", "Developer, Acme")])
    row = run([rv], units)[0]
    parts = row.trace["parts"]
    assert parts["stored procedures"]["status"] == "found" and parts["views"]["status"] == "found"  # 'view' and 'views'
    assert parts["triggers"]["status"] == "found" and parts["functions"]["status"] == "missing"
    assert parts["triggers"]["text"] and "audit" in parts["triggers"]["text"]
    assert S.partial_threshold <= row.final_score < S.met_threshold + 0.3 and row.status in ("partial", "met")
    assert row.final_score < S.skill_present_score  # one missing part pulls the average down


# 6 -----------------------------------------------------------------------------------------------------
def test_6_a_met_requirement_never_carries_a_weak_evidence_warning():
    class Strict(LexicalNLI):
        def entailment(self, pairs):
            return [0.0 for _ in pairs]

    class M(Models):
        nli = Strict()

    # the ontology finds Oracle in the sentence: the model's doubt is overruled, so no warning and status stays met
    direct = run([req(1, "Oracle", skills=["oracle"])], views([("Administered Oracle databases", "experience", "DBA")]), models=M)[0]
    assert direct.status == "met" and direct.trace["weak"] is False
    # no skill to vouch for the text and a doubting model: weak, and weak can never be met
    vague = run([req(2, "Zorblax platform delivery", skills=[], query="data platform delivery")],
                views([("Delivered a measurable data platform", "experience", "Engineer")]), models=M)[0]
    assert vague.trace["weak"] is True and vague.status != "met"


def test_6_the_api_flag_follows_the_same_rule():
    from app.db import Score
    s = Score(final_score=0.85, rerank_score=0.1, status="met", verified=True, entailment=0.0, trace={"weak": False})
    assert score_dict(s, S)["weak"] is False
    s.trace = {"weak": True}
    assert score_dict(s, S)["weak"] is True


# 7 -----------------------------------------------------------------------------------------------------
def test_7_a_summary_line_is_not_cited_for_several_requirements():
    units = views([("Backend developer with SQL and Python and Docker experience", "summary", "Summary"),
                   ("Wrote SQL reports", "experience", "Developer, Acme"),
                   ("Built Python scripts", "experience", "Developer, Acme"),
                   ("Containerised services with Docker", "experience", "Developer, Acme")])
    reqs = [req(i + 1, n, skills=[n.lower()], query=n) for i, n in enumerate(["SQL", "Python", "Docker"])]
    rows = run(reqs, units)
    assert [r.section for r in rows] == ["experience"] * 3  # work text beats the summary even though it also matches
    assert not any(r.hub for r in rows)


def test_7_a_generic_line_backs_at_most_one_requirement_and_unsupported_rows_show_no_quote():
    units = views([("Backend developer with SQL and Python and Docker experience", "summary", "Summary")])
    reqs = [req(i + 1, n, skills=[n.lower()], query=n) for i, n in enumerate(["SQL", "Python", "Docker"])]
    rows = run(reqs, units)
    assert sum(1 for r in rows if r.quote) == 3 and all(r.hub for r in rows)  # one summary line backs all three: flagged
    nothing = run([req(9, "Kafka", skills=["kafka"])], units)[0]
    assert nothing.status == "not_met" and nothing.quote is None and nothing.sentence is None and not nothing.verified
