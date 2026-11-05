"""Real-git checks that documents, databases, secrets and history can't be committed."""
import shutil
import subprocess

import pytest

from conftest import ROOT

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

MUST_IGNORE = ["data/originals/a.pdf", "data/originals/b.txt", "data/tutor.db", "data/tutor.db-wal",
               "data/tutor.db-shm", "data/anything/else.json", ".env", ".env.local", ".env.production",
               "app.db", "x.sqlite3", "exports/session.md", "uploads/a.md", "library/book.pdf",
               "documents/x.docx", "my-documents/y.epub", "stray-scan.pdf", "test-artifacts/s.png",
               ".venv/bin/python"]
MUST_TRACK = [".env.example", "fixtures/synthetic/synthetic_c_harbour_primer.pdf",
              "fixtures/synthetic/synthetic_a_mill_town_notes.md", "app/main.py", "CLAUDE.md"]


def git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)


@pytest.mark.parametrize("path", MUST_IGNORE)
def test_sensitive_paths_are_git_ignored(path):
    assert git("check-ignore", "-q", path).returncode == 0, f"{path} is NOT ignored"


@pytest.mark.parametrize("path", MUST_TRACK)
def test_expected_files_are_not_ignored(path):
    assert git("check-ignore", "-q", path).returncode == 1, f"{path} is unexpectedly ignored"


def test_nothing_sensitive_is_tracked():
    tracked = git("ls-files").stdout.split()
    bad = [f for f in tracked
           if f == ".env" or (f.startswith(".env.") and f != ".env.example") or f.startswith("data/")
           or f.endswith((".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm"))
           or (f.endswith((".pdf", ".epub", ".docx")) and not f.startswith("fixtures/synthetic/"))]
    assert bad == []
    assert not any(f.startswith(("exports/", "uploads/", "test-artifacts/")) for f in tracked)


def test_no_api_key_shaped_strings_in_tracked_files():
    import re
    pat = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")
    hits = []
    for f in git("ls-files").stdout.split():
        p = ROOT / f
        if p.suffix in {".png", ".pdf", ".ico"} or not p.is_file():
            continue
        if pat.search(p.read_text(errors="ignore")):
            hits.append(f)
    assert hits == []


def test_filled_evidence_packets_with_excerpts_are_ignored():
    for p in ("docs/dialectical/DIAGNOSTIC_PACKET.local.md", "notes.local.md", "docs/dialectical/local/packet.md"):
        assert git("check-ignore", "-q", p).returncode == 0, p
    assert git("check-ignore", "-q", "docs/dialectical/DIAGNOSTIC_PACKET.md").returncode == 1      # the empty template is tracked


def test_alternative_data_folders_are_ignored_too():
    for p in ("data-acceptance/tutor.db", "data-acceptance/originals/x.pdf", "data-backup/tutor.db"):
        assert git("check-ignore", "-q", p).returncode == 0, p
