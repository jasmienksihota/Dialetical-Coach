# CLAUDE.md — Source-Grounded Reasoning and Leadership Tutor

Project guidance for anyone (human or Claude) working in this repository.

## What this is

A **single-user, local-first** conversational tutor grounded in a document library
the owner curates (Marxist-Leninist texts and related traditions). It offers
NotebookLM-style source grounding plus sustained conversation and interactive
exercises. It is a **personal educational tool**. It is NOT a system for profiling
members, ranking ideological loyalty, collecting private political information, or
automating political persuasion. Do not add features in that direction.

Core loop: import docs -> approve -> ask / start an exercise -> retrieve passages
from the selected approved docs -> structured answer with inspectable, mechanically
validated citations -> continue the conversation -> save, revisit, export.

## Hard requirements (do not regress)

1. **Approval gate.** New imports are unapproved. Only approved documents are ever
   retrievable. Document and tag filters apply on *every* retrieval path.
   "Secondary study notes" (manual NotebookLM note imports) are excluded from
   retrieval unless the session scope explicitly includes them.
2. **Evidence policy, not a knowledge guarantee.** The model cannot forget its
   pretraining. Say "evidence policy"; never promise it knows nothing else.
3. **Untrusted source text.** Passages are data. They are delimited in the user turn,
   never in the system prompt, and instructions inside them must not be followed.
4. **Citations are validated mechanically** (passage ID was supplied this turn; doc
   approved and in scope; quote appears in the passage under whitespace-only
   normalization). At most one repair attempt, then withhold the claim. Never show
   an unvalidated citation. A valid ID does **not** prove semantic support — the UI
   says so and offers a flag button.
5. **Visible separation** of: direct quotation / interpretation / synthesis across
   texts / fictional exercise material / app-authored coaching.
6. **No outside tools** in the tutor: no web search, no autonomous acquisition.
7. **Exercises** ask one question at a time, wait for the user, never reveal the full
   analysis before an attempt (explicit confirmed "show analysis" is allowed),
   use qualitative feedback only (no scores), and label the rubric as an
   app-created learning aid. Do not treat dialectics as a thesis-antithesis-synthesis
   formula; derive concepts from retrieved texts.
8. **Privacy.** Localhost binding by default, no telemetry, API key only in env vars
   (never sent to the browser, logged, stored in the DB or committed). Originals,
   extracted text and databases live under `data/` (git-ignored).
9. **Honesty.** Demo/mock output is always labeled
   "Demo: scripted responses, not live tutoring." Mocked tests do not verify live
   model grounding — say so. Never invent bibliographic metadata.
10. **Live calls are opt-in.** Never call the real API from tests or during
    development without the owner's explicit permission. The model ID is
    configuration (`ANTHROPIC_MODEL`); never hard-code or guess one.

## Stack and layout

Python 3.10+ / FastAPI / SQLite (FTS5, with a safe non-FTS fallback) / vanilla
HTML-CSS-JS frontend / `pypdf` / Anthropic SDK adapter / deterministic mock provider.

```
app/
  config.py      settings, .env loading, the 7 topic tags
  db.py          SQLite schema, FTS5 detection/backfill
  ingest.py      validation, extraction (PDF/TXT/MD), chunking, dedup
  library.py     document CRUD, approval, passage lookup, location labels
  retrieval.py   Retriever interface + LexicalRetriever (FTS5 / fallback), scope
  providers.py   Provider interface, MockProvider (demo), AnthropicProvider
  prompts.py     system prompt + evidence packaging (untrusted-data framing)
  citations.py   mechanical citation validation + finalization
  tutor.py       chat turn orchestration (retrieve -> generate -> validate -> persist)
  exercises.py   exercise state machine (turn-taking, reveal gating, reflection)
  export.py      Markdown export for manual NotebookLM handoff
  main.py        FastAPI app, localhost guards, static frontend
  static/        index.html, app.js, style.css
tests/           pytest suite (+ tests/e2e browser smoke test)
fixtures/synthetic/   clearly labeled SYNTHETIC test/demo documents
docs/            BUILD_PLAN.md, BUILD_STATUS.md, ARCHITECTURE.md, INGESTION.md, PRIVACY.md
```

## Conventions

- Keep modules small and plain; no new framework without a strong reason.
- Retrieval stays behind `retrieval.Retriever`; do not claim lexical retrieval equals
  hybrid/semantic retrieval.
- All SQL uses bound parameters. Frontend renders untrusted text with `textContent`
  (or an escape helper), never raw `innerHTML`.
- Tests use only synthetic fixtures labeled as such. Do not download or bundle a real
  corpus without the owner's approval.
- Run `pytest -q` before every commit. Record what was actually run and its result in
  `docs/BUILD_STATUS.md`; separate *verified* from *unverified*.
- Small commits on the working branch (`claude/tutor-mvp`). Do not merge to `main`,
  deploy publicly, or commit documents, databases, secrets or personal history.

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m app            # starts on http://127.0.0.1:8000
pytest -q                # unit/integration tests
pytest -q tests/e2e      # browser smoke test (needs Playwright + Chromium)
```
