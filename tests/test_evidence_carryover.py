"""Regression: evidence from an earlier turn is carried ONLY into a recognised follow-up.

Found during real-document acceptance: an unrelated question asked mid-conversation inherited the
previous turn's cited passages, so the app answered from them instead of refusing. The gate lives in
the shared chat orchestration, so these tests use a spy provider (standing in for live) as well as demo.
"""
from conftest import Env, ScriptedProvider, make_env

Q1 = "What causes change in the fictional mill town, internal contradiction or external conditions?"
UNRELATED = "photosynthesis chlorophyll enzymes"


def cite_first(req):
    p = req.passages[0]
    q = " ".join(p["text"].split()[:10])
    return {"blocks": [{"type": "quote", "text": q, "citations": [{"passage_id": p["id"], "quote": q}]},
                       {"type": "interpretation", "text": "Reading.", "citations": [{"passage_id": p["id"]}]}]}


def test_unrelated_unsupported_question_gets_no_carried_evidence_and_no_provider_call(tmp_path):
    prov = ScriptedProvider(cite_first)
    e = make_env(tmp_path, prov)
    cid = e.chat()
    e.say(cid, Q1)
    calls = len(prov.requests)
    r = e.say(cid, UNRELATED).json()
    assert r["model_called"] is False
    assert len(prov.requests) == calls                                   # spy provider never invoked
    assert r["retrieval"]["carried_over"] == []
    assert r["assistant_message"]["evidence"] == []
    assert "no passages" in r["assistant_message"]["blocks"][0]["text"].lower()


def test_unrelated_question_refused_in_demo_mode_too(tmp_path):
    e = Env(tmp_path).load()                                            # real demo provider
    cid = e.chat(provider="demo")
    e.say(cid, Q1)
    r = e.say(cid, UNRELATED).json()
    assert r["model_called"] is False and r["assistant_message"]["evidence"] == []


def test_legitimate_followup_keeps_eligible_prior_evidence(tmp_path):
    prov = ScriptedProvider(cite_first)
    e = make_env(tmp_path, prov)
    cid = e.chat()
    e.say(cid, Q1)
    cited = prov.requests[0].passages[0]["id"]
    r = e.say(cid, "How does that change?").json()
    assert r["retrieval"]["followup"] is True
    assert cited in {p["id"] for p in prov.requests[-1].passages}


def test_new_supported_topic_does_not_inherit_old_topic_passages(tmp_path):
    prov = ScriptedProvider(cite_first)
    e = make_env(tmp_path, prov)
    cid = e.chat()
    e.say(cid, Q1)
    r = e.say(cid, "What does the primer say about delegation and fair assessment of newcomers?").json()
    assert r["retrieval"]["followup"] is False
    assert r["retrieval"]["carried_over"] == []                         # only freshly retrieved passages


def test_unapproval_between_turns_withdraws_evidence_from_followups(tmp_path):
    prov = ScriptedProvider(cite_first)
    e = make_env(tmp_path, prov)
    cid = e.chat()
    e.say(cid, Q1)
    cited_doc = prov.requests[0].passages[0]["doc_id"]
    e.client.post(f"/api/documents/{cited_doc}/approval", json={"approved": False})
    e.say(cid, "How does that change?")
    if len(prov.requests) > 1:
        assert cited_doc not in {p["doc_id"] for p in prov.requests[-1].passages}
