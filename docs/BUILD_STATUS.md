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

## Dialectical-materialism milestone — preparatory work (branch `claude/dm-concepts-eval`)
Core requirement: learning and practising dialectical materialism from the owner's approved sources. **Not achieved, not claimed.** The audit and
evaluation scaffold are *preparatory*; they are not evidence that the tutor understands dialectical materialism.

Implemented (bounded, unverified against a real model):
- **Evidence metadata:** every passage sent to the model now carries recorded author, title, date, edition, passage ID, location and primary/secondary status; unknown fields read "not recorded" (never guessed); tag-breaking metadata is neutralised; a system-prompt rule requires attribution to the named author. The app still cannot tell an author's text from an editor's/translator's note inside a document (documented, not claimed solved).
- **Misleading assessment removed:** the demo no longer shows keyword matching to the learner; its feedback is a clearly scripted prompt, and its hints/analysis/reflection no longer carry developer theory. The matcher survives only as a diagnostic (`tools/dm_eval.py baseline`).
- **Developer theory vs library claims:** dialectical mode objective/guidance neutralised; `docs/dialectical/TEACHING_CONTRACT.md` separates application rules from claims that need passage support (provisional; **not wired** into live prompts).
- **Evidence statuses:** `supported` / `not_found_in_reviewed` (needs `reviewed_scope`) / `needs_investigation`; the stronger "not addressed by this library" is not used.
- **First diagnostic reduced to three cases** (C2a, C1b, C3a; five concepts) — `docs/dialectical/DIAGNOSTIC_PACKET.md`: template only, supporting passages PENDING (no library in the cloud workspace), nothing reviewed.
- `docs/dialectical/LOCAL_PROBE_INSTRUCTIONS.md` for the local session (read-only probe; nothing leaves the Mac without the owner's permission).

Tests run on this branch: `pytest -q --ignore=tests/e2e` **267 passed**; `pytest -q tests/e2e` **3 passed**.
**Verified (contract level):** prompt rendering includes recorded metadata and "not recorded"; metadata cannot break the wrapper; demo learner-facing text has no keyword/theory wording across a full exercise; probe is read-only; statuses and readiness behave as specified.
**NOT verified:** any live-model behaviour; any real passage or author interpretation; whether the changes help the learner. No live call, no corpus download, no approval change, no retraining.
**Blocked (as of the last check):** no local session for this project is reachable from the cloud workspace, so the three-case packet is still empty; whether any starter documents are approved on the Mac is unverified. Reviewer provenance is now required on every `supported`/`not_found_in_reviewed` entry (AI-assisted review is recorded as such, never as the owner's), and filled packets are git-ignored (`*.local.md`). Tests: 272 passed.
**Next:** a local session (with permissions Jasmien has actually granted — verified, not assumed) runs the read-only probe on the approved library and prepares a local evidence packet for the three diagnostic cases; the owner approves sharing or spending only when asked. A live diagnostic needs separate spending authorization.

## Reference-text review and populated diagnostic packet (2026-11-05)
Jasmien authorized retrieving 15 specific public units from www.marxists.org (and allowed that domain in the cloud environment). robots.txt was read (no disallow for these paths, 1 s crawl delay; fetched 2 s apart); all 15 returned HTTP 200. Raw copies, extracted text, provenance (`PROVENANCE.md`) and the build script live in git-ignored `data/reference/`; the **populated three-case packet** is the git-ignored `docs/dialectical/local/DIAGNOSTIC_PACKET.local.md`. Nothing was imported or approved in the app, nothing from her computer was accessed, no live call was made.
- **Status: AI-assisted and UNVALIDATED.** 40 quotations, each machine-checked as an exact substring of the retrieved text; locations given as unit, section heading, block number and URL. Not every word of the 15 texts was read (coverage is listed in the packet); the rest was keyword-searched.
- **Findings that change expectations (see packet):** (1) Mao says every difference in men's concepts reflects an objective contradiction, which cuts against the developer's "mere disagreement vs contradiction" contrast: a proposed revision to case C3a's expectations is recorded in the packet but NOT applied to `cases.json`; (2) Engels uses "contradiction" for mathematical absurdities and counts formal logic alongside dialectics, so "logical inconsistency vs contradiction" is `needs_investigation`, not "not found"; (3) the sections closely reviewed do not establish thesis-antithesis-synthesis as a required universal method (a keyword search cannot establish absence across fifteen texts), and the M_TAS surface check is only a token heuristic: what a passage supports, not whether a token occurs, is what matters; (4) authors differ (internal-cause priority is explicit in Mao; Lenin even says Engels treats the identity of opposites as a sum of examples).
- **Correction made during the work:** my first thesis/antithesis search missed matches near block edges and produced a wrong statement; it was redone over every block and corrected in the packet.
- **Not verified:** that any model uses these passages well; retrieval/extraction on Jasmien's own imported files; the interpretations themselves (no human review).

**Case corrections after reading the reference texts (provisional, AI-assisted, unvalidated):** C3a, C1b and C2a no longer encode premises the sources do not support. C3a drops "disagreement is not contradiction"; C1b is judged by support in the case record (not resemblance to the authors' framing) and attributes the internal/external ordering to Mao; C2a locates the weakness in the missing case facts, not the vocabulary, and bounds the thesis-antithesis-synthesis claim. C3c/C3d carry a "premise not established" note. The M_TAS and M_INEV surface checks now only flag wording for a human to judge (a passage containing a token no longer excuses a use; quoted mentions of "inevitably" are ignored). Nothing here shows a model reasons dialectically.

**Further bounded corrections (provisional):** C3a's scenario no longer contains a rulebook "inconsistency" the two rules do not actually entail (the contents of sign-up sheets and the budget are stated as not supplied); the rulebook case is C3d with its conditions stated (scenario S2b). C1b's "rival interest" explanation is labelled a hypothesis, the internal/external-cause passage is cited to Mao's Section I (not II), and examining that explanatory claim is a dialogue goal, not a per-turn requirement. The Anti-Duhring XII transcription is flagged as losing mathematical notation (other units' formula loss is suspected, not checked). The three cases are a small provisional set of diagnostics, not a definition of dialectical reasoning. The next milestone is an authorized live dialogue against these passages with the transcript reviewed for interpretation and teaching quality; the 274+ tests establish neither.
