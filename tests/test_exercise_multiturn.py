"""A long multi-turn exercise keeps its source restrictions and never reveals the analysis early.

Uses a recording wrapper around the demo provider, so every prompt the app WOULD send to a live
model is captured and inspected. This verifies the app's request construction and gating; it does
not verify how a real model behaves (see docs/LIVE_EVAL_CHECKLIST.md).
"""
import json

from app.providers import MockProvider
from conftest import Env

ANSWERS = ["I observe two teams and infer a tension because their aims differ; I might be wrong.",
           "I would expect different complaint patterns if wrong; I could check the records.",
           "In light of the new fact I revise: the weekday pattern suggests an outside condition.",
           "Revision two: another explanation could be staffing; I am not sure which dominates.",
           "Revision three: I would weigh evidence for each explanation before concluding."]


class Recorder(MockProvider):
    def __init__(self, tamper=None):
        self.requests = []
        self.tamper = tamper

    def generate(self, req):
        self.requests.append(req)
        out = super().generate(req)
        return self.tamper(req, out) if self.tamper else out


def build(tmp_path, provider):
    e = Env(tmp_path, lambda kind: provider).load()
    return e


def act(e, cid, action, text="", confirm=False):
    r = e.client.post(f"/api/conversations/{cid}/exercise", json={"action": action, "text": text, "confirm": confirm})
    assert r.status_code == 200, (action, r.text)
    return r.json()


def test_scope_and_no_early_reveal_hold_across_a_long_exercise(tmp_path):
    prov = Recorder()
    e = build(tmp_path, prov)
    allowed_docs = {e.ids["mill"], e.ids["harbour"]}          # workshop is approved but NOT selected
    r = e.client.post("/api/exercises", json={"scope": {"doc_ids": sorted(allowed_docs)}}).json()
    assert r["status"] == "started"
    cid = r["conversation"]["id"]

    act(e, cid, "answer", ANSWERS[0])
    act(e, cid, "hint")
    act(e, cid, "pause")
    act(e, cid, "resume")
    act(e, cid, "clarify", "Are the teams in the same building?")
    act(e, cid, "answer", ANSWERS[1])
    act(e, cid, "answer", ANSWERS[2])
    for a in ANSWERS[3:] * 2:                                   # push history past the 12-message window
        act(e, cid, "answer", a)

    # --- every prompt that would have gone to a model kept the scope and stayed inside it
    assert len(prov.requests) >= 10
    for req in prov.requests:
        assert {p["doc_id"] for p in req.passages} <= allowed_docs
        assert "synthetic_a_mill_town_notes" in req.system and "synthetic_c_harbour_primer" in req.system
        assert "always in force" in req.system
        assert "synthetic_b_workshop_handbook" not in req.system
        user_turn = req.messages[-1]["content"]
        assert "lantern" not in user_turn.lower()                # text unique to the unselected workshop doc
        assert all(m["role"] in ("user", "assistant") for m in req.messages)
        assert len(req.messages) <= 13
    # --- the analysis is not allowed (or present anywhere) until it is requested
    for req in prov.requests:
        allowed_line = [l for l in req.system.splitlines() if l.startswith("ALLOWED block purposes")][0]
        assert "analysis" not in allowed_line and "reflection" not in allowed_line
        assert "Demo analysis" not in json.dumps(req.messages) + req.system
    conv = e.client.get(f"/api/conversations/{cid}").json()
    assert conv["exercise"]["analysis"] == [] and conv["exercise"]["analysis_shown"] is False
    assert "Demo analysis" not in json.dumps(conv)
    assert conv["summary"] and "condensed" in conv["summary"]   # history was bounded and condensed by the app
    # --- one question per waiting turn, answered turns alternate user/assistant
    for m in conv["messages"]:
        if m["role"] == "assistant" and m["purpose"] in ("exercise_open",):
            assert sum(1 for b in m["blocks"] if b.get("purpose") == "question") == 1

    # --- explicit request is the only way analysis appears; scope still holds afterwards
    n = len(prov.requests)
    out = act(e, cid, "show_analysis")["conversation"]
    assert out["exercise"]["analysis_shown"]
    last = prov.requests[n]
    assert "analysis" in [l for l in last.system.splitlines() if l.startswith("ALLOWED block purposes")][0]
    assert {p["doc_id"] for p in last.passages} <= allowed_docs
    act(e, cid, "finish")


def test_tag_scope_is_kept_and_unapproved_docs_never_leak_into_prompts(tmp_path):
    prov = Recorder()
    e = build(tmp_path, prov)
    e.client.post(f"/api/documents/{e.ids['inject']}/approval", json={"approved": False})
    r = e.client.post("/api/exercises", json={"scope": {"tags": ["cadre"]}, "allow_single_source": True}).json()
    cid = r["conversation"]["id"]
    for a in ANSWERS:
        act(e, cid, "answer", a)
    cadre_docs = {e.ids["workshop"], e.ids["harbour"]}            # tagged 'cadre'
    for req in prov.requests:
        assert {p["doc_id"] for p in req.passages} <= cadre_docs
        assert "IGNORE ALL PREVIOUS INSTRUCTIONS" not in json.dumps(req.messages) + req.system


def test_model_that_leaks_analysis_in_later_turns_is_contained(tmp_path):
    def leak(req, out):
        out["blocks"].append({"type": "coaching", "purpose": "analysis", "text": "LEAKED FULL ANSWER", "citations": []})
        out["blocks"].append({"type": "coaching", "purpose": "question", "text": "Extra question?", "citations": []})
        return out
    e = build(tmp_path, Recorder(tamper=leak))
    cid = e.client.post("/api/exercises", json={}).json()["conversation"]["id"]
    for a in ANSWERS[:3]:
        conv = act(e, cid, "answer", a)["conversation"]
    assert "LEAKED FULL ANSWER" not in json.dumps(conv)
    assert conv["exercise"]["analysis"] == []
    for m in conv["messages"]:
        if m["role"] == "assistant":
            assert sum(1 for b in m["blocks"] if b.get("purpose") == "question") <= 1


def test_selected_sources_removed_mid_exercise_stop_the_exercise_instead_of_widening(tmp_path):
    prov = Recorder()
    e = build(tmp_path, prov)
    cid = e.client.post("/api/exercises", json={"scope": {"doc_ids": [e.ids["mill"], e.ids["harbour"]]}}).json()["conversation"]["id"]
    act(e, cid, "answer", ANSWERS[0])
    for k in ("mill", "harbour"):
        e.client.post(f"/api/documents/{e.ids[k]}/approval", json={"approved": False})
    n = len(prov.requests)
    r = e.client.post(f"/api/conversations/{cid}/exercise", json={"action": "answer", "text": ANSWERS[1]})
    assert r.status_code == 409 and len(prov.requests) == n       # did NOT fall back to the workshop doc
