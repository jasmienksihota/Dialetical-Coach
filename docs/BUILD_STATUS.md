# Build Status

Updated after the review of commit `34d2f62`. "Verified" = exercised by a test or measurement listed below;
everything else is **unverified**. No paid API call has ever been made.

## Test results actually obtained (Linux sandbox, Python 3.13, SQLite 3.53)
| Command | Result |
|---|---|
| `pytest -q --ignore=tests/e2e` | **225 passed** |
| `pytest -q tests/e2e` (Playwright + Chromium, real uvicorn server) | **2 passed** |
| `TUTOR_FORCE_NO_FTS=1 pytest -q` on chat / exercise / multi-turn / follow-up / citation-bypass tests | **97 passed** (non-FTS fallback path) |
| `git check-ignore` audit of `.env*`, `data/`, `data-*/`, `*.db`, exports, stray PDFs/DOCX | all ignored; fixtures and `.env.example` tracked (enforced by `tests/test_repo_hygiene.py`) |
| Fresh `git clone` of the branch + `./run.sh` + upload via API | worked (Linux) |
Regressions found while fixing: none persisted. Old tests that encoded superseded behaviour were updated:
follow-up query order, live-session acknowledgement, retry/sleep in adapter tests, "verified" status keys.

## Review findings (commit 34d2f62)
| # | Finding | Reproduced? | Fix | Regression tests | Residual limits |
|---|---|---|---|---|---|
| 1 | Scope = doc ∪ tags is ambiguous | Yes (semantics undocumented in UI; no resolved list) | Behaviour **unchanged** (union is the safer, more useful reading). Added `explain_scope`, `POST /api/scope/resolve`, live preview in every scope picker, resolved list in each session header, `report.scope` recorded per turn, About text | `test_scope_transparency.py`, e2e smoke asserts preview + tag union | Scope can still be edited via API only for chats (no UI editor yet) |
| 2 | Source claims could hide in coaching/fiction/limits blocks | Yes (3/3 smuggled blocks passed as `uncited`) | Pattern guard → `uncited_source_claim` / `uncited_quotation`; fiction may not cite; prompt contract strengthened; UI labels "no sources cited" | `test_citation_bypass.py` (12 smuggled, 8 benign, copied-text, end-to-end repair/withhold, exercise question) | **Heuristic.** Paraphrase avoiding assertion verbs is not detected (asserted as a known-limitation test). May withhold harmless blocks, e.g. "your text states…". Mechanical validation still does not prove semantic support |
| 3 | HTTP success was labelled "verified" | Yes (any successful HTTP row counted) | Three stages stored/reported separately; the top stage is labelled **"citation checks passed"** (mechanical checks only); `--ping` establishes connectivity + structure only | `test_live_stages.py` (empty/garbage/fake-citation/uncited replies never reach that stage; migration of old DBs); `test_wording.py` | "Citation checks passed" says nothing about tutoring quality or whether passages support claims; unproven against a real model |
| 4 | Follow-ups ("How does that change?", "Give another example", "Why is that the principal one?") | Yes: chain drift (anchor was previous follow-up), nothing carried when prior turn cited nothing, "another example" re-ran a 3-word weak search | `followup.py`: anchor = last substantive question; carry cited-else-supplied passages; "another/different" excludes prior passages and says so when exhausted; query shown in UI | `test_followups.py` (scope never widened, unapproved docs dropped, exhaustion message) | Heuristic classifier; lexical only; a follow-up whose referent isn't in the last question can still retrieve poorly |
| 5 | Real-document checklist + PDF stress tests outstanding | — | `docs/REAL_DOCUMENT_ACCEPTANCE.md`, `tools/inspect_import.py`, `tests/stress_fixtures.py`, `tests/test_extraction_stress.py` | 32 stress tests (FTS5 and fallback) | **Owner has not yet run the checklist on real documents** |

Also fixed (found by the multi-turn test earlier): exercise sessions now carry the app-made summary and the learner's earlier attempts.

## Extraction stress test (SYNTHETIC documents imitating real layouts — not real documents)
Failures **observed** before fixes → fixed → now tested:
1. Running headers and footer page numbers were indexed as text → removed when repeated at page edges (≥40% of ≥4 text pages), **disclosed** in a warning. *Risk observed:* identical real opening lines on many pages are also removed (tested + disclosed).
2. Hyphenated line breaks left `caref- ully`, breaking word search → rejoined.
3. Text with single-newline paragraphs reported "lines 1–60" for every passage → per-line ranges (verified against file lines).
4. Windows-1252 text showed `�` for curly quotes → decoded as cp1252 with a note.
5. YAML front matter in Markdown indexed as a paragraph → skipped (line numbers stay file-accurate).
6. A few blank pages in a short PDF raised a "partly scanned" alarm → now a note unless ≥20% and ≥2 pages.
7. Fallback (non-FTS) retriever could not distinguish `marker-77` from `marker-12` → splits hyphenated terms like FTS5.
Observed and **not fixed (documented limits):** sentences straddling a page break are split between passages; footnotes/tables indexed as plain text; multi-column order depends on the PDF's text layer (the synthetic fixtures draw columns in reading order, so real column behaviour is **untested**); encrypted/truncated PDFs are rejected cleanly; 150-page PDF imports in ~0.7 s; partly scanned PDFs list the missing physical pages.

## Lexical retrieval probe (tiny synthetic corpus: 3 documents, ~10 passages)
8 probes: both exact-word probes hit; 4 of 6 paraphrase probes hit, but **all 4 were flagged "weak"** and 2 paraphrases missed (one returned no passages, one a wrong passage). A corpus this small flatters retrieval; the useful observation is that the weak/none signals fired where matching was poor. Paraphrase performance on a real library is **unmeasured**.

## Spending controls (what exists, what does not)
Exists: opt-in flag + per-session acknowledgement; daily request cap persisted in SQLite (retries and repairs count); output-token cap (ceiling 4096); prompt-size guard; bounded retries; token-usage logging (counts, no content). Does **not** exist: any dollar cap, balance awareness, or cost estimate; input tokens are only roughly bounded by characters; timed-out requests may still be billed. Set a billing limit with the provider.

## NOT verified
- **Live model behaviour** — no key, no request. `claude-sonnet-5-5` is configured in `.env.example` but its availability is **unverified** until `python -m app.check --ping` succeeds, and "citation checks passed" needs a reply whose citations pass the mechanical checks (which still does not measure tutoring quality).
- **Any real document**, real-corpus retrieval quality, real PDF column order/footnotes.
- macOS/Windows commands, Safari/Firefox.
- Semantic support of citations (by design), real-model resistance to injected instructions, answer leakage in free-text feedback.

## Current phase: feature pause
OCR, semantic/hybrid retrieval and all other feature additions are **paused** while the owner runs the
real-document checks. Only fixes for defects those checks reveal should be made.

## Next step (a working hypothesis, not a finding)
1. **Owner action, no code:** run `docs/REAL_DOCUMENT_ACCEPTANCE.md` on 3–4 real files and report pass/fail numbers.
2. **Working hypothesis:** extraction/import quality may turn out to be the weakest area. The only basis for this is
   that the bugs found so far surfaced in import and context handling — but those came from **synthetic fixtures I wrote
   myself**, which encode my own assumptions about what documents look like. They do **not** show where failures in
   the owner's real collection will occur, and the tally was not exclusively extraction (it also included a
   fallback-retriever tokenization bug, and earlier browser testing found three UI bugs). Real documents may fail in
   entirely different ways (or not at all).
3. **Let the checklist results set priorities.** Candidate follow-ups, each justified only if a specific check fails:
   layout-aware extraction / cross-page overlap (page or column failures), cleanup heuristic tuning (headers, footers,
   encodings), OCR (many scanned pages), semantic retrieval (real vocabulary-mismatch misses). None is scheduled.
4. **Live evaluation** (`docs/LIVE_EVAL_CHECKLIST.md`) is the other large unknown: the guard, the adapter and real-model
   grounding have never run against a real model. It needs the owner's key, a provider-side spend limit and explicit go-ahead.

## Remaining
Scope editing UI for existing chats; streaming; exercise history view; the items above.

## Dialectical-materialism milestone — design stage (branch `claude/dm-concepts-eval`, from `228563b`)
Core requirement: the app must support learning and practising dialectical materialism from the owner's approved sources.
**Not achieved, not claimed.** What exists:
- `docs/dialectical/AUDIT.md` — inspection of the workflow and prompts (8 findings, e.g. app-authored theory baked into `modes.py`; generic rubric; authorship not sent to the model; scripted demo cannot tell jargon from reasoning).
- `eval/dialectical/concept_map.json` + `docs/dialectical/CONCEPT_MAP.md` — a **skeleton of questions for the library with NO passages and no claims about any author**. Every concept is `unsupported`. Real passages can only come from the owner's approved library via `tools/dm_eval.py probe` (read-only) and the owner's own confirmation file.
- `eval/dialectical/cases.json` — 13 INVENTED cases in the requested pairs (static vs relational; empty vocabulary vs plain substance; contradiction not yet justified + tradeoff/inconsistency look-alikes; new evidence revision; 3 concept probes incl. Cartesian dualism), with observable `tutor_should` / `tutor_should_not` criteria, an app-created qualitative rubric, `owner_review: pending`.
- `docs/dialectical/PROMPT_CHANGES.md` — 7 proposed prompt/rubric changes, **proposed and not applied** (except P7).
- `tools/dm_eval.py` — `probe`, `readiness`, `baseline`, `check` (offline; no API).
- Applied: scripted demo feedback no longer says "Visible in your answer"; it says keyword matches do not show support.

Tests run on this branch: `pytest -q --ignore=tests/e2e` **260 passed** (20 new contract tests in `tests/test_dm_eval_contract.py`); `pytest -q tests/e2e` **3 passed**.
Observed: `tools/dm_eval.py baseline` — the demo's keyword matcher matched the empty-jargon response and the premature-"contradiction" responses but nothing in the best-supported revision (C4b). Readiness today: **0/13** cases traceable to confirmed passages.

**Verified (contract level only):** the materials parse, are labelled invented/app-created, have observable criteria, contain no source text; the probe is read-only and approved-primary-only; readiness rejects unapproved/missing/secondary/unannotated passages; surface checks behave as specified.
**NOT verified:** that any model, with any proposed prompt, reasons dialectically, withholds "contradiction" when unjustified, keeps authors apart, or admits insufficient evidence; any real passage; the owner's judgement of the cases. No live call was made; no model was retrained; no documents were downloaded, imported or approved.
**Needs the owner:** run `probe` against the approved library, confirm/mark concepts, review and edit the cases, decide which prompt changes to adopt; then a live evaluation (spend limit + human blind rating).
