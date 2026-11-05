"""Chat turn orchestration: retrieve -> generate -> validate (-> one repair) -> persist.

Also holds the shared ``generate_validated`` used by the exercise engine.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from . import followup, prompts
from .citations import error_summary, finalize, normalize_blocks, validate_blocks
from .config import Settings
from .conversations import (add_message, build_history, get_row, message_to_dict,
                            update_conversation)
from .db import Database
from .errors import AppError
from .providers import GenRequest, Provider, ProviderError
from .retrieval import Retriever, Scope, describe_scope, resolve_scope

MAX_USER_CHARS = 4000


@dataclass
class Services:
    settings: Settings
    db: Database
    retriever: Retriever
    make_provider: Callable[[str], Provider]


def snapshot(h: dict) -> dict:
    return {"id": h["id"], "doc_id": h["doc_id"], "doc_title": h["doc_title"],
            "doc_kind": h.get("doc_kind", "primary"), "location": h["location"],
            "text": h["text"], "score": h.get("score")}


def fetch_snapshots(conn, chunk_ids, scope_doc_ids: set[str]) -> list[dict]:
    """Re-fetch passages by ID, dropping any whose document is no longer in scope."""
    from .library import chunk_to_dict
    out = []
    for cid in chunk_ids:
        ch = conn.execute("SELECT * FROM chunks WHERE id=?", (cid,)).fetchone()
        if not ch or ch["doc_id"] not in scope_doc_ids:
            continue
        doc = conn.execute("SELECT * FROM documents WHERE id=?", (ch["doc_id"],)).fetchone()
        out.append(snapshot(chunk_to_dict(doc, ch)))
    return out


def app_block(text: str, purpose: str | None = None) -> dict:
    return {"type": "coaching", "purpose": purpose, "text": text, "status": "uncited",
            "citations": [], "app": True}


def cited_ids(report: dict) -> list[str]:
    seen, out = set(), []
    for rb in report["blocks"]:
        if rb["status"] == "invalid":
            continue
        for c in rb["citations"]:
            if c["ok"] and c["passage_id"] not in seen:
                seen.add(c["passage_id"])
                out.append(c["passage_id"])
    return out


def generate_validated(svc: Services, provider: Provider, req: GenRequest,
                       scope_doc_ids: set[str], post=None):
    """Generate, validate citations, repair at most once, then withhold what still fails."""
    allowed = {p["id"] for p in req.passages}

    texts = [p["text"] for p in req.passages]
    guard = getattr(provider, "guard", None)

    def attempt(r: GenRequest):
        raw = provider.generate(r)
        call_id = getattr(provider, "last_call_id", None)
        try:
            blocks = normalize_blocks(raw)
        except ValueError:
            if guard:
                guard.mark(call_id, structured=False)
            return raw, None, None
        if guard:
            guard.mark(call_id, structured=True)
        if post:
            blocks = post(blocks)
        with svc.db.tx() as c:
            report = validate_blocks(c, blocks, allowed, scope_doc_ids, texts)
        if guard:   # "citation checks passed" needs a reply that parses AND validates, not just an HTTP success
            verified = any(b["status"] == "verified" for b in report["blocks"])
            guard.mark(call_id, citations_ok=bool(report["ok"] and verified))
        return raw, blocks, report

    raw, blocks, report = attempt(req)
    repaired = False
    if blocks is None or not report["ok"]:
        repaired = True
        errors = (["the response was not valid structured output"] if blocks is None
                  else error_summary(report))
        previous = json.dumps({"blocks": blocks} if blocks is not None else raw, default=str)[:6000]
        fix = ("Your previous answer failed mechanical citation checks:\n- " + "\n- ".join(errors[:12])
               + "\nReturn a corrected full answer via submit_response. Cite ONLY passage IDs "
                 "supplied in <retrieved_passages>; quotes must be verbatim contiguous excerpts; "
                 "remove any claim you cannot support from the supplied passages.")
        req2 = GenRequest(
            task=req.task, system=req.system, passages=req.passages,
            messages=[*req.messages, {"role": "assistant", "content": previous},
                      {"role": "user", "content": fix}],
            context={**req.context, "repair": True, "repair_errors": errors})
        raw2, blocks2, report2 = attempt(req2)
        if blocks2 is not None:
            blocks, report = blocks2, report2
        elif blocks is None:
            raise ProviderError("The model did not return a usable structured answer, "
                                "even after one repair attempt. Nothing was saved.", 502)
    report["repair_attempted"] = repaired
    return finalize(blocks, report), report


def snapshots_with_cited(passages: list[dict], report: dict) -> list[dict]:
    cited = set(cited_ids(report))
    return [{**p, "cited": p["id"] in cited} for p in passages]


def _persist_pair(svc, cid, user_text, blocks, evidence, report, label, purpose, *, user_purpose=None):
    with svc.db.tx() as c:
        add_message(c, cid, "user", user_text, purpose=user_purpose)
        mid = add_message(c, cid, "assistant", "", blocks=blocks, evidence=evidence, report=report,
                          provider_label=label, purpose=purpose)
        _, _ = None, None
        summary, _hist = build_history(c, cid)
        update_conversation(c, cid, summary=summary)
        row = c.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
        umsg = c.execute("SELECT * FROM messages WHERE conversation_id=? AND role='user' "
                         "ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
        return message_to_dict(c, umsg), message_to_dict(c, row), summary


def _no_call_report(note: str) -> dict:
    return {"blocks": [{"index": 0, "type": "coaching", "status": "uncited", "errors": [],
                        "citations": []}], "invalid_count": 0, "ok": True,
            "note": note, "repair_attempted": False}


def chat_turn(svc: Services, cid: str, text: str, intent: str = "ask") -> dict:
    text = (text or "").strip()
    if not text:
        raise AppError("Type a message first.", 400)
    if len(text) > MAX_USER_CHARS:
        raise AppError(f"Message is too long (max {MAX_USER_CHARS} characters).", 400)
    intent = intent if intent in prompts.INTENT_GUIDE else "ask"

    with svc.db.tx() as c:
        row = get_row(c, cid)
        if row["mode"] != "chat":
            raise AppError("This is an exercise session; use the exercise controls.", 409)
        scope = Scope.from_dict(json.loads(row["scope"]))
        provider_kind = row["provider"]
        scope_ids = set(resolve_scope(c, scope))
        scope_desc = describe_scope(c, scope)
        summary, history = build_history(c, cid)
        user_texts = [r["text"] for r in c.execute(
            "SELECT text FROM messages WHERE conversation_id=? AND role='user' ORDER BY id", (cid,))]
        last_ai = c.execute("SELECT evidence, report FROM messages WHERE conversation_id=? AND role='assistant' "
                            "AND report IS NOT NULL ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
        prev_cited = cited_ids(json.loads(last_ai["report"])) if last_ai and last_ai["report"] else []
        prev_supplied = [e["id"] for e in json.loads(last_ai["evidence"] or "[]")] if last_ai else []

    provider = svc.make_provider(provider_kind)   # fails early (nothing saved) if not configured

    query, fu, anchor = followup.build_query(text, user_texts)
    compare = intent in ("compare", "disagreements")
    exclude = set(prev_supplied) if fu.seeks_new else set()
    with svc.db.tx() as c:
        res = svc.retriever.search(c, query, scope, limit=8 if compare else 6,
                                   min_docs=2 if compare else 1, exclude_ids=exclude)
        passages = [snapshot(h) for h in res.hits]
        have = {p["id"] for p in passages}
        if fu.seeks_new or not fu.is_followup:
            # Something NEW was asked for, or this is a new substantive question: use fresh retrieval
            # only. Carrying old evidence here would let an unrelated question inherit (and be answered
            # from) the previous topic's passages and would mask the insufficient-evidence refusal.
            carry_ids = []
        elif prev_cited:
            carry_ids = prev_cited[:3]
        else:
            carry_ids = prev_supplied[:3]
        carried = fetch_snapshots(c, [p for p in carry_ids if p not in have], scope_ids)
    passages += carried
    retrieval_info = {"strength": res.strength, "notes": res.notes, "mode": res.mode,
                      "terms": res.terms, "distinct_docs": res.distinct_docs,
                      "carried_over": [p["id"] for p in carried], "query": query,
                      "followup": fu.is_followup, "seeks_new": fu.seeks_new,
                      "anchor": anchor, "excluded_previous": len(exclude)}
    scope_info = {"description": scope_desc, "doc_ids": sorted(scope_ids)}

    label = provider.label
    no_call_msg = None
    if not scope_ids:
        no_call_msg = ("No approved documents are in this session's source scope, so I have nothing "
                       "to ground an answer in. Approve documents in the Library (or widen the "
                       "session scope), then ask again.")
    elif not passages and fu.seeks_new:
        no_call_msg = ("I found no further relevant passages in the selected sources beyond those I "
                       "already used, so I can't offer another example from the library. I won't "
                       "reach outside your selected scope. You can widen the selection, or ask me to "
                       "re-explain the earlier passages.")
    elif not passages:
        no_call_msg = ("I found no passages in the selected documents that match your question, so "
                       "I will not answer from outside the library. The selected library does not "
                       "establish anything on this as worded. Try different terms, or widen the "
                       "document/tag selection.")
    elif compare and len({p["doc_id"] for p in res.hits if p["coverage"] >= 0.34}) < 2:
        no_call_msg = ("A cross-text comparison needs relevant passages from at least two selected "
                       "documents, but only one has them. I will not manufacture a comparison. "
                       "The retrieved passage(s) are listed below; I can explain them as a "
                       "single-source question if you ask with “Explain”, or widen the selection.")
    if no_call_msg:
        report = _no_call_report("App-authored message; no model call was made.")
        report["retrieval"], report["scope"] = retrieval_info, scope_info
        u, a, summ = _persist_pair(svc, cid, text, [app_block(no_call_msg)],
                                   [{**p, "cited": False} for p in passages], report, "App", "app")
        return {"user_message": u, "assistant_message": a, "retrieval": retrieval_info,
                "summary": summ, "model_called": False}

    notes = []
    if res.strength == "weak":
        notes.append("Evidence strength is WEAK: say what the library does not establish.")
    if fu.is_followup:
        notes.append(f"The learner's message is a short follow-up. Earlier question it refers to: "
                     f"\"{anchor[:300]}\". Use ONLY the supplied passages.")
    system = prompts.build_system(scope_desc, summary,
                                  extra=f"THIS TURN ({intent}): {prompts.INTENT_GUIDE[intent]}")
    user_turn = prompts.build_user_turn(passages, text, intent, note=" ".join(notes))
    req = GenRequest(task="chat", system=system, passages=passages,
                     messages=[*history, {"role": "user", "content": user_turn}],
                     context={"intent": intent, "user_text": text, "strength": res.strength,
                              "scope": scope_desc})
    blocks, report = generate_validated(svc, provider, req, scope_ids)
    report["retrieval"], report["scope"] = retrieval_info, scope_info
    evidence = snapshots_with_cited(passages, report)
    u, a, summ = _persist_pair(svc, cid, text, blocks, evidence, report, label, "chat")
    return {"user_message": u, "assistant_message": a, "retrieval": retrieval_info,
            "summary": summ, "model_called": True}
