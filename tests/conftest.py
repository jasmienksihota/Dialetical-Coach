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
