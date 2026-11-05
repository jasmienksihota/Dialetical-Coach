# Handoff: conceptual branch `claude/dm-concepts-eval` (FROZEN)

**Status: frozen. Keep separate from the design branch (`claude/redesign-notebook`) and the working-preview branch (`claude/tutor-mvp`, base `228563b`). Do NOT merge the whole branch because its tests pass.** No further scaffolding, corpus expansion or paid evaluation without the owner's authorization.

## Candidate and test results
- Branch base: `228563b` (preview with the evidence-carryover fix). Last code-bearing commit: `c62cb3d`; documentation-only commits may follow it. The candidate SHA is the branch tip (`git rev-parse claude/dm-concepts-eval`), stated in the hand-off message.
- Reported at `c62cb3d`: one full `pytest -q` run, 275 passed (includes the 3 browser tests). The final tip's actual run is reported separately; **release decisions must use the final candidate's actual results, not these.**
- **Testing-history disclosure (do not erase):** commit `99f62c4` was pushed with one failing test (`test_no_case_mandates_a_template_or_rewards_vocabulary_or_agreement`): a test regex matched the substring "hypothesis". The cause was in the test, not the case; `c62cb3d` fixes it. The command chain that pushed `99f62c4` hid pytest's exit code. No history rewrite. Do not release from `99f62c4`.
- Automated tests establish structure and contract behaviour only. They do not establish philosophical or teaching quality.

## A. Runtime improvements suitable for separate review and integration (unverified against a live model)
Five small files, none in `app/static` (no UI conflict with the redesign is expected; merge conflicts were not tested):
1. **Evidence metadata** (`app/library.py`, `app/tutor.py`, `app/prompts.py`): each passage sent to the model carries recorded author, title, date, edition, passage ID, location and primary/secondary status; unknown fields read "not recorded" (never guessed); metadata cannot break the passage wrapper; the wrapper states that the app cannot tell an author's text from an editor's/translator's note.
2. **Attribution instruction** (`app/prompts.py`): statements about a text must be attributed to the named author; never guess author, date or edition.
3. **Misleading keyword feedback removed** (`app/demo_script.py`): the scripted demo no longer shows keyword matches as assessment; its hints/analysis/reflection no longer carry developer theory.
4. **Neutral dialectical-mode text** (`app/modes.py`): objective/guidance no longer assert developer-written theory (the `seed_query` is unchanged).
Tests that go with them: `tests/test_evidence_metadata.py`, a changed assertion in `tests/test_exercise.py`. These change live prompts, so review before adopting.

## B. Research and evaluation materials (all PROVISIONAL, AI-assisted, unvalidated)
`docs/dialectical/*` (audit, concept map guide, evaluation design, teaching contract [not wired into prompts], proposed prompt changes, diagnostic packet template, local-probe instructions), `eval/dialectical/*` (concept map skeleton with no passages; 13 invented cases, 3 of them the first diagnostic), `tools/dm_eval.py`, `tests/test_dm_eval_contract.py`. Repo-policy items that could be taken separately: requirement 11 in `CLAUDE.md`, `.gitignore` additions (filled packets, `data-*/`).
- The three diagnostic cases are a small provisional set, **not** a definition of dialectical reasoning. Source-informed corrections have been applied to C3a, C1b and C2a.
- **Known limitations recorded, not fixed:** C3d needs the meeting hours stated as counting toward the same cap (see its `limitation_note`); C3c/C3d premises are `needs_investigation`; M_TAS / M_INEV are token heuristics that only flag wording for a human; *Anti-Dühring* XII loses mathematical notation in transcription (formula loss in other units is suspected, not checked); "logical inconsistency vs contradiction" is `needs_investigation`.
- The populated reference-text packet (46 exact quotations from 15 authorized public units) and the reference copies are **local and git-ignored**; they are not in this branch.

## C. Untested
Live philosophical and teaching behaviour: whether a model uses the passages well, responds to a learner's reasoning, and distinguishes an explanation from terminology. No live call has been made. The next meaningful test is a short, authorized live dialogue against these passages with the transcript reviewed by a human; it needs the owner's key, a provider-side spend limit and explicit authorization.
