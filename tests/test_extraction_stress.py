"""PDF/text extraction stress tests on SYNTHETIC documents that imitate real-world layout problems.

These show the importer handles the cases below. They do NOT show it handles YOUR documents:
see docs/REAL_DOCUMENT_ACCEPTANCE.md and tools/inspect_import.py for that.
"""
import re
import time

import pytest

pytest.importorskip("reportlab")

import stress_fixtures as sf  # noqa: E402
from app.ingest import IngestError, ingest_file  # noqa: E402
from app.library import get_document, set_approval  # noqa: E402
from app.retrieval import LexicalRetriever, Scope  # noqa: E402


def load(db, settings, name, data, approve=True):
    r = ingest_file(db, settings, name, data)
    with db.tx() as c:
        if approve and get_document(c, r["document_id"])["chunk_count"]:
            set_approval(c, r["document_id"], True)
        doc = get_document(c, r["document_id"])
        chunks = c.execute("SELECT * FROM chunks WHERE doc_id=? ORDER BY ordinal", (doc["id"],)).fetchall()
    return doc, chunks


def search(db, q, limit=6):
    with db.tx() as c:
        return LexicalRetriever(db.fts).search(c, q, Scope(), limit=limit)


# ----------------------------------------------------------------- layout: headers, footers, hyphens
def test_running_headers_footers_and_page_numbers_are_removed_and_disclosed(db, settings):
    doc, chunks = load(db, settings, "two_col.pdf", sf.two_column_with_header_footer(4))
    text = " ".join(c["text"] for c in chunks)
    assert "THE FICTIONAL REVIEW" not in text and not re.search(r"-\s\d\s-", text)
    note = [w for w in doc["warnings"] if w.startswith("Note: removed")]
    assert note and "THE FICTIONAL REVIEW" in note[0]                       # what was removed is disclosed
    assert doc["status"] == "ok"                                            # benign cleanup does not alarm
    for n in range(1, 5):                                                  # body intact, on the right physical page
        pages = {c["page_start"] for c in chunks if f"PAGEMARK{n} " in c["text"]}
        assert pages == {n}


def test_hyphenated_line_breaks_are_rejoined_so_words_are_searchable(db, settings):
    doc, chunks = load(db, settings, "two_col.pdf", sf.two_column_with_header_footer(4))
    text = " ".join(c["text"] for c in chunks)
    assert not re.search(r"[a-z]- [a-z]", text)
    r = search(db, "apprentice investigators harbour")
    assert r.hits and r.strength in ("ok", "weak")


def test_header_removal_can_remove_real_repeated_lines_but_says_so(db, settings):
    """Documented risk: identical first lines on many pages look like running headers."""
    from reportlab.pdfgen import canvas
    import io
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for n in range(1, 6):
        c.drawString(72, 740, "Repeated opening sentence that is real body text.")
        c.drawString(72, 700, f"Unique content for page {n} follows here and is long enough to index properly.")
        c.showPage()
    c.save()
    doc, chunks = load(db, settings, "rep.pdf", buf.getvalue())
    assert any("Repeated opening sentence" in w for w in doc["warnings"])   # disclosed so you can check


def test_too_few_pages_skips_header_detection(db, settings):
    doc, chunks = load(db, settings, "two.pdf", sf.two_column_with_header_footer(3))
    assert "THE FICTIONAL REVIEW" in " ".join(c["text"] for c in chunks)     # <4 text pages: untouched, not claimed


# ----------------------------------------------------------------- pages
def test_page_numbers_stay_exact_in_a_long_pdf_and_import_is_fast(db, settings):
    t = time.time()
    doc, chunks = load(db, settings, "long.pdf", sf.long_pdf(150))
    assert time.time() - t < 10 and doc["page_count"] == 150
    assert all(re.search(rf"Page {c['page_start']} marker-{c['page_start']}\.", c["text"]) or c["page_start"] for c in chunks)
    r = search(db, "marker-77")
    assert r.hits and r.hits[0]["page"] == 77 and r.hits[0]["location"] == "PDF p. 77"


def test_partly_scanned_pdf_lists_the_missing_physical_pages(db, settings):
    doc, chunks = load(db, settings, "mixed.pdf", sf.mixed_text_and_scanned())
    assert doc["status"] == "warning" and "2, 4" in doc["warnings"][0]
    assert {c["page_start"] for c in chunks} == {1, 3, 5}                    # nothing invented for pages 2 and 4


def test_a_few_blank_pages_are_a_note_not_an_alarm(db, settings):
    doc, _ = load(db, settings, "span.pdf", sf.paragraph_spanning_pages())
    assert doc["status"] == "ok" and any(w.startswith("Note:") for w in doc["warnings"])


def test_encrypted_and_truncated_pdfs_are_rejected_and_nothing_is_stored(db, settings):
    for name, data in (("enc.pdf", sf.encrypted_pdf()), ("cut.pdf", sf.truncated_pdf())):
        with pytest.raises(IngestError):
            ingest_file(db, settings, name, data)
    with db.tx() as c:
        assert c.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
    assert not settings.originals_dir.exists() or not list(settings.originals_dir.iterdir())


def test_accents_dashes_and_curly_quotes_survive(db, settings):
    _, chunks = load(db, settings, "acc.pdf", sf.accents_and_punctuation())
    t = chunks[0]["text"]
    assert all(x in t for x in ("Café", "—", "“quoted”", "naïve", "Zürich", "coöperative"))


# ----------------------------------------------------------------- known limitations (documented, asserted)
def test_known_limitation_paragraph_spanning_a_page_break_is_split_per_page(db, settings):
    """By design chunks never cross pages (exact page references). A sentence that straddles the
    break is split across two chunks, so a phrase search across the break can miss."""
    _, chunks = load(db, settings, "span.pdf", sf.paragraph_spanning_pages())
    assert len({c["page_start"] for c in chunks}) >= 3
    assert sum("SPANNINGPARA" in c["text"] for c in chunks) == 1


def test_known_limitation_footnotes_are_indexed_as_ordinary_passages(db, settings):
    """Footnotes are not detected or labelled: they are plain text on the same physical page."""
    _, chunks = load(db, settings, "fn.pdf", sf.with_footnotes())
    fn = [c for c in chunks if "Footnote one" in c["text"]]
    assert fn and fn[0]["page_start"] == 1 and "footnote" not in (fn[0]["section"] or "").lower()


# ----------------------------------------------------------------- text files
def test_single_newline_text_gets_per_chunk_line_ranges_not_the_whole_file(db, settings):
    data = sf.txt_single_newline_paragraphs(60)
    doc, chunks = load(db, settings, "scraped.txt", data)
    lines = data.decode().split("\n")
    ranges = [(c["line_start"], c["line_end"]) for c in chunks]
    assert len(set(ranges)) == len(ranges) and max(b for _, b in ranges) <= 60
    assert all(b - a <= 3 for a, b in ranges)                                  # tight, not 1-60
    for c in chunks:                                                           # the claimed line really holds the text
        assert c["text"].split()[0] + " " + c["text"].split()[1] in lines[c["line_start"] - 1]


def test_hard_wrapped_text_keeps_paragraph_line_ranges(db, settings):
    data = sf.txt_hard_wrapped()
    _, chunks = load(db, settings, "wrapped.txt", data)
    assert [(c["line_start"], c["line_end"]) for c in chunks][0][0] == 1 and len(chunks) == 3


def test_windows_1252_text_is_decoded_not_mangled(db, settings):
    doc, chunks = load(db, settings, "win.txt", sf.txt_cp1252())
    assert "“cooperative”" in chunks[0]["text"] and "�" not in chunks[0]["text"]
    assert any("Windows-1252" in w for w in doc["warnings"]) and doc["status"] == "ok"


def test_crlf_and_markdown_front_matter(db, settings):
    _, chunks = load(db, settings, "crlf.txt", sf.txt_crlf())
    assert (chunks[0]["line_start"], chunks[0]["line_end"]) == (1, 3)
    _, md = load(db, settings, "c.md", sf.md_complex())
    assert not any("Front matter" in c["text"] for c in md)                    # YAML header not indexed
    sub = [c for c in md if c["section"] and c["section"].endswith("Subsection A1")][0]
    assert sub["line_start"] == 21                                              # still file-accurate after skipping it


def test_garbled_text_gets_a_warning(db, settings):
    junk = ("# $ % ^ & * ( ) _ + = [ ] { } | ; : < > / ? ~ 1 2 3 4 5 6 7 8 9 0 " * 12).encode()
    doc, _ = load(db, settings, "junk.txt", junk, approve=False)
    assert doc["status"] == "warning" and any("not letters" in w for w in doc["warnings"])
