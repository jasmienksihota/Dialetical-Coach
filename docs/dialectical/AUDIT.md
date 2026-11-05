# Audit: how the app currently supports dialectical materialism

**Core requirement:** the app must support *learning and practising dialectical materialism from the owner's
approved sources*. Nothing below shows that it does. "Dialectical" appearing in a prompt, citations passing
mechanical checks, and scripted exercises running are not evidence of that goal.

**Scope of this audit:** the code and prompts on branch point `228563b` plus the synthetic fixtures. **No real
approved library exists in this workspace** (it lives on the owner's Mac), so nothing here has been checked against
real passages, and no claim is made about what any author says.

## What the approved-source workflow does today
import → *owner approves* → lexical retrieval (SQLite FTS5, word matching) from approved primary documents in the
selected scope → passages placed in the user turn → model returns typed blocks → mechanical citation checks. The
workflow is subject-agnostic. All "dialectical" content comes from three app-authored places: `app/modes.py`
(the `dialectical` mode), `app/prompts.py` (`EXERCISE_RULES`), and `app/demo_script.py` (scripted feedback).

## Findings
| # | Finding (file) | Why it matters |
|---|---|---|
| F1 | `modes.py` `dialectical.guidance` ("how change arises from relationships and tensions inside a situation and from outside conditions, and how the main issue can shift") and `seed_query` ("contradiction tension internal external conditions…") are **theory written by the app's developer**, not derived from passages. | It silently imposes one framing (and one vocabulary) on every author, contrary to "derive concepts from retrieved texts" and "preserve differences among authors". |
| F2 | My invented fixture `synthetic_a_mill_town_notes.md` uses the same ideas ("principal", internal/external causes). | Circular: the fixtures echo the prompt, so tests built on them cannot show the prompt is source-grounded. |
| F3 | The rubric (`modes.RUBRIC`, six dimensions) is generic critical thinking. | It has no dimension for concrete conditions, history/development, evidenced opposition, or fidelity to the authors. |
| F4 | `EXERCISE_RULES` already forbids a thesis–antithesis–synthesis formula and says to derive concepts from passages — but says nothing about *not forcing every category*, *contradiction vs disagreement / tradeoff / inconsistency*, *evidence for opposed aspects*, *not rewarding terminology*, or *author differences*. | Items 3–8 of the requirement are unaddressed in the live prompt. |
| F5 | `demo_script.py` keyword feedback listed matches as "**Visible in your answer**". Measured with `python tools/dm_eval.py baseline` on the invented cases: keywords matched in the empty-jargon response (C2a: relationships) and the premature-"contradiction" responses (C3a/C3c: causal, relationships), but **nothing** matched in the best-supported revision (C4b), and only one keyword in the best relational analysis (C1b). | The script cannot separate jargon from reasoning and its wording read as approval of vocabulary. **Wording fixed on this branch** ("Keyword matches … does not show an idea is supported"); it still assesses nothing. |
| F6 | `prompts.render_passages` sends document title, location and kind — **not author, date or edition** even when recorded. | The model cannot attribute a statement to an author or notice that two authors differ. |
| F7 | Retrieval is lexical and the seed vocabulary is fixed. | Authors and translations use different words; a fixed term list can miss a concept or imply it is absent. |
| F8 | The block type `synthesis` (cross-document comparison) shares a name with dialectical "synthesis". The UI label is "Synthesis across texts". | Possible learner confusion; no change made. |

Not found / not established: whether the owner's real texts define or discuss any of these concepts; how any real
model behaves on the proposed prompts.
