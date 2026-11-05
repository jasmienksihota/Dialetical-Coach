# Real-document acceptance checklist

**Purpose:** establish that the app works on YOUR documents before you rely on it. Automated tests use
only invented fixtures, so they cannot tell you this. No live API call or key is needed for any step
(demo mode is enough). Do the steps in order; record results in the table at the end.

**Privacy:** results are counts, page numbers and short phrases. Don't paste copyrighted or private
text into chats or issues; describe the failure ("page 41 missing", "headers included") instead.

## 0. Prepare (10 minutes)
Pick **at least four** files you actually plan to use:
- **A** a text-based PDF with page numbers (ideally with footnotes and a header/footer),
- **B** a second document on an overlapping topic (PDF, TXT or MD),
- **C** a TXT or Markdown file (e.g. copied from a web page),
- **D** if you have one: a scanned or partly scanned PDF.

Use a separate data folder so practice never mixes with your real library:
```bash
cd ~/Documents/dialetical-coach
TUTOR_DATA_DIR=./data-acceptance ./run.sh          # (data-*/ is git-ignored)
```
(When finished, stop with Ctrl+C and delete `data-acceptance`, or keep it as a scratch library.)

## 1. Extraction quality — per file, BEFORE importing in the app
```bash
source .venv/bin/activate
python tools/inspect_import.py ~/path/to/fileA.pdf
```
It imports into a throw-away database and prints diagnostics. For each file check:

| Check | Pass when |
|---|---|
| Status | `ok`, or `warning` you can explain. `empty` = no text (scanned; OCR is not done) |
| PDF pages with NO indexed text | 0, or only pages you know are blank/images |
| Replacement characters (�) | 0 |
| Leftover hyphen breaks | ~0 (a handful is fine) |
| Same-start passages | none repeated ≥3× (that means headers/footers survived) |
| Sample passages | read three against the original: text is complete, in reading order, not interleaved across columns |
| "Note: removed … header/footer" | if present, open the doc in the app → *View extracted text* and confirm nothing real was removed |

Also in the app (Library → *View extracted text*): skim a page with a footnote, a table, a quotation
and a two-column spread. **Known limits:** footnotes and tables are indexed as ordinary text; a sentence
that crosses a page break is split between two passages; column order depends on how the PDF was made.

## 2. Page / line references
Pick **five phrases per PDF** from different physical pages (first, last, middle, a page with a
footnote, a two-column page). Copy 6–10 words exactly as printed. Physical page = the number your PDF
viewer shows, not the number printed on the page.
```bash
python tools/inspect_import.py fileA.pdf --probe 1:"first words here" --probe 87:"phrase from page 87" --probe 203:"..."
python tools/inspect_import.py fileC.txt --probe L40:"phrase from line 40"
```
Pass = every probe says `PASS`. Then in the app: Search the same phrase → *Inspect passage* → the label
must read `PDF p. N`. If the book's printed numbers differ, set *Printed page = PDF page + offset* in
Library → Edit and confirm the label shows `(printed p. M)`. The app never guesses printed numbers.

## 3. Approval filtering (in the app)
1. Import file A (tag it). Search a distinctive phrase → **no results** (unapproved).
2. Approve → same search finds it. Unapprove → no results again.
3. Approve A and B. Create a chat with scope = **only A** → ask a question B answers better. The
   evidence list must contain only A. Check the *Documents in scope right now* list at the top.
4. Select a tag shared by both → both appear, each with `tag: …` as the reason (UNION rule).
5. Select an unapproved document → it is listed as "NOT included (not approved)" and nothing falls back to "all".
6. Import a note as *Secondary study notes*: absent from results unless you tick "Include secondary".

## 4. Multi-document retrieval
Choose a phrase/concept that both A and B discuss. Search: results should come from **both** (check
the document name on each hit). Chat → *Compare across texts*: the answer should quote both and the
"synthesis" block must cite both. New exercise with "require ≥2 documents": it should start; with only
A selected it must warn and offer single-source. If retrieval misses a document because the other text
uses different WORDS, that is the known lexical limit — note it (see §7).

## 5. Citation inspection
In any demo answer: click every citation chip → the passage opens with context → confirm the quotation
appears **verbatim** and the location label is right. Click *Flag as unsupported* on one → export the
session and confirm it appears under "Flagged for review". Remember: the app proves the quote exists and
the passage was in scope; **you** judge whether it supports the claim. (Demo mode's "interpretations" are
scripted placeholders — they exist to exercise the machinery, not to evaluate meaning.)

## 6. Insufficient evidence
- Ask about something your library does not cover (e.g. a topic from an unrelated field) → expect an
  app message saying no passages matched; **no** model-style answer from outside knowledge.
- Ask with a vague one-word query → expect a weak-evidence / limits notice.
- Compare with only one relevant document → expect "needs two documents", not a made-up comparison.
- After an answer ask "Give another example" repeatedly → eventually "no further relevant passages…".
- Unapprove the document mid-conversation, ask a follow-up → expect "No approved documents…".

## 7. Record results
| # | Check | File | Result (pass/fail) | Notes (page numbers, counts — no text) |
|---|---|---|---|---|
| 1 | Extraction status/warnings | A | | |
| 1 | Header/footer, hyphens, columns | A | | |
| 1 | Encoding / quotes | C | | |
| 1 | Scanned detection | D | | |
| 2 | 5 page probes pass | A | | |
| 2 | Line probes pass | C | | |
| 2 | Printed-page offset label | A | | |
| 3 | Unapproved not searchable | A | | |
| 3 | Scope restricts to one doc | A,B | | |
| 3 | Tag union list correct | A,B | | |
| 4 | Results from both docs | A,B | | |
| 4 | Compare cites both | A,B | | |
| 5 | Quotes verbatim, labels right | any | | |
| 5 | Flag appears in export | any | | |
| 6 | Absent topic → no-evidence message | any | | |
| 6 | Compare w/ 1 doc → refusal | any | | |
| 6 | "Another example" exhaustion | any | | |

**If something fails:** note the check number, the file type, and what you saw (e.g. "PDF p. 41 contains
the running header", "phrase from p. 87 reported on p. 88"). Those observations decide the next
milestone (OCR, column handling, semantic retrieval, …) — see `docs/BUILD_STATUS.md`.

**What passing does NOT show:** that live-model answers are well grounded (use
`docs/LIVE_EVAL_CHECKLIST.md`, which needs your key and spend), that retrieval finds paraphrases, or
that citations semantically support claims.
