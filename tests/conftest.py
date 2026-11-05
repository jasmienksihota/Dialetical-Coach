"""Shared fixtures. All documents used by tests are SYNTHETIC (see fixtures/synthetic)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.ingest import ingest_file  # noqa: E402

FIX = ROOT / "fixtures" / "synthetic"


def fixture_bytes(name: str) -> bytes:
    return (FIX / name).read_bytes()


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data")


@pytest.fixture(params=[True, False], ids=["fts5", "fallback"])
def db(request, settings):
    """Every DB-level test runs with FTS5 and with the non-FTS fallback."""
    return Database(settings.db_path, force_no_fts=not request.param)


@pytest.fixture
def loaded(db, settings):
    """Library with synthetic docs imported (unapproved). Returns {key: doc_id}."""
    ids = {}
    spec = {
        "mill": ("synthetic_a_mill_town_notes.md", ["foundations"]),
        "workshop": ("synthetic_b_workshop_handbook.txt", ["investigation", "cadre"]),
        "harbour": ("synthetic_c_harbour_primer.pdf", ["organization", "cadre"]),
        "inject": ("synthetic_injection_notes.txt", ["foundations"]),
        "scanned": ("synthetic_e_scanned_like.pdf", []),
    }
    for key, (fname, tags) in spec.items():
        r = ingest_file(db, settings, fname, fixture_bytes(fname), tags=tags)
        ids[key] = r["document_id"]
    r = ingest_file(db, settings, "synthetic_secondary_notes.md",
                    fixture_bytes("synthetic_secondary_notes.md"), kind="secondary_notes")
    ids["notes"] = r["document_id"]
    return ids


def approve(db, *doc_ids):
    from app.library import set_approval
    with db.tx() as c:
        for d in doc_ids:
            set_approval(c, d, True)


# ---------------------------------------------------------------- API-level helpers
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from app.providers import GenRequest, Provider  # noqa: E402


class ScriptedProvider(Provider):
    """Test double: returns canned payloads (or callables) and records every request."""
    name = "scripted"
    is_live = False
    label = "Test scripted provider"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[GenRequest] = []

    def generate(self, req):
        self.requests.append(req)
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return r(req) if callable(r) else r


class Env:
    def __init__(self, tmp_path, provider_factory=None, **settings_kw):
        self.settings = Settings(data_dir=tmp_path / "data", **settings_kw)
        self.app = create_app(self.settings, provider_factory)
        self.client = TestClient(self.app)
        self.svc = self.app.state.svc
        self.ids = {}

    def load(self, approve_keys=("mill", "workshop", "harbour")):
        """Import synthetic fixtures through the API and approve some of them."""
        spec = {
            "mill": ("synthetic_a_mill_town_notes.md", "foundations"),
            "workshop": ("synthetic_b_workshop_handbook.txt", "investigation,cadre"),
            "harbour": ("synthetic_c_harbour_primer.pdf", "organization,cadre"),
            "inject": ("synthetic_injection_notes.txt", "foundations"),
            "scanned": ("synthetic_e_scanned_like.pdf", ""),
        }
        for key, (fname, tags) in spec.items():
            r = self.client.post("/api/documents", files={"file": (fname, fixture_bytes(fname))},
                                 data={"tags": tags})
            assert r.status_code == 200, r.text
            self.ids[key] = r.json()["document_id"]
        r = self.client.post("/api/documents", data={"kind": "secondary_notes"}, files={
            "file": ("synthetic_secondary_notes.md", fixture_bytes("synthetic_secondary_notes.md"))})
        self.ids["notes"] = r.json()["document_id"]
        for k in approve_keys:
            r = self.client.post(f"/api/documents/{self.ids[k]}/approval", json={"approved": True})
            assert r.status_code == 200, r.text
        return self

    def chat(self, provider="demo", scope=None, title="t"):
        r = self.client.post("/api/conversations",
                             json={"title": title, "provider": provider, "scope": scope or {}})
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def say(self, cid, text, intent="ask"):
        return self.client.post(f"/api/conversations/{cid}/messages", json={"text": text, "intent": intent})


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path).load()


def make_env(tmp_path, provider, approve=("mill", "workshop", "harbour"), **kw):
    return Env(tmp_path, lambda kind: provider, **kw).load(approve)
