"""Bounded live-test controls.

What these controls DO:
  * Live calls need explicit opt-in (TUTOR_LIVE_ENABLED=1 plus key and model, and an
    acknowledgement when a live session is created).
  * A hard cap on API requests per UTC day, counted in SQLite so a restart cannot reset it.
    Every attempt counts, including retries and the one citation-repair call.
  * Output tokens per request are capped (ANTHROPIC_MAX_TOKENS, hard ceiling 4096).
  * Prompts longer than TUTOR_LIVE_MAX_INPUT_CHARS are refused before sending.
  * Retries are bounded (TUTOR_LIVE_MAX_RETRIES, max 2) and each retry is counted.
  * Token usage reported by the API is logged (counts only; never content or keys).

What they do NOT do: they are NOT a dollar spending cap. Cost depends on the model's
price and on tokens actually billed, which this app cannot know or enforce, and a request
that times out client-side may still be billed. The only real spending ceiling is one you
set with the provider (billing limits / prepaid balance). Treat these as a brake on
accidents, not as a guarantee.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from .config import Settings
from .db import Database
from .providers import ProviderError as AppError

log = logging.getLogger("tutor.live")


def _now():
    return datetime.now(timezone.utc)


class LiveGuard:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings

    def reserve(self, task: str, model: str, input_chars: int) -> int:
        """Check limits and record the attempt BEFORE the request is sent."""
        s = self.settings
        if not s.live_enabled:
            raise AppError("Live calls are disabled (set TUTOR_LIVE_ENABLED=1 to opt in).", 400)
        if input_chars > s.live_max_input_chars:
            raise AppError(
                f"Prompt is too large for a live call ({input_chars} characters; limit "
                f"{s.live_max_input_chars}). Nothing was sent. Narrow the source scope or "
                "start a new session.", 413)
        day = _now().strftime("%Y-%m-%d")
        with self.db.tx() as c:
            used = c.execute("SELECT COUNT(*) FROM live_calls WHERE day=?", (day,)).fetchone()[0]
            if used >= s.live_max_requests_per_day:
                raise AppError(
                    f"Live request limit reached ({s.live_max_requests_per_day} per UTC day). "
                    "Nothing was sent. Change TUTOR_LIVE_MAX_REQUESTS_PER_DAY in .env and "
                    "restart only if you really want more.", 429)
            cur = c.execute(
                "INSERT INTO live_calls (ts, day, task, model, status, input_chars) VALUES (?,?,?,?,?,?)",
                (_now().isoformat(timespec="seconds"), day, task, model, "started", input_chars))
            return cur.lastrowid

    def finish(self, call_id: int, status: str, usage=None, error: str | None = None):
        inp = getattr(usage, "input_tokens", None) if usage is not None else None
        out = getattr(usage, "output_tokens", None) if usage is not None else None
        with self.db.tx() as c:
            c.execute("UPDATE live_calls SET status=?, input_tokens=?, output_tokens=?, error=? WHERE id=?",
                      (status, inp, out, (error or None), call_id))
        log.info("live call id=%s status=%s input_tokens=%s output_tokens=%s error=%s",
                 call_id, status, inp, out, error)

    def mark(self, call_id, *, structured=None, citations_ok=None):
        """Record what happened AFTER the HTTP call: usable structure, citation-validated turn."""
        if call_id is None:
            return
        with self.db.tx() as c:
            if structured is not None:
                c.execute("UPDATE live_calls SET structured=? WHERE id=?", (int(structured), call_id))
            if citations_ok is not None:
                c.execute("UPDATE live_calls SET citations_ok=? WHERE id=?", (int(citations_ok), call_id))

    def summary(self) -> dict:
        day = _now().strftime("%Y-%m-%d")
        with self.db.tx() as c:
            today = c.execute(
                "SELECT COUNT(*) n, COALESCE(SUM(input_tokens),0) i, COALESCE(SUM(output_tokens),0) o "
                "FROM live_calls WHERE day=?", (day,)).fetchone()
            def last(where):
                r = c.execute(f"SELECT ts FROM live_calls WHERE {where} ORDER BY id DESC LIMIT 1").fetchone()
                return r["ts"] if r else None
            api_ts, struct_ts, cite_ts = last("status='ok'"), last("status='ok' AND structured=1"), \
                last("status='ok' AND citations_ok=1")
            total = c.execute("SELECT COUNT(*) FROM live_calls").fetchone()[0]
        stage = ("tutoring_verified" if cite_ts else "structured_output" if struct_ts
                 else "api_reachable" if api_ts else "none")
        return {"requests_today": today["n"], "cap_per_day": self.settings.live_max_requests_per_day,
                "input_tokens_today": today["i"], "output_tokens_today": today["o"],
                "total_requests_ever": total,
                # three separate facts; only the last one may be called "verified tutoring"
                "api_reachable": bool(api_ts), "structured_output": bool(struct_ts),
                "tutoring_verified": bool(cite_ts), "stage": stage,
                "last_api_success": api_ts, "last_structured": struct_ts, "last_tutoring_verified": cite_ts,
                "note": ("Counts are requests this app sent and tokens the API reported. This is not a "
                         "dollar cap; set billing limits with your provider.")}
