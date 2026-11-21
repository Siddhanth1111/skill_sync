"""The v2 scoring pipeline through the API and the core: evidence-first scores, blind default, trace, versions,
hub limit, unverifiable status, weak-evidence cap, units migration, per-page OCR, columns, DOCX text boxes."""
import fitz
import numpy as np
import pytest

from app.config import Settings
from app.db import Candidate, Chunk, RerankCache, Score
from app.services.embeddings import HashEmbedder
from app.services.parsing import OcrResult, extract_pdf, extract_docx, normalize_text
from app.services.rerank import CachedReranker, LexicalReranker
from app.services.retrieval import ChunkView
from app.services.scoring import ReqView, candidate_total, chunk_views, embed_queries, score_candidate
from app.services.verify import LexicalNLI
from tests.conftest import JD, RESUME, WEAK_RESUME, DownLLM, make_docx, make_pdf, run_scoring

S = Settings(model_backend="light")


class Models:
    embedder, reranker, nli = HashEmbedder(), LexicalReranker(), LexicalNLI()


def req(id_, text, kind="hard_skill", skills=None, importance="must", weight=3.0, **meta):
    return ReqView(id_, id_, text, {"education": "education", "experience": "experience"}.get(kind, "skill"),
                   importance, weight, {"kind": kind, "skills": skills or [], **meta})


def views_for(texts_sections):
    e = HashEmbedder()
    texts = [t for t, _, _ in texts_sections]
    vecs = e.encode_docs(texts)
    return [ChunkView(i, i, sec, t, v, ctx) for i, ((t, sec, ctx), v) in enumerate(zip(texts_sections, vecs))]


# ---- API level ---------------------------------------------------------------------------------------

def test_b1_unscored_kinds_are_listed_with_weight_zero_and_never_scored(pipeline):
    reqs = pipeline.get("/jobs/%d" % pipeline.job_id).json()["requirements"]
    assert all(r["meta"]["kind"] for r in reqs) and all(r["meta"]["query"] for r in reqs)
    run_scoring(pipeline)
    m = pipeline.get("/jobs/%d/matrix" % pipeline.job_id).json()
    scored_ids = {int(k) for c in m["candidates"] for k in c["scores"]}
    for r in m["requirements"]:
        assert (r["id"] in scored_ids) == (r["meta"]["kind"] in ("hard_skill", "experience", "education")), r
        if r["meta"]["kind"] in ("soft_skill", "duty"):
            assert r["weight"] == 0


def test_every_score_carries_version_trace_and_a_verified_sentence(pipeline):
    run_scoring(pipeline)
    with pipeline.app.state.session_factory() as db:
        rows = db.query(Score).all()
        assert rows and all(r.pipeline_version == "v2" and r.trace and r.trace["retrieved"] for r in rows)
        assert all(r.trace["version"] == "v2" and r.trace["query"] for r in rows)
        shown = [r for r in rows if r.quote]
        assert shown and all(r.verified and r.sentence and " ".join(r.sentence.split()) in " ".join(r.quote.split()) for r in shown)
        cand = db.get(Candidate, pipeline.cands["strong.pdf"])
        text = cand.scoring_text
        assert all(" ".join(r.quote.split()) in " ".join(text.split()) for r in rows if r.quote and r.candidate_id == cand.id)


def test_f2_scoring_text_is_blind_by_default_but_the_original_is_kept(pipeline):
    with pipeline.app.state.session_factory() as db:
        cand = db.get(Candidate, pipeline.cands["strong.pdf"])
        assert "Jane" in cand.raw_text and "jane.doe@example.com" in cand.raw_text
        assert "Jane" not in cand.scoring_text and "@" not in cand.scoring_text and "IIT" not in cand.scoring_text
        chunk_text = " ".join(c.text + " " + (c.context or "") for c in db.query(Chunk).filter_by(candidate_id=cand.id))
        assert "jane" not in chunk_text.lower() and "98765" not in chunk_text
    run_scoring(pipeline)
    expl = pipeline.get("/candidates/%d/explanation" % pipeline.cands["strong.pdf"]).json()
    assert expl["musts"] >= 1 and "unscored" in expl and all("trace" in r for r in expl["requirements"])


def test_explanation_lists_unscored_requirements_separately_and_gaps_skip_them(pipeline):
    run_scoring(pipeline)
    expl = pipeline.get("/candidates/%d/explanation" % pipeline.cands["weak.pdf"]).json()
    gap_ids = {g["requirement_id"] for g in expl["gaps"]}
    unscored_ids = {u["id"] for u in expl["unscored"]}
    assert not gap_ids & unscored_ids


def test_patching_kind_and_importance_resets_weights_and_marks_scores_stale(pipeline):
    job = pipeline.get("/jobs/%d" % pipeline.job_id).json()
    skill = next(r for r in job["requirements"] if r["meta"]["kind"] == "hard_skill")
    run_scoring(pipeline)
    r = pipeline.patch("/jobs/%d/requirements" % pipeline.job_id, json=[{"id": skill["id"], "kind": "soft_skill"}]).json()
    p = next(x for x in r["requirements"] if x["id"] == skill["id"])
    assert p["weight"] == 0 and p["meta"]["kind"] == "soft_skill" and r["scores_stale"] is True
    r = pipeline.patch("/jobs/%d/requirements" % pipeline.job_id, json=[{"id": skill["id"], "kind": "hard_skill", "importance": "nice"}]).json()
    p = next(x for x in r["requirements"] if x["id"] == skill["id"])
    assert p["weight"] == 1 and p["meta"]["weight_source"] == "default"
    r = pipeline.patch("/jobs/%d/requirements" % pipeline.job_id, json=[{"id": skill["id"], "weight": 5}]).json()
    assert next(x for x in r["requirements"] if x["id"] == skill["id"])["meta"]["weight_source"] == "manual"


def test_old_candidates_are_rebuilt_into_units_when_scored(pipeline):
    """Phase 2 re-embed migration: a candidate ingested by the old pipeline gets context units on first scoring."""
    cid = pipeline.cands["strong.pdf"]
    with pipeline.app.state.session_factory() as db:
        cand = db.get(Candidate, cid)
        cand.chunk_version, cand.scoring_text = 1, None
        cand.chunks = [Chunk(idx=0, section="header", text="one big old chunk")]
        db.commit()
    run_scoring(pipeline)
    with pipeline.app.state.session_factory() as db:
        cand = db.get(Candidate, cid)
        assert cand.chunk_version == 2 and cand.scoring_text and len(cand.chunks) > 1
        assert any(c.context for c in cand.chunks)


def test_rerank_cache_key_includes_the_pipeline_version(settings):
    from app.db import make_session_factory
    sf = make_session_factory(settings.database_url)
    with sf() as db:
        CachedReranker(LexicalReranker(), db, "v1").score([("python", "python dev")])
        CachedReranker(LexicalReranker(), db, "v2").score([("python", "python dev")])
        assert sorted(r.model for r in db.query(RerankCache)) == ["light-lexical|v1", "light-lexical|v2"]


# ---- core level --------------------------------------------------------------------------------------

def test_d1_profile_skill_list_alone_no_longer_makes_a_requirement_met():
    chunks = views_for([("Cooked pasta for the team", "experience", "Cook, Cafe"), ("Updated web pages", "experience", "Intern")])
    r = req(1, "Python", skills=["python"], query="Python")
    rows = score_candidate([r], embed_queries([r], Models), chunks, "Cooked pasta for the team\nUpdated web pages",
                           {"skills": ["python"]}, Models, S)
    assert rows[0].status != "met" and rows[0].final_score <= S.skill_absent_cap


def test_c5_one_unit_cannot_back_more_than_three_requirements_when_alternatives_exist():
    units = views_for([("Built Python SQL Docker Kafka Spark AWS pipelines", "experience", "Engineer"),
                       ("Python scripts for reports", "experience", "Engineer"),
                       ("SQL reporting", "experience", "Engineer"),
                       ("Docker images", "experience", "Engineer"),
                       ("Kafka consumers", "experience", "Engineer"),
                       ("Spark jobs", "experience", "Engineer")])
    names = ["python", "sql", "docker", "kafka", "spark"]
    reqs = [req(i + 1, n, skills=[n], query=n) for i, n in enumerate(names)]
    text = "\n".join(u.text for u in units)
    rows = score_candidate(reqs, embed_queries(reqs, Models), units, text, {}, Models, S)
    reuse = {}
    for row in rows:
        reuse[row.chunk_id] = reuse.get(row.chunk_id, 0) + 1
    assert max(reuse.values()) <= S.hub_max_reuse and not any(r.hub for r in rows)


def test_c5_hub_is_flagged_when_there_is_no_alternative():
    units = views_for([("Built Python SQL Docker Kafka Spark AWS pipelines", "experience", "Engineer")])
    names = ["python", "sql", "docker", "kafka", "spark"]
    reqs = [req(i + 1, n, skills=[n], query=n) for i, n in enumerate(names)]
    rows = score_candidate(reqs, embed_queries(reqs, Models), units, units[0].text, {}, Models, S)
    assert all(r.hub for r in rows) and rows[0].trace["reuse"] == 5


def test_d8_unreadable_resume_gives_not_verifiable_instead_of_not_met():
    units = views_for([("Built Python services", "experience", "Developer")])
    reqs = [req(1, "Python", skills=["python"], query="Python"), req(2, "Kafka", skills=["kafka"], query="Kafka")]
    q = embed_queries(reqs, Models)
    clear = score_candidate(reqs, q, units, units[0].text, {}, Models, S, None, low_confidence=False)
    poor = score_candidate(reqs, q, units, units[0].text, {}, Models, S, None, low_confidence=True)
    assert [r.status for r in clear] == ["met", "not_met"] and [r.status for r in poor] == ["met", "not_verifiable"]
    assert poor[1].final_score == clear[1].final_score
    assert candidate_total(poor, reqs, S) > candidate_total(clear, reqs, S)  # E1: no must penalty when unreadable


def test_d5_weak_evidence_caps_the_requirement_at_partial():
    class Strict(LexicalNLI):
        def entailment(self, pairs):
            return [0.0 for _ in pairs]

    class M(Models):
        nli = Strict()

    units = views_for([("Delivered a measurable data platform", "experience", "Engineer")])
    r = req(1, "Zorblax platform delivery", skills=[], query="data platform delivery")
    r.meta["skills"] = []
    rr = LexicalReranker()
    assert rr.score([("data platform delivery", units[0].embed_text)])[0] >= S.met_threshold  # lexically strong
    row = score_candidate([r], embed_queries([r], Models), units, units[0].text, {}, M, S)[0]
    assert row.final_score < S.met_threshold and row.status == "partial" and row.trace["weak_evidence_cap"]


def test_d6_years_with_the_skill_decide_experience_requirements():
    units = views_for([("Used Python daily", "experience", "Developer, Acme Jan 2023 - Dec 2023")])
    r = req(1, "4 years of Python", kind="experience", skills=["python"], query="Python", years_min=4, years_required=4)
    prof = {"years_experience": 10, "skill_years": {"python": 1.0}}
    row = score_candidate([r], embed_queries([r], Models), units, units[0].text, prof, Models, S)[0]
    assert abs(row.final_score - 0.25) < 1e-9 and row.trace["years_with_skill"] == {"python": 1.0}


# ---- extraction level --------------------------------------------------------------------------------

def _two_page_pdf(path, native, blank_second_page=True):
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_textbox(fitz.Rect(40, 40, 560, 800), native, fontsize=10)
    doc.new_page()  # a page with no text layer, as in a scanned page
    doc.save(str(path))
    doc.close()


def test_a1_ocr_decision_is_per_page_and_the_texts_are_merged(tmp_path):
    p = tmp_path / "mixed.pdf"
    _two_page_pdf(p, RESUME)
    s = Settings(model_backend="light", ocr_min_chars=50)
    seen = []

    def fake_ocr(page, dpi):
        seen.append(page.number)
        return OcrResult("PROJECTS\nBuilt a Rust compiler", 82.0)

    doc = extract_pdf(str(p), s, fake_ocr)
    assert seen == [1]  # only the empty second page is OCRed
    assert "Kafka" in doc.text and "Rust compiler" in doc.text
    assert doc.ocr_used and doc.ocr_pages == 1 and doc.mean_confidence == 82.0


def test_a2_ocr_confidence_reaches_the_parse_confidence_flag():
    from app.services.parsing import ExtractedDocument, parse_confidence
    d = ExtractedDocument(text=RESUME, ocr_used=True, pages=1, char_count=len(RESUME), ocr_pages=1,
                          page_confidence=[41.0], mean_confidence=41.0)
    pc = parse_confidence(d, S)
    assert pc["low"] and pc["low_ocr"] and pc["ocr_confidence"] == 41.0 and any("confidence" in r for r in pc["reasons"])
    good = parse_confidence(ExtractedDocument(text=RESUME, ocr_used=True, pages=1, char_count=len(RESUME), ocr_pages=1,
                                              page_confidence=[90.0], mean_confidence=90.0), S)
    assert not good["low_ocr"]


def test_a3_two_columns_are_read_one_after_the_other(tmp_path):
    p = tmp_path / "cols.pdf"
    doc = fitz.open()
    page = doc.new_page()
    left = ["LEFT one", "LEFT two", "LEFT three"]
    right = ["RIGHT one", "RIGHT two", "RIGHT three"]
    for i, (a, b) in enumerate(zip(left, right)):
        page.insert_textbox(fitz.Rect(40, 60 + i * 80, 280, 120 + i * 80), a + "\nmore " + a.lower(), fontsize=10)
        page.insert_textbox(fitz.Rect(320, 60 + i * 80, 560, 120 + i * 80), b + "\nmore " + b.lower(), fontsize=10)
    doc.save(str(p))
    doc.close()
    text = extract_pdf(str(p), Settings(model_backend="light", ocr_min_chars=5), lambda pg, d: "")
    order = [text.text.index(w) for w in ("LEFT one", "LEFT two", "LEFT three", "RIGHT one", "RIGHT two", "RIGHT three")]
    assert order == sorted(order)


def test_a4_docx_text_boxes_headers_and_footers_are_read(tmp_path):
    import docx
    from docx.oxml import parse_xml
    d = docx.Document()
    d.add_paragraph("EXPERIENCE")
    d.add_paragraph("Built Python services")
    d.sections[0].header.paragraphs[0].text = "Jordan Lee jordan@example.com"
    d.sections[0].footer.paragraphs[0].text = "Page footer note"
    xml = ('<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:pict><w:txbxContent>'
           '<w:p><w:r><w:t>Skills: Kafka, Airflow in a text box</w:t></w:r></w:p></w:txbxContent></w:pict></w:r>')
    d.paragraphs[1]._p.append(parse_xml(xml))
    path = tmp_path / "r.docx"
    d.save(str(path))
    text = extract_docx(str(path)).text
    assert "Kafka, Airflow in a text box" in text and "jordan@example.com" in text and "Page footer note" in text


def test_a5_text_is_normalised_without_losing_meaning():
    raw = "Opti­mised ﬁnal data pipelines\n  Built  an optimi-\nzation tool\n\n\n\nDone"
    out = normalize_text(raw)
    assert out == "Optimised final data pipelines\n• Built an optimization tool\n\nDone"


def test_blinding_leaves_no_stray_punctuation_and_removes_known_school_abbreviations():
    from app.services.blind import blind_text
    out = blind_text("EDUCATION\nB.Tech in Computer Science, IIT Delhi, 2017\nMBA, XLRI (2019)\n", {})
    assert "IIT" not in out and "2017" not in out
    assert "B.Tech in Computer Science" in out and ", ," not in out and not out.splitlines()[1].rstrip().endswith(",")


def test_years_requirement_is_shown_with_a_role_entry_not_the_summary():
    units = views_for([("Backend engineer who builds data pipelines.", "summary", "Summary"),
                       ("Built services for a bank", "experience", "Developer, Acme Jan 2021 - Dec 2023")])
    r = req(1, "3+ years of backend experience", kind="experience", skills=[], query="backend", years_min=3, years_required=3)
    row = score_candidate([r], embed_queries([r], Models), units, "\n".join(u.text for u in units),
                          {"years_experience": 3.0}, Models, S)[0]
    assert row.section == "experience" and row.final_score == 1.0


def test_wrong_evidence_button_stores_a_verdict_without_resume_text_and_exports_it(pipeline, tmp_path, monkeypatch):
    run_scoring(pipeline)
    cid = pipeline.cands["weak.pdf"]
    m = pipeline.get("/jobs/%d/matrix" % pipeline.job_id).json()
    rid = int(next(iter(next(c for c in m["candidates"] if c["id"] == cid)["scores"])))
    r = pipeline.post("/candidates/%d/evidence-feedback" % cid, json={"requirement_id": rid, "judgement": "wrong_evidence", "grade": 0})
    assert r.status_code == 201 and r.json()["judgement"] == "wrong_evidence"
    pipeline.post("/candidates/%d/evidence-feedback" % cid, json={"requirement_id": rid, "judgement": "correct", "grade": 2})  # replaces it
    assert pipeline.get("/candidates/%d/evidence-feedback" % cid).json() == {str(rid): {"judgement": "correct", "grade": 2}}
    assert pipeline.post("/candidates/%d/evidence-feedback" % cid, json={"requirement_id": 99999, "judgement": "correct"}).status_code == 404
    assert pipeline.post("/candidates/%d/evidence-feedback" % cid, json={"requirement_id": rid, "judgement": "nonsense"}).status_code == 422
    from app.db import GoldLabel
    with pipeline.app.state.session_factory() as db:
        row = db.query(GoldLabel).one()
        assert (row.judgement, row.grade, row.pipeline_version) == ("correct", 2, "v2") and row.model_status
    # another recruiter cannot label this candidate's evidence
    pipeline.use("recruiter", 2)
    assert pipeline.post("/candidates/%d/evidence-feedback" % cid, json={"requirement_id": rid, "judgement": "correct"}).status_code == 404
    # operator export joins the verdict to the requirement and the supporting sentence
    import json
    from app import cli
    monkeypatch.setattr(cli, "get_settings", lambda: pipeline.app.state.settings)
    out = tmp_path / "gold.jsonl"
    assert cli.export_gold(str(out)) == 1
    line = json.loads(out.read_text().splitlines()[0])
    assert line["judgement"] == "correct" and line["requirement"] and "pipeline_version" in line
