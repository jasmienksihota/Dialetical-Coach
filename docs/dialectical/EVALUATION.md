# Evaluation: what is tested, what is not

## The set
`eval/dialectical/cases.json`: **13 cases, all INVENTED** (scenarios, learner responses and "new facts" written by the
app's developer; none from a source, author or real event), in paired contrasts:
| Pair | Contrast |
|---|---|
| P1 (C1a/C1b) | static, isolated analysis ↔ relational and developmental analysis |
| P2 (C2a/C2b) | impressive but empty dialectical vocabulary ↔ plain-language substantive analysis |
| P3 (C3a–C3d) | contradiction claimed but not yet justified ↔ restrained reading; plus tradeoff and logical-inconsistency look-alikes |
| P4 (C4a/C4b) | new evidence not integrated ↔ new evidence revising the interpretation |
| K (K1–K3) | concept probes: materialism/idealism, dialectical/metaphysical method, Cartesian dualism |

The rubric is an **app-created learning aid, not a canonical standard**; qualitative; no scores. Every case is marked
`owner_review: pending`: the drafter's pairings and expectations may be wrong and need your edits.

## First live run: a small three-case diagnostic (not the full set)
Only **C2a** (terminology without explanation), **C1b** (plain-language relational/developmental analysis) and **C3a** (contradiction claimed, not yet justified) — see `DIAGNOSTIC_PACKET.md`. Worst case with defaults is ~12 requests (3 turns × (1 answer + 1 repair) × (1 + 1 retry)); a request count, not a dollar figure. The full 13-case set is a later step. **A live run needs separate spending authorization and has not happened.** At best it shows whether, on these three cases, the tutor asks for evidence and avoids rewarding jargon; it would not show the tutor understands dialectical materialism.

## Success / failure criteria
Each case lists `tutor_should` and `tutor_should_not`, each tagged:
- `mechanical:M_*` — a surface check in `tools/dm_eval.py check` (thesis/antithesis wording absent from the passages; terminology praise;
  flat "this is a contradiction" declarations; "inevitably"; more than one question; missing limits block). **Heuristics**: a pass shows only that
  these patterns were absent.
- `human` — needs a person to read the tutor output (e.g. "asks what evidence would show the two interests are opposed").
A case **passes** only if every mechanical check passes **and** a human rater marks each `human` criterion met and no
`tutor_should_not` triggered. Report per-criterion counts; there is no aggregate score or ranking.

## Traceability to sources
Expected behaviours that depend on what authors say are valid only after a reviewer records reviewed passages (`supported`) or what was reviewed without finding any (`not_found_in_reviewed`)
for the case's anchor concepts. `python tools/dm_eval.py readiness` lists which cases are READY. **Currently 0/13**, because no
passages are confirmed, and none can be from this workspace.

## Not sufficient as proof
The same model's approval of its own output is **never** sufficient. A live run needs: (1) mechanical checks; (2) a human
rater who sees the paired outputs in random order without knowing which case is the "better" one and records quoted evidence for
each judgement; (3) you checking cited passages against the originals; (4) optionally a second model as a *supplementary* judge,
with disagreements logged — never the sole or deciding evidence.

## What is verified by automated tests (contract level, run in CI)
`tests/test_dm_eval_contract.py`: the files parse; every case is labelled invented and carries criteria, anchors and an owner-review flag;
the concept map has no source text; the five requested example types exist in pairs; real author names appear only in concept probes;
`probe` is read-only and uses approved primary documents only; `readiness` rejects unapproved, missing, secondary-note and unannotated
passages, and `not_found_in_reviewed` without a `reviewed_scope`; the surface checks behave as specified; the demo wording does not call keyword matches evidence. These verify **structure and
honesty of the materials**.

## NOT verified (no live run has occurred)
Whether any model, with any prompt in `PROMPT_CHANGES.md`, actually: investigates conditions rather than naming categories; withholds
"contradiction" when unjustified; avoids rewarding terminology; keeps authors' usages apart; says "insufficient evidence" for concepts
the library lacks; or revises appropriately. **Philosophical performance is untested.** No model was retrained or fine-tuned; this work only
changes prompts, data and checks.

## Cost note for a future live run
The full set (13 cases × 1 turn) would be ≈52 requests at worst; the default daily cap is 20. Start with the three-case diagnostic (≈12). These are request counts, not dollars; set a
provider-side spend limit first. Not run; needs your explicit go-ahead.
