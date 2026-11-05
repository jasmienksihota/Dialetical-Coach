# Build Status

Last updated at the end of the first build session. "Verified" = exercised by a test or manual
run listed below. Anything else is **unverified**.

## Implemented
- **Library**: PDF/TXT/MD import, size/type/magic-byte validation, sanitized filenames, SHA-256
  dedupe, optional metadata (never invented), 7 overlapping tags, unapproved-by-default, approval
  gate, scanned/empty-PDF warnings, secondary-study-notes kind, printed-page offset, source viewer.
- **Retrieval**: `Retriever` interface; `LexicalRetriever` (SQLite FTS5/BM25 + Porter stemming, with
  pure-Python fallback); document ∪ tag scope; multi-document breadth; strength (none/weak/ok).
- **Chat**: saved conversations, scope persisted and re-asserted every turn, evidence snapshots per
  turn, follow-up carry-over, bounded history + app-made summary, intents (ask/explain/compare/
  challenge/disagreements), no-model-call paths for empty/weak/impossible-compare cases.
- **Citations**: structured typed blocks; mechanical validation (supplied ID, approved + in scope,
  whitespace-only quote match, synthesis ≥ 2 docs); one repair; withholding; flag-as-unsupported.
- **Exercises**: dialectical reasoning end to end (+ Belief Test, Main Constraint, Development Lab via
  the same engine); one question per turn; hint/clarify/pause/resume/show-analysis (confirmation before
  any attempt); reflection; multi-source limitation + single-source offer; historical case gating.
- **Providers**: deterministic demo provider (labeled) and Anthropic adapter (forced tool call, env-only
  key/model, error mapping, redaction).
- **Export**: Markdown handoff (reflection, attempts, validated source references, flags, optional transcript).
- **Local-first guards**: localhost bind + Host/Origin checks, no telemetry, `.gitignore`/`.env.example`.
- **Frontend**: responsive single page (Library, Search, Sessions, About & privacy), passage inspector.

## Verified (actually run, this session)
| Command | Result |
|---|---|
| `pytest -q --ignore=tests/e2e` | 80 passed |
| `pytest -q tests/e2e` (Playwright + Chromium, real uvicorn server) | 1 passed |
| `TUTOR_FORCE_NO_FTS=1 pytest -q tests/test_chat.py tests/test_exercise.py` | 47 passed (the DB-level tests in `test_library.py` run both FTS5 and fallback via fixture params) |
| `python -m app` launched; `/` = 200, `/api/status` ok, wrong `Host` = 403 | confirmed manually |
| Screenshots reviewed (`test-artifacts/`, git-ignored) | UI renders library, passage inspector, exercise, finished state |

Covered by tests: import, dedupe, validation, approval, tag/doc filters, unapproved exclusion, page and
line/section references, document isolation, multi-document retrieval, weak/missing evidence, invalid
IDs, fabricated quotes, out-of-scope citations, repair/withhold, injection (prompt layout + fake-ID
withholding), conversation persistence across restart, exercise turn-taking, no premature reveal (incl. a
deliberately leaky provider), export, no secret leakage (API, DB, files, export, static), API error
mapping and absent credentials, localhost/origin guards, user answers never indexed.

Browser smoke flow verified: import fixtures → duplicate refused → unapproved not searchable → approve →
search → inspect passage → start demo exercise → answer → follow-up → revise → inspect citation → flag →
finish → export download.

## NOT verified
- **Live model behavior.** No real API call has ever been made. The Anthropic adapter is tested only with
  a fake client (call shape, error mapping, redaction). Grounding quality, prompt-injection resistance of
  a real model, tool-call reliability and free-text answer leakage are unverified → run
  `docs/LIVE_EVAL_CHECKLIST.md`.
- **Real corpus behavior**: only SYNTHETIC fixtures were used. Real PDFs (columns, footnotes, odd encodings)
  may extract poorly; retrieval quality on real texts is untested.
- Windows commands in the README were not run. Safari/Firefox not tested (Chromium only).
- Semantic support of citations is by design not machine-verified.
- The demo provider's keyword feedback is a script, not an assessment.

## Blocked / needs owner input
- Live evaluation needs: your API key, a current model ID (`ANTHROPIC_MODEL`), and your OK to spend balance.
- Your real documents (import them locally; nothing was downloaded).
- Decide whether to add OCR and/or a semantic retriever next.

## Remaining / next milestones
1. Run the live checklist; tune prompts based on results.
2. Real-document pass: extraction quality, chunk sizing, section detection for TXT.
3. Optional OCR path; optional semantic/hybrid retriever behind `Retriever`.
4. Streaming responses; per-session scope editing UI; exercise history view.
5. Richer exercise assessment views (still qualitative).
