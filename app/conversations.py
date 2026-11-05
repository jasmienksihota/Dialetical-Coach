"""Saved conversations: CRUD, bounded history and the transparent summary."""
from __future__ import annotations

import json
import secrets

from .errors import AppError
from .ingest import now_iso

KEEP_MESSAGES = 12      # most recent messages sent verbatim to the model
SUMMARY_ITEMS = 10
SUMMARY_NOTE = ("Earlier turns are condensed by the app (not by a model) to keep context bounded. "
                "The source restrictions are re-applied on every turn regardless.")


def _loads(s, default=None):
    return json.loads(s) if s else default


def create_conversation(conn, title: str, mode: str, provider: str, scope: dict,
                        exercise: dict | None = None) -> str:
    cid = secrets.token_hex(6)
    ts = now_iso()
    conn.execute(
        "INSERT INTO conversations (id,title,mode,provider,scope,summary,exercise,created_at,updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (cid, (title or "Untitled session").strip()[:120], mode, provider, json.dumps(scope), "",
         json.dumps(exercise) if exercise is not None else None, ts, ts))
    return cid


def get_row(conn, cid: str):
    row = conn.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
    if not row:
        raise AppError("Conversation not found.", 404)
    return row


def message_to_dict(conn, row) -> dict:
    flags = [{"id": f["id"], "block_index": f["block_index"], "chunk_id": f["chunk_id"],
              "note": f["note"], "created_at": f["created_at"]}
             for f in conn.execute("SELECT * FROM flags WHERE message_id=? ORDER BY id", (row["id"],))]
    return {"id": row["id"], "role": row["role"], "text": row["text"],
            "blocks": _loads(row["blocks"]), "evidence": _loads(row["evidence"], []),
            "report": _loads(row["report"]), "provider_label": row["provider_label"],
            "purpose": row["purpose"], "created_at": row["created_at"], "flags": flags}


def conversation_to_dict(conn, row, with_messages=True) -> dict:
    d = {"id": row["id"], "title": row["title"], "mode": row["mode"], "provider": row["provider"],
         "scope": _loads(row["scope"], {}), "summary": row["summary"],
         "summary_note": SUMMARY_NOTE if row["summary"] else "",
         "exercise": _loads(row["exercise"]), "created_at": row["created_at"],
         "updated_at": row["updated_at"]}
    if with_messages:
        rows = conn.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY id",
                            (row["id"],)).fetchall()
        d["messages"] = [message_to_dict(conn, r) for r in rows]
    return d


def get_conversation(conn, cid: str) -> dict:
    return conversation_to_dict(conn, get_row(conn, cid))


def list_conversations(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC").fetchall()
    out = []
    for r in rows:
        d = conversation_to_dict(conn, r, with_messages=False)
        d["message_count"] = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id=?", (r["id"],)).fetchone()[0]
        d.pop("exercise", None)
        out.append(d)
    return out


def add_message(conn, cid: str, role: str, text: str = "", *, blocks=None, evidence=None,
                report=None, provider_label=None, purpose=None) -> int:
    cur = conn.execute(
        "INSERT INTO messages (conversation_id,role,text,blocks,evidence,report,provider_label,purpose,created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (cid, role, text, json.dumps(blocks) if blocks is not None else None,
         json.dumps(evidence) if evidence is not None else None,
         json.dumps(report) if report is not None else None, provider_label, purpose, now_iso()))
    conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now_iso(), cid))
    return cur.lastrowid


def update_conversation(conn, cid: str, *, title=None, scope=None, exercise=None, summary=None):
    get_row(conn, cid)
    if title is not None:
        conn.execute("UPDATE conversations SET title=? WHERE id=?", (title.strip()[:120] or "Untitled session", cid))
    if scope is not None:
        conn.execute("UPDATE conversations SET scope=? WHERE id=?", (json.dumps(scope), cid))
    if exercise is not None:
        conn.execute("UPDATE conversations SET exercise=? WHERE id=?", (json.dumps(exercise), cid))
    if summary is not None:
        conn.execute("UPDATE conversations SET summary=? WHERE id=?", (summary, cid))


def delete_conversation(conn, cid: str):
    get_row(conn, cid)
    conn.execute("DELETE FROM conversations WHERE id=?", (cid,))


def block_text(blocks) -> str:
    parts = []
    for b in blocks or []:
        if b.get("type") == "withheld":
            continue
        parts.append(f"[{b.get('type')}] {b.get('text', '')}")
    return "\n".join(parts)


def message_model_text(m: dict) -> str:
    return block_text(m["blocks"]) if m.get("blocks") else m["text"]


def build_history(conn, cid: str):
    """(summary_text, messages_for_model). Older turns become an app-made summary."""
    rows = conn.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (cid,)).fetchall()
    msgs = [message_to_dict(conn, r) for r in rows]
    older, recent = msgs[:-KEEP_MESSAGES], msgs[-KEEP_MESSAGES:]
    summary = ""
    if older:
        items = []
        for m in older[-SUMMARY_ITEMS * 2:]:
            if m["role"] == "user":
                items.append("- Learner said: " + " ".join(m["text"].split())[:160])
            elif m["blocks"]:
                cited = sorted({c["passage_id"] for b in m["blocks"] for c in b.get("citations", [])})
                items.append(f"- Tutor replied (cited passages: {', '.join(cited) or 'none'})")
        summary = f"{len(older)} earlier message(s) condensed:\n" + "\n".join(items[-SUMMARY_ITEMS:])
    history = []
    for m in recent:
        text = message_model_text(m) if m["role"] == "assistant" else m["text"]
        if not text:
            continue
        if history and history[-1]["role"] == m["role"]:
            history[-1]["content"] += "\n" + text
        else:
            history.append({"role": m["role"], "content": text})
    while history and history[0]["role"] != "user":
        history.pop(0)
    return summary, history


def add_flag(conn, message_id: int, block_index, chunk_id, note: str) -> int:
    if not conn.execute("SELECT 1 FROM messages WHERE id=?", (message_id,)).fetchone():
        raise AppError("Message not found.", 404)
    cur = conn.execute(
        "INSERT INTO flags (message_id,block_index,chunk_id,note,created_at) VALUES (?,?,?,?,?)",
        (message_id, block_index, chunk_id, (note or "").strip()[:1000], now_iso()))
    return cur.lastrowid


def delete_flag(conn, flag_id: int):
    conn.execute("DELETE FROM flags WHERE id=?", (flag_id,))
