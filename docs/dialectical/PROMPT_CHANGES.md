# Proposed prompt and rubric changes

**Status: PROPOSED, not applied** — except P1 (mode text neutralised), P3 (author/date/edition now sent) and P7 (keyword feedback removed), which are applied on this branch and unverified against a real model. The rules in P2/P6 are now organised in `TEACHING_CONTRACT.md` (application rules vs claims needing passages). None has been run against a real model. Applying them changes live
tutoring behaviour, which cannot be verified without the owner's key, a provider-side spend limit and explicit go-ahead.
Evaluate with `docs/dialectical/EVALUATION.md` before adopting.

## P1 — Remove app-authored theory from the dialectical mode (`modes.py`) — PARTLY APPLIED (objective and guidance; `seed_query` unchanged)
Replace `guidance`/`objective`/`seed_query` so the app asserts no theory:
- `objective`: "Practise explaining a situation from its concrete facts, using only concepts the selected passages supply, attributed to their authors."
- `guidance`: "Concepts come from the supplied passages only. Do not introduce a term the passages do not use."
- `seed_query`: taken from the owner-edited `search_term_groups` in `concept_map.json` (several variants, since authors differ).
*Risk:* weaker retrieval if the term lists are poor. *Test:* contract test that no mode text contains a theory claim list (see `tests/test_dm_eval_contract.py`); live behaviour untested.

## P2 — Add a practice block to `EXERCISE_RULES` (`prompts.py`)
```
DIALECTICAL-MATERIALISM PRACTICE (app-created; derive every concept from the supplied passages):
- Use a term (e.g. contradiction, materialism, metaphysical method) only in the sense the supplied passages give it, attributed to the author who gives it. If authors use a term differently, show each. If the passages do not define or discuss a concept, say so in a limits block; do not supply a definition from outside the passages.
- Investigate before naming. Before anything is labelled, ask about: the concrete conditions and facts of this case; how the parties or processes are related and depend on one another; how the situation came about and how it is changing; and what evidence would show two aspects are really opposed rather than merely different.
- Not every case calls for every category. Say plainly when the evidence does not yet justify a category, including "contradiction". Ask what kind of contradiction is being proposed, what concrete relationships the analysis identifies, and what evidence supports it; weigh narrower accounts (a scheduling dispute, a resource tradeoff) without assuming in advance whether the sources count them as dialectical. Naming a category is not explaining a process. Do not claim the texts draw such a distinction unless a supplied passage does.
- No template. Do not use thesis–antithesis–synthesis, or any fixed sequence of stages, unless a supplied passage uses it, and then only as that author's usage.
- Assess the explanation, not the vocabulary. Do not praise or require technical terms. Plain-language reasoning that rests on evidence is as acceptable as technical wording; terminology without case evidence should prompt a request for the facts.
- Do not reward agreement. Accept defensible alternative explanations, including non-dialectical ones, and test the learner's reasoning against the case record and the passages.
- When new facts arrive, ask what they change. Do not treat the first interpretation as settled, or as wrong.
```
*Risk:* a long rules block can crowd the model's attention or be followed only superficially; "ask one question" must still hold. *Test:* contract tests check the text is present and the surface checks run; philosophical performance is untested.

## P3 — Give the model authorship (`prompts.render_passages`) — APPLIED
Add `author`, `date`, `edition` attributes per passage when recorded, and the literal value "not recorded" when missing,
so statements can be attributed and differences noticed. *Risk:* none for privacy (all local metadata the owner entered); longer prompts. *Test:* contract test on rendered prompt.

## P4 — Concept gating (needs a new feature, later)
Load owner confirmations (`data/concept_confirmations.json`); for a `not_addressed` or unresolved concept, the app tells the
model the library does not establish it and requires a `limits` block. Until then, P2's "say so in a limits block" relies
on the passages supplied each turn.

## P5 — Replace the rubric dimensions (`modes.RUBRIC`)
Use the eight dimensions in `eval/dialectical/cases.json` (concrete conditions; relations evidenced; development and
history; basis for opposition shown; alternatives incl. non-dialectical; revision on new evidence; uncertainty and limits;
fidelity to passages and author differences). Labelled app-created, qualitative, no scores.

## P6 — Evaluate evidence, not wording (feedback rules)
Covered by P2. Add a surface check (`tools/dm_eval.py check`) that flags terminology praise, flat "this is a contradiction"
declarations, thesis/antithesis wording absent from the passages, and extra questions. Surface checks are heuristics.

## P7 — Scripted demo feedback (APPLIED on this branch)
Keyword matching is no longer shown to the learner at all: demo feedback is a clearly scripted prompt ("this demo cannot assess your reasoning"), the demo's hint, analysis and reflection text no longer carry developer theory, and the keyword matcher survives only as a diagnostic in `tools/dm_eval.py baseline`.
