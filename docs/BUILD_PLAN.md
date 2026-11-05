# Build Plan

Short milestones with acceptance criteria. Status lives in `BUILD_STATUS.md`.

## M1 — Library: import, approve, search, source viewer
- Import PDF / TXT / MD with validation (type, size, magic bytes, sanitized names).
- Exact duplicates (SHA-256) are not re-imported.
- Metadata: title/author/date/edition optional and never invented; 7 overlapping tags.
- New imports unapproved; approval blocked when no text was extracted.
- Scanned / text-empty PDFs produce a visible warning and are not silently indexed.
- PDF chunks carry physical page numbers; text/MD chunks carry line ranges (+ MD section).
- Lexical retrieval (SQLite FTS5, fallback if unavailable) over approved docs only, with
  document / tag / secondary-notes filters applied on every query.
- Source viewer shows a passage with surrounding context.
- **Accept:** tests for import, dedup, approval, tag filter, unapproved exclusion,
  page/line references, document isolation, multi-document retrieval, weak evidence.

## M2 — Persistent chat + provider abstraction
- Conversations saved with scope, messages, supplied evidence per turn.
- Provider interface; deterministic demo provider (labeled); Anthropic adapter
  configured only by env vars; absent key => setup message, app still works.
- Bounded context with a transparent app-generated summary; scope re-asserted each turn.
- **Accept:** persistence tests; API error / missing credential tests; no secret leakage.

## M3 — Citation validation + evidence inspection
- Structured answers (typed blocks + passage references).
- Validate passage IDs, approval/scope, quote presence; one repair then withhold.
- UI renders clickable citations, visible block types, and a flag-unsupported control.
- **Accept:** tests for invalid IDs, fabricated quotes, out-of-scope passages,
  prompt-injection documents, repair/withhold behavior.

## M4 — Dialectical reasoning exercise
- Configurable level, scope, fictional scenario (historical only if adequately documented).
- State machine: setup -> scenario+one question -> attempt -> feedback + probe ->
  complication -> revision -> reflection. Hint / clarify / pause / show-analysis.
- No premature reveal; qualitative rubric labeled app-created.
- **Accept:** turn-taking and no-reveal tests (including a deliberately leaky provider).

## M5 — Export, docs, browser smoke test
- Markdown export (manual handoff, not sync).
- Browser smoke: import fixture -> approve -> search -> inspect -> demo exercise ->
  answer -> revise -> export.
- README (Mac + Windows), architecture, ingestion guide, privacy, live-model checklist.

## M6 — Extra exercise modes (only if core works)
- Belief Test, Main Constraint, Development Lab reuse the same engine via mode specs.
