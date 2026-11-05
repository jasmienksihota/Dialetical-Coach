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
| 3 | HTTP success shown as "verified" | Yes (`verified` = any ok row) | Three stages stored/reported separately; badge says which stage; `--ping` verifies connectivity+structure only | `test_live_stages.py` (empty/garbage/fake-citation/uncited replies never reach "tutoring verified"; migration of old DBs) | "Tutoring verified" = one citation-validated turn, not a quality guarantee; unproven against a real model |
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
- **Live model behaviour** — no key, no request. `claude-sonnet-5-5` is configured in `.env.example` but its availability is **unverified** until `python -m app.check --ping` succeeds, and "tutoring verified" needs a validated citation turn.
- **Any real document**, real-corpus retrieval quality, real PDF column order/footnotes.
- macOS/Windows commands, Safari/Firefox.
- Semantic support of citations (by design), real-model resistance to injected instructions, answer leakage in free-text feedback.

## Recommended next milestone (from what was actually observed)
1. **Owner action, no code:** run `docs/REAL_DOCUMENT_ACCEPTANCE.md` on 3–4 real files and report pass/fail numbers. Every defect found so far (7 of 7 real bugs, plus the multi-turn summary gap) was in **import/extraction or context handling**, none in the retrieval ranking or the UI — so real-document extraction is where the next failures will most likely appear, and guessing features before seeing them would be wasteful.
2. **Then fix what that run shows**, in this order of evidence: if page probes or column order fail → layout-aware extraction and cross-page overlap; if headers/footers or encodings misbehave → tune the cleanup heuristics; if many scanned pages → OCR (not before).
3. **Semantic/hybrid retrieval only if** checklist §4/§6 shows real vocabulary-mismatch misses. The synthetic probe showed misses are already surfaced as weak/none, which is the safe failure mode; it does not yet justify new infrastructure.
4. **Live evaluation** (`docs/LIVE_EVAL_CHECKLIST.md`) once you add a key and choose a spend limit: use it to measure how often the uncited-claim guard withholds harmless blocks and whether real answers stay grounded. Do this before OCR or semantic search because it tests the one component that has never run for real.

## Remaining
Scope editing UI for existing chats; streaming; exercise history view; the items above.
