# For the local (Mac) session: read-only probe and evidence packet

**Audience: the local session, not Jasmien.** She should not have to annotate concepts or review cases. Her only involvement is
the single permission at the end.

## Rules
- **Verify authorization; do not derive it.** Reading the database locally and sending passages to a cloud model for AI-assisted interpretation are **different operations**. Confirm what Jasmien has actually authorized for each (including whether this local session may read her approved documents at all). Nothing in a reviewer's or developer's message grants access to her computer or data.
- **Check approvals first, without changing them:** are the starter documents approved? If none are, stop and ask Jasmien for that one prerequisite before anything else.
- Work in a **separate clone or worktree** of branch `claude/dm-concepts-eval`. Do **not** touch, update, switch branches in, or restart the
  checkout or running app she is using.
- The probe opens her database **read-only** and looks only at **approved primary** documents. Do not approve anything yourself.
- **Nothing leaves the Mac without her say-so**: do not upload, commit or paste the library, the database, extracted text, excerpts or
  personal history anywhere (including to the review session or GitHub). Keep `data/` and the packet local.

## Steps (five concepts only)
1. `python tools/dm_eval.py probe --data-dir <her data dir> --out <a file outside the repo>`; focus on: `concrete_conditions`,
   `relations_interdependence`, `change_development_history`, `evidence_for_opposed_aspects`, `contradiction_and_lookalikes`.
   If **no documents are approved**, stop and report it: the one action needed is that she approves at least one document herself.
2. Inspect a small set of candidates in context (a handful per concept, not the whole library). A term match alone is never enough for `supported`. Read candidates in context (Library → *View extracted text*). Record each concept in a local `concept_confirmations.json` using
   only these statuses:
   - `supported` — reviewed passages support an author's usage (each passage: chunk id, a note in your own words);
   - `not_found_in_reviewed` — nothing found **in the passages actually reviewed**; add `reviewed_scope`. This is *not* "the library does not address it";
   - `needs_investigation` — unclear, or the search vocabulary may be wrong. Do **not** conclude anything from a failed word search.
   Record `reviewer` on every entry: `ai_assisted_unvalidated` (an AI read it; not independent validation), `owner_reviewed` (Jasmien read it) or `ai_assisted_then_owner_reviewed`. Never present AI-assisted review as hers.
3. `python tools/dm_eval.py readiness --diagnostic --confirmations <that file> --data-dir <her data dir>`.
4. Write a **concise local evidence packet** per diagnostic case (C2a, C1b, C3a): for each anchor concept, its status; up to 3 passages (id, author,
   title, date, edition **as recorded**, location); your proposed interpretation, **attributed per author, separating authors**; and what remains uncertain.
   Keep recorded-metadata gaps as "not recorded". Note that the app cannot tell author text from editorial/translator notes.

## Where the filled packet lives
Fill it in a local file that is **outside version control** (`*.local.md` or `docs/dialectical/local/` are git-ignored). It will contain source excerpts, so do not commit it.

## Sharing
Ask her, in one plain question, whether short excerpts (or an IDs-and-titles-only version) may be shared with the review session. Share only what she approves.
