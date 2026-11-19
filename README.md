# SkillSync: pipeline stages 1 to 15 (backend + UI)

SkillSync is an auditable candidate-ranking assistant. This repository implements **stages 1 to 15** of *SkillSync: Final
Pipeline and Build Specification* (the PDF in this folder): a FastAPI backend and a React UI with no login and no roles
(the Recruiter and Student tabs are only two views). Stage 16 (analytics), authentication and the evaluation harness
(gold set, five-system benchmark, MLflow) are not built yet.

Hard rules from the spec that the code follows:
- A human makes every hiring decision. Nothing approves or rejects anyone.
- Every quotation shown is checked to be an exact substring of the extracted resume. If it cannot be verified it is not shown.
- The LLM only extracts structure and paraphrases verified quotes. **It never produces a score.**
- Protected characteristics are never inferred or used as features.
- Model names, thresholds and weights live in one config file (`backend/app/config.py`).
- Per-requirement scores are stored, so changing weights needs no new model calls.

| Stage | What it does | Where |
|---|---|---|
| 1. Upload and validation | up to 200 PDF/DOCX, type/size/content checks, 3 workers, per-file status | `routers/resumes.py`, `services/ingest.py` |
| 2. Text extraction | PyMuPDF / python-docx, OCR fallback under 200 characters, parse-confidence flag | `services/parsing.py` |
| 3. Resume structuring | Llama 3.1 8B JSON profile, retries, sanity checks, rule fallback | `services/extraction.py`, `fallback.py`, `llm.py` |
| 4. Job understanding | typed, weighted, editable requirements; rule fallback | `routers/jobs.py`, `services/extraction.py` |
| 5. Sectioning and chunking | heading-based sections, segments of at most 500 characters | `services/chunking.py` |
| 6. Embedding and indexing | bge-base by default (MiniLM, bge-m3 via config), normalised vectors stored per chunk | `services/embeddings.py` |
| 7. Retrieval | top-3 nearest segments within the candidate, cosine distance | `services/retrieval.py` |
| 8. Reranking | cross-encoder, sigmoid to 0..1, cached by requirement/segment/model | `services/rerank.py` |
| 9. Evidence verification | exact-substring check, then DeBERTa-MNLI entailment flag (weak evidence) | `services/verify.py` |
| 10. Requirement scoring | per-type formulas, status met/partial/not met, stored matrix | `services/scoring.py` |
| 11. Ranking and re-weighting | weighted mean, 0.9 penalty per unmet must, same formula in browser | `services/ranking.py`, `frontend/src/lib/rank.js` |
| 12. Explanations and gaps | unmet first, gaps by points gained, narrative limited to verified quotes | `services/explain.py` |
| 13. Learning from feedback | thumbs, logistic regression on 7 features, CV AUC / Brier / ECE, SHAP | `services/feedback.py` |
| 14. Fairness audit | blind, counterfactual, adverse impact + Fairlearn, WEAT, monitoring | `services/fairness.py` |
| 15. Student mode | one resume vs many jobs, roadmap, what-if simulator | `services/student.py` |

## Quick start

Prerequisites: Python 3.9+, Node 18+, [Ollama](https://ollama.com) with `ollama pull llama3.1:8b`. Optional: Tesseract
(`brew install tesseract`) for scanned PDFs.

```bash
# terminal 1: backend
cd backend
python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements.txt
pytest                                            # 95 tests, no models or Ollama needed
uvicorn app.main:create_app --factory --reload    # http://localhost:8000/docs

# terminal 2: frontend
cd frontend
npm install
npm run dev                                       # http://localhost:5173
```

**Two modes for the ML models** (`SKILLSYNC_MODEL_BACKEND`):
- `real` (default): bge-base-en-v1.5 embeddings, bge-reranker-base, microsoft/deberta-base-mnli. About 2 GB downloaded
  from HuggingFace on first use, so the first scoring run is slow.
- `light`: small deterministic stand-ins (hashed word vectors, word-overlap reranker and entailment). No downloads, runs in
  seconds, good for trying the workflow and for tests. **Its scores say nothing about real model quality.**

```bash
SKILLSYNC_MODEL_BACKEND=light uvicorn app.main:create_app --factory --reload
```

Other settings (all `SKILLSYNC_*` env vars, see `backend/app/config.py` and `backend/.env.example`): database URL, Ollama
URL and model, upload limits, OCR threshold, embedding/reranker/NLI model names (swap for the ablation with no code
change), thresholds (0.6 / 0.3 / entailment / 0.9 penalty), minimum ratings, fairness thresholds.

Note: PDFs with under 200 characters of text are treated as scanned and need OCR (spec rule). If Tesseract is missing,
tiny test PDFs fail with a clear reason; set `SKILLSYNC_OCR_MIN_CHARS=50` to try short synthetic resumes.

## How to use it (workflow)

**Recruiter tab**
1. *New job*: paste a job description. Requirements appear (type, must/should/nice, weight).
2. *Requirements and resumes* tab: edit requirements, drop resumes, watch per-file status, click View to inspect a parsed
   resume (profile, parse-confidence warning, chunks).
3. *Ranking* tab: **Run scoring** (runs in the background with a progress count). Then:
   - weight panel: sliders and importance selectors **re-rank instantly in the browser** (no server call);
   - click a candidate to open the evidence drawer: each requirement with status, verified quotation and section (unmet
     first), weak-evidence warnings, gaps by points gained, and a short summary; 👍/👎 to rate;
   - *Save as default* stores the weights. Editing a requirement's wording marks scores stale until scoring is re-run.
4. *Fairness* tab: blind mode, counterfactual swap, adverse impact (synthetic group labels, top N), WEAT probe, and a trend
   chart of every past run.
5. *Learning* tab: rating counts, train the optional learned score (needs 10+ ratings, 3+ of each kind), CV AUC, Brier,
   ECE, learned score beside the rule score, SHAP drivers.

**Student tab**: upload one resume, paste job descriptions (kept separate from recruiter jobs), **Match** them (best first),
click a job for the roadmap (start here / next / later, points per step, running projected score, concrete action) and use
the what-if box to rescore a temporary copy with a project or skill added (nothing is saved).

## API

| Area | Endpoints |
|---|---|
| Jobs | `POST /jobs` (`mode`: recruiter or student), `GET /jobs?mode=`, `GET /jobs/{id}`, `PATCH /jobs/{id}/requirements` |
| Resumes | `POST /jobs/{id}/resumes` (multipart `files`), `GET /jobs/{id}/status`, `GET /candidates/{id}` |
| Scoring | `POST /jobs/{id}/score` (202, background), `GET /jobs/{id}/score/status`, `GET /jobs/{id}/matrix`, `GET /jobs/{id}/ranking` |
| Explanation | `GET /candidates/{id}/explanation` |
| Learning | `POST /candidates/{id}/feedback`, `POST /jobs/{id}/model/train`, `GET /jobs/{id}/model` |
| Fairness | `POST /jobs/{id}/audit/blind`, `/audit/counterfactual`, `/audit/impact`, `/audit/weat`, `GET /jobs/{id}/audit/history` |
| Student | `POST /student/resume`, `POST /student/match`, `GET /student/roadmap`, `POST /student/whatif` |
| Misc | `GET /health` |

Interactive docs: http://localhost:8000/docs.

## How it works

### Stages 1 to 5 (ingestion)
- **Upload:** each file is checked for extension, size (10 MB) and content signature; a job holds at most 200 resumes. A bad
  file becomes a `failed` row with a reason and never stops the batch. Valid files are written to a private temp folder under
  a generated name, parsed by 3 worker threads, and deleted afterwards.
- **Extraction:** PyMuPDF (DOCX: paragraphs and tables). Under 200 characters means scanned: pages are rendered at 200 dpi
  and read with Tesseract. A parse-confidence flag records OCR use, text size and sections found.
- **Structuring:** Llama 3.1 8B at temperature 0, output constrained to the Pydantic schema, up to 2 retries with the
  validation error fed back. Sanity checks drop an email, phone or skill that is not in the text. **Years of experience are
  computed by code** from role dates with overlaps merged. If the LLM is down or never validates, the rule extractor answers
  and the record says `source = rules`.
- **Job requirements:** same LLM with a `JDExtraction` schema; benefits and legal text ignored; **code assigns the weights**
  3/2/1 from importance; heading-and-bullet rules are the fallback.
- **Chunking:** headings label sections (experience, education, skills, projects, certifications, summary, achievements,
  header). Sections are packed by line into segments of at most 500 characters. Chunks are exact substrings of the text.

### Stages 6 to 9 (evidence)
- Chunks are embedded when a resume is parsed (documents) and requirements are embedded as queries (bge instruction prefix
  added only for bge English models). The model name is stored with each vector, so changing the embedding model in config
  re-embeds lazily on the next scoring run.
- For each requirement the 3 nearest chunks of that candidate are retrieved, reranked by the cross-encoder (sigmoid, cached in
  `rerank_cache` by requirement hash + segment hash + model), and the best becomes the evidence.
- **Verification:** the quote is the winning chunk. It must be an exact substring of the resume text (whitespace normalised),
  otherwise no evidence is stored for that requirement. DeBERTa-MNLI then scores whether the quote entails the requirement
  written as a statement; below the threshold the row is flagged **weak evidence**. The flag never changes the stored score.

### Stages 10 and 11 (score and rank)
- Skill: reranker score; if the requirement names taxonomy skills, all mentioned gives 0.85, none gives at most 0.45, and in
  between is interpolated by the share mentioned. Experience: years / years required, capped at 1. Education: level / level
  required, capped at 1. If a requirement states no years or level, the reranker score is used.
- Status: met at 0.6 or above, partial from 0.3, otherwise not met. Each cell (score, status, quote, section, entailment,
  verified) is one row of `scores`, the requirement-evidence matrix.
- Final score = weighted mean of requirement scores, times 0.9 for each **must** that is not met. Ties are broken by number
  of met musts, then by candidate id. `backend/app/services/ranking.py` and `frontend/src/lib/rank.js` are the same formula;
  `tests/test_rank_parity.py` runs both on random matrices (including threshold edge cases) and compares.

### Stage 12 (explanations)
Requirements are listed unmet first. A gap is `weight × (1 − score) / total weight`, in points of 100. The narrative comes
from the LLM using only verified quotes; afterwards every quoted string is checked against the resume and a fixed template
replaces the narrative if any check fails (or the LLM is down). The UI labels which one you are reading.

### Stage 13 (learning)
Ratings store seven features (overall score, mean score on must/should/nice, share met/partial/not met). With at least 10
ratings and 3 of each kind, a standardised logistic regression is fitted; the cross-validated AUC, Brier score and expected
calibration error are reported (AUC near 0.5 means no signal). The learned probability is shown beside the rule score and
never replaces or reorders it. SHAP for a linear model has a closed form (`coef × (x − mean) / scale`), implemented directly
instead of adding the `shap` package.

### Stage 14 (fairness)
- **Blind:** removes name, email/phone, links, postcodes, school names and education years, makes pronouns neutral, rescores,
  and reports average score change and how many candidates changed rank.
- **Counterfactual:** two variants per candidate (first name from a male-coded list with male pronouns, and a female-coded
  list with female pronouns), no gender is inferred; flags any change above 2 points of 100.
- **Adverse impact:** with synthetic group labels, selection = top N; each group's rate is divided by the highest group's
  rate and a ratio under 0.8 is flagged. Demographic parity difference comes from **Fairlearn**.
- **WEAT:** effect size and permutation p-value for two name groups against pleasant/unpleasant words in the embedding model.
- Every run is saved in `audit_runs` and charted over time. Every report states its limits (synthetic labels, and school,
  address and employment gaps are proxies these tests do not cover).

### Stage 15 (student mode)
A student resume is a candidate with no job. Matching scores it against each chosen job with the same stages 6 to 11 and lists
jobs best first. The roadmap lists unmet requirements as start here (must), next (should), later (nice), with points per step
and a running projected score. Suggested actions are drafted by the LLM but kept only if they share wording with the
requirement; otherwise a template is used. What-if appends the described project or skill (and any taxonomy skills it
mentions) to a temporary copy, rescores, and saves nothing.

## Database (`backend/app/db.py`)
Tables: `jobs`, `requirements`, `candidates`, `chunks` (with `embedding` JSON), `scores`, `score_runs`, `rerank_cache`,
`feedback`, `job_models`, `audit_runs`. Deleting a job cascades. Default is SQLite (`backend/skillsync.db`); an older database
gets the new columns added automatically at start-up (a small dev-time migration). Deviations from the spec's table list:
extra `status`, `error`, `raw_text` on candidates; `mode` and `scores_stale` on jobs; `user_id` is a nullable placeholder
until auth is built; embeddings are JSON lists searched with numpy, **not pgvector** (see limitations).

To look at the data: `sqlite3 -header -column backend/skillsync.db` (it contains resume text; it is git-ignored).

## Tests

`cd backend && pytest` runs 95 tests in about 20 seconds. The LLM is a scripted mock and the models use the `light` backend,
so no downloads are needed. They cover: dates, chunking, rule fallbacks, LLM retry/fallback/sanity checks, parsing and OCR
paths, scoring formulas, ranking formula and tie-breaks, **backend/browser ranking parity (runs the real `rank.js` with Node)**,
rerank cache, verified quotes being exact substrings, stale scores, failure reporting, narrative grounding (fabricated quote
replaced by template), learning (training gate, metrics, SHAP sums to the logit), fairness (blind, swaps, exact impact
ratios, WEAT statistics, audits leave stored scores untouched, history) and student mode (ordering, roadmap, what-if saves
nothing).

## What has and has not been verified

REAL_RESULTS_PLACEHOLDER

## Known limitations
- **pgvector is not wired.** Docker was not running on the build machine, so a Postgres/pgvector path could not be tested.
  Vectors are stored as JSON and compared with numpy, which is fine for the spec's scale (about 200 resumes × 15 chunks per
  job, searched within one candidate). Moving to pgvector means a `Vector` column and an `<=>` query in `retrieval.py`.
- No authentication, roles or per-user filtering (Phase 3). The Recruiter/Student tabs are not access control. Do not expose
  this API publicly as it is.
- Thresholds (0.6, 0.3, 0.5 entailment, 0.9 penalty) are the spec's starting values and have **not been tuned**; no accuracy,
  fairness or ranking-quality number has been measured, and none is claimed. The evaluation harness (stage 7 of the build
  order) is not built.
- The `light` backend is only a stand-in for trying the workflow. The fairness audits are crude text transformations; a pass
  does not mean the system is fair.
- The skill taxonomy (`services/taxonomy.py`) is small; ambiguous names such as R, C and Go are deliberately left out.
- The experience and education evidence is the nearest text segment, which can be a date line or degree line; the NLI model
  may mark it as weak evidence even though the score (computed from the profile) is right.
- Audits and scoring rerun the models; with the real models a 200-resume job will take minutes.

## Next steps
Stage 16 analytics, authentication and roles, Docker Compose packaging (pgvector, Ollama, MLflow), then the evaluation
harness: gold set, kappa, five-system benchmark, faithfulness test.
