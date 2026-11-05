"""Retrieval behind an interface.

Only LEXICAL retrieval is implemented (SQLite FTS5 / BM25 with Porter stemming, or a
plain-Python fallback). It matches words, not meaning: synonyms, paraphrase and
translation variants are NOT matched. Semantic or hybrid retrieval can be added by
implementing ``Retriever`` and swapping it in ``get_retriever``; nothing here should
be described as equivalent to that.

The approval gate and the scope filters are applied in ONE place
(``resolve_scope``) and every retriever must restrict itself to the returned IDs.
"""
from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .config import TAGS
from .library import chunk_to_dict

STOPWORDS = set("""
a about above after again against all also am an and any are as at be because been before
being below between both but by can could did do does doing down during each few for from
further had has have having he her here hers him his how i if in into is it its itself just
me more most my no nor not now of off on once only or other our ours out over own same she
should so some such than that the their theirs them then there these they this those through
to too under until up very was we were what when where which while who whom why will with
would you your yours explain tell please compare passage passages text texts document
documents source sources say says said
""".split())

COVERAGE_MIN = 0.34   # a hit "counts" as relevant to a document if it covers >= this share of query terms
WEAK_BELOW = 0.4      # best hit coverage below this => evidence is "weak"


@dataclass
class Scope:
    doc_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    include_secondary: bool = False

    @classmethod
    def from_dict(cls, d: dict | None) -> "Scope":
        d = d or {}
        return cls(list(d.get("doc_ids") or []), list(d.get("tags") or []),
                   bool(d.get("include_secondary", False)))

    def to_dict(self) -> dict:
        return {"doc_ids": self.doc_ids, "tags": self.tags,
                "include_secondary": self.include_secondary}


def resolve_scope(conn, scope: Scope) -> list[str]:
    """IDs of documents eligible for retrieval. THE approval gate lives here.

    - Only approved documents.
    - Secondary study notes only if the scope opts in.
    - If doc_ids and/or tags are given: union of those selections (never widens to
      "everything" when the selection resolves to nothing eligible).
    - If neither is given: every eligible document.
    """
    sql = "SELECT id FROM documents WHERE approved=1 AND chunk_count>0"
    params: list = []
    if not scope.include_secondary:
        sql += " AND kind='primary'"
    selectors, sel_params = [], []
    if scope.doc_ids:
        selectors.append(f"id IN ({','.join('?' * len(scope.doc_ids))})")
        sel_params += scope.doc_ids
    if scope.tags:
        selectors.append("id IN (SELECT doc_id FROM document_tags WHERE tag IN "
                         f"({','.join('?' * len(scope.tags))}))")
        sel_params += scope.tags
    if selectors:
        sql += " AND (" + " OR ".join(selectors) + ")"
        params += sel_params
    return [r["id"] for r in conn.execute(sql, params)]


def describe_scope(conn, scope: Scope) -> str:
    labels = dict(TAGS)
    parts = []
    if scope.doc_ids:
        rows = conn.execute(
            f"SELECT title FROM documents WHERE id IN ({','.join('?' * len(scope.doc_ids))})",
            scope.doc_ids).fetchall()
        parts.append("documents: " + "; ".join(r["title"] for r in rows))
    if scope.tags:
        parts.append("tags: " + "; ".join(labels.get(t, t) for t in scope.tags))
    if not parts:
        parts.append("all approved documents")
    if scope.include_secondary:
        parts.append("including secondary study notes (not primary sources)")
    return " | ".join(parts)


SCOPE_SEMANTICS = (
    "Documents and tags combine as a UNION: a document is included if it is checked directly OR "
    "carries ANY checked tag. Only approved documents with extracted text are ever included, and "
    "secondary study notes only if you opt in. If nothing is checked, ALL approved primary "
    "documents are included. Checking something that is not eligible never widens the scope.")


def explain_scope(conn, scope: Scope) -> dict:
    """The resolved document list with the reason each document is in or out."""
    labels = dict(TAGS)
    eligible = set(resolve_scope(conn, scope))
    rows = conn.execute("SELECT * FROM documents ORDER BY title").fetchall()
    tag_map: dict[str, list[str]] = {}
    for r in conn.execute("SELECT doc_id, tag FROM document_tags"):
        tag_map.setdefault(r["doc_id"], []).append(r["tag"])
    selecting = bool(scope.doc_ids or scope.tags)
    included, excluded = [], []
    for d in rows:
        reasons = []
        if d["id"] in scope.doc_ids:
            reasons.append("selected directly")
        reasons += [f"tag: {labels.get(t, t)}" for t in tag_map.get(d["id"], []) if t in scope.tags]
        if d["id"] in eligible:
            included.append({"id": d["id"], "title": d["title"], "kind": d["kind"],
                             "reasons": reasons or ["no filter: all approved primary documents"]})
        elif reasons:   # selected or tagged, but not eligible
            why = ("not approved" if not d["approved"] else "no extracted text" if d["chunk_count"] == 0
                   else "secondary study notes (opt in to include)")
            excluded.append({"id": d["id"], "title": d["title"], "reasons": reasons, "why_excluded": why})
    return {"semantics": SCOPE_SEMANTICS, "mode": "selection" if selecting else "all",
            "included": included, "excluded": excluded,
            "include_secondary": scope.include_secondary}


def query_terms(query: str, limit: int = 12) -> list[str]:
    seen, out = set(), []
    for tok in re.findall(r"[\w'-]+", (query or "").lower()):
        tok = tok.strip("'-").replace("'", "")
        if len(tok) < 2 or tok in STOPWORDS or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out[:limit]


def _prefix(term: str) -> str:
    return term if len(term) <= 5 else term[:5]


def coverage(terms: list[str], text: str) -> float:
    """Share of query terms whose 5-char prefix starts some word in text (heuristic)."""
    if not terms:
        return 0.0
    words = re.findall(r"[\w'-]+", text.lower())
    hit = sum(1 for t in terms if any(w.startswith(_prefix(t)) for w in words))
    return hit / len(terms)


@dataclass
class RetrievalResult:
    hits: list[dict]
    strength: str                 # none | weak | ok
    distinct_docs: int            # docs with at least one reasonably relevant hit
    terms: list[str]
    mode: str
    notes: list[str] = field(default_factory=list)


class Retriever(ABC):
    name = "abstract"

    @abstractmethod
    def search(self, conn, query: str, scope: Scope, limit: int = 6,
               min_docs: int = 1, exclude_ids: set[str] | None = None) -> RetrievalResult: ...


class LexicalRetriever(Retriever):
    name = "lexical"

    def __init__(self, use_fts: bool):
        self.use_fts = use_fts

    # candidate generation ------------------------------------------------------
    def _candidates_fts(self, conn, terms, doc_ids, pool, exclude=()):
        match = " OR ".join(f'"{t}"' for t in terms)
        marks = ",".join("?" * len(doc_ids))
        ex = f" AND c.id NOT IN ({','.join('?' * len(exclude))})" if exclude else ""
        rows = conn.execute(
            f"""SELECT c.id AS id, bm25(chunks_fts) AS s FROM chunks_fts
                JOIN chunks c ON c.id = chunks_fts.chunk_id
                WHERE chunks_fts MATCH ? AND c.doc_id IN ({marks}){ex}
                ORDER BY s LIMIT ?""", (match, *doc_ids, *exclude, pool)).fetchall()
        return [(r["id"], -float(r["s"])) for r in rows]

    def _candidates_fallback(self, conn, terms, doc_ids, pool, exclude=()):
        marks = ",".join("?" * len(doc_ids))
        rows = [r for r in conn.execute(
            f"SELECT id, text FROM chunks WHERE doc_id IN ({marks})", doc_ids).fetchall()
            if r["id"] not in exclude]
        prefixes = [_prefix(t) for t in terms]
        tokenized = [(r["id"], re.findall(r"[\w'-]+", r["text"].lower())) for r in rows]
        n = max(1, len(tokenized))
        df = {p: sum(1 for _, ws in tokenized if any(w.startswith(p) for w in ws))
              for p in prefixes}
        scored = []
        for cid, words in tokenized:
            score = 0.0
            for p in prefixes:
                tf = sum(1 for w in words if w.startswith(p))
                if tf:
                    score += math.log(1 + n / max(1, df[p])) * (1 + math.log(tf))
            if score > 0:
                scored.append((cid, score))
        scored.sort(key=lambda x: -x[1])
        return scored[:pool]

    # public --------------------------------------------------------------------
    def search(self, conn, query, scope, limit=6, min_docs=1, exclude_ids=None) -> RetrievalResult:
        terms = query_terms(query)
        mode = "sqlite-fts5" if self.use_fts else "lexical-fallback"
        doc_ids = resolve_scope(conn, scope)
        if not terms or not doc_ids:
            note = ("No approved documents match the selected scope." if not doc_ids
                    else "The query had no searchable terms.")
            return RetrievalResult([], "none", 0, terms, mode, [note])

        pool = max(limit * 6, 30)
        exclude = tuple(exclude_ids or ())
        cands = (self._candidates_fts(conn, terms, doc_ids, pool, exclude) if self.use_fts
                 else self._candidates_fallback(conn, terms, doc_ids, pool, exclude))
        hits = []
        for cid, score in cands:
            chunk = conn.execute("SELECT * FROM chunks WHERE id=?", (cid,)).fetchone()
            doc = conn.execute("SELECT * FROM documents WHERE id=?", (chunk["doc_id"],)).fetchone()
            d = chunk_to_dict(doc, chunk)
            d["score"] = round(score, 4)
            d["coverage"] = round(coverage(terms, chunk["text"]), 3)
            hits.append(d)
        if not hits:
            return RetrievalResult([], "none", 0, terms, mode,
                                   ["No passage in the selected documents matched the query terms."])

        # Prefer breadth: best relevant hit per document first, then fill by score.
        picked, seen_docs = [], set()
        for h in hits:
            if h["doc_id"] not in seen_docs and h["coverage"] >= COVERAGE_MIN and len(picked) < limit:
                picked.append(h)
                seen_docs.add(h["doc_id"])
        per_doc_cap = max(2, math.ceil(limit / 2)) if len(seen_docs) > 1 else limit
        counts: dict[str, int] = {}
        for h in picked:
            counts[h["doc_id"]] = counts.get(h["doc_id"], 0) + 1
        for h in hits:
            if len(picked) >= limit:
                break
            if h in picked or counts.get(h["doc_id"], 0) >= per_doc_cap:
                continue
            picked.append(h)
            counts[h["doc_id"]] = counts.get(h["doc_id"], 0) + 1

        best = max(h["coverage"] for h in picked)
        relevant_docs = {h["doc_id"] for h in picked if h["coverage"] >= COVERAGE_MIN}
        strength = "ok" if best >= WEAK_BELOW else "weak"
        notes = []
        if strength == "weak":
            notes.append("Matches are weak: no passage covers most of the query terms.")
        if len(relevant_docs) < min_docs:
            notes.append(f"Only {len(relevant_docs)} selected document(s) have relevant "
                         f"passages; {min_docs} were requested.")
        return RetrievalResult(picked, strength, len(relevant_docs), terms, mode, notes)


def get_retriever(db) -> Retriever:
    return LexicalRetriever(use_fts=db.fts)
