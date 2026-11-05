"""Document library operations: listing, metadata, approval, passages, locations."""
from __future__ import annotations

import json

from .config import TAG_SLUGS
from .ingest import IngestError, now_iso


def location_label(doc, chunk) -> str:
    """Human-readable location. PDF => physical page (+ printed page only if known)."""
    if doc["file_type"] == "pdf":
        page = chunk["page_start"]
        label = f"PDF p. {page}"
        off = doc["printed_page_offset"]
        if off is not None and page is not None:
            label += f" (printed p. {page + off})"
        return label
    lines = ""
    if chunk["line_start"] is not None:
        a, b = chunk["line_start"], chunk["line_end"]
        lines = f"line {a}" if a == b else f"lines {a}–{b}"
    sec = f"§ {chunk['section']}" if chunk["section"] else ""
    return ", ".join(x for x in (sec, lines) if x) or "document"


def doc_to_dict(conn, row) -> dict:
    tags = [r["tag"] for r in conn.execute(
        "SELECT tag FROM document_tags WHERE doc_id=? ORDER BY tag", (row["id"],))]
    return {
        "id": row["id"], "sha256": row["sha256"], "title": row["title"],
        "author": row["author"], "date": row["date"], "edition": row["edition"],
        "original_filename": row["original_filename"], "file_type": row["file_type"],
        "kind": row["kind"], "approved": bool(row["approved"]), "status": row["status"],
        "warnings": json.loads(row["warnings"] or "[]"), "page_count": row["page_count"],
        "chunk_count": row["chunk_count"], "char_count": row["char_count"],
        "printed_page_offset": row["printed_page_offset"], "tags": tags,
        "created_at": row["created_at"], "approved_at": row["approved_at"],
    }


def list_documents(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC, title").fetchall()
    return [doc_to_dict(conn, r) for r in rows]


def get_document(conn, doc_id: str) -> dict:
    row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not row:
        raise IngestError("Document not found.", 404)
    return doc_to_dict(conn, row)


def update_document(conn, doc_id: str, fields: dict) -> dict:
    get_document(conn, doc_id)
    sets, vals = [], []
    for key in ("title", "author", "date", "edition"):
        if key in fields:
            v = (fields[key] or "").strip()[:300] or None
            if key == "title" and not v:
                raise IngestError("Title cannot be empty.")
            sets.append(f"{key}=?")
            vals.append(v)
    if "printed_page_offset" in fields:
        v = fields["printed_page_offset"]
        if v in ("", None):
            v = None
        else:
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise IngestError("printed_page_offset must be a whole number or empty.")
        sets.append("printed_page_offset=?")
        vals.append(v)
    if "kind" in fields:
        if fields["kind"] not in ("primary", "secondary_notes"):
            raise IngestError("kind must be 'primary' or 'secondary_notes'.")
        sets.append("kind=?")
        vals.append(fields["kind"])
    if sets:
        conn.execute(f"UPDATE documents SET {', '.join(sets)} WHERE id=?", (*vals, doc_id))
    if "tags" in fields:
        tags = sorted({t for t in fields["tags"] or []})
        bad = [t for t in tags if t not in TAG_SLUGS]
        if bad:
            raise IngestError(f"Unknown topic tag(s): {', '.join(bad)}")
        conn.execute("DELETE FROM document_tags WHERE doc_id=?", (doc_id,))
        for t in tags:
            conn.execute("INSERT INTO document_tags (doc_id, tag) VALUES (?,?)", (doc_id, t))
    return get_document(conn, doc_id)


def set_approval(conn, doc_id: str, approved: bool) -> dict:
    doc = get_document(conn, doc_id)
    if approved and doc["chunk_count"] == 0:
        raise IngestError(
            "This document has no extracted text, so it cannot be approved. "
            "(Scanned PDFs need OCR, which this app does not do.)", 409)
    conn.execute("UPDATE documents SET approved=?, approved_at=? WHERE id=?",
                 (1 if approved else 0, now_iso() if approved else None, doc_id))
    return get_document(conn, doc_id)


def delete_document(conn, settings, doc_id: str) -> None:
    row = conn.execute("SELECT stored_name FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not row:
        raise IngestError("Document not found.", 404)
    if _has_fts(conn):
        conn.execute("DELETE FROM chunks_fts WHERE chunk_id IN "
                     "(SELECT id FROM chunks WHERE doc_id=?)", (doc_id,))
    conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    path = settings.originals_dir / row["stored_name"]
    if path.is_file():
        path.unlink()


def _has_fts(conn) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='chunks_fts'").fetchone())


def chunk_to_dict(doc, chunk) -> dict:
    return {
        "id": chunk["id"], "doc_id": doc["id"], "ordinal": chunk["ordinal"],
        "text": chunk["text"], "before_text": chunk["before_text"],
        "after_text": chunk["after_text"], "page": chunk["page_start"],
        "section": chunk["section"], "line_start": chunk["line_start"],
        "line_end": chunk["line_end"], "location": location_label(doc, chunk),
        "doc_title": doc["title"], "doc_kind": doc["kind"], "doc_approved": bool(doc["approved"]),
        "doc_author": doc["author"], "doc_date": doc["date"], "doc_edition": doc["edition"],
    }


def get_passage(conn, chunk_id: str, context: int = 2) -> dict:
    chunk = conn.execute("SELECT * FROM chunks WHERE id=?", (chunk_id,)).fetchone()
    if not chunk:
        raise IngestError("Passage not found.", 404)
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (chunk["doc_id"],)).fetchone()
    lo, hi = max(0, chunk["ordinal"] - context), chunk["ordinal"] + context
    neighbours = conn.execute(
        "SELECT * FROM chunks WHERE doc_id=? AND ordinal BETWEEN ? AND ? ORDER BY ordinal",
        (doc["id"], lo, hi)).fetchall()
    return {
        "passage": chunk_to_dict(doc, chunk),
        "document": doc_to_dict(conn, doc),
        "neighbours": [chunk_to_dict(doc, c) for c in neighbours],
    }


def document_chunks(conn, doc_id: str, offset: int = 0, limit: int = 40) -> dict:
    doc = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not doc:
        raise IngestError("Document not found.", 404)
    rows = conn.execute(
        "SELECT * FROM chunks WHERE doc_id=? ORDER BY ordinal LIMIT ? OFFSET ?",
        (doc_id, max(1, min(limit, 200)), max(0, offset))).fetchall()
    return {"document": doc_to_dict(conn, doc),
            "chunks": [chunk_to_dict(doc, c) for c in rows], "total": doc["chunk_count"]}
