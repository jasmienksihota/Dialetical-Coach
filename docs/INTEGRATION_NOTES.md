# Integration candidate notes

Built from design baseline `c0b7107` (Sugar Doodle UI, evidence-carryover fix) plus a **selective** import from the frozen conceptual branch `claude/dm-concepts-eval` at `f07fce2`.

**Imported (runtime):** `app/library.py`, `app/tutor.py`, `app/prompts.py`, `app/demo_script.py`, `app/modes.py` (passage metadata sent to the model with "not recorded" for unknown fields, attribution instruction, wrapper hardening, demo script without keyword-match "assessment", neutral dialectical-mode wording).
**Imported (tests/docs they need):** `tests/test_evidence_metadata.py`, the changed assertion in `tests/test_exercise.py`, and the one-line `docs/INGESTION.md` limit that a test asserts.
**Not imported:** teaching contract, diagnostic rubrics/cases, concept map, `tools/dm_eval.py`, `tests/test_dm_eval_contract.py`, CLAUDE.md/.gitignore changes, all `docs/dialectical/*`. A comment in `app/demo_script.py` still mentions `tools/dm_eval.py`, which is not in this branch.

These prompt changes are unverified against a live model. Automated tests establish structure only, not tutoring quality. The local reference texts / quotation packet are not in GitHub and are not added by this code.
