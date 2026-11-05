"""Finding 2: substantive source claims smuggled into uncited block types.

Mechanical validation cannot prove semantic support. These tests cover the OBVIOUS bypasses
(pattern-based) and document one known limitation honestly.
"""
import json

import pytest

from app.citations import detect_uncited_source_claim, normalize_blocks, validate_blocks
from conftest import ScriptedProvider, make_env

Q = "What causes change: internal contradiction or external conditions?"
NAMES = ["synthetic_a_mill_town_notes", "Harbour Primer", "Jane Example"]

SMUGGLED = [
    ("coaching", "The author argues that the rail line was only a condition of the change."),
    ("coaching", "Remember, the text states that weavers caused the change."),
    ("coaching", "According to the Harrowmere notes, owners always win."),
    ("coaching", "As the handbook puts it, mistakes are useful."),
    ("coaching", "These passages claim that delegation is the cheapest way to grow makers."),
    ("coaching", "The authors argue for fixed standards."),
    ("limits", "The primer teaches that every newcomer must be assessed identically."),
    ("limits", "The library shows that principal tensions never change."),
    ("fiction", "FICTIONAL: In this pond co-op, the handbook insists apprentices are paid last."),
    ("coaching", "Jane Example explains that apprentices should lead from day one."),
    ("coaching", "Harbour Primer recommends delegating all tasks."),
    ("coaching", "synthetic_a_mill_town_notes describes the quarrel over pay as principal."),
]
BENIGN = [
    ("coaching", "Try restating the quoted passage in your own words, then ask a follow-up."),
    ("coaching", "Compare the two texts and explain the differences you see."),
    ("coaching", "Reread the passage and explain why it matters to you."),
    ("coaching", "What would you expect to find if your explanation were wrong?"),
    ("coaching", "You wrote: “I think the bakers are in tension with counter staff”. What would count against that?"),
    ("limits", "The selected library does not, from these passages alone, establish whether the two texts would agree."),
    ("limits", "The retrieved passages only weakly match your question, so the library may not address it."),
    ("fiction", "FICTIONAL SCENARIO (invented for this exercise): a small bakery has two teams who disagree about timing."),
]


@pytest.mark.parametrize("btype,text", SMUGGLED)
def test_obvious_uncited_source_claims_are_flagged(btype, text):
    assert detect_uncited_source_claim(text, NAMES, []) == "uncited_source_claim", text


@pytest.mark.parametrize("btype,text", BENIGN)
def test_ordinary_coaching_fiction_limits_are_not_flagged(btype, text):
    assert detect_uncited_source_claim(text, NAMES, []) is None, text


def test_verbatim_passage_text_without_citation_is_flagged():
    passage = "A member of the lantern workshop who has not investigated has no right to speak about what the workshop should do."
    text = "Here is a thought: a member of the lantern workshop who has not investigated has no right to speak, so be careful."
    assert detect_uncited_source_claim(text, [], [passage]) == "uncited_quotation"
    assert detect_uncited_source_claim("Think about whether you have investigated enough before speaking.", [], [passage]) is None


def test_validator_marks_each_smuggling_block_invalid_but_cited_versions_pass(env):
    with env.svc.db.tx() as c:
        pid = c.execute("SELECT id FROM chunks WHERE doc_id=? LIMIT 1", (env.ids["workshop"],)).fetchone()["id"]
        blocks = normalize_blocks({"blocks": [{"type": t, "text": x} for t, x in SMUGGLED[:3] + SMUGGLED[6:9]]})
        rep = validate_blocks(c, blocks, {pid}, set(env.ids.values()))
        assert [b["status"] for b in rep["blocks"]] == ["invalid"] * 6
        assert {e["code"] for b in rep["blocks"] for e in b["errors"]} == {"uncited_source_claim"}
        # the SAME words are acceptable where the contract says they belong: a cited interpretation
        ok = normalize_blocks({"blocks": [{"type": "interpretation", "text": SMUGGLED[0][1], "citations": [{"passage_id": pid}]}]})
        assert validate_blocks(c, ok, {pid}, {env.ids["workshop"]})["blocks"][0]["status"] == "verified"
        # ...but a coaching block that DOES cite is validated as a cited block (and checked for ID validity)
        bad = normalize_blocks({"blocks": [{"type": "coaching", "text": SMUGGLED[0][1], "citations": [{"passage_id": "ZZZZ-1"}]}]})
        assert validate_blocks(c, bad, {pid}, {env.ids["workshop"]})["blocks"][0]["status"] == "invalid"


def test_fiction_may_never_cite(env):
    with env.svc.db.tx() as c:
        pid = c.execute("SELECT id FROM chunks WHERE doc_id=? LIMIT 1", (env.ids["workshop"],)).fetchone()["id"]
        b = normalize_blocks({"blocks": [{"type": "fiction", "text": "FICTIONAL: a pond co-op.", "citations": [{"passage_id": pid}]}]})
        rep = validate_blocks(c, b, {pid}, {env.ids["workshop"]})
        assert rep["blocks"][0]["errors"][0]["code"] == "fiction_cannot_cite"


def _grounded(req):
    p = req.passages[0]
    q = " ".join(p["text"].split()[:10])
    return {"type": "quote", "text": q, "citations": [{"passage_id": p["id"], "quote": q}]}


@pytest.mark.parametrize("btype,text", [SMUGGLED[0], SMUGGLED[6], SMUGGLED[8]])
def test_end_to_end_smuggled_claim_is_repaired_once_then_withheld_and_never_displayed(tmp_path, btype, text):
    prov = ScriptedProvider(lambda r: {"blocks": [_grounded(r), {"type": btype, "text": text}]})
    e = make_env(tmp_path, prov)
    a = e.say(e.chat(), Q).json()["assistant_message"]
    assert len(prov.requests) == 2 and "uncited_source_claim" in " ".join(prov.requests[1].context["repair_errors"])
    assert [b["type"] for b in a["blocks"]] == ["quote", "withheld"]
    assert text not in json.dumps(a["blocks"]) and a["report"]["invalid_count"] == 1
    assert "without a citation" in a["blocks"][1]["reason"]


def test_end_to_end_repair_moves_the_claim_into_a_cited_block(tmp_path):
    def fixed(req):
        p = req.passages[0]
        return {"blocks": [{"type": "interpretation", "text": SMUGGLED[0][1], "citations": [{"passage_id": p["id"]}]}]}
    prov = ScriptedProvider(lambda r: {"blocks": [_grounded(r), {"type": "coaching", "text": SMUGGLED[0][1]}]}, fixed)
    e = make_env(tmp_path, prov)
    a = e.say(e.chat(), Q).json()["assistant_message"]
    assert [b["status"] for b in a["blocks"]] == ["verified"] and a["blocks"][0]["citations"][0]["ok"]


def test_exercise_question_containing_a_source_claim_is_withheld_and_replaced(tmp_path):
    def opening(req):
        p = req.passages[0]
        q = " ".join(p["text"].split()[:10])
        return {"blocks": [
            {"type": "quote", "purpose": "source_basis", "text": q, "citations": [{"passage_id": p["id"], "quote": q}]},
            {"type": "fiction", "purpose": "scenario", "text": "FICTIONAL: a pond co-op.", "citations": []},
            {"type": "coaching", "purpose": "question", "text": "The handbook insists the answer is X; do you agree?", "citations": []}]}
    e = make_env(tmp_path, ScriptedProvider(opening))
    msg = e.client.post("/api/exercises", json={"allow_single_source": True}).json()["conversation"]["messages"][0]
    qs = [b for b in msg["blocks"] if b.get("purpose") == "question" and b["type"] != "withheld"]
    assert len(qs) == 1 and qs[0].get("app") is True and "The handbook insists" not in json.dumps(msg["blocks"])
    assert any(b["type"] == "withheld" for b in msg["blocks"])


def test_known_limitation_paraphrased_attribution_is_not_detected():
    """Honest limit: pattern checks miss paraphrase that avoids assertion verbs. Documented, not hidden."""
    sneaky = "In the notes, the pay-period quarrel gets priority over lighting and apprentices."
    assert detect_uncited_source_claim(sneaky, NAMES, []) is None


def test_report_never_claims_semantic_support(env):
    cid = env.chat()
    a = env.say(cid, Q, "explain").json()["assistant_message"]
    assert "NOT verified" in a["report"]["note"] and "support" in a["report"]["note"]
