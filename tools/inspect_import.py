#!/usr/bin/env python3
"""Inspect how the app would import ONE document, without touching your real library.

    python tools/inspect_import.py path/to/book.pdf
    python tools/inspect_import.py book.pdf --probe 12:"a phrase copied from physical PDF page 12"
    python tools/inspect_import.py notes.txt --probe L40:"a phrase from line 40"

It imports into a throw-away temporary database (nothing is added to data/), prints extraction
diagnostics, samples of the indexed text with their locations, and checks each --probe:
 * "N:phrase"  -> the phrase must be found in a passage whose PHYSICAL PDF page is N
 * "LN:phrase" -> the phrase must be found in a passage whose line range includes line N
 * "phrase"    -> the phrase must be found in some passage (location printed)
Exit status is 1 if any probe fails. Output contains counts and short samples only.
"""
from __future__ import annotations

import argparse
import re
import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.citations import norm_ws  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.ingest import IngestError, ingest_file  # noqa: E402
from app.library import get_document, location_label, set_approval  # noqa: E402
from app.retrieval import LexicalRetriever, Scope  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--probe", action="append", default=[], help="see above; repeatable")
    ap.add_argument("--samples", type=int, default=3)
    args = ap.parse_args(argv)

    path = Path(args.path).expanduser()
    if not path.is_file():
        print(f"No such file: {path}")
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="tutor-inspect-"))
    settings = Settings(data_dir=tmp)
    db = Database(settings.db_path)
    try:
        res = ingest_file(db, settings, path.name, path.read_bytes())
    except IngestError as e:
        print(f"REJECTED: {e.message}")
        return 1
    with db.tx() as c:
        doc = get_document(c, res["document_id"])
        if doc["chunk_count"]:
            set_approval(c, doc["id"], True)
        chunks = c.execute("SELECT * FROM chunks WHERE doc_id=? ORDER BY ordinal", (doc["id"],)).fetchall()

    print(f"File: {path.name}  ({path.stat().st_size:,} bytes)   type={doc['file_type']}   id={doc['id']}")
    print(f"Status: {doc['status']}   chunks={doc['chunk_count']}   characters={doc['char_count']:,}"
          + (f"   PDF pages={doc['page_count']}" if doc["page_count"] else ""))
    for w in doc["warnings"]:
        print(f"  WARNING: {w}")
    if not chunks:
        print("No indexed text. Nothing else to check (scanned PDF? OCR is not performed).")
        return 1

    text = " ".join(c["text"] for c in chunks)
    flags = {
        "replacement characters (�)": text.count("�"),
        "leftover hyphen breaks ('wo- rd')": len(re.findall(r"[a-z]- [a-z]", text)),
        "very short passages (<80 chars)": sum(len(c["text"]) < 80 for c in chunks),
        "very long passages (>1500 chars)": sum(len(c["text"]) > 1500 for c in chunks),
    }
    lens = [len(c["text"]) for c in chunks]
    print(f"Passage length: min {min(lens)}, median {int(statistics.median(lens))}, max {max(lens)}")
    for k, v in flags.items():
        print(f"  {k}: {v}")
    repeated = {}
    for c in chunks:
        key = norm_ws(c["text"])[:40].lower()
        repeated[key] = repeated.get(key, 0) + 1
    rep = [(k, v) for k, v in repeated.items() if v >= 3]
    if rep:
        print("  passages starting with the same words (possible leftover headers):")
        for k, v in sorted(rep, key=lambda kv: -kv[1])[:3]:
            print(f"    {v}x “{k}…”")
    if doc["file_type"] == "pdf":
        have = {c["page_start"] for c in chunks}
        missing = [p for p in range(1, (doc["page_count"] or 0) + 1) if p not in have]
        print(f"  PDF pages with NO indexed text: {len(missing)}" + (f"  (e.g. {missing[:15]})" if missing else ""))

    print("\nSample passages (check against your original):")
    picks = sorted({0, len(chunks) // 2, len(chunks) - 1} | set(range(0, len(chunks), max(1, len(chunks) // args.samples)))) [: max(args.samples, 3)]
    for i in picks:
        c = chunks[i]
        print(f"  [{location_label(doc, c)}]  {c['id']}\n    {norm_ws(c['text'])[:300]}")

    failed = 0
    if args.probe:
        print("\nProbes:")
    for probe in args.probe:
        m = re.match(r"^(L?)(\d+):(.+)$", probe, re.S)
        kind, num, phrase = (m.group(1), int(m.group(2)), m.group(3)) if m else ("", None, probe)
        needle = norm_ws(phrase).strip()
        found = [c for c in chunks if needle in norm_ws(c["text"])]
        if not found:
            with db.tx() as c2:
                hits = LexicalRetriever(db.fts).search(c2, needle, Scope(), limit=3).hits
            print(f"  FAIL  “{needle[:60]}…” not found verbatim in any passage."
                  + (f" Closest by words: {hits[0]['location']}" if hits else " No word matches either."))
            failed += 1
            continue
        locs = [location_label(doc, c) for c in found]
        ok = True
        if num is not None and not kind:
            ok = any(c["page_start"] == num for c in found)
        elif num is not None and kind == "L":
            ok = any(c["line_start"] is not None and c["line_start"] <= num <= c["line_end"] for c in found)
        print(f"  {'PASS' if ok else 'FAIL'}  “{needle[:60]}…” found at: {', '.join(locs)}"
              + ("" if ok else f"   (expected {'line' if kind else 'PDF page'} {num})"))
        failed += 0 if ok else 1
    print(f"\n(Temporary data in {tmp} — safe to delete. Your real library was not touched.)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
