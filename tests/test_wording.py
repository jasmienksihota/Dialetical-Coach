"""Guards honest wording in user-facing text (not a substitute for reading it)."""
import re

import pytest

from conftest import ROOT, Env

USER_FACING = ["app/static/app.js", "app/static/index.html", "README.md", "docs/LOCAL_SETUP.md",
               "docs/LIVE_EVAL_CHECKLIST.md", "docs/REAL_DOCUMENT_ACCEPTANCE.md", "docs/PRIVACY.md", ".env.example"]
FORBIDDEN = [r"tutoring[ _]verified", r"verified tutoring", r"verified[- ]tutor"]


@pytest.mark.parametrize("path", USER_FACING)
def test_no_user_facing_claim_that_tutoring_is_verified(path):
    text = (ROOT / path).read_text()
    for pat in FORBIDDEN:
        assert not re.search(pat, text, re.I), f"{path} contains /{pat}/"


def test_status_api_and_check_output_use_the_honest_label(tmp_path, monkeypatch, capsys):
    e = Env(tmp_path)
    u = e.client.get("/api/status").json()["live_usage"]
    assert "citation_checks_passed" in u and "tutoring_verified" not in u and u["stage"] == "none"
    from app.check import main
    monkeypatch.setenv("TUTOR_DATA_DIR", str(tmp_path / "d2"))
    main([])
    out = capsys.readouterr().out
    assert "citation checks passed:" in out and "tutoring verified" not in out.lower()


def test_next_step_is_framed_as_a_hypothesis_not_a_finding():
    status = (ROOT / "docs" / "BUILD_STATUS.md").read_text()
    assert "working hypothesis" in status.lower()
    assert "synthetic fixtures I wrote" in status                  # states why it is not evidence about real files
    for overclaim in ("most likely appear", "7 of 7", "none in the retrieval ranking"):
        assert overclaim not in status
    assert "paused" in status.lower()
    assert "paused" in (ROOT / "CLAUDE.md").read_text().lower()
