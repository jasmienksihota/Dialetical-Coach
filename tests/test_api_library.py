"""Library endpoints through the HTTP API (uploads, validation, approval, viewer)."""
from conftest import Env, fixture_bytes


def up(e, name, data=None, **form):
    return e.client.post("/api/documents", files={"file": (name, data if data is not None else fixture_bytes(name))}, data=form)


def test_upload_dedupe_validation_and_approval_over_http(tmp_path):
    e = Env(tmp_path)
    r = up(e, "synthetic_a_mill_town_notes.md", tags="foundations,cadre", title="My title", author="", edition="2nd")
    assert r.status_code == 200
    d = r.json()["document"]
    assert d["approved"] is False and d["title"] == "My title" and d["author"] is None
    assert d["edition"] == "2nd" and d["tags"] == ["cadre", "foundations"]
    dup = up(e, "other-name.md", fixture_bytes("synthetic_a_mill_town_notes.md")).json()
    assert dup["duplicate"] is True and len(e.client.get("/api/documents").json()) == 1
    assert up(e, "x.exe", b"MZ").status_code == 415
    assert up(e, "x.pdf", b"nope").status_code == 400
    assert up(e, "x.txt", b"y" * 50, tags="bogus").status_code == 400
    big = Env(tmp_path / "b", max_upload_bytes=1000)
    assert up(big, "a.txt", b"z" * 2000).status_code == 413
    scanned = up(e, "synthetic_e_scanned_like.pdf").json()["document"]
    assert scanned["status"] == "empty" and scanned["warnings"]
    assert e.client.post(f"/api/documents/{scanned['id']}/approval", json={"approved": True}).status_code == 409
    ok = e.client.post(f"/api/documents/{d['id']}/approval", json={"approved": True}).json()
    assert ok["approved"] is True and ok["approved_at"]


def test_metadata_patch_passage_viewer_and_delete(tmp_path):
    e = Env(tmp_path)
    d = up(e, "synthetic_c_harbour_primer.pdf").json()["document"]
    p = e.client.patch(f"/api/documents/{d['id']}", json={"author": "Someone", "printed_page_offset": -1, "tags": ["strategy"]}).json()
    assert p["author"] == "Someone" and p["tags"] == ["strategy"] and p["printed_page_offset"] == -1
    assert e.client.patch(f"/api/documents/{d['id']}", json={"tags": ["nope"]}).status_code == 400
    chunks = e.client.get(f"/api/documents/{d['id']}/chunks").json()
    assert [c["page"] for c in chunks["chunks"]] == [1, 2, 3]
    psg = e.client.get(f"/api/passages/{chunks['chunks'][1]['id']}?context=1").json()
    assert psg["passage"]["location"] == "PDF p. 2 (printed p. 1)" and len(psg["neighbours"]) == 3
    assert e.client.get("/api/passages/nope").status_code == 404
    assert e.client.delete(f"/api/documents/{d['id']}").status_code == 200
    assert e.client.get("/api/documents").json() == [] and not list((e.settings.originals_dir).iterdir())


def test_demo_fixtures_import_unapproved_and_secondary_kind(tmp_path):
    e = Env(tmp_path)
    r = e.client.post("/api/demo/fixtures").json()
    assert "invented" in r["message"]
    docs = e.client.get("/api/documents").json()
    assert len(docs) == 6 and not any(d["approved"] for d in docs)
    assert [d["kind"] for d in docs].count("secondary_notes") == 1
    assert e.client.post("/api/demo/fixtures").json()["imported"][0]["duplicate"] is True


def test_all_seven_tags_are_exposed(tmp_path):
    labels = [t["label"] for t in Env(tmp_path).client.get("/api/status").json()["tags"]]
    assert labels == ["Building the organization", "Cadre development", "Mass consciousness and mass work",
                      "Strategy, tactics and alliances", "National liberation and colonialism",
                      "Investigation, learning and correcting mistakes", "Foundations and historical records"]
