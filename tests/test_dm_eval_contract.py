"""CONTRACT tests for the dialectical-materialism concept map and evaluation set.

These verify the STRUCTURE and HONESTY of the materials and the behaviour of the offline tooling, using only the
SYNTHETIC fixtures. They do NOT test whether any model reasons dialectically: that is untested (see
docs/dialectical/EVALUATION.md). Passing here must never be described as achieving the learning goal.
"""
import hashlib
import importlib.util
import json
import re
import sqlite3

import pytest

from conftest import ROOT

spec = importlib.util.spec_from_file_location("dm_eval", ROOT / "tools" / "dm_eval.py")
dm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dm)

CMAP = dm.load_map()
CASES = dm.load_cases()
CONCEPT_IDS = {c["id"] for c in CMAP["concepts"]}
REAL_NAMES = re.compile(r"\b(Marx|Engels|Lenin|Mao|Stalin|Hegel|Plekhanov|Gramsci|Trotsky)\b", re.I)


# ------------------------------------------------------------------ concept map
def test_concept_map_is_a_labelled_skeleton_with_no_source_text():
    assert "NO source passages" in CMAP["_label"] and "NO claim" in CMAP["_label"]
    for c in CMAP["concepts"]:
        assert c["support"] == {"status": "unsupported", "passages": []}, c["id"]
        assert c["question_for_the_library"].endswith("?") and c["search_term_groups"] and c["app_framing_question"]
        assert not ({"quote", "text", "excerpt"} & set(c["support"]))
    assert "opposed aspects of one process" not in json.dumps(CMAP)           # no embedded definition of contradiction


def test_concept_map_covers_the_required_distinctions():
    assert {"materialism_idealism", "dialectical_vs_metaphysical_method", "cartesian_mind_body_dualism",
            "contradiction_and_lookalikes", "concrete_conditions", "relations_interdependence",
            "change_development_history", "evidence_for_opposed_aspects", "author_differences"} <= CONCEPT_IDS
    node = next(c for c in CMAP["concepts"] if c["id"] == "contradiction_and_lookalikes")
    assert set(node["teaching_comparators"]) == {"disagreement", "practical_tradeoff", "logical_inconsistency"}
    for c in CMAP["concepts"]:
        assert set(c["must_not_be_conflated_with"]) <= CONCEPT_IDS
    dual = next(c for c in CMAP["concepts"] if c["id"] == "cartesian_mind_body_dualism")
    assert {"materialism_idealism", "dialectical_vs_metaphysical_method"} <= set(dual["must_not_be_conflated_with"])
    assert "do not fill the gap from outside" in dual["app_framing_question"].lower()


# ------------------------------------------------------------------ cases
def test_every_case_is_labelled_invented_and_owner_review_is_pending():
    assert "INVENTED" in CASES["_label"] and "owner" in CASES["_review_note"].lower()
    assert "app-created" in CASES["rubric"]["_label"].lower() and "no scores" in CASES["rubric"]["_label"].lower()
    for s in CASES["scenarios"].values():
        assert "INVENTED" in s["label"]
    for c in CASES["cases"]:
        assert "INVENTED" in c["label"] and c["owner_review"] == "pending"
        assert c["source_traceability"]["status"] == "pending"
        assert set(c["source_traceability"]["depends_on_concepts"]) == set(c["anchors"]) <= CONCEPT_IDS


def test_the_five_requested_example_types_exist_in_pairs():
    kinds = {c["kind"] for c in CASES["cases"]}
    assert {"static_isolated_analysis", "relational_developmental_analysis", "empty_dialectical_vocabulary",
            "contradiction_claimed_not_yet_justified", "new_evidence_revision"} <= kinds
    by_pair = {}
    for c in CASES["cases"]:
        by_pair.setdefault(c["pair"], []).append(c["id"])
    for pair in ("P1", "P2", "P3", "P4"):
        assert len(by_pair[pair]) >= 2, pair
    assert {c["kind"] for c in CASES["cases"] if c["pair"] == "P3"} >= {
        "practical_tradeoff_mislabelled", "logical_inconsistency_mislabelled", "restrained_appropriately"}
    revising = [c for c in CASES["cases"] if c["pair"] == "P4"]
    assert all(c.get("new_fact") and "INVENTED" in c["new_fact"] for c in revising)


def test_every_case_has_observable_criteria_with_valid_check_types():
    registry = set(CASES["checks"]) - {"_label"}
    for c in CASES["cases"]:
        assert c["tutor_should"] and c["tutor_should_not"], c["id"]
        for crit in c["tutor_should"] + c["tutor_should_not"]:
            kind, _, name = crit["check"].partition(":")
            assert kind in ("human", "mechanical") and (kind == "human" or name in registry), crit
            assert crit["text"].strip() and crit["id"].startswith(c["id"])
        assert any(x["check"] == "human" for x in c["tutor_should"] + c["tutor_should_not"]), c["id"]
    dims = {d["id"] for d in CASES["rubric"]["dimensions"]}
    assert all(set(c["rubric_focus"]) <= dims for c in CASES["cases"])


def test_no_case_mandates_a_template_or_rewards_vocabulary_or_agreement():
    for c in CASES["cases"]:
        for crit in c["tutor_should"]:
            assert not re.search(r"\b(thesis|antithesis)\b|use (the|any) (technical )?term", crit["text"], re.I), crit
    for cid in ("C2a", "C2b", "C3b", "C4b"):
        case = next(c for c in CASES["cases"] if c["id"] == cid)
        assert any(x["check"] == "mechanical:M_PRAISE" for x in case["tutor_should_not"]), cid
    c2a = next(c for c in CASES["cases"] if c["id"] == "C2a")
    assert any("M_TAS" in x["check"] for x in c2a["tutor_should_not"]) and any("M_INEV" in x["check"] for x in c2a["tutor_should_not"])


def test_real_thinkers_are_not_attributed_anything_in_invented_material():
    for c in CASES["cases"]:
        blob = json.dumps([c["learner_input"], c.get("new_fact", ""), c.get("prior_interpretation", "")])
        assert not REAL_NAMES.search(blob), c["id"]
        if "Descartes" in blob:
            assert c["kind"] == "concept_probe_cartesian_dualism"           # a topic to test, with no claims attached
    for s in CASES["scenarios"].values():
        assert not REAL_NAMES.search(s["text"]) and "Descartes" not in s["text"]


def test_probe_cases_require_a_limits_statement_when_library_is_silent():
    for cid in ("K1", "K2", "K3"):
        case = next(c for c in CASES["cases"] if c["id"] == cid)
        assert any(x["check"] == "mechanical:M_LIMITS" for x in case["tutor_should"]), cid
        assert any("outside" in x["text"].lower() or "without a cited passage" in x["text"].lower()
                   for x in case["tutor_should"] + case["tutor_should_not"]), cid


# ------------------------------------------------------------------ docs stay honest
def test_documents_state_status_and_limits_plainly():
    d = ROOT / "docs" / "dialectical"
    audit, prompts_doc, ev = (" ".join((d / n).read_text().split()) for n in ("AUDIT.md", "PROMPT_CHANGES.md", "EVALUATION.md"))
    assert "No real approved library exists in this workspace" in audit
    assert "PROPOSED, not applied" in prompts_doc
    assert "Philosophical performance is untested" in ev and "No model was retrained" in ev
    assert "never** sufficient" in ev and "0/13" in ev


def test_proposals_are_not_silently_applied():
    """If P2 is adopted, update PROMPT_CHANGES.md and this test together."""
    from app import modes, prompts
    assert "DIALECTICAL-MATERIALISM PRACTICE" not in prompts.EXERCISE_RULES                      # the contract is not wired in
    assert "DIALECTICAL-MATERIALISM PRACTICE" in (ROOT / "docs" / "dialectical" / "PROMPT_CHANGES.md").read_text()
    tc = (ROOT / "docs" / "dialectical" / "TEACHING_CONTRACT.md").read_text()
    assert "PROVISIONAL and not yet wired" in tc and "Application rules" in tc and "Requires passage-level support" in tc
    d = modes.MODES["dialectical"]                                                                  # P1 applied: no developer theory
    for text in (d["guidance"], d["objective"]):
        assert not re.search(r"internal|outside conditions|main issue|tensions", text, re.I)
    assert "concepts the selected" in d["objective"] and "attributed to" in d["guidance"]


# ------------------------------------------------------------------ probe: read-only, approved primary only
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_probe_is_read_only_and_uses_only_approved_primary_documents(env):
    env.client.post(f"/api/documents/{env.ids['notes']}/approval", json={"approved": True})   # approved but SECONDARY
    db = env.settings.db_path
    before = sha(db)
    conn = dm.open_readonly(env.settings.data_dir)
    found = dm.probe(conn, CMAP, per_group=4)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("UPDATE documents SET approved=0")                       # truly read-only
    conn.close()
    assert sha(db) == before                                                  # nothing written
    cands = [x for v in found.values() for x in v]
    assert cands
    titles = {x["doc_title"] for x in cands}
    assert titles <= {"synthetic_a_mill_town_notes", "synthetic_b_workshop_handbook", "synthetic_c_harbour_primer"}
    assert "synthetic_injection_notes" not in titles and "synthetic_secondary_notes" not in titles
    assert all("approved" not in x for x in cands)                            # carries no verdict
    sheet = dm.render_review(CMAP, found)
    assert "app has not judged" in sheet and "candidates only" in sheet.lower()


def test_probe_reports_concepts_the_library_may_not_address(env):
    conn = dm.open_readonly(env.settings.data_dir)
    found = dm.probe(conn, CMAP)
    assert found["cartesian_mind_body_dualism"] == []                         # synthetic library never mentions it
    assert "No candidate passages found" in dm.render_review(CMAP, found)


# ------------------------------------------------------------------ readiness / traceability
def chunk_ids(env, key, n=1):
    with env.svc.db.tx() as c:
        return [r["id"] for r in c.execute("SELECT id FROM chunks WHERE doc_id=? ORDER BY ordinal LIMIT ?", (env.ids[key], n))]


def test_nothing_is_ready_without_owner_confirmations(env):
    conn = dm.open_readonly(env.settings.data_dir)
    rep = dm.readiness(conn, CMAP, CASES, {"concepts": {}})
    assert rep["ready_count"] == 0 and rep["total"] == 13
    assert dm.main(["readiness", "--data-dir", str(env.settings.data_dir)]) == 1


def test_readiness_accepts_only_valid_confirmations(env):
    """Uses SYNTHETIC passages purely to exercise the machinery; this says nothing about any real text."""
    ok = chunk_ids(env, "mill")[0]
    inject = chunk_ids(env, "inject")[0]                                       # unapproved document
    conn = dm.open_readonly(env.settings.data_dir)
    conf = {"concepts": {
        "concrete_conditions": {"reviewer": "ai_assisted_unvalidated", "status": "supported", "passages": [{"chunk_id": ok, "author": "synthetic", "note": "reviewer words"}]},
        "relations_interdependence": {"reviewer": "ai_assisted_unvalidated", "status": "supported", "passages": [{"chunk_id": ok, "note": "reviewer words"}]},
        "change_development_history": {"reviewer": "ai_assisted_unvalidated", "status": "not_found_in_reviewed", "reviewed_scope": "synthetic mill notes only"},
        "evidence_for_opposed_aspects": {"reviewer": "ai_assisted_unvalidated", "status": "supported", "passages": [{"chunk_id": inject, "note": "x"}]},
        "materialism_idealism": {"reviewer": "ai_assisted_unvalidated", "status": "supported", "passages": []},
        "dialectical_vs_metaphysical_method": {"reviewer": "ai_assisted_unvalidated", "status": "supported", "passages": [{"chunk_id": "nope-0001", "note": "x"}]},
        "author_differences": {"reviewer": "ai_assisted_unvalidated", "status": "supported", "passages": [{"chunk_id": ok}]},
        "contradiction_and_lookalikes": {"reviewer": "owner_reviewed", "status": "not_found_in_reviewed"},                  # no reviewed_scope
        "concrete_analysis_x": {"status": "supported"},
        "cartesian_mind_body_dualism": {"status": "needs_investigation"},
    }}
    rep = dm.readiness(conn, CMAP, CASES, conf)
    st = rep["concept_status"]
    assert st["concrete_conditions"] == "supported"
    assert st["change_development_history"] == "not_found_in_reviewed"
    assert st["cartesian_mind_body_dualism"] == "needs_investigation"            # recorded, but not "resolved"
    for bad in ("evidence_for_opposed_aspects", "materialism_idealism", "dialectical_vs_metaphysical_method",
                "author_differences", "contradiction_and_lookalikes"):
        assert st[bad] == "unresolved", bad
    problems = " | ".join(rep["problems"])
    for needle in ("UNAPPROVED", "lists no passages", "does not exist", "no note in the reviewer's own words",
                   "not a concept", "needs 'reviewed_scope'"):
        assert needle in problems, needle
    rows = {r["case"]: r for r in rep["cases"]}
    assert rows["C1a"]["ready"] and rows["C1a"]["limits_only"] == ["change_development_history"]   # limits-only, flagged
    assert not rows["C1b"]["ready"]                                                # still needs the invalid evidence concept
    assert not rows["K3"]["ready"]


def test_every_resolved_status_must_record_who_reviewed_it(env):
    ok = chunk_ids(env, "mill")[0]
    conn = dm.open_readonly(env.settings.data_dir)
    base = {"status": "supported", "passages": [{"chunk_id": ok, "note": "n"}]}
    for entry in (base, {**base, "reviewer": "claude"}, {**base, "reviewer": "ai_assisted"}):
        st, problems = dm.validate_confirmations(conn, CMAP, {"concepts": {"concrete_conditions": entry}})
        assert st["concrete_conditions"] == "unresolved" and "who reviewed it" in problems[0]
    for who in dm.REVIEWERS:
        st, _ = dm.validate_confirmations(conn, CMAP, {"concepts": {"concrete_conditions": {**base, "reviewer": who}}})
        assert st["concrete_conditions"] == "supported"
    assert set(dm.REVIEWERS) == {"ai_assisted_unvalidated", "owner_reviewed", "ai_assisted_then_owner_reviewed"}
    assert "Verify authorization" in " ".join((ROOT / "docs" / "dialectical" / "LOCAL_PROBE_INSTRUCTIONS.md").read_text().split())


def test_a_failed_search_alone_never_becomes_a_strong_claim(env):
    conn = dm.open_readonly(env.settings.data_dir)
    st, problems = dm.validate_confirmations(conn, CMAP, {"concepts": {"cartesian_mind_body_dualism": {"status": "not_addressed"}}})
    assert st["cartesian_mind_body_dualism"] == "unresolved" and "status must be" in problems[0]   # old strong status is refused
    assert "not_addressed" not in json.dumps(CMAP) and "not_addressed" not in (ROOT / "docs" / "dialectical" / "CONCEPT_MAP.md").read_text()
    assert set(CMAP["support_policy"]["statuses"]) == {"unsupported", "supported", "not_found_in_reviewed", "needs_investigation"}
    assert "NOT the same as" in CMAP["support_policy"]["statuses"]["not_found_in_reviewed"]


def test_first_diagnostic_is_exactly_three_cases_and_needs_five_concepts(env):
    diag = [c for c in CASES["cases"] if c.get("first_diagnostic")]
    assert {c["id"] for c in diag} == {"C2a", "C1b", "C3a"} and len(diag) == 3
    assert {a for c in diag for a in c["anchors"]} == {"concrete_conditions", "relations_interdependence",
        "change_development_history", "evidence_for_opposed_aspects", "contradiction_and_lookalikes"}
    conn = dm.open_readonly(env.settings.data_dir)
    rep = dm.readiness(conn, CMAP, CASES, {"concepts": {}}, diagnostic_only=True)
    assert {r["case"] for r in rep["cases"]} == {"C2a", "C1b", "C3a"} and len(rep["cases"]) == 3 and rep["ready_count"] == 0
    packet = " ".join((ROOT / "docs" / "dialectical" / "DIAGNOSTIC_PACKET.md").read_text().split())
    assert packet.count("PENDING (local probe)") >= 6 and "NOTHING reviewed" in packet and "INVENTED" in packet
    assert "needs separate spending authorization" in " ".join((ROOT / "docs" / "dialectical" / "EVALUATION.md").read_text().split()) or \
           "separate spending authorization" in " ".join((ROOT / "docs" / "dialectical" / "EVALUATION.md").read_text().split())


def test_secondary_notes_cannot_confirm_a_concept(env):
    env.client.post(f"/api/documents/{env.ids['notes']}/approval", json={"approved": True})
    sec = chunk_ids(env, "notes")[0]
    conn = dm.open_readonly(env.settings.data_dir)
    rep = dm.readiness(conn, CMAP, CASES, {"concepts": {"concrete_conditions": {"status": "supported", "reviewer": "owner_reviewed",
                       "passages": [{"chunk_id": sec, "note": "x"}]}}})
    assert rep["concept_status"]["concrete_conditions"] == "unresolved" and "secondary notes" in " ".join(rep["problems"])


# ------------------------------------------------------------------ surface checks
P = ["The workshop handbook says investigate the facts first."]


def kinds(blocks, passages=P, **kw):
    return {f["check"] for f in dm.check_output(blocks, passages, **kw)}


def blk(text, **kw):
    return [{"type": kw.pop("type", "coaching"), "text": text, **kw}]


def test_surface_checks_flag_the_specified_patterns():
    assert "M_TAS" in kinds(blk("Think of it as thesis and antithesis resolving."))
    assert "M_TAS" in kinds(blk("The author's own thesis here is stated as such."), ["The thesis of the pamphlet is X."])   # a passage with the token does not excuse a use; a human judges
    assert "M_PRAISE" in kinds(blk("Excellent use of dialectical terminology!"))
    assert "M_PRAISE" in kinds(blk("You correctly identified the contradiction."))
    assert "M_PREMATURE" in kinds(blk("This is clearly a dialectical contradiction."))
    assert "M_PREMATURE" in kinds(blk("You have found the contradiction."))
    assert "M_INEV" in kinds(blk("So it will inevitably transcend itself."))
    assert "M_ONEQ" in kinds([{"type": "coaching", "text": "A?", "purpose": "question"}, {"type": "coaching", "text": "B?", "purpose": "question"}])
    assert "M_LIMITS" in kinds(blk("Here is an answer."), unresolved_anchor=True)
    assert "M_LIMITS" not in kinds(blk("Not established.", type="limits"), unresolved_anchor=True)


def test_surface_checks_do_not_flag_ordinary_investigative_replies():
    ok = blk("The records show a disagreement about hours. What would show that the two positions depend on each other?",
             purpose="question")
    assert kinds(ok) == set()
    assert kinds(blk("I can't say yet whether this is a contradiction; what would count against it?")) == set()
    assert kinds(blk("What would show that this is a contradiction rather than a scheduling dispute?")) == set()
    assert "M_PREMATURE" in kinds(blk("Whether or not you agree, this is a contradiction."))      # declaration after a hedge-free clause
    assert kinds([{"type": "withheld", "text": "thesis antithesis inevitably"}]) == set()       # withheld text is not shown


def test_check_cli_reports_failures(tmp_path, capsys):
    f = tmp_path / "reply.json"
    f.write_text(json.dumps({"blocks": blk("Great use of terminology; this is a contradiction.")}))
    assert dm.main(["check", str(f)]) == 1
    assert "M_PRAISE" in capsys.readouterr().out


# ------------------------------------------------------------------ the scripted demo's limits, documented not hidden
def test_scripted_demo_keyword_baseline_cannot_discriminate_the_cases():
    base = dm.baseline(CASES)
    assert base["C2a"]["keyword_features_matched"]                              # empty vocabulary matches keywords
    assert base["C4b"]["keyword_features_matched"] == []                        # best-supported revision matches none
    # so the demo must never present keyword matches as evidence of understanding:
    from app import demo_script
    assert "Visible in your answer" not in open(demo_script.__file__).read()


def test_demo_learner_facing_text_has_no_keyword_assessment_or_developer_theory(env):
    """Walk a whole demo exercise; scripted coaching/interpretation text must not assess or carry theory."""
    env.client.post("/api/exercises", json={})
    cid = env.client.get("/api/conversations").json()[0]["id"]
    case = next(c for c in CASES["cases"] if c["id"] == "C2a")
    seq = [("answer", case["learner_input"]), ("hint", ""), ("hint", ""), ("answer", "More detail about records."),
           ("answer", "A revision."), ("show_analysis", ""), ("finish", "")]
    conv = None
    for action, text in seq:
        r = env.client.post(f"/api/conversations/{cid}/exercise", json={"action": action, "text": text, "confirm": True})
        assert r.status_code == 200, (action, r.text)
        conv = r.json()["conversation"]
    texts = [b["text"] for m in conv["messages"] if m["role"] == "assistant" for b in m["blocks"]
             if b["type"] in ("coaching", "interpretation") and b.get("purpose") in ("feedback", "hint", "analysis", "reflection", "next_steps")]
    assert len(texts) >= 8
    for t in texts:
        assert not re.search(r"keyword|matched|visible in your answer|internal|external|principal|outside condition|thesis|dialectic|contradict|tension", t, re.I), t
    fb = next(t for t in texts if t.startswith("Demo feedback"))
    assert "cannot assess your reasoning" in fb and "nothing here evaluates it" in fb


def test_c3a_no_longer_teaches_a_categorical_disagreement_is_not_contradiction_premise():
    """Correction of a developer-authored teaching rule after reading the reference texts (provisional; not validation)."""
    c3a = next(c for c in CASES["cases"] if c["id"] == "C3a")
    blob = json.dumps(c3a["tutor_should"] + c3a["tutor_should_not"]).lower()
    assert "rather than two preferences" not in blob and "only a scheduling disagreement" not in blob
    assert any("what kind of contradiction" in x["text"].lower() for x in c3a["tutor_should"])
    assert any("a disagreement is not a contradiction" in x["text"].lower() for x in c3a["tutor_should_not"])      # may not assert it as a source claim
    assert any("adequate explanation" in x["text"].lower() for x in c3a["tutor_should_not"])                       # nor accept the label as the explanation
    assert "PROVISIONAL" in c3a["revision_note"]
    dim = next(d for d in CASES["rubric"]["dimensions"] if d["id"] == "alternatives_considered")
    assert "non-dialectical" not in dim["text"] and "without assuming in advance" in dim["text"]
    for cid in ("C3c", "C3d"):
        assert "needs_investigation" in next(c for c in CASES["cases"] if c["id"] == cid)["provisional_note"]
    tc = " ".join((ROOT / "docs" / "dialectical" / "TEACHING_CONTRACT.md").read_text().split())
    assert "live alternative readings" not in tc and "without assuming in advance" in tc


def test_c1b_and_c2a_no_longer_encode_unsupported_premises_and_checks_do_not_flag_the_intended_response():
    """Provisional corrections after reading the reference texts; not validation of anything."""
    by = {c["id"]: c for c in CASES["cases"]}
    for cid in ("C1b", "C2a"):
        assert "PROVISIONAL" in by[cid]["revision_note"]
    c1b = json.dumps(by["C1b"]["tutor_should"] + by["C1b"]["tutor_should_not"]).lower()
    assert "rather than just different" not in c1b and "support in the case record" in c1b
    assert any("shared by all the authors" in x["text"] for x in by["C1b"]["tutor_should_not"])
    c2a_should = " ".join(x["text"] for x in by["C2a"]["tutor_should"]).lower()
    assert "not the vocabulary" in c2a_should and "do not claim the authors reject it" in c2a_should
    assert any("illegitimate" in x["text"] for x in by["C2a"]["tutor_should_not"])
    assert "thesis-antithesis" in " ".join(x["text"] for x in by["C2a"]["tutor_should_not"]).lower()
    assert "not a failure" in CASES["checks"]["M_TAS"] and "quoted" in CASES["checks"]["M_INEV"]
    # the reply the packet calls successful must not trip the 'inevitably' check; thesis wording is flagged only for human review
    good = blk("I'd also hold off on “inevitably”: there, necessity is shown from history, not from the label. The passages I have do not present "
               "thesis–antithesis–synthesis as the method. Which fact in the minutes shows what is opposed to what?", purpose="question")
    flags = dm.check_output(good, [])
    assert {f["check"] for f in flags} == {"M_TAS"} and all(f["review"] for f in flags)
    assert "M_INEV" in kinds(blk("So it will inevitably transcend itself."))                       # an unquoted endorsement is still flagged


def test_bounded_corrections_scenario_hypothesis_and_scope():
    """Source-reading corrections; provisional, not validation."""
    s2 = CASES["scenarios"]["S2"]["text"].lower()
    assert "rulebook" not in s2 and "not supplied" in s2                                # no assumed inconsistency; records' contents not supplied
    s2b = CASES["scenarios"]["S2b"]["text"].lower()
    assert "conflict only under these added conditions" in s2b and "19 hours" in s2b
    by = {c["id"]: c for c in CASES["cases"]}
    assert by["C3d"]["scenario_ref"] == "S2b" and by["C3a"]["scenario_ref"] == "S2"
    assert "hypothesis" in " ".join(x["text"] for x in by["C1b"]["tutor_should"]).lower()
    assert "remains to be established" in by["C1b"]["defensible_assessment"]
    assert any("not necessarily in every turn" in x["text"] for x in by["C1b"]["tutor_should"])
    assert "exhaustive or authoritative definition" in CASES["_scope_note"]
    for doc in ("DIAGNOSTIC_PACKET.md", "EVALUATION.md"):
        assert "exhaustive or authoritative definition" in " ".join((ROOT / "docs" / "dialectical" / doc).read_text().split())
