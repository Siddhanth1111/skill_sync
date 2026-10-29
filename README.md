# SkillSync backend: pipeline stages 1 to 5

SkillSync is an auditable candidate-ranking assistant. This repository currently holds the **backend for pipeline
stages 1 to 5** of *SkillSync: Final Pipeline and Build Specification* (the PDF in this folder). The frontend and
stages 6 onward are not built yet.

| Stage | What it does | Status |
|---|---|---|
| 1. Upload and validation | Accept up to 200 PDF/DOCX files, check type and size, process 3 at a time, track status | Done |
| 2. Text extraction | PyMuPDF / python-docx, OCR fallback for scanned PDFs, parse-confidence flag | Done |
| 3. Resume structuring | Llama 3.1 8B (Ollama) to a validated JSON profile, retries, sanity checks, rule fallback | Done |
| 4. Job description understanding | LLM splits a JD into typed, weighted requirements the recruiter can edit; rule fallback | Done |
| 5. Sectioning and chunking | Heading-based sections, segments of at most 500 characters, section label kept | Done |
| 6+. Embeddings, retrieval, rerank, verification, scoring, ranking, fairness, student mode | | Not started |

## Quick start

```bash
cd backend
python3 -m venv ../.venv && source ../.venv/bin/activate
pip install -r requirements.txt
pytest                                           # 49 tests, no Ollama or Tesseract needed
uvicorn app.main:create_app --factory --reload   # API docs at http://localhost:8000/docs
```

Optional, for real runs: `ollama pull llama3.1:8b` and install Tesseract (`brew install tesseract`). Without Ollama
the system still works, using the rule extractors. Without Tesseract, scanned PDFs fail with a clear reason and the
rest of the batch continues.

Configuration lives in `backend/app/config.py` and can be overridden with `SKILLSYNC_*` environment variables
(see `backend/.env.example`). It covers the model name, Ollama URL, DB URL, upload limits, OCR threshold, default
weights and chunk size. The default DB is SQLite for easy local use. Set `SKILLSYNC_DATABASE_URL` to a Postgres URL
for the real setup.

## API (stages 1 to 5)

| Method and path | Purpose |
|---|---|
| `POST /jobs` `{title, text}` | Stage 4: extract requirements from the pasted JD and store them |
| `GET /jobs`, `GET /jobs/{id}` | List jobs / get one with its requirements |
| `PATCH /jobs/{id}/requirements` | Edit requirement text, importance (must/should/nice) or weight |
| `POST /jobs/{id}/resumes` (multipart `files`) | Stage 1: validate and queue files. Returns 202 and a row per file |
| `GET /jobs/{id}/status` | Per-file status (queued, parsing, done, failed + reason) and counts. The UI polls this |
| `GET /health` | Liveness check |

## How it works, stage by stage

Code is in `backend/app/`. `services/` holds the logic, `routers/` is a thin HTTP layer, and `services/ingest.py`
ties stages 2, 3 and 5 together for one file.

### Stage 1: upload and validation (`routers/resumes.py`, `services/parsing.py`, `services/ingest.py`)
- Each file is checked for extension (`.pdf`/`.docx`), size (10 MB) and content (`%PDF` / zip header), so a renamed
  file is caught. A job holds at most 200 resumes.
- **A bad file never stops the batch.** It becomes a row with status `failed` and a readable reason.
- Valid files are written to a private temp folder under a generated name (the user's filename is never used on
  disk) and handed to a `ThreadPoolExecutor` of 3 workers. The upload call returns immediately (HTTP 202).
- The worker deletes the temp file when it finishes, whether it succeeded or failed.
- Status moves `queued` to `parsing` to `done` or `failed`. Any unexpected error is stored as the error class only,
  so resume text can never leak into logs or the DB error field.

### Stage 2: text extraction (`services/parsing.py`)
- PDFs: PyMuPDF with sorted reading order. DOCX: paragraphs plus table cells (resumes often put skills in tables).
- If a PDF yields fewer than 200 characters it is treated as scanned: each page is rendered at 200 dpi and read with
  Tesseract.
- `parse_confidence` is stored per candidate: whether OCR was used, character count, number of sections found, and a
  `low` flag with reasons. The UI will show a warning when `low` is true.

### Stage 3: resume structuring (`services/llm.py`, `services/extraction.py`, `services/fallback.py`)
1. The LLM (Ollama, temperature 0, output constrained to the Pydantic JSON schema) returns name, email, phone,
   skills, roles with dates, and education with a level from 0 to 3.
2. Output is validated. On failure the validation error is fed back and the call is retried, up to 2 retries.
   Dates that cannot be parsed are a validation error, so the model is told exactly what was wrong.
3. Sanity checks run on the validated output:
   - email and phone must appear in the resume text, otherwise they are dropped;
   - skills must appear in the text (whole-token match, so "Java" does not match "JavaScript"), otherwise dropped;
   - **years of experience are computed by code** from role dates with overlapping periods merged. The LLM is not
     asked for it and the field is not in its schema;
   - a warning is added if the LLM's education level is higher than any degree wording the rules can find.
4. If Ollama is unreachable, or the output never validates, the **rule extractor** (regex and heading rules)
   answers and the record is marked `source = "rules"`.

The LLM only extracts structure. It never produces scores.

### Stage 4: job description understanding (`routers/jobs.py`, `services/extraction.py`)
- The same LLM, with the `JDExtraction` schema, splits the description into atomic requirements: type (skill,
  experience, education), importance (must, should, nice), related skills, and years or degree level where stated.
  Benefits, perks and legal text are ignored.
- Empty and duplicate requirements are removed.
- **Code, not the LLM, assigns weights** from importance: must 3, should 2, nice 1 (configurable).
- The fallback reads headings and bullets: "Requirements" bullets are must, "Preferred / Nice to have" are nice,
  "Responsibilities" are should, and "Benefits / About us" blocks are skipped. Inline words such as "preferred"
  override the heading.
- The recruiter edits requirements through `PATCH`. Changing importance resets the weight to that level's default,
  unless an explicit weight is sent too.

### Stage 5: sectioning and chunking (`services/chunking.py`)
- A heading matcher labels sections: experience, education, skills, projects, certifications, summary, achievements.
  Text before the first heading is `header`.
- Each section is packed line by line into segments of at most 500 characters, cutting only on line boundaries. A
  single line longer than 500 is split on word boundaries, the only exception.
- Every chunk keeps its section label. **Chunks are exact substrings of the extracted text**, which Stage 9 (quote
  verification) will rely on. This is covered by a test.

## Database (`backend/app/db.py`)

Tables: `jobs`, `requirements`, `candidates`, `chunks`, following section 6 of the spec. Deleting a job cascades to
its requirements, candidates and chunks.

Deliberate differences from the spec's table list, so teammates are not surprised:
- `candidates` has extra columns `status`, `error` and `raw_text`. Status and error are needed for the polling
  interface. `raw_text` holds the extracted resume text because Stage 9 must verify quotes against it.
- `jobs`/`candidates` have a nullable `user_id` that is not enforced yet. Auth is Phase 3.
- `chunks` has no `embedding` column yet. It is added in Stage 6, with the dimension taken from the chosen model.
- `users`, `scores`, `feedback`, `audit_runs`, `gold_labels` and `experiment_runs` are later phases.

## Tests (`backend/tests/`, 49 tests)

All run without Ollama or Tesseract: the LLM is a scripted mock and OCR is injected. PDFs and DOCX files are generated
in the test, so no resume files are in the repo.

- `test_dates.py`: date formats, future-date clamping, overlap merging, years of experience.
- `test_chunking.py`: heading detection, 500-character limit, line-boundary cuts, chunks are substrings.
- `test_fallback.py`: rule extraction for resumes and JDs, including benefit blocks being ignored.
- `test_extraction.py`: valid LLM reply, retry with the error fed back, fallback after 3 failed attempts, LLM down,
  hallucinated email/phone/skills dropped, JD dedupe and fallback.
- `test_parsing.py`: PDF, DOCX, scanned PDF to OCR, OCR unavailable, corrupt files, upload rejection rules.
- `test_api.py`: end-to-end batch with bad files, status counts, temp-file deletion, 200-file limit, 404s, cascade.

## What has and has not been verified

- Verified: all 49 tests pass (repeated runs, so no flakiness), and a live `uvicorn` smoke test of `/health` and
  `POST /jobs` with Ollama down used the rule fallback correctly.
- **Not verified:** behaviour against a real Llama 3.1 8B model, and real Tesseract OCR. Both need to be tried on
  real or synthetic scanned resumes. The prompts in `services/extraction.py` may need tuning once that is done.
- Parse and extraction quality has not been measured. Per the spec, no accuracy numbers are claimed.

## Known limitations

- The skill taxonomy (`services/taxonomy.py`) is small and deliberately leaves out ambiguous names (R, C, Go).
- Rule-based name and role extraction are heuristics, used only when the LLM fails.
- Uploaded files are read into memory (up to 10 MB each) before being written to temp storage.
- No authentication, role checks or per-user filtering yet (Phase 3). Do not expose this API publicly as is.
- Passworded PDFs are rejected, not unlocked.

## Next steps

Stage 6 (embeddings and pgvector, which also brings the Docker Compose file) and Stage 7 (top-3 retrieval), then
Phase 2 of the build order: reranker, evidence verification, scoring matrix and ranking.
