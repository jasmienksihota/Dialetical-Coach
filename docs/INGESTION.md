# Source-ingestion guide

Supported: `.pdf`, `.txt`, `.md`/`.markdown`. Max size `TUTOR_MAX_UPLOAD_MB` (default 25).

1. **Validate** – extension allow-list, size limit, `%PDF-` header for PDFs, no NUL bytes in text,
   topic tags must be one of the seven. Filenames are sanitized and only stored as metadata.
2. **Hash / dedupe** – SHA-256 of the bytes. Document ID = first 12 hex chars, so identical files
   map to the same ID; an exact duplicate is reported and not re-imported.
3. **Extract** – PDFs per *physical* page with `pypdf`; TXT/MD by line. Markdown headings become a
   `§ Heading > Subheading` trail. Encrypted PDFs that need a password are rejected.
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

Tips: use text-based PDFs; if a PDF is scanned, run OCR elsewhere and import the result.
Vocabulary matters because retrieval is lexical.
