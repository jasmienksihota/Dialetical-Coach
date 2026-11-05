"""Finding 3: API connectivity, usable structured output and validated tutoring are separate facts.

All fake clients; no network, no spend.
"""
import sqlite3

import pytest

import app.check as check_mod
from app.config import Settings
from app.db import Database
from app.livecontrol import LiveGuard
from app.providers import AnthropicProvider
from conftest import make_env
from test_live_controls import FakeClient, Tool, Usage, SECRET

Q = "What causes change: internal contradiction or external conditions?"


def resp(content, i=10, o=5):
    return type("R", (), {"content": content, "usage": Usage(i, o), "stop_reason": "tool_use"})()


def live_env(tmp_path, client):
    s = dict(live_enabled=True, anthropic_api_key=SECRET, anthropic_model="claude-sonnet-5-5")
    holder = {}
    def factory(kind):
        return AnthropicProvider(SECRET, "claude-sonnet-5-5", 500, client=client, guard=holder["g"], max_retries=0)
    e = make_env(tmp_path, None, **s)
    holder["g"] = e.app.state.guard
    e.svc.make_provider = factory
    return e


def usage(e):
    return e.client.get("/api/status").json()["live_usage"]


def first_passage_id(kw):
    for m in reversed(kw["messages"]):            # the repair turn is last; the passages are in an earlier turn
        if '<passage id="' in m["content"]:
            return m["content"].split('<passage id="', 1)[1].split('"', 1)[0]
    raise AssertionError("no passage in prompt")


class Smart(FakeClient):
    """Builds a reply from the prompt it receives."""
    def __init__(self, mode):
        super().__init__(None)
        self.mode = mode

    def create(self, **kw):
        self.calls += 1
        pid = first_passage_id(kw)
        if self.mode == "empty":
            return resp([])
        if self.mode == "garbage":
            return resp([Tool({"blocks": "nope"})])
        if self.mode == "fake_citation":
            return resp([Tool({"blocks": [{"type": "interpretation", "text": "x", "citations": [{"passage_id": "ZZZZ-9"}]}]})])
        if self.mode == "uncited_only":
            return resp([Tool({"blocks": [{"type": "coaching", "text": "Think about it."}]})])
        return resp([Tool({"blocks": [{"type": "interpretation", "text": "My reading.", "citations": [{"passage_id": pid}]}]})])


def test_fresh_install_reports_no_stage(tmp_path):
    e = live_env(tmp_path, Smart("good"))
    u = usage(e)
    assert (u["api_reachable"], u["structured_output"], u["citation_checks_passed"], u["stage"]) == (False, False, False, "none")


@pytest.mark.parametrize("mode,stage,structured", [
    ("empty", "api_reachable", False),            # HTTP fine, no tool call returned
    ("garbage", "api_reachable", False),          # tool call but not usable blocks
    ("fake_citation", "structured_output", True),  # usable blocks, citations fail validation
    ("uncited_only", "structured_output", True),   # usable, but nothing source-backed to validate
])
def test_http_success_alone_never_counts_as_citation_checks_passed(tmp_path, mode, stage, structured):
    client = Smart(mode)
    e = live_env(tmp_path, client)
    cid = e.chat("live")
    e.say(cid, Q)                                     # may be 502/200 depending on mode; stage is what matters
    u = usage(e)
    assert u["api_reachable"] is True
    assert u["structured_output"] is structured
    assert u["citation_checks_passed"] is False and u["stage"] == stage and u["last_citation_checks_passed"] is None


def test_only_a_reply_with_passing_citation_checks_sets_that_stage(tmp_path):
    e = live_env(tmp_path, Smart("good"))
    r = e.say(e.chat("live"), Q)
    assert r.status_code == 200 and r.json()["assistant_message"]["blocks"][0]["status"] == "verified"
    u = usage(e)
    assert (u["api_reachable"], u["structured_output"], u["citation_checks_passed"], u["stage"]) == (True, True, True, "citation_checks_passed")
    assert u["last_citation_checks_passed"]


def test_a_failed_repair_then_good_reply_counts_once_validated(tmp_path):
    class Flaky(Smart):
        def create(self, **kw):
            self.mode = "fake_citation" if self.calls == 0 else "good"
            return super().create(**kw)
    e = live_env(tmp_path, Flaky("good"))
    e.say(e.chat("live"), Q)
    assert usage(e)["citation_checks_passed"] is True and usage(e)["total_requests_ever"] == 2


def test_ping_establishes_only_connectivity_and_structure(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TUTOR_DATA_DIR", str(tmp_path / "d"))
    for k, v in (("ANTHROPIC_API_KEY", SECRET), ("ANTHROPIC_MODEL", "claude-sonnet-5-5"), ("TUTOR_LIVE_ENABLED", "1")):
        monkeypatch.setenv(k, v)
    fake = FakeClient(resp([Tool({"blocks": [{"type": "coaching", "text": "ok"}]})]))
    real = check_mod.AnthropicProvider
    monkeypatch.setattr(check_mod, "AnthropicProvider", lambda *a, **k: real(*a, **{**k, "client": fake}))
    assert check_mod.main(["--ping", "--yes"]) == 0
    out = capsys.readouterr().out
    assert "API request succeeded" in out and "valid structured output" in out
    assert "nothing about tutoring quality" in out and "citation checks passed" in out and SECRET not in out
    s = Settings.from_env()
    u = LiveGuard(Database(s.db_path), s).summary()
    assert (u["api_reachable"], u["structured_output"], u["citation_checks_passed"]) == (True, True, False)


def test_old_databases_are_migrated_without_losing_rows(tmp_path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""CREATE TABLE live_calls (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, day TEXT NOT NULL,
        task TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL, input_chars INTEGER NOT NULL DEFAULT 0,
        input_tokens INTEGER, output_tokens INTEGER, error TEXT);
        INSERT INTO live_calls (ts,day,task,model,status) VALUES ('2026-01-01T00:00:00','2026-01-01','chat','m','ok');""")
    con.commit(); con.close()
    db = Database(path)
    with db.tx() as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(live_calls)")}
    assert {"structured", "citations_ok"} <= cols
    u = LiveGuard(db, Settings(data_dir=tmp_path)).summary()
    assert u["api_reachable"] is True and u["citation_checks_passed"] is False        # a legacy ok row proves HTTP only
