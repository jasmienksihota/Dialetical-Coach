"""Mechanical citation validation.

What this DOES check (per cited passage):
  1. the passage ID was among the passages supplied for THIS turn,
  2. the passage's document is approved, in the session's source scope (and, for
     secondary notes, the scope opted in) at validation time,
  3. any quoted text appears verbatim in the passage after whitespace-only
     normalization (runs of whitespace collapse to one space; nothing else changes:
     case, punctuation, ellipses and typographic quotes must match exactly).
  4. "quote" blocks: the block text itself must occur in a cited passage;
     "synthesis" blocks must cite passages from at least two different documents.

What this does NOT check: whether the passage actually SUPPORTS the claim made about
it. That is a semantic judgement; the UI says so and offers a flag button.

Uncited-claim guard (heuristic, NOT proof): a model could try to smuggle claims about
what the sources say into blocks that need no citation (coaching, fiction, limits).
``detect_uncited_source_claim`` flags the obvious forms: source-subject + assertion verb
("the author argues…"), "according to …", a named in-scope document/author + assertion
verb, and verbatim runs of passage text copied without a citation. Fiction may never
cite. These are pattern checks: a paraphrase that avoids those patterns can slip
through (see tests/test_citation_bypass.py::test_known_limitation_*), which is why the
UI still labels uncited blocks and the owner can inspect everything.
"""
from __future__ import annotations

import re

BLOCK_TYPES = ("quote", "interpretation", "synthesis", "fiction", "coaching", "limits")
NEEDS_CITATION = {"quote", "interpretation", "synthesis"}
QUOTE_CHARS = "\"'“”‘’«»`"

REASONS = {
    "bad_structure": "the answer was not in the expected structured format",
    "bad_block_type": "unknown block type",
    "empty_block": "empty block",
    "missing_citation": "no source citation was provided for a source claim",
    "unknown_passage": "cited a passage that was not supplied for this turn",
    "out_of_scope": "cited a document that is not approved or not in the selected scope",
    "quote_not_found": "the quoted text does not appear in the cited passage",
    "synthesis_needs_two_documents": "a synthesis must cite passages from at least two documents",
    "uncited_source_claim": "it describes what the sources say without a citation (such claims belong in cited interpretation blocks)",
    "uncited_quotation": "it reproduces source text without citing it",
    "fiction_cannot_cite": "fictional material must not carry source citations",
}

_SING = r"(?:text|passage|author|document|source|writer|handbook|primer|essay|pamphlet|book|library|notes)"
_PLUR = r"(?:texts|passages|authors|documents|sources|writers|readings)"
_V3 = (r"(?:says|argues|states|claims|holds|asserts|writes|insists|contends|maintains|explains|shows|"
       r"teaches|warns|notes|describes|concludes|recommends|proposes|defines|identifies|distinguishes|"
       r"emphasi[sz]es|stresses|believes|suggests|observes|demonstrates|treats|rejects|advises|requires)")
_VPAST = (r"(?:said|argued|stated|claimed|held|asserted|wrote|insisted|contended|maintained|explained|"
          r"showed|taught|warned|noted|described|concluded|recommended|proposed|defined|identified|"
          r"distinguished|emphasi[sz]ed|stressed|believed|suggested|observed|demonstrated|rejected|advised)")
_VBASE = (r"(?:say|argue|state|claim|hold|assert|write|insist|contend|maintain|explain|show|teach|warn|"
          r"note|describe|conclude|recommend|propose|define|identify|distinguish|emphasi[sz]e|stress|"
          r"believe|suggest|observe|demonstrate|treat|reject|advise|require)")
# up to 3 filler words between subject and verb, but never across an imperative-looking joiner
_GAP = (r"(?:\s+(?!(?:and|or|then|to|you|your|we|i|me|my|us|should|would|could|can|will|try|please|so|"
        r"but|if|not|do)\b)\w+){0,3}?\s+")
_ATTRIB = [
    re.compile(rf"\b(?:the|this|that|these|those|each|both|all|any)?\s*{_SING}\b{_GAP}(?:{_V3}|{_VPAST})\b", re.I),
    re.compile(rf"\b{_PLUR}\b{_GAP}(?:{_VBASE}|{_VPAST})\b", re.I),
    re.compile(r"\baccording to\b[^.?!]{0,60}\b(?:text|texts|passage|passages|author|authors|document|documents|source|sources|handbook|primer|notes|library)\b", re.I),
    re.compile(r"\bas (?:the )?(?:author|text|passage|handbook|primer|notes) (?:puts it|says|states|argues)\b", re.I),
]
_NAME_VERB = re.compile(rf"\b(?:{_V3}|{_VPAST})\b", re.I)
_SENT = re.compile(r"(?<=[.!?])\s+")


def _tokens(s: str) -> list[str]:
    return re.findall(r"\w+", (s or "").lower())


def detect_uncited_source_claim(text: str, names: list[str], passage_texts: list[str]) -> str | None:
    """Return an error code if an UNCITED block appears to make claims about the sources."""
    for rx in _ATTRIB:
        if rx.search(text):
            return "uncited_source_claim"
    low_names = [n.lower() for n in names if len(n) >= 5]
    if low_names:
        for sent in _SENT.split(text):
            ls = sent.lower()
            if any(n in ls for n in low_names) and _NAME_VERB.search(sent):
                return "uncited_source_claim"
    toks = _tokens(text)
    if len(toks) >= 8 and passage_texts:
        grams = {" ".join(toks[i:i + 8]) for i in range(len(toks) - 7)}
        for pt in passage_texts:
            pk = _tokens(pt)
            if any(" ".join(pk[i:i + 8]) in grams for i in range(max(0, len(pk) - 7))):
                return "uncited_quotation"
    return None


def norm_ws(s: str) -> str:
    return " ".join((s or "").split())


def normalize_blocks(raw) -> list[dict]:
    """Coerce a provider payload into a clean list of blocks, or raise ValueError."""
    if isinstance(raw, dict):
        raw = raw.get("blocks")
    if not isinstance(raw, list) or not raw:
        raise ValueError("no blocks")
    out = []
    for b in raw:
        if not isinstance(b, dict):
            raise ValueError("block is not an object")
        cites = []
        for c in b.get("citations") or []:
            if isinstance(c, str):
                c = {"passage_id": c}
            if not isinstance(c, dict) or not isinstance(c.get("passage_id"), str):
                raise ValueError("bad citation")
            q = c.get("quote")
            cites.append({"passage_id": c["passage_id"].strip(),
                          **({"quote": q} if isinstance(q, str) and q.strip() else {})})
        out.append({
            "type": str(b.get("type", "")).strip().lower(),
            "purpose": (str(b["purpose"]).strip().lower() if b.get("purpose") else None),
            "text": str(b.get("text", "")).strip(),
            "citations": cites,
        })
    return out


def validate_blocks(conn, blocks: list[dict], allowed_ids: set[str],
                    scope_doc_ids: set[str], passage_texts: list[str] | None = None) -> dict:
    """Return a report; never raises on bad model output."""
    from .library import location_label

    names: list[str] = []
    if scope_doc_ids:
        marks = ",".join("?" * len(scope_doc_ids))
        for r in conn.execute(f"SELECT title, author FROM documents WHERE id IN ({marks})",
                              list(scope_doc_ids)):
            names += [x for x in (r["title"], r["author"]) if x]

    report_blocks = []
    for i, b in enumerate(blocks):
        errors: list[dict] = []
        cites_out = []
        valid_docs: set[str] = set()
        valid_texts: list[str] = []
        btype = b["type"]
        if btype not in BLOCK_TYPES:
            errors.append({"code": "bad_block_type", "detail": btype})
        if not b["text"]:
            errors.append({"code": "empty_block"})
        if btype in NEEDS_CITATION and not b["citations"]:
            errors.append({"code": "missing_citation"})
        for c in b["citations"]:
            pid = c["passage_id"]
            info = {"passage_id": pid, "quote": c.get("quote"), "ok": False,
                    "doc_id": None, "doc_title": None, "location": None}
            cite_errors = []
            chunk = doc = None
            if pid not in allowed_ids:
                cite_errors.append({"code": "unknown_passage", "detail": pid})
            else:
                chunk = conn.execute("SELECT * FROM chunks WHERE id=?", (pid,)).fetchone()
                if chunk is None:
                    cite_errors.append({"code": "unknown_passage", "detail": pid})
            if chunk is not None:
                doc = conn.execute("SELECT * FROM documents WHERE id=?",
                                   (chunk["doc_id"],)).fetchone()
                info.update(doc_id=doc["id"], doc_title=doc["title"],
                            doc_kind=doc["kind"], location=location_label(doc, chunk))
                if not doc["approved"] or doc["id"] not in scope_doc_ids:
                    cite_errors.append({"code": "out_of_scope", "detail": pid})
            if not cite_errors and c.get("quote"):
                if norm_ws(c["quote"].strip(QUOTE_CHARS)) not in norm_ws(chunk["text"]):
                    cite_errors.append({"code": "quote_not_found", "detail": pid})
            if cite_errors:
                errors.extend(cite_errors)
            else:
                info["ok"] = True
                valid_docs.add(doc["id"])
                valid_texts.append(norm_ws(chunk["text"]))
            cites_out.append(info)
        if btype == "quote" and not errors:
            needle = norm_ws(b["text"].strip().strip(QUOTE_CHARS))
            if not any(needle and needle in t for t in valid_texts):
                errors.append({"code": "quote_not_found", "detail": "block text"})
        if btype == "synthesis" and not errors and len(valid_docs) < 2:
            errors.append({"code": "synthesis_needs_two_documents"})
        if btype == "fiction" and b["citations"]:
            errors.append({"code": "fiction_cannot_cite"})
        if btype in ("coaching", "fiction", "limits") and not valid_docs and b["text"] and not any(
                e["code"] == "bad_block_type" for e in errors):
            code = detect_uncited_source_claim(b["text"], names, passage_texts or [])
            if code:
                errors.append({"code": code})
        if errors:
            status = "invalid"
        elif b["citations"]:
            status = "verified"
        else:
            status = "uncited"
        report_blocks.append({"index": i, "type": btype, "status": status,
                              "errors": errors, "citations": cites_out})
    invalid = [r for r in report_blocks if r["status"] == "invalid"]
    return {"blocks": report_blocks, "invalid_count": len(invalid), "ok": not invalid,
            "note": ("Mechanical checks only: passage was supplied, document approved and "
                     "in scope, quoted text present. Whether a passage actually supports "
                     "a claim is NOT verified.")}


def error_summary(report: dict) -> list[str]:
    msgs = []
    for rb in report["blocks"]:
        for e in rb["errors"]:
            msgs.append(f"block {rb['index']} ({rb['type']}): {e['code']}"
                        + (f" [{e['detail']}]" if e.get("detail") else ""))
    return msgs


def finalize(blocks: list[dict], report: dict) -> list[dict]:
    """Display blocks: valid ones with checked citations; invalid ones withheld."""
    out = []
    for b, rb in zip(blocks, report["blocks"]):
        if rb["status"] == "invalid":
            codes = sorted({e["code"] for e in rb["errors"]})
            why = "; ".join(REASONS.get(c, c) for c in codes)
            out.append({"type": "withheld", "original_type": b["type"], "purpose": b.get("purpose"),
                        "text": "", "citations": [], "status": "withheld",
                        "reason": f"A statement was withheld because its citation could not be verified: {why}.",
                        "errors": codes})
        else:
            out.append({"type": b["type"], "purpose": b.get("purpose"), "text": b["text"],
                        "status": rb["status"], "citations": rb["citations"]})
    return out
