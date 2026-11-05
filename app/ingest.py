"""Document ingestion: validation, extraction, chunking, de-duplication.

Design notes
- Originals are stored as ``data/originals/<sha256><ext>``; the user-supplied filename
  is only metadata (sanitized) and never used as a path.
- PDF text is extracted per *physical* page. Printed page numbers are not guessed;
  an optional per-document offset can be set by the owner.
- Text-empty / mostly-empty PDFs get a visible warning. OCR is not performed.
- Chunks never cross PDF page boundaries, so page references are exact.
  For TXT/MD, line numbers refer to the paragraph(s) the chunk was built from.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

from .config import TAG_SLUGS, Settings
from .db import Database
from .errors import AppError

ALLOWED_EXTS = {".pdf": "pdf", ".txt": "txt", ".md": "md", ".markdown": "md"}
MIN_PAGE_CHARS = 25          # fewer non-space chars => page counts as "no text"
MIN_PARA_CHARS = 15          # ignore tiny fragments (page numbers, stray marks)
TARGET_CHUNK = 900
HARD_CHUNK = 1400
CONTEXT_CHARS = 300


class IngestError(AppError):
    pass


@dataclass
class Para:
    text: str
    page: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    section: str | None = None


@dataclass
class Chunk:
    text: str
    page: int | None
    section: str | None
    line_start: int | None
    line_end: int | None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sanitize_filename(name: str) -> str:
    name = (name or "").replace("\\", "/").split("/")[-1]
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"[^\w.\- ()]", "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name or "unnamed")[:150]


def _nonspace(s: str) -> int:
    return len(re.sub(r"\s", "", s))


# --------------------------------------------------------------------------- extraction
def extract_pdf(data: bytes):
    """Return (paras, page_count, warnings, pages_with_text)."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                ok = reader.decrypt("")
            except Exception:  # noqa: BLE001
                ok = 0
            if not ok:
                raise IngestError("The PDF is password-protected; it cannot be read.")
        pages = list(reader.pages)
    except IngestError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise IngestError(f"Could not read this PDF ({type(exc).__name__}).") from exc

    warnings: list[str] = []
    raw_pages: list[str] = []
    for number, page in enumerate(pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Page {number}: text extraction failed ({type(exc).__name__}).")
            text = ""
        raw_pages.append(text.replace("\x00", "").replace("\r", ""))

    raw_pages, removed = _strip_running_lines(raw_pages)
    if removed:
        shown = "; ".join(f"“{t[:50]}”" for t in removed[:3])
        warnings.append(f"Note: removed {len(removed)} repeated header/footer line pattern(s) at page edges "
                        f"from the indexed text (e.g. {shown}). Check “View extracted text” if something "
                        "important is missing.")

    paras: list[Para] = []
    empty_pages: list[int] = []
    pages_with_text = 0
    for number, text in enumerate(raw_pages, start=1):
        if _nonspace(text) < MIN_PAGE_CHARS:
            empty_pages.append(number)
        else:
            pages_with_text += 1
        for block in re.split(r"\n\s*\n", text):
            block = _HYPHEN_BREAK.sub("", block)          # "evi-\ndence" -> "evidence"
            block = re.sub(r"\s*\n\s*", " ", block).strip()
            if _nonspace(block) >= MIN_PARA_CHARS:
                paras.append(Para(text=block, page=number))

    total = len(pages)
    if total == 0:
        raise IngestError("The PDF has no pages.")
    if pages_with_text == 0:
        warnings.insert(0, (
            "No extractable text found. This PDF is probably scanned images. OCR was "
            "NOT performed, so nothing from it can be searched or cited."))
    elif pages_with_text < total:
        shown = ", ".join(str(p) for p in empty_pages[:20])
        more = " …" if len(empty_pages) > 20 else ""
        share = len(empty_pages) / total
        if share >= 0.2 and len(empty_pages) >= 2:
            warnings.insert(0, (
                f"Only {pages_with_text} of {total} pages contain extractable text "
                f"(little or no text on physical page(s): {shown}{more}). Those pages are not indexed; "
                "the document may be partly scanned."))
        else:   # a few blank / near-empty pages are normal (chapter ends, plates); disclose, don't alarm
            warnings.insert(0, (
                f"Note: {len(empty_pages)} of {total} pages have little or no extractable text "
                f"(physical page(s): {shown}{more}); probably blank or image-only."))
    return paras, total, warnings, pages_with_text


_HYPHEN_BREAK = re.compile(r"(?<=[a-z])-[ \t]*\n[ \t]*(?=[a-z])")


def _edge_key(line: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", line.lower())).strip()


def _strip_running_lines(pages: list[str]) -> tuple[list[str], list[str]]:
    """Remove running headers / footers / page numbers: lines that recur at the top or
    bottom edge (first/last two non-empty lines) of at least 40% of the text pages."""
    if sum(1 for p in pages if _nonspace(p) >= MIN_PAGE_CHARS) < 4:
        return pages, []
    edges: list[set[str]] = []
    for text in pages:
        lines = [ln for ln in text.split("\n") if ln.strip()]
        edge = lines[:2] + lines[-2:] if len(lines) > 4 else lines[:1] + lines[-1:]
        edges.append({_edge_key(ln) for ln in edge if len(ln.strip()) < 120})
    counts: dict[str, int] = {}
    for e in edges:
        for k in e:
            counts[k] = counts.get(k, 0) + 1
    need = max(3, int(0.4 * len(pages) + 0.999))
    repeated = {k for k, v in counts.items() if v >= need and k}
    if not repeated:
        return pages, []
    out, examples = [], {}
    for text in pages:
        lines = text.split("\n")
        idx = [i for i, ln in enumerate(lines) if ln.strip()]
        cand = set(idx[:2] + idx[-2:]) if len(idx) > 4 else set(idx[:1] + idx[-1:])
        keep = []
        for i, ln in enumerate(lines):
            k = _edge_key(ln)
            if i in cand and k in repeated:
                examples.setdefault(k, ln.strip())
                continue
            keep.append(ln)
        out.append("\n".join(keep))
    return out, list(examples.values())


_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def extract_text(data: bytes, file_type: str):
    """Return (paras, warnings). Line numbers are 1-based physical lines of the file."""
    if b"\x00" in data[:8192]:
        raise IngestError("This file contains binary data and is not a text file.")
    warnings: list[str] = []
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("cp1252")
            warnings.append("Note: file is not UTF-8; it was decoded as Windows-1252. Check quotes and "
                            "accented letters in “View extracted text”.")
        except UnicodeDecodeError:
            text = data.decode("utf-8", errors="replace")
            warnings.append("File is not valid UTF-8 or Windows-1252; undecodable bytes were replaced.")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    first = 0
    if file_type == "md" and lines and lines[0].strip() == "---":       # YAML front matter
        for j in range(1, min(len(lines), 60)):
            if lines[j].strip() in ("---", "..."):
                first = j + 1
                break

    paras: list[Para] = []
    trail: list[tuple[int, str]] = []
    buf: list[tuple[int, str]] = []          # (1-based line number, text)

    def section() -> str | None:
        return " > ".join(t for _, t in trail) or None

    def emit(group: list[tuple[int, str]]):
        body = " ".join(t.strip() for _, t in group).strip()
        if _nonspace(body) >= MIN_PARA_CHARS:
            paras.append(Para(body, None, group[0][0], group[-1][0], section()))

    def flush():
        nonlocal buf
        if buf:
            total = sum(len(t) + 1 for _, t in buf)
            if total > HARD_CHUNK and len(buf) > 1:
                # one long block without blank lines (scraped / single-newline text): keep each
                # piece tied to its OWN lines instead of the whole block's range
                group, size = [], 0
                for item in buf:
                    if group and size + len(item[1]) + 1 > TARGET_CHUNK:
                        emit(group)
                        group, size = [], 0
                    group.append(item)
                    size += len(item[1]) + 1
                if group:
                    emit(group)
            else:
                emit(buf)
        buf = []

    for i, line in enumerate(lines, start=1):
        if i <= first:
            continue
        m = _HEADING.match(line) if file_type == "md" else None
        if m:
            flush()
            level, title = len(m.group(1)), m.group(2).strip()
            while trail and trail[-1][0] >= level:
                trail.pop()
            if title:
                trail.append((level, title))
            continue
        if not line.strip():
            flush()
            continue
        buf.append((i, line))
    flush()
    return paras, warnings


# --------------------------------------------------------------------------- chunking
_SENT = re.compile(r"(?<=[.!?])\s+")


def split_long(text: str, limit: int = HARD_CHUNK) -> list[str]:
    if len(text) <= limit:
        return [text]
    pieces, cur = [], ""
    for sent in _SENT.split(text):
        while len(sent) > limit:  # no punctuation: hard split on whitespace
            cut = sent.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(sent[:cut].strip())
            sent = sent[cut:].strip()
        if cur and len(cur) + 1 + len(sent) > limit:
            pieces.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        pieces.append(cur)
    return [p for p in pieces if p]


def chunk_paragraphs(paras: list[Para]) -> list[Chunk]:
    chunks: list[Chunk] = []
    cur: Chunk | None = None
    for p in paras:
        for piece in split_long(p.text):
            can_join = (
                cur is not None and cur.page == p.page and cur.section == p.section
                and len(cur.text) + 2 + len(piece) <= TARGET_CHUNK
            )
            if can_join:
                cur.text += "\n\n" + piece
                if p.line_end is not None:
                    cur.line_end = p.line_end
            else:
                if cur:
                    chunks.append(cur)
                cur = Chunk(piece, p.page, p.section, p.line_start, p.line_end)
    if cur:
        chunks.append(cur)
    return chunks


# --------------------------------------------------------------------------- ingest
def _clean(value: str | None, limit: int = 300) -> str | None:
    value = (value or "").strip()
    return value[:limit] or None


def ingest_file(db: Database, settings: Settings, filename: str, data: bytes, *,
                title: str | None = None, author: str | None = None,
                date: str | None = None, edition: str | None = None,
                tags: list[str] | tuple[str, ...] = (), kind: str = "primary") -> dict:
    """Import one file. Returns {'document_id', 'duplicate': bool}. New docs are unapproved."""
    safe_name = sanitize_filename(filename)
    ext = ("." + safe_name.rsplit(".", 1)[-1].lower()) if "." in safe_name else ""
    if ext not in ALLOWED_EXTS:
        raise IngestError("Unsupported file type. Import PDF, TXT or Markdown (.md) files.", 415)
    file_type = ALLOWED_EXTS[ext]
    if not data:
        raise IngestError("The file is empty.")
    if len(data) > settings.max_upload_bytes:
        mb = settings.max_upload_bytes // (1024 * 1024)
        raise IngestError(f"File is larger than the {mb} MB limit.", 413)
    if file_type == "pdf" and not data.lstrip()[:5] == b"%PDF-":
        raise IngestError("This file does not look like a real PDF (missing %PDF header).")
    if kind not in ("primary", "secondary_notes"):
        raise IngestError("kind must be 'primary' or 'secondary_notes'.")
    tag_list = sorted({t.strip() for t in tags if t and t.strip()})
    bad = [t for t in tag_list if t not in TAG_SLUGS]
    if bad:
        raise IngestError(f"Unknown topic tag(s): {', '.join(bad)}")

    sha = hashlib.sha256(data).hexdigest()
    doc_id = sha[:12]
    with db.tx() as conn:
        existing = conn.execute("SELECT id FROM documents WHERE sha256=?", (sha,)).fetchone()
    if existing:
        return {"document_id": existing["id"], "duplicate": True}

    page_count = None
    if file_type == "pdf":
        paras, page_count, warnings, pages_with_text = extract_pdf(data)
    else:
        paras, warnings = extract_text(data, file_type)
        if not paras:
            warnings.insert(0, "No usable text was found in this file.")
    chunks = chunk_paragraphs(paras)
    char_count = sum(len(c.text) for c in chunks)
    if chunks:
        body = "".join(c.text for c in chunks)
        visible = re.sub(r"\s", "", body)
        letters = sum(ch.isalpha() for ch in visible)
        if len(visible) >= 200 and (letters / len(visible) < 0.55 or body.count("\ufffd") / len(visible) > 0.01):
            warnings.append("Much of the extracted text is not letters or contains replacement characters "
                            "(tables, OCR noise or a bad encoding). Search and citations may be unreliable; "
                            "check “View extracted text”.")
    status = ("empty" if not chunks
              else "warning" if any(not w.startswith("Note:") for w in warnings) else "ok")

    settings.originals_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{sha}{ext}"
    (settings.originals_dir / stored_name).write_bytes(data)

    stem = safe_name.rsplit(".", 1)[0]
    with db.tx() as conn:
        conn.execute(
            """INSERT INTO documents (id, sha256, title, author, date, edition,
               original_filename, stored_name, file_type, kind, approved, status, warnings,
               page_count, chunk_count, char_count, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?,?)""",
            (doc_id, sha, _clean(title) or stem, _clean(author), _clean(date, 60),
             _clean(edition), safe_name, stored_name, file_type, kind, status,
             json.dumps(warnings), page_count, len(chunks), char_count, now_iso()),
        )
        for tag in tag_list:
            conn.execute("INSERT INTO document_tags (doc_id, tag) VALUES (?,?)", (doc_id, tag))
        for i, ch in enumerate(chunks):
            cid = f"{doc_id}-{i:04d}"
            before = chunks[i - 1].text[-CONTEXT_CHARS:] if i > 0 else ""
            after = chunks[i + 1].text[:CONTEXT_CHARS] if i + 1 < len(chunks) else ""
            conn.execute(
                """INSERT INTO chunks (id, doc_id, ordinal, text, before_text, after_text,
                   page_start, page_end, section, line_start, line_end)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (cid, doc_id, i, ch.text, before, after, ch.page, ch.page, ch.section,
                 ch.line_start, ch.line_end),
            )
            if db.fts:
                conn.execute("INSERT INTO chunks_fts (text, chunk_id) VALUES (?,?)", (ch.text, cid))
    return {"document_id": doc_id, "duplicate": False}
