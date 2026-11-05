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
ANTHROPIC_MODEL=<model id from Anthropic's current documentation>
```

Restart, then pick **Live model** when creating a session. The model ID has no default on purpose.
Live calls use *your* API balance, which is separate from Claude Code / claude.ai credits.
Selected passages and conversation context are sent to Anthropic in live mode only.
Use the checklist in `docs/LIVE_EVAL_CHECKLIST.md` before trusting live grounding.

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

`docs/ARCHITECTURE.md` · `docs/INGESTION.md` · `docs/PRIVACY.md` · `docs/LIVE_EVAL_CHECKLIST.md` ·
`docs/BUILD_PLAN.md` · `docs/BUILD_STATUS.md` · `CLAUDE.md`

## Known limitations

- **Lexical retrieval only**: matches words (with stemming), not meaning. No synonyms, paraphrase,
  or cross-language matching. A semantic/hybrid retriever can be added behind `retrieval.Retriever`.
- **No OCR**: scanned PDFs are flagged and not indexed. Printed page numbers are never guessed.
- **Citations are checked mechanically**, not semantically. A valid citation can still be a bad reading.
- **Evidence policy, not a guarantee**: a live model may still use pretraining knowledge or leak a
  model answer inside free-text feedback; the engine only enforces structure.
- Demo feedback is keyword matching and is not an assessment.
- Single user, no auth: keep it on localhost.
