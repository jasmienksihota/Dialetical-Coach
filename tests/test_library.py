import pytest

from app.ingest import IngestError, ingest_file, sanitize_filename
from app.library import get_document, get_passage, list_documents, set_approval
from app.retrieval import LexicalRetriever, Scope, resolve_scope
from conftest import approve, fixture_bytes


def search(db, q, scope=None, limit=6, min_docs=1):
    with db.tx() as c:
        return LexicalRetriever(db.fts).search(c, q, scope or Scope(), limit, min_docs)


# ---- import, metadata, dedup ---------------------------------------------------
def test_import_records_metadata_unapproved_and_never_invents(db, loaded):
    with db.tx() as c:
        doc = get_document(c, loaded["mill"])
    assert doc["approved"] is False                     # unapproved by default
    assert doc["author"] is None and doc["date"] is None and doc["edition"] is None
    assert len(doc["sha256"]) == 64 and doc["id"] == doc["sha256"][:12]
    assert doc["original_filename"] == "synthetic_a_mill_town_notes.md"
    assert doc["tags"] == ["foundations"]
    assert doc["status"] == "ok" and doc["chunk_count"] >= 2


def test_exact_duplicate_not_reimported(db, settings, loaded):
    again = ingest_file(db, settings, "renamed copy.md", fixture_bytes("synthetic_a_mill_town_notes.md"))
    assert again["duplicate"] is True and again["document_id"] == loaded["mill"]
    with db.tx() as c:
        assert len(list_documents(c)) == len(loaded)


def test_validation_rejects_bad_files(db, settings):
    with pytest.raises(IngestError):
        ingest_file(db, settings, "evil.exe", b"MZ....")
    with pytest.raises(IngestError):
        ingest_file(db, settings, "fake.pdf", b"not a pdf at all")
    with pytest.raises(IngestError):
        ingest_file(db, settings, "empty.txt", b"")
    with pytest.raises(IngestError):
        ingest_file(db, settings, "bin.txt", b"abc\x00\x01\x02")
    with pytest.raises(IngestError) as e:
        ingest_file(db, settings, "a.txt", b"x" * (settings.max_upload_bytes + 1))
    assert e.value.status == 413
    with pytest.raises(IngestError):
        ingest_file(db, settings, "a.txt", b"hello world this is text", tags=["not-a-tag"])


def test_filename_sanitized_and_original_stored_by_hash(db, settings):
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\win.ini") == "win.ini"
    assert "/" not in sanitize_filename("a/b\\c.txt")
    r = ingest_file(db, settings, "../../sneaky name!.txt",
                    b"A paragraph long enough to be indexed as text here.")
    with db.tx() as c:
        doc = get_document(c, r["document_id"])
    assert ".." not in doc["original_filename"] and "/" not in doc["original_filename"]
    stored = list(settings.originals_dir.iterdir())
    assert len(stored) == 1 and stored[0].name == f"{doc['sha256']}.txt"
    assert stored[0].resolve().parent == settings.originals_dir.resolve()


# ---- scanned PDFs ----------------------------------------------------------------
def test_scanned_pdf_warns_and_cannot_be_approved(db, loaded):
    with db.tx() as c:
        doc = get_document(c, loaded["scanned"])
        assert doc["status"] == "empty" and doc["chunk_count"] == 0
        assert "OCR" in doc["warnings"][0] and "scanned" in doc["warnings"][0].lower()
        with pytest.raises(IngestError) as e:
            set_approval(c, loaded["scanned"], True)
        assert e.value.status == 409


# ---- locations ---------------------------------------------------------------------
def test_pdf_pages_are_physical_and_printed_unknown(db, loaded):
    with db.tx() as c:
        rows = c.execute("SELECT * FROM chunks WHERE doc_id=? ORDER BY ordinal",
                         (loaded["harbour"],)).fetchall()
        assert [r["page_start"] for r in rows] == [1, 2, 3]       # exact physical pages
        p = get_passage(c, rows[1]["id"])["passage"]
        assert p["location"] == "PDF p. 2" and "printed" not in p["location"]
        c.execute("UPDATE documents SET printed_page_offset=-1 WHERE id=?", (loaded["harbour"],))
        p = get_passage(c, rows[1]["id"])["passage"]
        assert p["location"] == "PDF p. 2 (printed p. 1)"


def test_markdown_and_text_locations(db, loaded):
    with db.tx() as c:
        md = c.execute("SELECT * FROM chunks WHERE doc_id=? ORDER BY ordinal", (loaded["mill"],)).fetchall()
        sections = [r["section"] for r in md]
        assert any(s and s.endswith("Part One: Change comes from within and from outside") for s in sections)
        assert all(r["line_start"] and r["line_end"] >= r["line_start"] for r in md)
        loc = get_passage(c, md[1]["id"])["passage"]["location"]
        assert loc.startswith("§ ") and "lines" in loc
        tx = c.execute("SELECT * FROM chunks WHERE doc_id=? ORDER BY ordinal", (loaded["workshop"],)).fetchall()
        assert all(r["section"] is None and r["page_start"] is None for r in tx)
        assert get_passage(c, tx[0]["id"])["passage"]["location"].startswith("line")


def test_chunk_ids_are_stable_across_reimport(settings, tmp_path):
    from app.db import Database
    ids = []
    for n in (1, 2):
        d = Database(tmp_path / f"x{n}.db")
        s = type(settings)(data_dir=tmp_path / f"d{n}")
        ingest_file(d, s, "x.md", fixture_bytes("synthetic_a_mill_town_notes.md"))
        with d.tx() as c:
            ids.append([r["id"] for r in c.execute("SELECT id FROM chunks ORDER BY ordinal")])
    assert ids[0] == ids[1] and ids[0][0].endswith("-0000")


# ---- approval, filters, isolation ---------------------------------------------------
def test_unapproved_documents_are_never_retrieved(db, loaded):
    assert search(db, "contradiction internal conditions").hits == []
    assert search(db, "contradiction").strength == "none"
    approve(db, loaded["mill"])
    r = search(db, "contradiction internal conditions")
    assert r.hits and {h["doc_id"] for h in r.hits} == {loaded["mill"]}
    with db.tx() as c:
        set_approval(c, loaded["mill"], False)
    assert search(db, "contradiction internal conditions").hits == []


def test_document_and_tag_filters_isolate_documents(db, loaded):
    approve(db, loaded["mill"], loaded["workshop"], loaded["harbour"])
    q = "main constraint problem facts conditions"
    only = search(db, q, Scope(doc_ids=[loaded["workshop"]]))
    assert only.hits and {h["doc_id"] for h in only.hits} == {loaded["workshop"]}
    by_tag = search(db, q, Scope(tags=["organization"]))
    assert {h["doc_id"] for h in by_tag.hits} <= {loaded["harbour"]}
    union = search(db, q, Scope(doc_ids=[loaded["mill"]], tags=["investigation"]))
    assert {h["doc_id"] for h in union.hits} <= {loaded["mill"], loaded["workshop"]}


def test_selecting_unapproved_doc_does_not_widen_scope(db, loaded):
    approve(db, loaded["mill"])
    # inject is unapproved: selecting it must yield nothing, not "everything approved"
    r = search(db, "contradiction", Scope(doc_ids=[loaded["inject"]]))
    assert r.hits == [] and r.strength == "none"
    with db.tx() as c:
        assert resolve_scope(c, Scope(doc_ids=[loaded["inject"]])) == []


def test_secondary_notes_excluded_unless_opted_in(db, loaded):
    approve(db, loaded["mill"], loaded["notes"])
    q = "summary contradiction weavers owners rail line condition"
    assert loaded["notes"] not in {h["doc_id"] for h in search(db, q).hits}
    opted = search(db, q, Scope(include_secondary=True))
    assert loaded["notes"] in {h["doc_id"] for h in opted.hits}
    assert any(h["doc_kind"] == "secondary_notes" for h in opted.hits)


def test_retrieval_spans_multiple_documents(db, loaded):
    approve(db, loaded["mill"], loaded["workshop"], loaded["harbour"])
    r = search(db, "main constraint changes when facts change conditions", limit=6, min_docs=2)
    docs = {h["doc_id"] for h in r.hits}
    assert len(docs) >= 2 and r.distinct_docs >= 2
    assert r.strength in ("ok", "weak")


def test_missing_and_weak_evidence(db, loaded):
    approve(db, loaded["mill"], loaded["workshop"])
    none = search(db, "quantum chromodynamics tokamak")
    assert none.hits == [] and none.strength == "none" and none.notes
    weak = search(db, "contradiction zebra spaceship volcano pancake teleportation")
    assert weak.strength in ("weak", "none")
    one_doc = search(db, "apprentices delegation fairly", min_docs=2)
    assert one_doc.distinct_docs < 2 and any("requested" in n for n in one_doc.notes)


def test_no_approved_docs_in_scope_message(db, loaded):
    r = search(db, "contradiction")
    assert r.strength == "none" and "No approved documents" in r.notes[0]
