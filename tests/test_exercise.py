"""Exercise engine: turn-taking, no premature reveal, gating, modes, reflection."""
import json

import pytest

from conftest import Env, ScriptedProvider, make_env

ANSWER = ("The two teams are in tension because their aims differ; I observe the sales rose, and I infer "
          "stock timing is the cause. Another explanation might be the new oven, but I am not sure.")


def start(env, **cfg):
    r = env.client.post("/api/exercises", json={"provider": "demo", **cfg})
    assert r.status_code == 200, r.text
    return r.json()


def act(env, cid, action, text="", confirm=False):
    return env.client.post(f"/api/conversations/{cid}/exercise",
                           json={"action": action, "text": text, "confirm": confirm})


def purposes(msg):
    return [b.get("purpose") for b in msg["blocks"]]


def questions(msg):
    return [b for b in msg["blocks"] if b.get("purpose") == "question" and b["type"] != "withheld"]


def last_ai(conv):
    return [m for m in conv["messages"] if m["role"] == "assistant"][-1]


def test_opening_has_labeled_fiction_one_question_and_no_analysis(env):
    j = start(env, level="beginner")
    assert j["status"] == "started"
    conv = j["conversation"]
    ex = conv["exercise"]
    msg = conv["messages"][0]
    assert ex["phase"] == "attempt" and ex["attempts"] == [] and ex["analysis"] == [] and ex["analysis_shown"] is False
    assert len(questions(msg)) == 1 and msg["blocks"][-1]["purpose"] == "question"
    fiction = [b for b in msg["blocks"] if b["type"] == "fiction"]
    assert fiction and fiction[0]["text"].startswith("FICTIONAL SCENARIO")
    assert "analysis" not in purposes(msg) and "reflection" not in purposes(msg)
    assert "app-created learning aid" in ex["rubric_note"]
    assert msg["provider_label"] == "Demo: scripted responses, not live tutoring."
    # source basis is quoted, validated and spans two documents
    quotes = [b for b in msg["blocks"] if b["type"] == "quote"]
    assert len({c["doc_id"] for b in quotes for c in b["citations"]}) == 2
    assert "score" not in ex["rubric_note"].lower().replace("no scores", "")


def test_full_flow_waits_for_user_and_asks_one_question_at_a_time(env):
    cid = start(env)["conversation"]["id"]
    seen_phases = ["attempt"]
    # an empty attempt is refused and does not advance anything
    assert act(env, cid, "answer", "   ").status_code == 400
    c1 = act(env, cid, "answer", ANSWER).json()["conversation"]
    assert c1["exercise"]["phase"] == "probe" and len(questions(last_ai(c1))) == 1
    assert "feedback" in purposes(last_ai(c1))
    c2 = act(env, cid, "answer", "If I were wrong the complaints would not cluster; I would check the logs.").json()["conversation"]
    assert c2["exercise"]["phase"] == "revision" and len(questions(last_ai(c2))) == 1
    assert "complication" in purposes(last_ai(c2)) and c2["exercise"]["complication"]
    c3 = act(env, cid, "answer", "In light of the new fact I revise my explanation; previously I assumed too much.").json()["conversation"]
    assert c3["exercise"]["phase"] == "review" and questions(last_ai(c3)) == []   # invites revision, no new question
    assert "next_steps" in purposes(last_ai(c3))
    assert [a["phase"] for a in c3["exercise"]["attempts"]] == ["attempt", "probe", "revision"]
    c4 = act(env, cid, "finish").json()["conversation"]
    assert c4["exercise"]["phase"] == "done" and c4["exercise"]["reflection"]
    assert "reflection" in purposes(last_ai(c4)) and c4["exercise"]["available_actions"] == ["show_analysis"]
    assert act(env, cid, "answer", "more").status_code == 409                    # finished
    # every user message was followed by exactly one assistant message
    roles = [m["role"] for m in c4["messages"]]
    assert roles == ["assistant"] + ["user", "assistant"] * 4


def test_cannot_advance_without_attempt_or_while_paused(env):
    cid = start(env)["conversation"]["id"]
    assert act(env, cid, "finish").status_code == 409                    # no attempt yet
    assert act(env, cid, "resume").status_code == 409                    # not paused
    p = act(env, cid, "pause").json()["conversation"]
    assert p["exercise"]["phase"] == "paused" and p["exercise"]["available_actions"] == ["resume"]
    for bad in ("answer", "hint", "clarify", "show_analysis", "finish"):
        assert act(env, cid, bad, "text").status_code == 409, bad
    r = act(env, cid, "resume").json()["conversation"]
    assert r["exercise"]["phase"] == "attempt"
    assert r["messages"][-1]["blocks"][-1]["text"] == r["exercise"]["current_question"]


def test_hint_and_clarify_do_not_advance_or_reveal_and_restate_the_question(env):
    c0 = start(env)["conversation"]
    cid, q = c0["id"], c0["exercise"]["current_question"]
    h = act(env, cid, "hint").json()["conversation"]
    assert h["exercise"]["phase"] == "attempt" and h["exercise"]["hints_used"] == 1 and h["exercise"]["attempts"] == []
    assert "hint" in purposes(last_ai(h)) and last_ai(h)["blocks"][-1]["text"] == q
    for _ in range(2):
        h = act(env, cid, "hint").json()["conversation"]
    assert "will not narrow it further" in json.dumps(last_ai(h)["blocks"])
    assert act(env, cid, "clarify", "").status_code == 400
    cl = act(env, cid, "clarify", "How many bakers are there?").json()["conversation"]
    assert cl["exercise"]["phase"] == "attempt" and cl["exercise"]["attempts"] == []
    assert "cannot add facts" in json.dumps(last_ai(cl)["blocks"])


def test_show_analysis_needs_confirmation_before_any_attempt(env):
    cid = start(env)["conversation"]["id"]
    r = act(env, cid, "show_analysis").json()
    assert r["status"] == "needs_confirmation"
    conv = env.client.get(f"/api/conversations/{cid}").json()
    assert len(conv["messages"]) == 1 and conv["exercise"]["analysis"] == []       # nothing revealed or saved
    shown = act(env, cid, "show_analysis", confirm=True).json()["conversation"]
    assert shown["exercise"]["analysis_shown"] and shown["exercise"]["analysis"]
    assert "analysis" in purposes(last_ai(shown))
    assert "not THE answer" in json.dumps(last_ai(shown)["blocks"])               # defensible alternatives allowed
    cid2 = start(env)["conversation"]["id"]
    act(env, cid2, "answer", ANSWER)
    assert act(env, cid2, "show_analysis").json()["status"] == "ok"                # after an attempt: no confirm


def test_leaky_or_chatty_model_is_contained_by_the_engine(tmp_path):
    """A provider that reveals the analysis and asks 3 questions in the opening turn."""
    def leaky(req):
        p = req.passages[0]
        q = " ".join(p["text"].split()[:10])
        return {"blocks": [
            {"type": "quote", "purpose": "source_basis", "text": q, "citations": [{"passage_id": p["id"], "quote": q}]},
            {"type": "fiction", "purpose": "scenario", "text": "FICTIONAL SCENARIO: a pond co-op.", "citations": []},
            {"type": "coaching", "purpose": "analysis", "text": "FULL ANSWER: the cause is X.", "citations": []},
            {"type": "coaching", "purpose": "reflection", "text": "Reflection already?", "citations": []},
            {"type": "coaching", "purpose": "question", "text": "Question one?", "citations": []},
            {"type": "coaching", "purpose": "question", "text": "Question two?", "citations": []},
            {"type": "coaching", "purpose": "question", "text": "Question three?", "citations": []}]}
    e = make_env(tmp_path, ScriptedProvider(leaky))
    j = e.client.post("/api/exercises", json={"allow_single_source": True}).json()
    assert j["status"] == "started"
    msg = j["conversation"]["messages"][0]
    assert "FULL ANSWER" not in json.dumps(msg) and "analysis" not in purposes(msg)
    assert len(questions(msg)) == 1 and questions(msg)[0]["text"] == "Question one?"
    assert set(msg["report"]["engine"]["stripped_purposes"]) >= {"analysis", "reflection", "extra_question"}
    assert j["conversation"]["exercise"]["analysis"] == []


def test_missing_question_gets_app_authored_fallback(tmp_path):
    def silent(req):
        p = req.passages[0]
        q = " ".join(p["text"].split()[:10])
        return {"blocks": [{"type": "quote", "purpose": "source_basis", "text": q,
                            "citations": [{"passage_id": p["id"], "quote": q}]},
                           {"type": "fiction", "purpose": "scenario", "text": "FICTIONAL: a pond co-op.", "citations": []}]}
    e = make_env(tmp_path, ScriptedProvider(silent))
    j = e.client.post("/api/exercises", json={"allow_single_source": True}).json()
    msg = j["conversation"]["messages"][0]
    assert len(questions(msg)) == 1 and questions(msg)[0].get("app") is True
    assert msg["report"]["engine"]["fallback_question"] is True


def test_exercise_citations_are_validated_like_chat(tmp_path):
    def fake_cite(req):
        return {"blocks": [{"type": "interpretation", "purpose": "source_basis", "text": "Per source...",
                            "citations": [{"passage_id": "NOPE-0001"}]},
                           {"type": "coaching", "purpose": "question", "text": "Q?", "citations": []}]}
    prov = ScriptedProvider(fake_cite)
    e = make_env(tmp_path, prov)
    j = e.client.post("/api/exercises", json={"allow_single_source": True}).json()
    blocks = j["conversation"]["messages"][0]["blocks"]
    assert blocks[0]["type"] == "withheld" and len(prov.requests) == 2


def test_multi_source_limitation_is_explained_not_faked(tmp_path):
    e = Env(tmp_path).load(approve_keys=("workshop",))
    r = e.client.post("/api/exercises", json={"level": "beginner"}).json()
    assert r["status"] == "needs_confirmation" and "at least two" in r["message"]
    assert e.client.get("/api/conversations").json() == []                 # nothing created yet
    r = e.client.post("/api/exercises", json={"allow_single_source": True}).json()
    assert r["status"] == "started"
    conv = r["conversation"]
    assert conv["exercise"]["multi_source"] is False
    assert conv["messages"][0]["blocks"][0]["text"].startswith("Limitation: Single-source")
    assert len({c["doc_id"] for b in conv["messages"][0]["blocks"] for c in b["citations"]}) == 1


def test_blocked_when_library_empty_or_irrelevant_or_history_thin(tmp_path):
    e = Env(tmp_path).load(approve_keys=())
    assert e.client.post("/api/exercises", json={}).json()["status"] == "blocked"
    e2 = Env(tmp_path / "b").load()
    r = e2.client.post("/api/exercises", json={"focus": "", "scope": {"doc_ids": [e2.ids["mill"]]},
                                              "scenario_kind": "historical", "historical_topic": "Siege of Zorblax"}).json()
    assert r["status"] == "blocked" and "too thinly" in r["message"]
    assert e2.client.post("/api/exercises", json={"scenario_kind": "historical"}).status_code == 400
    # a documented historical case works only because the library actually covers it
    r = e2.client.post("/api/exercises", json={"scenario_kind": "historical", "historical_topic":
                                              "town tension conditions"}).json()
    assert r["status"] == "started"
    assert not [b for b in r["conversation"]["messages"][0]["blocks"] if b["type"] == "fiction"]


def test_exercise_stops_if_its_source_basis_is_unapproved_mid_session(env):
    cid = start(env)["conversation"]["id"]
    for k in ("mill", "workshop", "harbour"):
        env.client.post(f"/api/documents/{env.ids[k]}/approval", json={"approved": False})
    r = act(env, cid, "answer", ANSWER)
    assert r.status_code == 409 and "no longer available" in r.json()["detail"]


def test_sessions_are_saved_and_resumable(tmp_path):
    e1 = Env(tmp_path).load()
    cid = start(e1)["conversation"]["id"]
    act(e1, cid, "answer", ANSWER)
    e2 = Env(tmp_path)
    conv = e2.client.get(f"/api/conversations/{cid}").json()
    assert conv["exercise"]["phase"] == "probe" and len(conv["exercise"]["attempts"]) == 1
    assert act(e2, cid, "answer", "Second answer, would check the logs.").status_code == 200


@pytest.mark.parametrize("mode", ["belief_test", "main_constraint", "development_lab"])
def test_other_modes_reuse_the_same_engine(env, mode):
    r = env.client.post("/api/exercises", json={"mode": mode, "level": "intermediate", "allow_single_source": True}).json()
    assert r["status"] == "started", r
    conv = r["conversation"]
    msg = conv["messages"][0]
    assert len(questions(msg)) == 1 and any(b["type"] == "fiction" for b in msg["blocks"])
    assert conv["exercise"]["mode"] == mode
    a = act(env, conv["id"], "answer", ANSWER).json()["conversation"]
    assert a["exercise"]["phase"] == "probe" and len(questions(last_ai(a))) == 1


def test_validation_of_bad_exercise_requests(env):
    assert env.client.post("/api/exercises", json={"mode": "nope"}).status_code == 400
    assert env.client.post("/api/exercises", json={"level": "godlike"}).status_code == 400
    cid = start(env)["conversation"]["id"]
    assert act(env, cid, "dance").status_code == 400
    assert act(env, cid, "answer", "x" * 7000).status_code == 400
    chat = env.chat()
    assert act(env, chat, "answer", "hi").status_code == 409
    assert env.say(cid, "free chat in an exercise").status_code == 409


def test_feedback_is_qualitative_labeled_and_sources_are_checkable(env):
    cid = start(env)["conversation"]["id"]
    c = act(env, cid, "answer", ANSWER).json()["conversation"]
    fb = [b for b in last_ai(c)["blocks"] if b.get("purpose") == "feedback"]
    text = " ".join(b["text"] for b in fb)
    assert "NOT an evaluation" in text and "Keyword matches" in text and "does not show an idea is supported" in text
    assert not any(ch in text for ch in ("/10", "%", "IQ"))
    assert any(b["type"] == "quote" and b["status"] == "verified" for b in fb)    # source-supported feedback
