"""Finding 4: context-aware follow-up retrieval that never silently widens source scope."""
import pytest

from app import followup
from conftest import Env, ScriptedProvider, make_env

Q1 = "What causes change in the fictional mill town, internal contradiction or external conditions?"


def cite_first(req):
    p = req.passages[0]
    q = " ".join(p["text"].split()[:10])
    return {"blocks": [{"type": "quote", "text": q, "citations": [{"passage_id": p["id"], "quote": q}]},
                       {"type": "interpretation", "text": "Reading.", "citations": [{"passage_id": p["id"]}]}]}


@pytest.mark.parametrize("msg", ["How does that change?", "Give another example", "Why is that the principal one?",
                                 "Can you say more about that?", "And what about it?"])
def test_short_messages_are_recognised_as_followups(msg):
    assert followup.classify(msg).is_followup


@pytest.mark.parametrize("msg", [Q1, "Explain the principal contradiction in the workshop handbook",
                                 "What does the primer say about delegation and fair assessment?"])
def test_substantive_questions_are_not_followups(msg):
    assert not followup.classify(msg).is_followup


def test_seeks_new_only_for_requests_for_other_material():
    assert followup.classify("Give another example").seeks_new
    assert followup.classify("Is there a different case?").seeks_new
    assert not followup.classify("Can you say more about that?").seeks_new      # elaboration, not new


def test_anchor_is_last_substantive_question_so_followup_chains_do_not_drift():
    texts = [Q1, "Give another example"]
    assert followup.anchor_question(texts) == Q1
    q, fu, anchor = followup.build_query("Why is that the principal one?", texts)
    assert anchor == Q1 and q.startswith("Why is that the principal one?") and "mill" in q
    assert "another example" not in q                                          # the old bug


def test_why_principal_followup_finds_the_principal_passage(tmp_path):
    prov = ScriptedProvider(cite_first)
    e = make_env(tmp_path, prov, approve=("mill", "workshop", "harbour"))
    cid = e.chat()
    e.say(cid, Q1)
    e.say(cid, "Give another example")
    r = e.say(cid, "Why is that the principal one?").json()
    assert r["retrieval"]["followup"] and r["retrieval"]["anchor"] == Q1
    texts = " ".join(p["text"] for p in prov.requests[-1].passages).lower()
    assert "principal" in texts                                                # Part Two of the mill notes
    assert r["assistant_message"]["report"]["retrieval"]["query"] == r["retrieval"]["query"]   # shown to the user


def test_how_does_that_change_carries_previous_evidence_even_if_nothing_was_cited(tmp_path):
    prov = ScriptedProvider({"blocks": [{"type": "coaching", "text": "What do you think?"}]})   # cites nothing
    e = make_env(tmp_path, prov, approve=("mill", "workshop", "harbour"))
    cid = e.chat()
    e.say(cid, Q1)
    first_ids = [p["id"] for p in prov.requests[0].passages]
    r = e.say(cid, "How does that change?").json()
    second_ids = [p["id"] for p in prov.requests[1].passages]
    assert set(first_ids[:3]) & set(second_ids)                                 # context survives
    assert r["retrieval"]["followup"] is True


def test_followups_never_widen_the_selected_scope(tmp_path):
    prov = ScriptedProvider(cite_first)
    e = make_env(tmp_path, prov, approve=("mill", "workshop", "harbour"))
    scope = {"doc_ids": [e.ids["workshop"]]}                                    # 'principal' exists only in the mill notes
    cid = e.chat(scope=scope)
    e.say(cid, "What does the handbook say about delegation and fair assessment of apprentices?")
    for follow in ("Why is that the principal one?", "Give another example", "How does that change?"):
        e.say(cid, follow)
    for req in prov.requests:
        assert {p["doc_id"] for p in req.passages} <= {e.ids["workshop"]}
        assert "synthetic_b_workshop_handbook" in req.system and "synthetic_a_mill" not in req.system


def test_another_example_excludes_passages_already_used_and_says_so_when_exhausted(tmp_path):
    prov = ScriptedProvider(cite_first)
    e = make_env(tmp_path, prov, approve=("workshop",))
    cid = e.chat()
    e.say(cid, "What does the handbook say about apprentices, delegation and the main constraint?")
    used = {p["id"] for p in prov.requests[0].passages}
    r = e.say(cid, "Give another example").json()
    if r["model_called"]:
        assert not used & {p["id"] for p in prov.requests[-1].passages}         # genuinely new material
    # keep asking until the small scope is exhausted: the app must say so, not repeat or go outside
    for _ in range(4):
        r = e.say(cid, "Give another example").json()
        if not r["model_called"]:
            break
    assert r["model_called"] is False
    text = r["assistant_message"]["blocks"][0]["text"]
    assert "no further relevant passages" in text and "won't reach outside your selected scope" in text
    assert all(p["doc_id"] == e.ids["workshop"] for req in prov.requests for p in req.passages)


def test_carried_evidence_is_dropped_if_its_document_is_unapproved_between_turns(tmp_path):
    prov = ScriptedProvider(cite_first)
    e = make_env(tmp_path, prov, approve=("mill", "workshop"))
    cid = e.chat(scope={"doc_ids": [e.ids["mill"]]})
    e.say(cid, Q1)
    e.client.post(f"/api/documents/{e.ids['mill']}/approval", json={"approved": False})
    n = len(prov.requests)
    r = e.say(cid, "How does that change?").json()
    assert r["model_called"] is False and len(prov.requests) == n               # nothing stale or widened
    assert "No approved documents" in r["assistant_message"]["blocks"][0]["text"]


def test_followup_context_is_stated_to_the_model_without_giving_it_extra_sources(tmp_path):
    prov = ScriptedProvider(cite_first)
    e = make_env(tmp_path, prov)
    cid = e.chat()
    e.say(cid, Q1)
    e.say(cid, "Why is that the principal one?")
    user_turn = prov.requests[-1].messages[-1]["content"]
    assert "short follow-up" in user_turn and Q1[:40] in user_turn and "ONLY the supplied passages" in user_turn
