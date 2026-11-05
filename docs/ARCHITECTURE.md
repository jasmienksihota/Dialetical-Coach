# Architecture

```
Browser (vanilla JS)  ──HTTP/JSON──>  FastAPI (app/main.py, localhost-only guard)
                                         │
      ┌──────────────┬─────────────┬─────┴────────┬───────────────┐
   ingest.py     library.py    retrieval.py   tutor.py        exercises.py
   (extract,     (CRUD,        (Scope, FTS5   (chat turn,      (state machine,
    chunk,        approval,     / fallback,    generate →       purpose gating,
    dedupe)       locations)    Retriever)     validate →       one question,
                                               repair → save)   reflection)
                                         │              │
                                    citations.py   providers.py ── MockProvider (demo_script.py)
                                  (mechanical     (interface)   └─ AnthropicProvider (SDK, env key)
                                   validation)
                          SQLite (data/tutor.db): documents, chunks, chunks_fts,
                          conversations, messages(evidence, report), flags
```

**One approval gate.** `retrieval.resolve_scope` is the only place that decides which documents
are eligible (approved, primary unless opted in, selected docs ∪ tags). Retrievers and the
chunk-fetch used for carry-over evidence all restrict themselves to its result, and the citation
validator re-checks approval/scope at validation time.

**Turn pipeline (chat).** scope → bounded history (+ app-made summary) → retrieve (re-using prior
cited passages for follow-ups) → *no model call* if nothing relevant / compare impossible →
prompt (system = policy + scope; user turn = passages wrapped as untrusted data) → provider returns
typed blocks → `citations.validate_blocks` → at most one repair → `finalize` (invalid blocks are
withheld) → persist user + assistant message with the evidence snapshot and validation report.

**Block types.** quote, interpretation, synthesis, fiction, coaching, limits (+ exercise `purpose`
labels). The UI colors and labels each, so quotation, interpretation, synthesis, fiction and
app-authored coaching are visibly separate.

**Exercise engine.** State JSON on the conversation (`phase`, attempts, hints, basis passage IDs,
reflection, analysis only after it is requested). `exercises.RULES` lists the allowed `purpose`
values per action; other blocks are stripped, extra questions dropped, and a missing question is
replaced by an app-authored one. Modes are data (`modes.py`), so all four share the engine.

**Providers.** `Provider.generate(GenRequest) -> {blocks}`. The Anthropic adapter forces a
`submit_response` tool call for structured output, maps SDK errors to user-safe messages, and
redacts the key. The mock provider is deterministic and labeled.

**Swapping retrieval.** Implement `retrieval.Retriever.search(...)` (respecting `resolve_scope`) and
return it from `get_retriever`.

## Additions after the first review
- **Scope transparency:** `retrieval.explain_scope` (and `POST /api/scope/resolve`) returns the resolved document
  list with reasons; every assistant turn records `report.scope` (documents in scope that turn).
- **Uncited-claim guard** (`citations.detect_uncited_source_claim`): pattern checks for source claims in
  coaching/fiction/limits blocks; fiction may not cite. Heuristic, not proof of anything.
- **Live stages** (`livecontrol.LiveGuard`): `live_calls.status/structured/citations_ok` keep "API reachable",
  "usable structured output" and "citation checks passed" (mechanical only) separate.
- **Follow-ups** (`followup.py`): short messages are expanded with the last *substantive* question; "another/different"
  excludes passages already used; everything stays inside `resolve_scope`.
