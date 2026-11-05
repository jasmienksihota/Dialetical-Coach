# Concept map (skeleton) — questions to put to YOUR approved library

`eval/dialectical/concept_map.json` is an **app-created skeleton**. It contains **no source passages and no claims
about what any author says.** It lists the concepts the learning goal needs and, for each, the *question to ask the
library*, search-term variants for finding candidate passages, and a neutral framing question the tutor may pose.
Passage-level support can only come from documents *you* approved, confirmed *by you*.

Passage support is currently **none** for every concept (status `unsupported`). Nothing was added, downloaded or
approved to change that.

| Concept id | Question put to the library |
|---|---|
| `materialism_idealism` | What does each selected author treat as primary, and why? |
| `dialectical_vs_metaphysical_method` | How does each author characterise the two methods, in their own usage? |
| `cartesian_mind_body_dualism` | Do the texts discuss mind–body dualism / Descartes at all, and how do they relate it to the other two? |
| `contradiction_and_lookalikes` | What do the texts say a contradiction is, and do they distinguish it from disagreement, tradeoff or logical inconsistency? |
| `concrete_conditions` | What do they say about studying the specific conditions of a case first? |
| `relations_interdependence` | How do they describe things as connected and dependent on each other? |
| `change_development_history` | How do they treat change, development and historical formation? |
| `evidence_for_opposed_aspects` | What would show, in a concrete case, that an identified contradiction is really present? |
| `author_differences` | Where do the selected authors differ in terms, emphasis, context or conclusions? |

## Keeping the four distinctions apart
1. **Materialism / idealism** is one question (what is primary, per each author).
2. **Dialectical / metaphysical method** is a different question (how things are to be studied, per each author's *own* usage; usages may differ).
3. **Cartesian mind–body dualism** is a third question (how mind and body relate in one individual). Whether the library addresses it at all is itself a finding. If it does not, the tutor must say the library does not establish it — it must not fill the gap with outside knowledge presented as a source claim.
4. **Contradiction vs look-alikes.** The app's *teaching contrasts* (mere disagreement, practical tradeoff, logical inconsistency) are used to ask "what evidence would distinguish these here?". They are **not** claims about the authors; the tutor may say the texts draw a contrast only if a confirmed passage does.

## How support gets attached (all local, all by you)
```bash
python tools/dm_eval.py probe --out data/concept_review.sheet.md     # read-only candidates from APPROVED docs
# read the passages in context; then YOU write data/concept_confirmations.json:
#   {"concepts": {"materialism_idealism": {"status": "confirmed", "reviewed": "2026-11-05",
#       "passages": [{"chunk_id": "<id>", "author": "<name>", "note": "what it shows, in your words"}]},
#     "cartesian_mind_body_dualism": {"status": "not_addressed", "reviewed": "2026-11-05"}}}
python tools/dm_eval.py readiness                                        # which cases are now traceable
```
`probe` opens the database **read-only**, looks only at approved primary documents, and never approves, edits or
imports anything. A candidate is a word match, not support. `confirmed` requires passage IDs that exist, belong to
approved primary documents, and carry your own note. `not_addressed` records that you reviewed and the library does
not cover the concept (which is what the tutor must then say).

Both files with excerpts/confirmations live under `data/` (git-ignored).
