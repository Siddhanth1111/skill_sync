# SkillSync: pipeline stages 1 to 16 (backend + UI)

SkillSync is an auditable candidate-ranking assistant. This repository implements **stages 1 to 16** of *SkillSync: Final
Pipeline and Build Specification* (the PDF in this folder): a FastAPI backend and a React + Tailwind frontend with sign-up,
sign-in, three roles (recruiter, student, admin), per-user data isolation, and a full set of pages. Not built yet: the
evaluation harness (gold set, five-system benchmark, MLflow), Docker Compose packaging, pgvector.

Hard rules from the spec that the code follows:
- A human makes every hiring decision. Nothing approves or rejects anyone.
- Every quotation shown is checked to be an exact substring of the extracted resume. If it cannot be verified it is not shown.
- The LLM only extracts structure and paraphrases verified quotes. **It never produces a score.**
- Protected characteristics are never inferred or used as features.
- Model names, thresholds and weights live in one config file (`backend/app/config.py`).
- Per-requirement scores are stored, so changing weights needs no new model calls.
- Every query on user data is filtered by the signed-in user. Passwords are hashed, tokens are signed and expire.

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
pytest                                            # 124 tests, no models or Ollama needed
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
Tables: `users`, `activity_log`, `jobs`, `requirements`, `candidates`, `chunks` (with `embedding` JSON), `scores`, `score_runs`,
`rerank_cache`, `feedback`, `job_models`, `audit_runs`. Deleting a job cascades. Default is SQLite (`backend/skillsync.db`); an older database
gets the new columns added automatically at start-up (a small dev-time migration). Deviations from the spec's table list:
extra `status`, `error`, `raw_text` on candidates; `mode` and `scores_stale` on jobs; `jobs.user_id` and `candidates.user_id` link to `users` (rows created before auth have no owner and are not visible to anyone); embeddings are JSON lists searched with numpy, **not pgvector** (see limitations).

To look at the data: `sqlite3 -header -column backend/skillsync.db` (it contains resume text; it is git-ignored).

## Tests

`cd backend && pytest` runs 124 tests in about 20 seconds. The LLM is a scripted mock and the models use the `light` backend,
so no downloads are needed. They cover: dates, chunking, rule fallbacks, LLM retry/fallback/sanity checks, parsing and OCR
paths, scoring formulas, ranking formula and tie-breaks, **backend/browser ranking parity (runs the real `rank.js` with Node)**,
rerank cache, verified quotes being exact substrings, stale scores, failure reporting, narrative grounding, learning, fairness,
student mode, analytics, CSV safety, search, and **auth and access control**: registration rules, hashing, wrong-password and
unknown-email responses, login throttle, expired / forged / `alg=none` tokens, deleted-user tokens, role checks across every
route group, cross-user isolation on 16 routes, admin actions, delete-my-data, and an activity log free of personal data.

The UI was driven end to end in a real headless browser (sign-up, every recruiter tab, student flow, admin flow, route guards,
CSV download, slider re-rank with zero server calls), with no unexpected console errors. That script is not in the repo.

## What has and has not been verified

- **Unit and API tests:** all 124 pass (see above).
- **Real models, end to end** (Llama 3.1 8B through Ollama, bge-base, bge-reranker-base, deberta-base-mnli) on three
  synthetic resumes and one job: all 4 requirements extracted, all 3 resumes parsed by the LLM in about 25 seconds, ranking
  strong 94.0 / mid 85.5 / weak 3.7, every displayed quotation verified, LLM narrative accepted only because its quotes were
  verified, roadmap actions drafted by the LLM, what-if 85.5 to 94.0 with nothing saved. This is a smoke test on 3 resumes. It
  says nothing about accuracy.
- **Bugs this real run found, now fixed and covered by tests:** the SQLite "database is locked" error when three workers wrote
  while the embedding model loaded; leaked temp resume files when the final commit failed; Llama returning empty skills and
  roles because optional fields could be skipped (every schema property is now required); Llama dropping the nice-to-have
  requirement (prompt fixed); a heading ("SUMMARY") being read as a candidate name by the rule extractor; a UI race where a
  scoring run that finished before the first poll never refreshed the page.
- **Not verified:** Tesseract OCR on real scanned resumes (not installed on the build machine); Postgres; any measure of
  ranking quality, fairness or calibration (the evaluation harness is not built).

## Known limitations
- **pgvector is not wired.** Docker was not running on the build machine, so a Postgres/pgvector path could not be tested.
  Vectors are stored as JSON and compared with numpy, which is fine at the spec's scale (about 200 resumes x 15 chunks per
  job, searched within one candidate). Moving to pgvector means a `Vector` column and an `<=>` query in `retrieval.py`.
- SQLite is the default. A small start-up step adds new columns to an older database, but it cannot change existing
  constraints; use a real migration tool before production. Login throttling is in memory, so it resets on restart and is per
  process.
- Thresholds (0.6, 0.3, 0.9 penalty) are the spec's starting values and have **not been tuned**. The entailment threshold is
  0.05, chosen from an 8-pair sanity probe with the real DeBERTa model (the spec's idea of 0.5 flagged everything because this
  model gives low probabilities even for supported quotes). It has not been tuned on a development set either.
- The `light` backend is only a stand-in for trying the workflow. The fairness audits are crude text transformations; a pass
  does not mean the system is fair.
- The skill taxonomy (`services/taxonomy.py`) is small; ambiguous names such as R, C and Go are deliberately left out.
- The evidence for experience and education requirements is the nearest text segment (a date line or degree line). The NLI
  model often marks the date line as weak evidence even though the score (computed from the profile) is right.
- Scoring and audits rerun the models; with the real models a 200-resume job takes minutes, and parsing 200 resumes with an 8B
  model on a laptop takes an hour or more.
- No password reset, email verification or refresh tokens yet.

## Next steps
Docker Compose packaging (pgvector, Ollama, MLflow), password reset and email verification, then the evaluation harness:
gold set, kappa, five-system benchmark, faithfulness test, MLflow logging.
