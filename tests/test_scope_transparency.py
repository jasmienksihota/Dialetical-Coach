"""Finding 1: scope semantics are explicit, resolved document lists are visible, behaviour unchanged."""
from app.retrieval import Scope, explain_scope, resolve_scope
from conftest import Env, approve


def explain(db, **kw):
    with db.tx() as c:
        return explain_scope(c, Scope(**kw)), set(resolve_scope(c, Scope(**kw)))


def test_union_semantics_documented_and_explanation_matches_the_real_resolver(db, loaded):
    approve(db, loaded["mill"], loaded["workshop"], loaded["harbour"])
    ex, resolved = explain(db, doc_ids=[loaded["mill"]], tags=["investigation"])
    assert "UNION" in ex["semantics"] and "ANY checked tag" in ex["semantics"]
    ids = {d["id"] for d in ex["included"]}
    assert ids == resolved == {loaded["mill"], loaded["workshop"]}          # unchanged: doc ∪ tag
    reasons = {d["id"]: d["reasons"] for d in ex["included"]}
    assert reasons[loaded["mill"]] == ["selected directly"]
    assert reasons[loaded["workshop"]] == ["tag: Investigation, learning and correcting mistakes"]
    assert ex["mode"] == "selection"


def test_doc_selected_and_tagged_lists_both_reasons(db, loaded):
    approve(db, loaded["workshop"])
    ex, _ = explain(db, doc_ids=[loaded["workshop"]], tags=["cadre"])
    assert ex["included"][0]["reasons"] == ["selected directly", "tag: Cadre development"]


def test_no_selection_means_all_approved_primary_documents_only(db, loaded):
    approve(db, loaded["mill"], loaded["harbour"], loaded["notes"])
    ex, resolved = explain(db)
    assert ex["mode"] == "all" and {d["id"] for d in ex["included"]} == resolved == {loaded["mill"], loaded["harbour"]}
    assert all(d["reasons"] == ["no filter: all approved primary documents"] for d in ex["included"])
    assert loaded["inject"] not in resolved and loaded["notes"] not in resolved     # unapproved / secondary


def test_ineligible_selections_are_listed_as_excluded_and_never_widen_scope(db, loaded):
    approve(db, loaded["mill"], loaded["workshop"], loaded["notes"])
    ex, resolved = explain(db, doc_ids=[loaded["inject"], loaded["notes"], loaded["scanned"]], tags=["foundations"])
    why = {d["id"]: d["why_excluded"] for d in ex["excluded"]}
    assert why[loaded["inject"]] == "not approved"
    assert why[loaded["notes"]].startswith("secondary study notes")
    assert why[loaded["scanned"]] == "not approved"
    assert resolved == {loaded["mill"]}                       # only the approved doc carrying the tag
    ex2, resolved2 = explain(db, doc_ids=[loaded["inject"]])
    assert ex2["included"] == [] and resolved2 == set()       # NOT "everything approved"
    ex3, resolved3 = explain(db, doc_ids=[loaded["notes"]], include_secondary=True)
    assert resolved3 == {loaded["notes"]} and ex3["included"][0]["kind"] == "secondary_notes"


def test_resolve_endpoint_and_per_turn_scope_audit(tmp_path):
    e = Env(tmp_path).load()
    body = {"doc_ids": [e.ids["mill"]], "tags": ["cadre"], "include_secondary": False}
    r = e.client.post("/api/scope/resolve", json=body).json()
    assert {d["id"] for d in r["included"]} == {e.ids["mill"], e.ids["workshop"], e.ids["harbour"]}
    cid = e.chat(scope=body)
    a = e.say(cid, "What causes change, internal contradiction or external conditions?").json()["assistant_message"]
    assert set(a["report"]["scope"]["doc_ids"]) == {d["id"] for d in r["included"]}     # recorded per turn
    assert "documents:" in a["report"]["scope"]["description"] and "tags:" in a["report"]["scope"]["description"]
    ex = e.client.post("/api/exercises", json={"scope": body}).json()["conversation"]
    assert set(ex["messages"][0]["report"]["scope"]["doc_ids"]) == set(a["report"]["scope"]["doc_ids"])
