# Source-Grounded Reasoning and Leadership Tutor

A **personal, local-first** study tutor grounded in a document library **you** approve.
Import PDF / TXT / Markdown, approve what may be used, then chat or run exercises. Answers
come with inspectable, mechanically validated citations, and sessions are saved.

> Personal educational tool. Not for profiling members, ranking loyalty, collecting private
> political information, or automating persuasion.

## Quick start (macOS)

```bash
git clone https://github.com/jasmienksihota/dialetical-coach.git
cd dialetical-coach
git checkout claude/tutor-mvp        # until the branch is merged
./run.sh
```

Open <http://127.0.0.1:8000>. `run.sh` creates `.venv`, installs `requirements.txt`, copies
`.env.example` to `.env` if missing, and starts the app. Requires Python 3.10+
(`python3 --version`; install from python.org or `brew install python` if needed).

Manual equivalent:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app
```

**Windows (PowerShell):**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m app
```

No API key needed to start. Try it immediately: **Library → Load synthetic demo documents →
Approve → Sessions → New exercise** (demo mode is clearly labeled
"Demo: scripted responses, not live tutoring.").

## Using it

1. **Library** – import files, fill in metadata only if you know it (nothing is invented),
   tick any of the 7 topic tags, then **Approve**. New imports are unapproved and never
   retrieved until approved. Scanned/text-empty PDFs show a warning and cannot be approved
   (no OCR). Exact duplicates are detected by SHA-256.
2. **Search** – lexical search over approved documents with document/tag filters; inspect any
   passage with surrounding context and its exact location (physical PDF page, or lines/section).
3. **Sessions → New chat** – choose scope (documents and/or tags) and Demo or Live. Intents:
   Ask, Explain, Compare, Challenge my interpretation, Find disagreements. Each answer shows the
   evidence supplied, with citation chips; use **Flag as unsupported** when a reading overreaches.
4. **Sessions → New exercise** – *Dialectical reasoning* (plus Belief Test, Main Constraint and
   Development Lab on the same engine). The tutor asks one question, waits, gives qualitative
   feedback, probes, introduces a new fact, invites revision, and ends with a reflection. Hint,
   clarify, pause/resume and Show analysis are available.
5. **Export Markdown** – a manual handoff for NotebookLM or another notes tool (see below).

## Live model (optional, opt-in)

Edit `.env` (never commit it):

```
ANTHROPIC_API_KEY=your-key
ANTHROPIC_MODEL=claude-sonnet-5-5      # configurable; NOT verified until a live request succeeds
TUTOR_LIVE_ENABLED=1
```

Also set `TUTOR_LIVE_ENABLED=1` (explicit opt-in). Check the configuration without spending anything:
`python -m app.check`. Restart, then pick **Live model** when creating a session. The model ID has no default on purpose.
Live calls use *your* API balance, which is separate from Claude Code / claude.ai credits.
Selected passages and conversation context are sent to Anthropic in live mode only.
Use the checklist in `docs/LIVE_EVAL_CHECKLIST.md` before trusting live grounding.

### Spending controls — what they do and do not do
The app enforces: explicit opt-in (env flag + per-session acknowledgement), a **daily request cap**
(`TUTOR_LIVE_MAX_REQUESTS_PER_DAY`, default 20, stored in SQLite so restarts don't reset it, every retry and
citation-repair call counts), an **output-token cap** per request (`ANTHROPIC_MAX_TOKENS`, hard ceiling 4096),
a **prompt-size guard**, **bounded retries** (default 1, max 2, each counted), and **token-usage logging**
(counts only) shown in the status badge.
These are brakes on accidents, **not a dollar cap**: cost depends on the model's price and the tokens actually
billed (including input tokens, which this app only roughly bounds), a request that times out client-side may still
be billed, and the app cannot see your balance. The only real ceiling is a billing/spend limit you set with
your provider. The status badge reports three separate facts — API reachable, usable structured output, and a
citation-validated tutoring turn — and only the last may be called verified tutoring (even that checks
citations mechanically, not meaning).

## Choosing sources: documents + tags
Checked documents and checked tags combine as a **union**; the app lists the exact resolved documents (and why each
is in or out) when you choose a scope and at the top of each session. Nothing checked = all approved primary
documents. Ineligible selections never widen the scope.

## NotebookLM relationship

No API integration, no scraping, no login automation. Use the same original files in both
tools and the same seven categories. **Export Markdown** on a session produces reflections and
source references you paste/upload into NotebookLM yourself; import notes back via
Library → "Secondary study notes", which are excluded from retrieval unless a session opts in.
This is a manual handoff, not synchronization.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q                 # everything (browser test auto-skips without Chromium)
pytest -q --ignore=tests/e2e
pytest -q tests/e2e       # browser smoke test; set CHROMIUM_PATH if needed
```

See `docs/BUILD_STATUS.md` for what was actually run and what remains unverified.

## Docs

`docs/REAL_DOCUMENT_ACCEPTANCE.md` (**start here with your own files**) · `docs/ARCHITECTURE.md` · `docs/INGESTION.md` · `docs/PRIVACY.md` · `docs/LIVE_EVAL_CHECKLIST.md` ·
`docs/BUILD_PLAN.md` · `docs/BUILD_STATUS.md` · `CLAUDE.md`

## Known limitations

- **Lexical retrieval only**: matches words (with stemming), not meaning. No synonyms, paraphrase,
  or cross-language matching. A semantic/hybrid retriever can be added behind `retrieval.Retriever`.
- **No OCR**: scanned PDFs are flagged and not indexed. Printed page numbers are never guessed.
- **Extraction heuristics**: running headers/footers are detected and removed (and disclosed); hyphenated line
  breaks are rejoined. Both are heuristics and can be wrong on unusual layouts. Footnotes/tables are not
  recognised; a sentence crossing a page break is split between two passages; column order depends on the PDF.
- **Uncited-claim guard is a pattern check**: it withholds obvious source claims in coaching/fiction/limits
  blocks ("the author argues…") but can miss paraphrase and may occasionally withhold a harmless block.
- **Citations are checked mechanically**, not semantically. A valid citation can still be a bad reading.
- **Evidence policy, not a guarantee**: a live model may still use pretraining knowledge or leak a
  model answer inside free-text feedback; the engine only enforces structure.
- Demo feedback is keyword matching and is not an assessment.
- Single user, no auth: keep it on localhost.
