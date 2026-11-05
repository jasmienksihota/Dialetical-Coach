#!/usr/bin/env python3
"""Tools for the dialectical-materialism concept map and evaluation set. Offline; no API calls.

    python tools/dm_eval.py probe [--data-dir data] [--per-group 3] [--out data/concept_review.md]
    python tools/dm_eval.py readiness [--data-dir data] [--confirmations data/concept_confirmations.json]
    python tools/dm_eval.py baseline          # what the scripted demo's keyword feedback does on the cases
    python tools/dm_eval.py check FILE.json   # surface checks on a saved tutor reply (blocks) for one case

`probe` is READ-ONLY: it opens your database in SQLite read-only mode, looks only at APPROVED primary
documents, and proposes candidate passages for each concept. It never approves, edits or imports anything,
and a candidate is NOT support: the app has judged nothing. You decide, by hand, in a local file.

`readiness` reports which evaluation cases are traceable to passages YOU confirmed. A case is READY only when
every concept it is anchored to is either 'supported' (reviewed passages whose IDs exist in approved primary documents,
each with a reviewer note) or 'not_found_in_reviewed' (with a 'reviewed_scope' saying what was actually reviewed; a failed
word search is NOT proof a concept is absent). 'needs_investigation' is not resolved.

Confirmation file (local; git-ignored under data/):
  {"concepts": {"contradiction_and_lookalikes": {
       "status": "supported",            # or "not_found_in_reviewed" (+ "reviewed_scope") or "needs_investigation"
       "reviewer": "ai_assisted_unvalidated",   # or owner_reviewed / ai_assisted_then_owner_reviewed
       "passages": [{"chunk_id": "...", "author": "...", "note": "reviewer's words on what it shows"}],
       "reviewed": "2026-11-05"}}}
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.library import location_label  # noqa: E402
from app.retrieval import LexicalRetriever, Scope  # noqa: E402

EVAL = ROOT / "eval" / "dialectical"
STATUSES = ("supported", "not_found_in_reviewed", "needs_investigation")
REVIEWERS = ("ai_assisted_unvalidated", "owner_reviewed", "ai_assisted_then_owner_reviewed")
RESOLVED = ("supported", "not_found_in_reviewed")


def load_map() -> dict:
    return json.loads((EVAL / "concept_map.json").read_text(encoding="utf-8"))


def load_cases() -> dict:
    return json.loads((EVAL / "cases.json").read_text(encoding="utf-8"))


def open_readonly(data_dir: Path) -> sqlite3.Connection:
    db = Path(data_dir) / "tutor.db"
    if not db.is_file():
        raise SystemExit(f"No database at {db}. Run the app and import/approve documents first.")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _has_fts(conn) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='chunks_fts'").fetchone())


# ------------------------------------------------------------------ probe
def probe(conn, concept_map: dict, per_group: int = 3) -> dict:
    """Candidate passages per concept from APPROVED PRIMARY documents only. Read-only."""
    retriever = LexicalRetriever(use_fts=_has_fts(conn))
    out = {}
    for c in concept_map["concepts"]:
        found, seen = [], set()
        for group in c["search_term_groups"]:
            res = retriever.search(conn, " ".join(group), Scope(), limit=per_group)
            for h in res.hits:
                if h["id"] in seen:
                    continue
                seen.add(h["id"])
                doc = conn.execute("SELECT author, date, edition FROM documents WHERE id=?", (h["doc_id"],)).fetchone()
                found.append({"chunk_id": h["id"], "doc_title": h["doc_title"], "author": doc["author"],
                              "date": doc["date"], "edition": doc["edition"], "location": h["location"],
                              "term_coverage": h["coverage"], "excerpt": " ".join(h["text"].split())[:400],
                              "matched_group": group})
        out[c["id"]] = found
    return out


def render_review(concept_map: dict, found: dict) -> str:
    lines = ["# Concept review sheet (candidates only)", "",
             "**These are word-match candidates from your APPROVED documents. The app has not judged whether any of them "
             "supports anything.** Read the passage in context (Library -> View extracted text), then record your decision "
             "by hand in `data/concept_confirmations.json`. A concept with no candidates is NOT shown to be absent: the library may use "
             "different words than the search lists (edit `eval/dialectical/concept_map.json` to add terms).", ""]
    for c in concept_map["concepts"]:
        lines += [f"## {c['title']}  (`{c['id']}`)", f"*Question for the library:* {c['question_for_the_library']}", ""]
        cands = found.get(c["id"], [])
        if not cands:
            lines += ["_No candidate passages found for these search terms._", ""]
        for x in cands:
            who = x["author"] or "author not recorded"
            lines += [f"- `{x['chunk_id']}` — {x['doc_title']} ({who}), {x['location']}",
                      f"  > {x['excerpt']}"]
        lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------------ readiness
def validate_confirmations(conn, concept_map: dict, conf: dict) -> tuple[dict, list[str]]:
    """Return ({concept_id: status}, problems). Statuses: supported | not_found_in_reviewed |
    needs_investigation | unresolved (nothing recorded)."""
    ids = {c["id"] for c in concept_map["concepts"]}
    status, problems = {c: "unresolved" for c in ids}, []
    for cid, entry in (conf.get("concepts") or {}).items():
        if cid not in ids:
            problems.append(f"{cid}: not a concept in concept_map.json")
            continue
        st = entry.get("status")
        if st in ("supported", "not_found_in_reviewed") and entry.get("reviewer") not in REVIEWERS:
            problems.append(f"{cid}: record who reviewed it: 'reviewer' must be one of {', '.join(REVIEWERS)} "
                            "(AI-assisted review is not the owner's review and is not independent validation)")
            continue
        if st == "needs_investigation":
            status[cid] = "needs_investigation"
        elif st == "not_found_in_reviewed":
            # A failed word search is NOT proof the library never addresses a concept, so say what was reviewed.
            if (entry.get("reviewed_scope") or "").strip():
                status[cid] = "not_found_in_reviewed"
            else:
                problems.append(f"{cid}: 'not_found_in_reviewed' needs 'reviewed_scope' (which documents/passages were actually reviewed)")
        elif st == "supported":
            passages = entry.get("passages") or []
            ok = True
            if not passages:
                problems.append(f"{cid}: 'supported' but lists no passages")
                ok = False
            for p in passages:
                row = (conn.execute(
                    "SELECT d.approved, d.kind FROM chunks c JOIN documents d ON d.id=c.doc_id WHERE c.id=?",
                    (p.get("chunk_id"),)).fetchone() if conn is not None else None)
                if conn is not None and row is None:
                    problems.append(f"{cid}: passage {p.get('chunk_id')} does not exist")
                    ok = False
                elif conn is not None and not row["approved"]:
                    problems.append(f"{cid}: passage {p.get('chunk_id')} is in an UNAPPROVED document")
                    ok = False
                elif conn is not None and row["kind"] != "primary":
                    problems.append(f"{cid}: passage {p.get('chunk_id')} is secondary notes, not a primary source")
                    ok = False
                if not (p.get("note") or "").strip():
                    problems.append(f"{cid}: passage {p.get('chunk_id')} has no note in the reviewer's own words")
                    ok = False
            status[cid] = "supported" if ok else "unresolved"
        else:
            problems.append(f"{cid}: status must be one of {', '.join(STATUSES)}")
    return status, problems


def readiness(conn, concept_map: dict, cases: dict, conf: dict, diagnostic_only: bool = False) -> dict:
    status, problems = validate_confirmations(conn, concept_map, conf)
    rows = []
    for case in cases["cases"]:
        if diagnostic_only and not case.get("first_diagnostic"):
            continue
        missing = [a for a in case["anchors"] if status.get(a) not in RESOLVED]
        limits_only = [a for a in case["anchors"] if status.get(a) == "not_found_in_reviewed"]
        rows.append({"case": case["id"], "kind": case["kind"], "ready": not missing, "missing": missing,
                     "limits_only": limits_only})
    return {"concept_status": status, "problems": problems, "cases": rows,
            "ready_count": sum(r["ready"] for r in rows), "total": len(rows)}


# ------------------------------------------------------------------ baseline (scripted demo)
def baseline(cases: dict) -> dict:
    from app.demo_script import analyse
    out = {}
    for c in cases["cases"]:
        fired = sorted(k for k, v in analyse(c["learner_input"]).items() if v)
        out[c["id"]] = {"kind": c["kind"], "keyword_features_matched": fired}
    return out


# ------------------------------------------------------------------ surface checks on a tutor reply
_TAS = re.compile(r"\b(thesis|antithesis)\b", re.I)
_PRAISE = [
    re.compile(r"\b(excellent|great|good|impressive|nice|strong|correct|proper)(ly)?\b[^.!?]{0,40}\b(use of|usage of|using)\b[^.!?]{0,40}\b(terminolog\w*|dialectic\w*|vocabular\w*|concepts?)\b", re.I),
    re.compile(r"\bcorrectly (identified|applied|used|recogni[sz]ed)\b[^.!?]{0,60}\b(contradiction|dialectic\w*|method)\b", re.I),
    re.compile(r"\bwell done\b[^.!?]{0,60}\b(contradiction|dialectic\w*)\b", re.I),
]
_PREMATURE = re.compile(
    r"\b(this|that|it|here)\s+(is|constitutes)\s+(clearly\s+|indeed\s+|undoubtedly\s+|a clear case of\s+|precisely\s+)?"
    r"(a\s+|the\s+)?(genuine\s+|real\s+|true\s+)?(dialectical\s+)?contradiction\b|"
    r"\b(you(?:'ve| have)\s+(found|identified|proven|shown))\b[^.!?]{0,40}\bcontradiction\b", re.I)
_HEDGE = re.compile(r"\b(whether|if|unless|show|shows|establish|decide|determine|tell|say|claim|call|test|ask)\s+(or not\s+|that\s+)?$", re.I)
_INEV = re.compile(r"\binevitabl[ey]\b", re.I)


def check_output(blocks: list[dict], passage_texts: list[str], *, unresolved_anchor: bool = False) -> list[dict]:
    """Heuristic surface checks. Returns [{'check','detail'}] for each failure. NOT a quality judgement."""
    failures = []
    text_blocks = [b for b in blocks if b.get("type") != "withheld"]
    text = " ".join(b.get("text", "") for b in text_blocks)
    corpus = " ".join(passage_texts).lower()
    for m in _TAS.finditer(text):
        if m.group(1).lower() not in corpus:
            failures.append({"check": "M_TAS", "detail": f"'{m.group(0)}' used but not in any supplied passage"})
            break
    for rx in _PRAISE:
        m = rx.search(text)
        if m:
            failures.append({"check": "M_PRAISE", "detail": m.group(0)[:80]})
            break
    for m in _PREMATURE.finditer(text):
        before = text[max(0, m.start() - 25):m.start()]
        if _HEDGE.search(before):          # "whether this is a contradiction", "what would show it is…": not a declaration
            continue
        failures.append({"check": "M_PREMATURE", "detail": m.group(0)[:80]})
        break
    if _INEV.search(text):
        failures.append({"check": "M_INEV", "detail": "uses 'inevitable/inevitably' — review whether endorsed"})
    if sum(1 for b in text_blocks if b.get("purpose") == "question") > 1:
        failures.append({"check": "M_ONEQ", "detail": "more than one question block"})
    if unresolved_anchor and not any(b.get("type") == "limits" for b in text_blocks):
        failures.append({"check": "M_LIMITS", "detail": "no limits block although an anchored concept is unresolved"})
    return failures


# ------------------------------------------------------------------ CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--data-dir", default=str(ROOT / "data"))
    p.add_argument("--per-group", type=int, default=3)
    p.add_argument("--out", default=None, help="write the review sheet (with excerpts) to this file")
    r = sub.add_parser("readiness")
    r.add_argument("--data-dir", default=str(ROOT / "data"))
    r.add_argument("--confirmations", default=None)
    r.add_argument("--diagnostic", action="store_true", help="only the 3-case first diagnostic")
    sub.add_parser("baseline")
    c = sub.add_parser("check")
    c.add_argument("file")
    c.add_argument("--unresolved-anchor", action="store_true")
    a = ap.parse_args(argv)
    cmap, cases = load_map(), load_cases()

    if a.cmd == "probe":
        conn = open_readonly(Path(a.data_dir))
        found = probe(conn, cmap, a.per_group)
        for c_ in cmap["concepts"]:
            print(f"{c_['id']:36} {len(found[c_['id']]):2} candidate(s)")
        if a.out:
            Path(a.out).write_text(render_review(cmap, found), encoding="utf-8")
            print(f"\nReview sheet written to {a.out}. Nothing in the library was changed. Candidates are not support.")
        else:
            print("\n(Use --out FILE to write the review sheet with excerpts.)")
        return 0
    if a.cmd == "readiness":
        data_dir = Path(a.data_dir)
        conf_path = Path(a.confirmations) if a.confirmations else data_dir / "concept_confirmations.json"
        conf = json.loads(conf_path.read_text(encoding="utf-8")) if conf_path.is_file() else {"concepts": {}}
        conn = open_readonly(data_dir) if (data_dir / "tutor.db").is_file() else None
        rep = readiness(conn, cmap, cases, conf, a.diagnostic)
        print(f"Confirmations file: {conf_path} ({'found' if conf_path.is_file() else 'not found: nothing is confirmed'})")
        for cid, st in rep["concept_status"].items():
            print(f"  {cid:36} {st}")
        for pr in rep["problems"]:
            print(f"  PROBLEM: {pr}")
        print()
        for row in rep["cases"]:
            print(f"  {row['case']:4} {'READY    ' if row['ready'] else 'NOT READY'} {row['kind']}"
                  + ("" if row["ready"] else f"   (unresolved: {', '.join(row['missing'])})")
                  + (f"   [limits-only for: {', '.join(row['limits_only'])}]" if row["limits_only"] else ""))
        print(f"\n{rep['ready_count']}/{rep['total']} cases are traceable to reviewed passages. "
              "A READY case still needs HUMAN scoring of tutor output; this tool does not score anything.")
        return 0 if rep["ready_count"] else 1
    if a.cmd == "baseline":
        print("Keyword features the SCRIPTED DEMO would 'see' in each learner response (not an assessment):")
        for cid, v in baseline(cases).items():
            print(f"  {cid:4} {v['kind']:44} {', '.join(v['keyword_features_matched']) or '-'}")
        return 0
    if a.cmd == "check":
        blocks = json.loads(Path(a.file).read_text(encoding="utf-8"))
        blocks = blocks.get("blocks", blocks) if isinstance(blocks, dict) else blocks
        fails = check_output(blocks, [], unresolved_anchor=a.unresolved_anchor)
        for f in fails:
            print(f"FAIL {f['check']}: {f['detail']}")
        print("surface checks passed" if not fails else f"{len(fails)} surface check(s) failed")
        return 1 if fails else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
