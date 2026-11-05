# For the local (Mac) session: read-only probe and evidence packet

**Audience: the local session, not Jasmien.** She should not have to annotate concepts or review cases. Her only involvement is
the single permission at the end.

## Rules
- Work in a **separate clone or worktree** of branch `claude/dm-concepts-eval`. Do **not** touch, update, switch branches in, or restart the
  checkout or running app she is using.
- The probe opens her database **read-only** and looks only at **approved primary** documents. Do not approve anything yourself.
- **Nothing leaves the Mac without her say-so**: do not upload, commit or paste the library, the database, extracted text, excerpts or
  personal history anywhere (including to the review session or GitHub). Keep `data/` and the packet local.

## Steps (five concepts only)
1. `python tools/dm_eval.py probe --data-dir <her data dir> --out <a file outside the repo>`; focus on: `concrete_conditions`,
   `relations_interdependence`, `change_development_history`, `evidence_for_opposed_aspects`, `contradiction_and_lookalikes`.
   If **no documents are approved**, stop and report it: the one action needed is that she approves at least one document herself.
2. Read candidates in context (Library → *View extracted text*). Record each concept in a local `concept_confirmations.json` using
   only these statuses:
   - `supported` — reviewed passages support an author's usage (each passage: chunk id, a note in your own words);
   - `not_found_in_reviewed` — nothing found **in the passages actually reviewed**; add `reviewed_scope`. This is *not* "the library does not address it";
   - `needs_investigation` — unclear, or the search vocabulary may be wrong. Do **not** conclude anything from a failed word search.
   Mark the reviewer as `AI-assisted, not independently validated`.
3. `python tools/dm_eval.py readiness --diagnostic --confirmations <that file> --data-dir <her data dir>`.
4. Write a **concise local evidence packet** per diagnostic case (C2a, C1b, C3a): for each anchor concept, its status; up to 3 passages (id, author,
   title, date, edition **as recorded**, location); your proposed interpretation, **attributed per author, separating authors**; and what remains uncertain.
   Keep recorded-metadata gaps as "not recorded". Note that the app cannot tell author text from editorial/translator notes.

## Sharing
Ask her, in one plain question, whether short excerpts (or an IDs-and-titles-only version) may be shared with the review session. Share only what she approves.
