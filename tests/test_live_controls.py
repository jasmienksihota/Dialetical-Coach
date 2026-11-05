"""Config loading and bounded live-test controls. NO real API calls: fake clients only."""
import json
import logging

import anthropic
import httpx
import pytest

from app.check import main as check_main
from app.config import TOKENS_CEILING, Settings, load_dotenv
from app.livecontrol import LiveGuard
from app.main import create_app
from app.providers import AnthropicProvider, GenRequest, ProviderError, make_provider_factory
from conftest import Env, fixture_bytes

SECRET = "sk-" "ant-NOTREAL-config-test-123"   # split so secret scanners/tests do not flag a fake value


# ------------------------------------------------------------------ configuration loading
def test_dotenv_loading_precedence_and_placeholders(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# comment\nANTHROPIC_API_KEY=\nANTHROPIC_MODEL=claude-sonnet-5-5\n"
                 f"export TUTOR_LIVE_ENABLED=1\nANTHROPIC_MAX_TOKENS=\"900\"\nTUTOR_PORT=9001\n")
    env = {"TUTOR_PORT": "7777"}              # real environment wins over the file
    load_dotenv(f, env)
    assert env["ANTHROPIC_MODEL"] == "claude-sonnet-5-5" and env["TUTOR_LIVE_ENABLED"] == "1"
    assert "ANTHROPIC_API_KEY" not in env     # empty placeholder is ignored, not treated as set
    assert env["TUTOR_PORT"] == "7777" and env["ANTHROPIC_MAX_TOKENS"] == "900"
    s = Settings.from_env(env, dotenv=False)
    assert s.anthropic_model == "claude-sonnet-5-5" and s.anthropic_api_key is None
    assert s.live_enabled and not s.live_configured                       # key missing
    assert "ANTHROPIC_API_KEY" in s.live_setup_message
    assert s.anthropic_max_tokens == 900 and s.port == 7777


def test_live_requires_key_model_and_explicit_enable():
    base = {"ANTHROPIC_API_KEY": SECRET, "ANTHROPIC_MODEL": "claude-sonnet-5-5"}
    assert not Settings.from_env(base, dotenv=False).live_configured                      # no opt-in
    assert "TUTOR_LIVE_ENABLED" in Settings.from_env(base, dotenv=False).live_setup_message
    assert Settings.from_env({**base, "TUTOR_LIVE_ENABLED": "1"}, dotenv=False).live_configured
    assert not Settings.from_env({"TUTOR_LIVE_ENABLED": "1", "ANTHROPIC_API_KEY": SECRET}, dotenv=False).live_configured


def test_limits_are_clamped_and_defaults_are_conservative():
    s = Settings.from_env({"ANTHROPIC_MAX_TOKENS": "999999", "TUTOR_LIVE_MAX_RETRIES": "50",
                           "TUTOR_LIVE_MAX_REQUESTS_PER_DAY": "banana"}, dotenv=False)
    assert s.anthropic_max_tokens == TOKENS_CEILING and s.live_max_retries == 2
    assert s.live_max_requests_per_day == 20 and s.live_enabled is False
    assert Settings.from_env({}, dotenv=False).host == "127.0.0.1"


def test_env_example_is_safe_and_matches_requested_model():
    from conftest import ROOT
    ex = (ROOT / ".env.example").read_text()
    assert "ANTHROPIC_API_KEY=\n" in ex and "sk-" not in ex
    assert "ANTHROPIC_MODEL=claude-sonnet-5-5\n" in ex and "TUTOR_LIVE_ENABLED=0\n" in ex
    s = Settings.from_env(dict(l.split("=", 1) for l in ex.splitlines() if l and not l.startswith("#")), dotenv=False)
    assert s.anthropic_model == "claude-sonnet-5-5" and not s.live_configured   # copying it enables nothing


def test_check_command_prints_no_secret_and_never_pings_by_default(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TUTOR_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    monkeypatch.setenv("TUTOR_LIVE_ENABLED", "1")
    assert check_main([]) == 0
    out = capsys.readouterr().out
    assert SECRET not in out and "set (hidden)" in out and "NO - no successful live request" in out
    assert "not a dollar spending cap" in out
    monkeypatch.setenv("TUTOR_LIVE_ENABLED", "0")
    assert check_main(["--ping", "--yes"]) == 2         # refuses without opt-in; nothing sent
    assert "TUTOR_LIVE_ENABLED" in capsys.readouterr().out


# ------------------------------------------------------------------ fake Anthropic client
def _err(cls, status):
    return cls("boom", response=httpx.Response(status, request=httpx.Request("POST", "https://x")), body=None)


class Tool:
    type = "tool_use"
    def __init__(self, inp): self.input = inp


class Usage:
    def __init__(self, i, o): self.input_tokens, self.output_tokens = i, o


class FakeClient:
    """Programmable fake: list of exceptions / responses consumed one per call."""
    def __init__(self, *script):
        self.script, self.calls, self.kwargs = list(script), 0, []
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        self.kwargs.append(kw)
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return item


def ok_resp(i=100, o=50):
    return type("R", (), {"content": [Tool({"blocks": [{"type": "coaching", "text": "ok"}]})],
                          "usage": Usage(i, o), "stop_reason": "tool_use"})()


def req(chars=100):
    return GenRequest(task="chat", system="s" * 10, messages=[{"role": "user", "content": "u" * chars}], passages=[])


def guarded(tmp_path, client, **kw):
    s = Settings(data_dir=tmp_path / "d", live_enabled=True, anthropic_api_key=SECRET,
                 anthropic_model="claude-sonnet-5-5", **kw)
    env = Env.__new__(Env)
    from app.db import Database
    db = Database(s.db_path)
    g = LiveGuard(db, s)
    p = AnthropicProvider(SECRET, "claude-sonnet-5-5", s.anthropic_max_tokens, client=client, guard=g,
                          max_retries=s.live_max_retries, sleep=lambda x: None)
    return s, db, g, p


# ------------------------------------------------------------------ the controls
def test_request_cap_is_enforced_and_persists_across_restart(tmp_path):
    client = FakeClient(ok_resp())
    s, db, g, p = guarded(tmp_path, client, live_max_requests_per_day=3)
    for _ in range(3):
        p.generate(req())
    with pytest.raises(ProviderError) as e:
        p.generate(req())
    assert e.value.status == 429 and "limit reached" in e.value.message and "not a dollar" not in e.value.message
    assert client.calls == 3                                       # the 4th never reached the client
    # "restart": new guard + provider on the same database still refuses
    g2 = LiveGuard(db, s)
    p2 = AnthropicProvider(SECRET, "m", 100, client=client, guard=g2)
    with pytest.raises(ProviderError):
        p2.generate(req())
    assert client.calls == 3 and g2.summary()["requests_today"] == 3


def test_retries_are_bounded_and_every_attempt_counts(tmp_path):
    client = FakeClient(_err(anthropic.InternalServerError, 500))
    s, db, g, p = guarded(tmp_path, client, live_max_retries=1, live_max_requests_per_day=10)
    with pytest.raises(ProviderError) as e:
        p.generate(req())
    assert client.calls == 2 and g.summary()["requests_today"] == 2         # 1 try + exactly 1 retry
    assert "HTTP 500" in e.value.message
    client0 = FakeClient(_err(anthropic.APIConnectionError, 0) if False else
                         anthropic.APIConnectionError(request=httpx.Request("POST", "https://x")))
    s0, db0, g0, p0 = guarded(tmp_path / "z", client0, live_max_retries=0)
    with pytest.raises(ProviderError):
        p0.generate(req())
    assert client0.calls == 1                                              # retries off => single attempt


def test_non_transient_errors_are_not_retried(tmp_path):
    for cls, status in ((anthropic.AuthenticationError, 401), (anthropic.NotFoundError, 404), (anthropic.BadRequestError, 400)):
        client = FakeClient(_err(cls, status))
        s, db, g, p = guarded(tmp_path / str(status), client, live_max_retries=2)
        with pytest.raises(ProviderError):
            p.generate(req())
        assert client.calls == 1, cls


def test_retry_that_succeeds_logs_both_attempts(tmp_path):
    client = FakeClient(_err(anthropic.RateLimitError, 429), ok_resp(120, 40))
    s, db, g, p = guarded(tmp_path, client, live_max_retries=1)
    assert p.generate(req())["blocks"][0]["text"] == "ok"
    with db.tx() as c:
        rows = [dict(r) for r in c.execute("SELECT status,input_tokens,output_tokens,error FROM live_calls ORDER BY id")]
    assert [r["status"] for r in rows] == ["error", "ok"] and rows[1]["input_tokens"] == 120 and rows[1]["output_tokens"] == 40
    assert "RateLimitError" in rows[0]["error"]


def test_output_token_limit_is_sent_and_clamped(tmp_path):
    client = FakeClient(ok_resp())
    s, db, g, p = guarded(tmp_path, client, anthropic_max_tokens=700)
    p.generate(req())
    assert client.kwargs[0]["max_tokens"] == 700
    assert AnthropicProvider("k", "m", 10**6, client=client).max_tokens == TOKENS_CEILING


def test_oversized_prompt_is_refused_before_any_request(tmp_path):
    client = FakeClient(ok_resp())
    s, db, g, p = guarded(tmp_path, client, live_max_input_chars=2000)
    with pytest.raises(ProviderError) as e:
        p.generate(req(chars=5000))
    assert e.value.status == 413 and client.calls == 0 and g.summary()["requests_today"] == 0


def test_token_usage_is_logged_without_content_or_key(tmp_path, caplog):
    client = FakeClient(ok_resp(321, 123))
    s, db, g, p = guarded(tmp_path, client)
    secret_prompt = "PRIVATE-LEARNER-TEXT-XYZ"
    with caplog.at_level(logging.INFO, logger="tutor.live"):
        p.generate(GenRequest(task="chat", system="sys", passages=[],
                              messages=[{"role": "user", "content": secret_prompt}]))
    assert "input_tokens=321" in caplog.text and "output_tokens=123" in caplog.text
    assert SECRET not in caplog.text and secret_prompt not in caplog.text
    u = g.summary()
    assert (u["input_tokens_today"], u["output_tokens_today"], u["verified"]) == (321, 123, True)
    raw = (tmp_path / "d" / "tutor.db").read_bytes()
    assert secret_prompt.encode() not in raw and SECRET.encode() not in raw


def test_verified_flag_only_after_a_real_success(tmp_path):
    client = FakeClient(_err(anthropic.AuthenticationError, 401))
    s, db, g, p = guarded(tmp_path, client)
    with pytest.raises(ProviderError):
        p.generate(req())
    assert g.summary()["verified"] is False and g.summary()["requests_today"] == 1      # failures never "verify"


# ------------------------------------------------------------------ opt-in at the API level
def test_live_session_needs_server_optin_and_explicit_acknowledgement(tmp_path):
    only_key = Env(tmp_path / "a", anthropic_api_key=SECRET, anthropic_model="claude-sonnet-5-5").load()
    r = only_key.client.post("/api/conversations", json={"provider": "live", "acknowledge_live": True})
    assert r.status_code == 400 and "TUTOR_LIVE_ENABLED" in r.json()["detail"] and SECRET not in r.text
    full = Env(tmp_path / "b", anthropic_api_key=SECRET, anthropic_model="claude-sonnet-5-5", live_enabled=True).load()
    r = full.client.post("/api/conversations", json={"provider": "live"})
    assert r.status_code == 400 and "acknowledged explicitly" in r.json()["detail"]
    r = full.client.post("/api/exercises", json={"provider": "live"})
    assert r.status_code == 400 and "acknowledged explicitly" in r.json()["detail"]
    st = full.client.get("/api/status").json()
    assert st["live_configured"] and st["live_usage"]["verified"] is False and st["model"] == "claude-sonnet-5-5"
    assert st["live_limits"]["max_requests_per_day"] == 20 and SECRET not in json.dumps(st)


def test_a_chat_turn_and_its_repair_each_count_as_requests(tmp_path):
    """Worst case per chat turn is 2 generations (answer + one repair), each possibly retried."""
    bad = type("R", (), {"content": [Tool({"blocks": [{"type": "interpretation", "text": "x",
                                                         "citations": [{"passage_id": "NOPE-1"}]}]})],
                         "usage": Usage(10, 5), "stop_reason": "tool_use"})()
    client = FakeClient(bad)
    s = Settings(data_dir=tmp_path / "d", live_enabled=True, anthropic_api_key=SECRET,
                 anthropic_model="claude-sonnet-5-5", live_max_requests_per_day=2)
    app = create_app(s)
    from fastapi.testclient import TestClient
    c = TestClient(app)
    for name, tags in (("synthetic_a_mill_town_notes.md", "foundations"),):
        d = c.post("/api/documents", files={"file": (name, fixture_bytes(name))}, data={"tags": tags}).json()
        c.post(f"/api/documents/{d['document_id']}/approval", json={"approved": True})
    guard = app.state.guard
    app.state.svc.make_provider = lambda kind: AnthropicProvider(
        SECRET, "claude-sonnet-5-5", 500, client=client, guard=guard, max_retries=0)
    cid = c.post("/api/conversations", json={"provider": "live", "acknowledge_live": True}).json()["id"] if False else None
    app.state.svc.make_provider  # (conversation creation is validated separately above)
    from app import conversations as convs
    with app.state.svc.db.tx() as conn:
        cid = convs.create_conversation(conn, "t", "chat", "live", {})
    r = c.post(f"/api/conversations/{cid}/messages", json={"text": "What causes change, internal contradiction or external conditions?"})
    assert r.status_code == 200 and client.calls == 2                       # answer + one repair, then withheld
    assert r.json()["assistant_message"]["blocks"][0]["type"] == "withheld"
    r2 = c.post(f"/api/conversations/{cid}/messages", json={"text": "What causes change, internal contradiction or external conditions?"})
    assert r2.status_code == 429 and client.calls == 2                      # cap (2/day) reached; nothing sent
    assert c.get(f"/api/conversations/{cid}").json()["messages"][-1]["role"] == "assistant"   # failed turn not saved
