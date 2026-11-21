# SkillSync: pipeline stages 1 to 16 (backend + UI)

SkillSync is an auditable candidate-ranking assistant. This repository implements **stages 1 to 16** of *SkillSync: Final
Pipeline and Build Specification* (the PDF in this folder): a FastAPI backend and a React + Tailwind frontend with sign-up,
sign-in, three roles (recruiter, student, admin), per-user data isolation, and a full set of pages.

**Version 2 of the scoring core** (pipeline `v2`) follows the QA review in `SkillSync Project Review and Fix Plan.pdf`:
evidence-first scoring, bullet-level units with context, hybrid retrieval, a skill ontology, requirement kinds (soft skills
and duties are listed, not scored), blind scoring by default, tiers instead of a false 1-to-N order, per-page OCR, and a
debug trace on every score. See **QA review plan: status** below for what is fixed, what is partial and what is not done.
Not built yet: the trained judge and calibration (they need the human-labelled gold set), Docker Compose packaging, pgvector.

Hard rules from the spec that the code follows:
- A human makes every hiring decision. Nothing approves or rejects anyone.
- Every quotation shown is checked to be an exact substring of the extracted resume. If it cannot be verified it is not shown.
- The LLM only extracts structure and paraphrases verified quotes. **It never produces a score.**
- The scorer reads the resume with identity details removed (name, contact, links, school, pronouns); the recruiter still sees the original.
- Protected characteristics are never inferred or used as features.
- Model names, thresholds and weights live in one config file (`backend/app/config.py`).
- Per-requirement scores are stored, so changing weights needs no new model calls.
- Every query on user data is filtered by the signed-in user. Passwords are hashed, tokens are signed and expire.

| Stage | What it does | Where |
|---|---|---|
| 1. Upload and validation | up to 200 PDF/DOCX, type/size/content checks, 3 workers, per-file status | `routers/resumes.py`, `services/ingest.py` |
| 2. Text extraction | PyMuPDF / python-docx, per-page OCR (300 dpi, preprocessing, confidence), column-aware order, text normalisation | `services/parsing.py` |
| 3. Resume structuring | Llama 3.1 8B JSON profile, retries, sanity checks, rule fallback | `services/extraction.py`, `fallback.py`, `llm.py` |
| 4. Job understanding | requirements with a kind, year range, any-of mode and a clean query; weights 3/2/1 by code; rule fallback | `routers/jobs.py`, `services/extraction.py`, `services/requirements.py` |
| 5. Sectioning and units | wide headings (fuzzy, inline), one unit per bullet or sentence with its role as context, no contact text | `services/chunking.py`, `services/skillgraph.py`, `services/blind.py` |
| 6. Embedding and indexing | bge-base by default (MiniLM, bge-m3 via config), normalised vectors stored per chunk | `services/embeddings.py` |
| 7. Retrieval | hybrid: BM25 + dense fused by reciprocal rank, alias-expanded query, top 8 | `services/retrieval.py`, `services/taxonomy.py` |
| 8. Reranking | cross-encoder, sigmoid to 0..1, cached by requirement/segment/model | `services/rerank.py` |
| 9. Evidence verification | exact-substring check, then entailment on the single supporting sentence; weak evidence caps a requirement at partial | `services/verify.py` |
| 10. Requirement scoring | evidence-first per kind, statuses met / partial / not met / not verifiable, trace per cell | `services/scoring.py` |
| 11. Ranking and re-weighting | weighted mean, 0.9 penalty per confidently unmet must, tiers, same formula in browser | `services/ranking.py`, `frontend/src/lib/rank.js` |
| 12. Explanations and gaps | unmet first, gaps by points gained, narrative limited to verified quotes | `services/explain.py` |
| 13. Learning from feedback | thumbs, logistic regression on 7 features, CV AUC / Brier / ECE, SHAP | `services/feedback.py` |
| 14. Fairness audit | blind, counterfactual, adverse impact + Fairlearn, WEAT, monitoring | `services/fairness.py` |
| 15. Student mode | one resume vs many jobs, roadmap, what-if simulator | `services/student.py` |
| 16. Analytics | score distribution, tiers, requirement coverage, near matches, skill demand | `routers/analytics.py` |
| Auth, roles, admin, privacy | register/login, JWT, role checks, ownership checks, admin, delete-my-data | `security.py`, `deps.py`, `routers/auth.py`, `routers/admin.py` |
| Also | CSV export, semantic search over resumes | `routers/analytics.py` |

## Quick start

Prerequisites: Python 3.9+, Node 18+, [Ollama](https://ollama.com) with `ollama pull llama3.1:8b`. Optional: Tesseract
(`brew install tesseract`) for scanned PDFs.

```bash
# terminal 1: backend
cd backend
python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements.txt
pytest                                            # 188 tests, no models or Ollama needed
uvicorn app.main:create_app --factory --reload    # http://localhost:8000/docs

# terminal 2: frontend
cd frontend
npm install
npm run dev                                       # http://localhost:5173
```

Open http://localhost:5173 and **create an account** (recruiter or student). Admins cannot self-register; create one with:

```bash
cd backend && python -m app.cli create-admin you@example.com      # prompts for a password
# or set SKILLSYNC_ADMIN_EMAIL and SKILLSYNC_ADMIN_PASSWORD and one is created at start-up
```

**Two modes for the ML models** (`SKILLSYNC_MODEL_BACKEND`):
- `real` (default): bge-base-en-v1.5 embeddings, bge-reranker-base, microsoft/deberta-base-mnli. About 2 GB downloaded
  from HuggingFace on first use, so the first scoring run is slow.
- `light`: small deterministic stand-ins (hashed word vectors, word-overlap reranker and entailment). No downloads, runs in
  seconds, good for trying the workflow and for tests. **Its scores say nothing about real model quality.**

Other settings (all `SKILLSYNC_*` env vars, see `backend/app/config.py` and `backend/.env.example`): database URL, JWT secret
and lifetime, Ollama URL and model, upload limits, OCR threshold, embedding/reranker/NLI model names, thresholds, minimum
ratings, fairness thresholds. If no `SKILLSYNC_JWT_SECRET` is set, a random secret is created once in `backend/.jwt_secret`
(git-ignored).

Note: PDFs with under 200 characters of text are treated as scanned and need OCR (spec rule). If Tesseract is missing,
tiny test PDFs fail with a clear reason; set `SKILLSYNC_OCR_MIN_CHARS=50` to try short synthetic resumes.

## The frontend (`frontend/`)

React 19 (JavaScript), Vite, **Tailwind CSS v4**, **React Router**, lucide-react icons, DM Sans. It is built on the
design-system tokens in `src/styles/` (semantic colours such as `bg-card`, `text-muted-foreground`, `border-border`; flat,
border-driven surfaces; one primary action per screen). The reusable pieces are in `src/components/ui/` (Button, Badge, Card,
Form, Layout/DataTable/Tabs, Overlay/Dialog/Sheet, Feedback/Alert/Progress, Toast, Charts).

| Route | Who | What |
|---|---|---|
| `/login`, `/register` | public | sign in, create a recruiter or student account |
| `/recruiter` | recruiter | dashboard: stats, recent jobs, most-missed requirements, skills in demand |
| `/recruiter/jobs`, `/jobs/new` | recruiter | job list (delete), create from a pasted description |
| `/recruiter/jobs/:id` | recruiter | requirements editor |
| `.../resumes` | recruiter | drag-and-drop upload, live parse status, parsed resume panel, delete |
| `.../ranking` | recruiter | run scoring, weight sliders that re-rank in the browser, evidence panel (`?candidate=ID`), ratings |
| `.../fairness` | recruiter | blind, counterfactual, impact ratio, WEAT, trend chart, reopen past audits |
| `.../learning` | recruiter | rating progress, train learned score, AUC / Brier / ECE, SHAP drivers |
| `.../analytics` | recruiter | score histogram, tiers, requirement coverage, one-requirement-away list |
| `/recruiter/search`, `/analytics` | recruiter | semantic resume search; cross-job analytics |
| `/student`, `/resume`, `/jobs`, `/matches`, `/matches/:jobId` | student | overview checklist, one resume, job descriptions, ranked matches, roadmap and what-if |
| `/admin`, `/users`, `/activity` | admin | stats, user list and delete, activity log |
| `/settings` | everyone | account, delete my data, delete my account |

Route guards send signed-out users to `/login` and signed-in users to their own area if they open another role's pages.
The API client (`src/api/`) adds the bearer token, turns errors into readable messages, and signs the user out on an expired
token. Vite proxies `/api/*` to the backend on port 8000 (`VITE_BACKEND_URL` to change it).

## How to use it (workflow)

**Recruiter**
1. *New job*: paste a job description. Requirements appear (type, must/should/nice, weight) and can be edited.
2. *Resumes* tab: drop resumes, watch per-file status, open a parsed resume (profile, parse-confidence warning, segments).
3. *Ranking* tab: **Run scoring** (background, with progress). Move the sliders or change an importance: the ranking updates
   instantly in the browser. Click a candidate for the evidence (verified quotation and section per requirement, weak-evidence
   warnings, biggest gaps, summary) and rate with the thumbs. *Save as default* stores the weights. Editing a requirement's
   wording marks scores out of date until scoring is re-run.
4. *Fairness*, *Learning*, *Analytics* tabs as described above. *Export CSV* is in the job header.

**Student**: upload one resume, paste job descriptions, **Match** (best first), open a job for the roadmap (start here / next /
later, points per step, running projected score) and use the what-if box (nothing is saved).

**Admin**: see users and the activity log; delete a user together with all of their data. Admins cannot open anyone's resumes.

## API

Everything except `/auth/register`, `/auth/login` and `/health` needs `Authorization: Bearer <token>`. Interactive docs:
http://localhost:8000/docs. A record that belongs to someone else returns 404, exactly like a missing one.

| Area | Endpoints | Roles |
|---|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `DELETE /me/data?delete_account=` | all |
| Jobs | `POST /jobs`, `GET /jobs`, `GET/DELETE /jobs/{id}`, `PATCH /jobs/{id}/requirements` | recruiter, student (own jobs) |
| Resumes | `POST /jobs/{id}/resumes`, `GET /jobs/{id}/status`, `GET/DELETE /candidates/{id}` | recruiter (status, upload), recruiter and student (candidate) |
| Scoring | `POST /jobs/{id}/score` (202), `GET /jobs/{id}/score/status`, `GET /jobs/{id}/matrix`, `GET /jobs/{id}/ranking` | recruiter |
| Explanation | `GET /candidates/{id}/explanation` | recruiter |
| Learning | `POST /candidates/{id}/feedback`, `POST /jobs/{id}/model/train`, `GET /jobs/{id}/model` | recruiter |
| Fairness | `POST /jobs/{id}/audit/blind`, `/counterfactual`, `/impact`, `/weat`; `GET /jobs/{id}/audit/history`, `/audit/{audit_id}` | recruiter |
| Analytics | `GET /jobs/{id}/analytics`, `GET /analytics/overview`, `GET /jobs/{id}/export.csv`, `GET /search?q=&job_id=` | recruiter |
| Student | `POST/GET /student/resume`, `POST /student/match`, `GET /student/matches`, `GET /student/roadmap`, `POST /student/whatif` | student |
| Admin | `GET /admin/users`, `/admin/stats`, `/admin/activity`, `DELETE /admin/users/{id}` | admin |

**Security notes.** Passwords are hashed with bcrypt (8 to 72 characters). Tokens are HS256 JWTs with an expiry (default 8
hours), and every request re-checks that the user still exists. Login returns the same message for an unknown email and a wrong
password, always runs one bcrypt comparison, and blocks an email after 8 failures in 15 minutes (in memory, per process).
Roles are checked on every route, and ownership on every record. The CSV export neutralises spreadsheet formulas in
resume-derived cells. The activity log stores action names, ids and counts only.

## How it works

### Stages 1 to 5 (ingestion)
- **Upload:** each file is checked for extension, size (10 MB) and content signature; a job holds at most 200 resumes. A bad
  file becomes a `failed` row with a reason and never stops the batch. Valid files are written to a private temp folder under
  a generated name, parsed by 3 worker threads, and deleted afterwards.
- **Extraction:** PyMuPDF reads each page; two-column pages are read left column then right. **OCR is decided per page**
  (under 60 characters, mostly images with little text, or garbled text) and the page texts are merged. OCR renders at 300 dpi,
  converts to grayscale, stretches contrast, denoises, deskews, binarises (Otsu), uses Tesseract page mode 4 and records the mean
  word confidence per page. DOCX also reads text boxes, headers and footers. The text is then normalised (ligatures, bullets,
  soft hyphens, line-break hyphenation, odd spacing); the normalised text is what everything downstream, including quote
  verification, uses. The parse-confidence flag records OCR use, OCR confidence, text size and sections found.
- **Structuring:** Llama 3.1 8B at temperature 0, output constrained to the Pydantic schema, up to 2 retries with the
  validation error fed back. Sanity checks drop an email or phone that is not in the text, and a skill the ontology cannot find
  (aliases count, so "Postgres" keeps PostgreSQL). **Years of experience are computed by code** from role dates with overlaps
  merged, and so are **years per skill** (the dated roles whose text mentions the skill, plus the skills it implies) and the
  skill-to-unit links. Roles without dates are flagged in the profile. If the LLM is down or never validates, the rule
  extractor answers and the record says `source = rules`.
- **Job requirements:** same LLM with a `JDExtraction` schema. Code then makes each requirement consistent: a **kind**
  (`hard_skill`, `experience`, `education`, `soft_skill`, `duty`; only the first three are scored, the others get weight 0 and
  are listed), the **minimum** of a year range ("2 to 5 years" needs 2), **any-of** mode for "A / B / C" or "A or B", a
  **query** with filler removed ("Strong understanding of RDBMS" is searched as "RDBMS"), near-duplicates merged, and importance
  taken from the posting's own headings when the bullet can be found (an LLM that labels everything "must" cannot override the
  headings). Bullets under an unknown heading default to `should`. Code assigns weights 3/2/1 by importance. The editor shows
  where each weight came from and warns above 15 scored requirements.
- **Units:** headings label sections (wide alias list, fuzzy match for typos, inline forms like `Education: B.Tech`). Under a
  role or project each **bullet or sentence is one unit** with a context line (title, company, dates), so a short generic
  bullet is never searched without knowing where it came from. Name, contact lines, personal details and hobbies are never
  indexed. Units are built from the **blind** scoring text (see Stage 14); each is an exact substring of that text.

### Stages 6 to 9 (evidence)
- Units are embedded with their context line when a resume is parsed; requirements are embedded as queries (bge instruction
  prefix for bge English models). The model name is stored with each vector, so changing the embedding model re-embeds lazily.
  A candidate ingested by an older pipeline is rebuilt into units on its first scoring run.
- **Hybrid retrieval:** for each requirement, dense cosine and BM25 (over the context-prefixed text, with the query expanded by
  ontology aliases) rank the candidate's units; reciprocal rank fusion merges them and the top 8 go to the reranker (sigmoid,
  cached by requirement hash + unit hash + model + **pipeline version**).
- **Verification:** the shown unit must be an exact substring of the scoring text, otherwise no evidence is stored. The single
  supporting sentence is picked inside the unit and highlighted in the UI. DeBERTa-MNLI scores whether that sentence entails the
  requirement; below the threshold the row is flagged **weak evidence** and cannot be "met" (it is capped at partial) unless the
  ontology finds the skill in the sentence itself.

### Stages 10 and 11 (score and rank)
- **Skills are scored from evidence, never from the profile's skill list.** Per skill the ontology reads the retrieved units:
  found in work history 0.85, found only in a skills list 0.65, a named technique of the skill (logistic regression for machine
  learning) 0.5, a sibling tool (RabbitMQ for Kafka) 0.35, not found at most 0.45 (capped reranker score). "All of" averages
  the skills, "any of" takes the best. A skill the ontology does not know uses the reranker score.
- **Experience:** years *with the skill* (from dated roles that mention it) over years required, capped at 1; total career years
  when no skill is named; a skill that appears but is not linked to any dated role is capped at partial.
- **Education:** level over level required, multiplied by 0.7 when the required field of study is not found, with an explicit
  rule that "or equivalent experience" counts as 0.8 at 5 or more years.
- **Status:** met at 0.6, partial from 0.3, otherwise not met; **not verifiable** instead of not met when the resume was read
  poorly (low OCR confidence), and a not-verifiable must is not penalised. One unit may back at most 3 requirements (heavier
  requirements choose first); beyond that it is flagged as a hub.
- Every cell (score, status, quote, supporting sentence, section, entailment, verified, hub, pipeline version and a **trace** of
  query, retrieved units with their ranks, rule and skill matches) is one row of `scores`, the requirement-evidence matrix.
- **Final score** = weighted mean of the scored requirements, times 0.9 for each **must** that is confidently not met. Candidates
  within 2 points of a tier's leader share a **tier** (the order inside it is deterministic but not meaningful); the UI shows
  "musts met: 3 of 4". `services/ranking.py` and `frontend/src/lib/rank.js` are the same formula, tiers and flags included;
  `tests/test_rank_parity.py` runs both on random matrices and compares.

### Stage 12 (explanations)
Requirements are listed unmet first. A gap is `weight × (1 − score) / total weight`, in points of 100, and never lists soft
skills or duties (they have no weight). Those are shown in their own "Listed, not scored" list. The narrative comes from the LLM
using only verified quotes; afterwards every quoted string is checked against the scoring text and a fixed template replaces the
narrative if any check fails (or the LLM is down). Each requirement has a "How this was scored" trace.

### Stage 13 (learning)
Ratings store seven features (overall score, mean score on must/should/nice, share met/partial/not met). With at least 10
ratings and 3 of each kind, a standardised logistic regression is fitted; the cross-validated AUC, Brier score and expected
calibration error are reported (AUC near 0.5 means no signal). The learned probability is shown beside the rule score and
never replaces or reorders it. SHAP for a linear model has a closed form (`coef × (x − mean) / scale`), implemented directly
instead of adding the `shap` package.

### Stage 14 (fairness)
- **Blind by default:** scoring reads text with name, email/phone, links, postcodes, school names (patterns, common
  abbreviations such as IIT/NIT, and the extracted institution), education years and pronouns removed. A person named Ruby or
  Swift keeps the skill of that name: single name parts are removed from the resume header only. The **blind audit** scores every
  resume twice through the same pipeline, with and without identity details, and reports how many candidates changed rank.
- **Counterfactual:** four variants per candidate (male-coded name and pronouns, female-coded, a different school, a different
  date format), scored through the live pipeline; any change above 2 points of 100 is flagged. With blind scoring on, name,
  pronoun and school changes should show no change. No gender is inferred.
- **Adverse impact:** selection = top N; each group's rate is divided by the highest group's rate and a ratio under 0.8 is
  flagged, with 95% Wilson intervals and a small-group warning. Group labels are **never generated**: the audit needs labels the
  recruiter confirms are self-reported and consented, or it runs as a clearly marked **demo**. Demographic parity difference
  comes from **Fairlearn**.
- **WEAT:** effect size and permutation p-value for two name groups in the embedding model. It tests the model, not the ranking.
- Every run is saved in `audit_runs` and charted over time. Every report states its limits.

### Stage 15 (student mode)
A student resume is a candidate with no job. Matching scores it against each chosen job with the same stages 6 to 11 and lists
jobs best first. The roadmap lists unmet scored requirements as start here (must), next (should), later (nice), with points per
step and a running projected score. Suggested actions are drafted by the LLM but kept only if they share wording with the
requirement; otherwise a template is used. **What-if is an estimate:** it needs an evidence-style sentence (an action verb or a
number, at least six words), appends it under a Projects heading on a temporary copy, rescores, saves nothing, and says it
assumes the statement is true.

## Evaluation harness (`backend/eval/`)
- `python -m eval.paraphrase [--light]` runs the review plan's **paraphrase table** through the full pipeline (8 cases: query
  optimisation, RDBMS, CI/CD, stakeholder management, machine learning, Kafka vs RabbitMQ, Python vs Perl, years of backend
  experience). The light version runs in the normal test suite; `SKILLSYNC_REAL_TESTS=1 pytest tests/test_paraphrase.py` runs the
  real models. **Caveat:** several ontology aliases were written for these exact examples, so this is a regression guard, not
  evidence that unseen paraphrases work.
- `python -m eval.benchmark eval/gold/pairs.jsonl` computes quadratic-weighted kappa per requirement kind, nDCG@5, Brier and
  ECE with bootstrap intervals (and logs to MLflow if installed). **The gold set does not exist yet**: it needs two human
  annotators (format and rubric in `eval/gold/README.md`). The "Wrong evidence" buttons in the evidence panel store reviewer
  verdicts (ids and a grade, no resume text) in `gold_labels`; `python -m app.cli export-gold seeds.jsonl` writes them out as seeds.

## Database (`backend/app/db.py`)
Tables: `users`, `activity_log`, `jobs`, `requirements`, `candidates` (with `scoring_text`, `chunk_version`), `chunks` (with `context`, `embedding` JSON), `scores` (with `sentence`, `hub`, `trace`, `pipeline_version`), `score_runs`,
`rerank_cache`, `feedback`, `gold_labels`, `job_models`, `audit_runs`. Deleting a job cascades. Default is SQLite (`backend/skillsync.db`); an older database
gets the new columns added automatically at start-up (a small dev-time migration). Deviations from the spec's table list:
extra `status`, `error`, `raw_text` on candidates; `mode` and `scores_stale` on jobs; `jobs.user_id` and `candidates.user_id` link to `users` (rows created before auth have no owner and are not visible to anyone); embeddings are JSON lists searched with numpy, **not pgvector** (see limitations).

To look at the data: `sqlite3 -header -column backend/skillsync.db` (it contains resume text; it is git-ignored).

## Tests

`cd backend && pytest` runs 188 tests (1 skipped: the real-model paraphrase run) in about 25 seconds. The LLM is a scripted mock and the models use the `light` backend,
so no downloads are needed. They cover: dates, chunking, rule fallbacks, LLM retry/fallback/sanity checks, parsing and OCR
paths, scoring formulas, ranking formula and tie-breaks, **backend/browser ranking parity (runs the real `rank.js` with Node)**,
rerank cache, verified quotes being exact substrings, stale scores, failure reporting, narrative grounding, learning, fairness,
student mode, analytics, CSV safety, search, **one regression test or more per fixed flaw ID in the QA review** (`test_requirements_v2`, `test_ontology`, `test_units_v2`, `test_retrieval_v2`, `test_pipeline_v2`, `test_paraphrase`, `test_eval_metrics`), and **auth and access control**: registration rules, hashing, wrong-password and
unknown-email responses, login throttle, expired / forged / `alg=none` tokens, deleted-user tokens, role checks across every
route group, cross-user isolation on 16 routes, admin actions, delete-my-data, and an activity log free of personal data.

The UI was driven end to end in a real headless browser (sign-up, every recruiter tab, student flow, admin flow, route guards,
CSV download, slider re-rank with zero server calls, the demo-labels path of the impact audit), 27 checks, with no unexpected console errors. That script is not in the repo. One earlier run showed one failed check that did not reproduce in two further runs; I treated it as a timing flake.

## What has and has not been verified

- **Unit and API tests:** all 188 pass (see above).
- **Real models, end to end** (Llama 3.1 8B through Ollama, bge-base, bge-reranker-base, deberta-base-mnli) on three synthetic
  resumes and one job, after the v2 rebuild: all 4 requirements extracted with kinds, all 3 resumes parsed by the LLM, ranking
  strong 94.0 / mid 76.5 / weak 3.8 in tiers 1, 2 and 3, musts met 3 of 3 / 3 of 3 / 0 of 3, every displayed quotation
  verified, LLM narrative accepted, blind and counterfactual audits show 0.00 change (as designed with blind scoring on), what-if
  76.5 to 85.0 with nothing saved. A smoke test on 3 resumes: it says nothing about accuracy.
- **Paraphrase table with the real models:** 8 of 8 as expected after one fix (see the next bullet). Read the caveat above.
- **What the real run exposed in this round, now fixed and tested:** the reranker scored "Machine learning" against a logistic
  regression bullet at about 0 (a keyword query is not what that model is trained for), so the ontology gained a "technique"
  level worth partial credit; the "3+ years" requirement was shown with a summary line as its evidence; blinding left `, ,`
  behind and missed `IIT Delhi` (school abbreviations are now removed inside education sections); the wrong-evidence panel
  crashed the evidence sheet for one build (found by the browser run).
- **Earlier real-run bugs, fixed:** SQLite "database is locked" with three workers; leaked temp files; Llama returning empty
  skills (all schema properties are now required); Llama dropping the nice-to-have requirement; "SUMMARY" read as a name; a UI
  race on fast scoring runs.
- **OCR:** Tesseract 5.5.4 is installed on this machine; a synthetic scanned page reads correctly at mean confidence about 90.
  Not tested on photographs, skewed phone scans, or real resumes.
- **Not verified:** Postgres; any measure of ranking quality, kappa, calibration or fairness against humans (no gold set).

## QA review plan: status

IDs are from `SkillSync Project Review and Fix Plan.pdf`. "Partial" says what is missing.

| Area | Fixed | Partial | Not done |
|---|---|---|---|
| A. Ingestion | A1 per-page OCR, A2 preprocessing + page mode + confidence, A3 columns, A5 normalisation, A6 alias-aware skill check, A7 skill-to-unit links and years per skill, A8 undated roles flagged, A9 contact text not indexed | A2 no fallback OCR engine, A4 no OCR of images inside DOCX, A5 no offset map (the normalised text is the stored source of truth; the original file is deleted) | |
| B. Requirements | B1 kinds, B2 year ranges, B3 any-of, B4 weights follow importance with a source label, B6 query field, B7 unknown headings default to should, B8 review UI and warning | B5 duplicates merged by token overlap, not embeddings | |
| C. Retrieval | C1 headings, C2 bullet units with context, C3 top 8, C4 hybrid BM25 + dense, C5 hub limit and flag, C6 sentence highlight | | C7 pgvector |
| D. Scoring | D1 evidence-first, D2 ontology with aliases, parents and families, D5 weak evidence caps at partial, D6 years with the skill, D7 field of study and equivalence rule, D8 not-verifiable state, D9 versioned cache | D3 thresholds still untuned and the reranker is not fine-tuned or calibrated (needs the gold set), D4 support is judged by a stronger signal (ontology, MNLI on one sentence) but not by a trained judge, D6 no recency | |
| E. Ranking | E1 musts x of y and no penalty when unreadable, E2 tiers, E3 unscored kinds never in gaps | E4 the narrative does not cite evidence ids and offsets | |
| F. Fairness | F1 no hash-based labels (consent or marked demo, with intervals), F2 blind scoring by default, F6 what-if labelled an estimate and needs evidence-style text | F3 school and date-format variants added (no city or layout), F4 impact intervals and small-group warnings (no subgroup calibration), F5 the learned score stays behind its rating threshold but is not moved out of the main flow | F7 roadmap resources |

Also added from the plan: requirement review step, wrong-evidence button feeding `gold_labels`, model and pipeline version on
every score, a per-requirement debug trace, model-quality and evidence-reuse metrics in job analytics, the benchmark harness
(metrics only), the paraphrase regression set, a CI workflow, and `datetime.utcnow` removed.

**Not done** (needs people, data or infrastructure): the gold set and baseline numbers (Phase 0), the silver set, the fine-tuned
judge and calibration (Phase 3), the five-system comparison and ablations, Postgres + pgvector + Alembic, a real job queue,
Docker Compose, httpOnly-cookie sessions, password reset, email verification, per-IP limits, a separate model service,
TypeScript and React Query (the project stays JavaScript, which the plan says to record as a deviation: this is that record),
knock-out filters, candidate comparison, shortlists and a decision log, the synonym manager, the JD linter, PDF reports, and the
student features beyond what-if and roadmap.

## Known limitations
- **The scores are rule-and-model blends, not a trained judge.** The reranker is a general cross-encoder and gives near 0 for
  short keyword queries even when the passage is relevant; the ontology covers that for known skills and not for others. Expect
  misses on skills and phrasings the ontology does not list (`services/taxonomy.py`; extend `ENTRIES`).
- **pgvector is not wired.** Vectors are stored as JSON and compared with numpy, fine at the spec's scale. Search still loads
  every vector of the user's resumes.
- SQLite is the default. A small start-up step adds new columns to an older database, but it cannot change constraints; use
  Alembic before production. Login throttling is in memory and resets on restart. Tokens live in localStorage.
- Thresholds (0.6, 0.3, 0.9 penalty, 0.85 / 0.65 / 0.5 / 0.35 / 0.45 skill levels, the 2-point tier band, entailment 0.05) are
  starting values and have **not been tuned** on a development set.
- Jobs created before this version have requirements without a kind or query; they are scored as before. Create the job again
  to get kinds and any-of lists.
- Blinding removes schools by pattern, abbreviation and extracted institution; an unusual school name can slip through. It does
  not remove location other than postcodes. Evidence quotes are shown with identity details removed.
- The `light` backend is only a stand-in for trying the workflow. The fairness audits are crude text transformations; a pass
  does not mean the system is fair. Hiring tools are regulated in several places; check before any real-world use.
- With the real models a 200-resume job scores in minutes (8 units per requirement are reranked, cached by version), and
  parsing 200 resumes with an 8B model on a laptop takes an hour or more.

## Next steps
1. Label the 150-pair gold set with two annotators and run `python -m eval.benchmark` to get the v2 baseline (Phase 0).
2. Use that to tune thresholds on the development split only, then build the silver set and fine-tune the judge (Phase 3).
3. Postgres, pgvector, Alembic, a job queue and Docker Compose; cookie sessions and password reset.
4. The recruiter features from the plan: comparison, shortlists with a decision log, knock-out filters.
