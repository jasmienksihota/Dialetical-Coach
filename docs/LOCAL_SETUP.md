# Local setup on a Mac (no API key needed)

Everything below works offline in **demo mode**. No paid API calls are made.

## 1. Get the branch
Open **Terminal** (Cmd+Space, type "Terminal"). Check git and Python exist:
```bash
git --version
python3 --version
```
If either is missing, macOS offers to install the developer tools — accept, wait, re-run. You need Python 3.10 or newer.
```bash
cd ~/Documents
git clone --branch claude/tutor-mvp https://github.com/jasmienksihota/dialetical-coach.git
cd dialetical-coach
```
(The branch isn't merged to `main` yet, hence `--branch claude/tutor-mvp`.) If you already cloned: `git fetch origin && git checkout claude/tutor-mvp && git pull`.

## 2 + 3 + 4. Install, start, open
```bash
./run.sh
```
`run.sh` creates a private `.venv/` folder, installs `requirements.txt`, copies `.env.example` to `.env`, and starts the app. Leave that Terminal window open. When you see
`Source-Grounded Tutor -> http://127.0.0.1:8000   [demo mode only ...]`, open **http://127.0.0.1:8000** in your browser. The top-right badge should say "Demo mode only — live not configured".
If `./run.sh` says "permission denied": `chmod +x run.sh` then retry. To stop: press **Ctrl+C**. To start again later: `./run.sh` (or `source .venv/bin/activate && python -m app`).

Manual equivalent if `run.sh` fails:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app
```

## 5. Import, approve, search
1. **Library** tab → *Import a document* → **Choose File** (PDF, .txt, .md) → optionally fill Title/Author/Date/Edition (leave blank if unknown) and tick topic tags → **Import (unapproved)**.
2. Check the card: "text extracted" is good; a yellow warning (e.g. scanned PDF, missing pages) means text is missing. **View extracted text** shows exactly what the app will search; compare with your PDF.
3. Click **Approve for use**. Unapproved documents are never searched or cited.
4. **Search** tab → type words that appear in the text (matching is by words, not meaning) → **Search** → **Inspect passage** to see the exact location (PDF page number or lines).
Try it risk-free first: Library → **Load synthetic demo documents** (invented test texts), approve them, search "contradiction conditions".

## 6. Your data and backup
Everything private lives in the **`data/`** folder inside the repository folder (e.g. `~/Documents/dialetical-coach/data`): `data/originals/` (your imported files, renamed by hash), `data/tutor.db` (extracted text, sessions, flags). It's git-ignored. Open it in Finder: `open data`.

Back up (stop the app first with Ctrl+C):
```bash
cd ~/Documents/dialetical-coach
cp -R data ~/Documents/tutor-backup-$(date +%Y-%m-%d)
```
Restore: stop the app, move the current `data` aside, copy the backup back as `data`. Your `.env` (if you add a key later) is separate: back it up privately and never share it.

## Adding a key later (not required now)
Open `.env` in a text editor (`open -e .env`), paste the key after `ANTHROPIC_API_KEY=`, set `TUTOR_LIVE_ENABLED=1`, save, restart. Check without spending anything: `python -m app.check`. Do not paste the key into chats or commit `.env`.
