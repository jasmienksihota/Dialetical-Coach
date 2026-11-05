# Source-ingestion guide

Supported: `.pdf`, `.txt`, `.md`/`.markdown`. Max size `TUTOR_MAX_UPLOAD_MB` (default 25).

1. **Validate** – extension allow-list, size limit, `%PDF-` header for PDFs, no NUL bytes in text,
   topic tags must be one of the seven. Filenames are sanitized and only stored as metadata.
2. **Hash / dedupe** – SHA-256 of the bytes. Document ID = first 12 hex chars, so identical files
   map to the same ID; an exact duplicate is reported and not re-imported.
3. **Extract** – PDFs per *physical* page with `pypdf`; TXT/MD by line. Markdown headings become a
   `§ Heading > Subheading` trail. Encrypted PDFs that need a password are rejected.
   Cleanups applied to PDF text (all heuristic, disclosed in the document's warnings): lines repeated at the
   top/bottom edge of ≥40% of pages (running headers, footers, page numbers; only when ≥4 text pages) are
   removed; `wo-⏎rd` line-end hyphenation is rejoined (lowercase on both sides). Text files that are not UTF-8
   are decoded as Windows-1252 (with a note); Markdown YAML front matter is skipped.
4. **Warn honestly** – no text at all ⇒ status `empty`, cannot be approved (probably scanned, OCR
   not performed). Some pages empty ⇒ status `warning` listing the pages. Non-UTF-8 text ⇒ warning.
5. **Chunk** – ~900-character passages. PDF chunks never cross page boundaries (exact page
   references). TXT/MD line ranges are those of the paragraph(s) the chunk came from. Each chunk
   has a stable ID `<docid>-<ordinal>` and stores neighbouring context for the viewer.
6. **Store** – originals at `data/originals/<sha256>.<ext>`, text in `data/tutor.db`; both are
   git-ignored. Imports start **unapproved**.

Metadata you know (title, author, date, edition/translation) can be added at import or later;
blank fields stay blank. For PDFs you may set a *printed page offset* (printed = PDF page + offset);
it is never guessed. Notes exported from NotebookLM go in as **secondary study notes**.

**Known limits:** the app does not distinguish an author's own text from an editor's or translator's notes inside a document (only primary vs secondary-notes documents are distinguished), and recorded author/date/edition are passed to the model exactly as entered ('not recorded' when blank); footnotes, tables and multi-column reading order are whatever the PDF's text layer gives;
chunks never cross a PDF page break, so a phrase straddling it is split between two passages; for TXT/MD, a
passage's line range covers the lines it was built from (a long run without blank lines is split by line, so
ranges stay tight). Check any document with `python tools/inspect_import.py file.pdf --probe 12:"phrase"` and
see `docs/REAL_DOCUMENT_ACCEPTANCE.md`.

Tips: use text-based PDFs; if a PDF is scanned, run OCR elsewhere and import the result.
Vocabulary matters because retrieval is lexical.
