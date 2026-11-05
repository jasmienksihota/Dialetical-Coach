"""Chat, evidence tracking, citation validation, injection, persistence, errors, privacy."""
import json
import sqlite3

import anthropic
import httpx
import pytest

from app.citations import normalize_blocks, validate_blocks
from app.config import Settings
from app.main import create_app
from app.providers import AnthropicProvider, ProviderError
from conftest import Env, ScriptedProvider, make_env

Q = "What causes change: internal contradiction or external conditions?"


def passage_ids(req):
    return [p["id"] for p in req.passages]


def good_reply(req, quote_from=0):
    p = req.passages[quote_from]
    q = " ".join(p["text"].split()[:12])
    return {"blocks": [
        {"type": "quote", "text": q, "citations": [{"passage_id": p["id"], "quote": q}]},
        {"type": "interpretation", "text": "My reading of that.", "citations": [{"passage_id": p["id"]}]}]}


# ------------------------------------------------------------------ evidence + persistence
def test_assistant_turn_records_supplied_evidence_and_cited_flags(env):
    cid = env.chat()
    r = env.say(cid, Q, "explain")
    assert r.status_code == 200
    a = r.json()["assistant_message"]
    assert a["provider_label"] == "Demo: scripted responses, not live tutoring."
    assert a["evidence"] and all({"id", "doc_title", "location", "text", "cited"} <= set(e) for e in a["evidence"])
    cited = {c["passage_id"] for b in a["blocks"] for c in b["citations"]}
    assert cited and cited <= {e["id"] for e in a["evidence"]}
    assert {e["id"] for e in a["evidence"] if e["cited"]} == cited
    assert all(c["ok"] for b in a["blocks"] for c in b["citations"])
    assert {b["type"] for b in a["blocks"]} >= {"quote", "interpretation"}


def test_conversation_persists_across_restart(tmp_path):
    e1 = Env(tmp_path).load()
    cid = e1.chat(title="Persist me")
    e1.say(cid, Q, "explain")
    e1.say(cid, "And how do they relate?", "ask")
    e2 = Env(tmp_path)                      # new app instance, same data dir
    conv = e2.client.get(f"/api/conversations/{cid}").json()
    assert conv["title"] == "Persist me" and len(conv["messages"]) == 4
    assert conv["messages"][1]["evidence"] and conv["messages"][1]["report"]["ok"]
    assert conv["scope"] == {"doc_ids": [], "tags": [], "include_secondary": False}
    assert [c["id"] for c in e2.client.get("/api/conversations").json()] == [cid]
    assert e2.client.patch(f"/api/conversations/{cid}", json={"title": "Renamed"}).json()["title"] == "Renamed"
    assert e2.client.delete(f"/api/conversations/{cid}").status_code == 200
    assert e2.client.get(f"/api/conversations/{cid}").status_code == 404


def test_scope_restricts_chat_evidence_and_unapproved_never_used(env):
    scope = {"doc_ids": [env.ids["workshop"]]}
    cid = env.chat(scope=scope)
    a = env.say(cid, "constraint facts conditions teach apprentices", "ask").json()["assistant_message"]
    assert {e["doc_id"] for e in a["evidence"]} == {env.ids["workshop"]}
    # the unapproved injection doc can never appear even in an unrestricted session
    cid2 = env.chat()
    a2 = env.say(cid2, "orchard cooperative pickers packers pace contradiction", "ask").json()["assistant_message"]
    assert env.ids["inject"] not in {e["doc_id"] for e in a2["evidence"]}


def test_no_approved_docs_or_no_match_makes_no_model_call(tmp_path):
    prov = ScriptedProvider(lambda r: good_reply(r))
    e = make_env(tmp_path, prov, approve=())
    cid = e.chat()
    r = e.say(cid, Q).json()
    assert r["model_called"] is False and "No approved documents" in r["assistant_message"]["blocks"][0]["text"]
    assert prov.requests == []
    e.client.post(f"/api/documents/{e.ids['mill']}/approval", json={"approved": True})
    r = e.say(cid, "quantum chromodynamics tokamak").json()
    assert r["model_called"] is False
    assert "does not establish" in r["assistant_message"]["blocks"][0]["text"]
    assert prov.requests == []


def test_compare_with_one_document_is_not_manufactured(tmp_path):
    prov = ScriptedProvider(lambda r: good_reply(r))
    e = make_env(tmp_path, prov, approve=("workshop",))
    r = e.say(e.chat(), "compare apprentices delegation fairly", "compare").json()
    assert r["model_called"] is False
    assert "at least two" in r["assistant_message"]["blocks"][0]["text"]
    assert r["assistant_message"]["evidence"]       # the passages found are still inspectable


def test_compare_across_two_documents_yields_verified_synthesis(env):
    r = env.say(env.chat(), "main constraint conditions facts change", "compare").json()
    blocks = r["assistant_message"]["blocks"]
    syn = [b for b in blocks if b["type"] == "synthesis"]
    assert syn and syn[0]["status"] == "verified"
    assert len({c["doc_id"] for c in syn[0]["citations"]}) >= 2


# ------------------------------------------------------------------ citation validation
def bad_id_reply(req):
    return {"blocks": [{"type": "interpretation", "text": "Fake claim.",
                        "citations": [{"passage_id": "ZZZZ-9999"}]}]}


def test_invalid_passage_id_gets_one_repair_then_is_withheld(tmp_path):
    prov = ScriptedProvider(bad_id_reply)
    e = make_env(tmp_path, prov)
    a = e.say(e.chat("demo"), Q).json()["assistant_message"]
    assert len(prov.requests) == 2                              # original + exactly one repair
    assert prov.requests[1].context["repair"] is True
    assert "unknown_passage" in " ".join(prov.requests[1].context["repair_errors"])
    assert a["blocks"][0]["type"] == "withheld" and "Fake claim" not in json.dumps(a["blocks"])
    assert a["report"]["repair_attempted"] and a["report"]["invalid_count"] == 1


def test_repair_that_succeeds_shows_verified_citations(tmp_path):
    prov = ScriptedProvider(bad_id_reply, lambda r: good_reply(r))
    e = make_env(tmp_path, prov)
    a = e.say(e.chat(), Q).json()["assistant_message"]
    assert len(prov.requests) == 2
    assert all(b["status"] == "verified" for b in a["blocks"]) and a["report"]["repair_attempted"]


def test_fabricated_quotation_is_withheld(tmp_path):
    def fab(req):
        p = req.passages[0]
        return {"blocks": [{"type": "quote", "text": "This sentence appears nowhere in the library at all.",
                            "citations": [{"passage_id": p["id"], "quote": "This sentence appears nowhere in the library at all."}]}]}
    prov = ScriptedProvider(fab)
    e = make_env(tmp_path, prov)
    a = e.say(e.chat(), Q).json()["assistant_message"]
    assert a["blocks"][0]["type"] == "withheld" and "quoted text does not appear" in a["blocks"][0]["reason"]


def test_quote_matching_is_whitespace_only(env):
    with env.svc.db.tx() as c:
        pid = c.execute("SELECT id, text FROM chunks WHERE doc_id=? ORDER BY ordinal LIMIT 1",
                        (env.ids["workshop"],)).fetchone()
        text = pid["text"]
        base = " ".join(text.split()[:8])
        allowed, scope = {pid["id"]}, {env.ids["workshop"]}
        def check(q):
            b = normalize_blocks({"blocks": [{"type": "quote", "text": q, "citations": [{"passage_id": pid["id"], "quote": q}]}]})
            return validate_blocks(c, b, allowed, scope)["ok"]
        assert check(base)
        assert check(base.replace(" ", "\n  "))          # whitespace differences tolerated
        assert not check(base.upper())                    # case is NOT normalized
        assert not check(base.replace(" ", "... ", 1))    # no ellipsis tolerance


def test_out_of_scope_or_unapproved_citation_is_invalid(env):
    with env.svc.db.tx() as c:
        mill = c.execute("SELECT id FROM chunks WHERE doc_id=? LIMIT 1", (env.ids["mill"],)).fetchone()["id"]
        inj = c.execute("SELECT id FROM chunks WHERE doc_id=? LIMIT 1", (env.ids["inject"],)).fetchone()["id"]
        blocks = normalize_blocks({"blocks": [
            {"type": "interpretation", "text": "a", "citations": [{"passage_id": mill}]},
            {"type": "interpretation", "text": "b", "citations": [{"passage_id": inj}]}]})
        rep = validate_blocks(c, blocks, {mill, inj}, {env.ids["workshop"]})   # mill not in scope
        assert [b["status"] for b in rep["blocks"]] == ["invalid", "invalid"]
        assert all(b["errors"][0]["code"] == "out_of_scope" for b in rep["blocks"])
        rep2 = validate_blocks(c, blocks, {mill, inj}, {env.ids["mill"], env.ids["inject"]})
        assert rep2["blocks"][0]["status"] == "verified"
        assert rep2["blocks"][1]["errors"][0]["code"] == "out_of_scope"        # inject unapproved


def test_passage_not_supplied_this_turn_is_rejected(env):
    with env.svc.db.tx() as c:
        mill = c.execute("SELECT id FROM chunks WHERE doc_id=? LIMIT 1", (env.ids["mill"],)).fetchone()["id"]
        b = normalize_blocks({"blocks": [{"type": "interpretation", "text": "x", "citations": [{"passage_id": mill}]}]})
        rep = validate_blocks(c, b, set(), {env.ids["mill"]})
        assert rep["blocks"][0]["errors"][0]["code"] == "unknown_passage"


def test_synthesis_needs_two_documents_and_cited_claims_need_citations(env):
    with env.svc.db.tx() as c:
        mill = c.execute("SELECT id FROM chunks WHERE doc_id=? LIMIT 1", (env.ids["mill"],)).fetchone()["id"]
        b = normalize_blocks({"blocks": [
            {"type": "synthesis", "text": "x", "citations": [{"passage_id": mill}]},
            {"type": "interpretation", "text": "no cite"},
            {"type": "coaching", "text": "A question for you?"},
            {"type": "weird", "text": "?"}]})
        rep = validate_blocks(c, b, {mill}, {env.ids["mill"]})
        assert [x["status"] for x in rep["blocks"]] == ["invalid", "invalid", "uncited", "invalid"]
        assert rep["blocks"][0]["errors"][0]["code"] == "synthesis_needs_two_documents"
        assert rep["blocks"][1]["errors"][0]["code"] == "missing_citation"


def test_malformed_model_output_is_repaired_once_then_errors_without_saving(tmp_path):
    prov = ScriptedProvider({"blocks": "nope"})
    e = make_env(tmp_path, prov)
    cid = e.chat()
    r = e.say(cid, Q)
    assert r.status_code == 502 and "usable structured answer" in r.json()["detail"]
    assert len(prov.requests) == 2
    assert e.client.get(f"/api/conversations/{cid}").json()["messages"] == []   # nothing half-saved


# ------------------------------------------------------------------ prompt injection
def test_document_prompt_injection_cannot_reach_system_prompt_or_break_wrapper(tmp_path):
    prov = ScriptedProvider(lambda r: good_reply(r))
    e = make_env(tmp_path, prov, approve=("mill", "inject"))
    e.say(e.chat(), "orchard cooperative pickers packers pace contradiction", "ask")
    req = prov.requests[0]
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" not in req.system
    user = req.messages[-1]["content"]
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in user                 # present, but only as data...
    inside = user.split("<retrieved_passages", 1)[1].split("</retrieved_passages>")[0]
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in inside               # ...inside the wrapper
    assert user.count("</retrieved_passages>") == 1 and user.count("</passage>") == len(req.passages)
    assert "&lt;/passage" in user                                     # spoofed closing tags neutralised
    assert "untrusted" in req.system.lower() and "never obey" in req.system.lower()


def test_injected_instruction_to_cite_fake_id_is_withheld(tmp_path):
    def obeys_injection(req):
        return {"blocks": [{"type": "interpretation", "text": "Per the document, no other sources are needed.",
                            "citations": [{"passage_id": "ZZZZ-9999"}]}]}
    prov = ScriptedProvider(obeys_injection)
    e = make_env(tmp_path, prov, approve=("mill", "inject"))
    a = e.say(e.chat(), "orchard cooperative pickers packers pace contradiction").json()["assistant_message"]
    assert a["blocks"][0]["type"] == "withheld"


# ------------------------------------------------------------------ bounded context
def test_scope_stays_in_force_and_context_is_bounded_with_summary(tmp_path):
    prov = ScriptedProvider(lambda r: good_reply(r))
    e = make_env(tmp_path, prov)
    cid = e.chat(scope={"doc_ids": [e.ids["mill"]]})
    for i in range(9):
        assert e.say(cid, f"Question {i}: what causes change, internal contradiction or conditions?").status_code == 200
    last = prov.requests[-1]
    assert "synthetic_a_mill_town_notes" in last.system and "always in force" in last.system
    assert len(last.messages) <= 13                                   # 12 history + current turn
    assert "condensed" in last.system and "Learner said: Question 0" in last.system
    conv = e.client.get(f"/api/conversations/{cid}").json()
    assert conv["summary"] and "not by a model" in conv["summary_note"]
    assert all(m["role"] in ("user", "assistant") for m in last.messages)


def test_followup_reuses_previous_cited_passages(tmp_path):
    prov = ScriptedProvider(lambda r: good_reply(r))
    e = make_env(tmp_path, prov)
    cid = e.chat()
    e.say(cid, Q)
    first = prov.requests[0].passages[0]["id"]
    r = e.say(cid, "Can you say more about that?").json()
    assert r["retrieval"]["query"].startswith(Q[:20])                 # short follow-up reuses prior question
    assert first in [p["id"] for p in prov.requests[1].passages]


# ------------------------------------------------------------------ provider errors / credentials
def test_live_without_credentials_gives_setup_message_and_app_still_works(env):
    st = env.client.get("/api/status").json()
    assert st["live_configured"] is False and "ANTHROPIC_API_KEY" in st["live_setup_message"]
    r = env.client.post("/api/conversations", json={"provider": "live", "scope": {}, "acknowledge_live": True})
    assert r.status_code == 400 and "ANTHROPIC_API_KEY" in r.json()["detail"] and "ANTHROPIC_MODEL" in r.json()["detail"]
    assert env.client.get("/api/documents").status_code == 200
    assert env.client.get("/api/search", params={"q": "contradiction"}).status_code == 200
    r = env.client.post("/api/exercises", json={"provider": "live", "acknowledge_live": True})
    assert r.status_code == 400


def _anthropic_error(cls, status, msg):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(status, request=req)
    return cls(msg, response=resp, body=None)


class FakeClient:
    def __init__(self, exc=None, content=None):
        self.exc, self.content = exc, content
        self.calls = 0
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        self.kwargs = kw
        if self.exc:
            raise self.exc
        return type("R", (), {"content": self.content})()


@pytest.mark.parametrize("cls,status,expect", [
    (anthropic.AuthenticationError, 401, "authentication failed"),
    (anthropic.NotFoundError, 404, "ANTHROPIC_MODEL"),
    (anthropic.RateLimitError, 429, "rate limit"),
    (anthropic.InternalServerError, 500, "HTTP 500"),
])
def test_api_errors_are_reported_without_leaking_key_or_saving(tmp_path, cls, status, expect):
    secret = "sk-ant-SECRET-1234567890"
    fake = FakeClient(exc=_anthropic_error(cls, status, f"boom {secret}"))
    prov = AnthropicProvider(secret, "model-id-from-env", 512, client=fake, sleep=lambda s: None)
    e = make_env(tmp_path, prov, anthropic_api_key=secret, anthropic_model="model-id-from-env")
    cid = e.chat("live")
    r = e.say(cid, Q)
    assert r.status_code in (429, 502) and expect in r.json()["detail"]
    assert secret not in r.text
    assert e.client.get(f"/api/conversations/{cid}").json()["messages"] == []


def test_connection_error_is_reported(tmp_path):
    fake = FakeClient(exc=anthropic.APIConnectionError(request=httpx.Request("POST", "https://x")))
    e = make_env(tmp_path, AnthropicProvider("k", "m", 512, client=fake, sleep=lambda s: None))
    r = e.say(e.chat("live"), Q)
    assert r.status_code == 502 and "Could not reach" in r.json()["detail"]


def test_anthropic_adapter_uses_forced_tool_call_and_returns_blocks(tmp_path):
    def reply(req):
        return good_reply(req)
    holder = {}

    class Tool:
        type = "tool_use"
        def __init__(self, inp): self.input = inp
    class Capturing(FakeClient):
        def create(self, **kw):
            holder["kw"] = kw
            user = kw["messages"][-1]["content"]
            pid = user.split('<passage id="', 1)[1].split('"', 1)[0]
            text = user.split(">\n", 2)[2].split("\n</passage>")[0] if False else None
            return type("R", (), {"content": [Tool({"blocks": [
                {"type": "interpretation", "text": "ok", "citations": [{"passage_id": pid}]}]})]})()
    fake = Capturing()
    e = make_env(tmp_path, AnthropicProvider("k", "configured-model", 777, client=fake))
    a = e.say(e.chat("live"), Q).json()["assistant_message"]
    kw = holder["kw"]
    assert kw["model"] == "configured-model" and kw["max_tokens"] == 777
    assert kw["tool_choice"] == {"type": "tool", "name": "submit_response"}
    assert a["provider_label"] == "Live model: configured-model" and a["blocks"][0]["status"] == "verified"


# ------------------------------------------------------------------ privacy / secrets / local-only
def test_no_secret_leakage_anywhere(tmp_path):
    secret = "sk-ant-LEAKCHECK-987654321"
    prov = ScriptedProvider(lambda r: good_reply(r))
    e = make_env(tmp_path, prov, anthropic_api_key=secret, anthropic_model="m-1")
    cid = e.chat()
    e.say(cid, Q)
    outputs = [e.client.get(p).text for p in (
        "/api/status", "/api/documents", "/api/conversations", f"/api/conversations/{cid}",
        f"/api/conversations/{cid}/export.md?transcript=true", "/", "/static/app.js", "/static/style.css")]
    assert all(secret not in o for o in outputs)
    st = e.client.get("/api/status").json()
    assert st["api_key_present"] is True and "anthropic_api_key" not in json.dumps(st)
    db_bytes = (tmp_path / "data" / "tutor.db").read_bytes()
    assert secret.encode() not in db_bytes
    for f in (tmp_path / "data").rglob("*"):
        if f.is_file():
            assert secret.encode() not in f.read_bytes()
    assert repr(e.settings.public_dict()).find(secret) == -1


def test_gitignore_protects_secrets_and_data():
    from conftest import ROOT
    gi = (ROOT / ".gitignore").read_text()
    for needle in (".env", "data/", "*.db"):
        assert needle in gi
    ex = (ROOT / ".env.example").read_text()
    assert "ANTHROPIC_API_KEY=\n" in ex and "sk-" not in ex


def test_only_localhost_hosts_and_same_origin_posts(env):
    assert env.client.get("/api/status", headers={"host": "evil.example.com"}).status_code == 403
    assert env.client.get("/api/status", headers={"host": "localhost:8000"}).status_code == 200
    r = env.client.post("/api/conversations", json={"provider": "demo"},
                        headers={"origin": "http://evil.example.com"})
    assert r.status_code == 403
    assert Settings.from_env({}, dotenv=False).host == "127.0.0.1"


def test_users_own_answers_are_never_indexed_as_sources(env):
    env.client.post("/api/exercises", json={})
    cid = env.client.get("/api/conversations").json()[0]["id"]
    env.client.post(f"/api/conversations/{cid}/exercise",
                    json={"action": "answer", "text": "My xylophonic zebra hypothesis explains everything."})
    hits = env.client.get("/api/search", params={"q": "xylophonic zebra hypothesis"}).json()["hits"]
    assert hits == []


def test_flagging_unsupported_interpretations(env):
    cid = env.chat()
    a = env.say(cid, Q, "explain").json()["assistant_message"]
    pid = a["blocks"][1]["citations"][0]["passage_id"]
    r = env.client.post(f"/api/messages/{a['id']}/flags", json={"block_index": 1, "chunk_id": pid, "note": "overreads"})
    assert r.status_code == 200
    conv = env.client.get(f"/api/conversations/{cid}").json()
    assert conv["messages"][1]["flags"][0]["note"] == "overreads"
    md = env.client.get(f"/api/conversations/{cid}/export.md").text
    assert "Flagged for review" in md and "overreads" in md
    env.client.delete(f"/api/flags/{r.json()['id']}")
    assert env.client.get(f"/api/conversations/{cid}").json()["messages"][1]["flags"] == []
