"""Browser smoke test (Playwright + Chromium), run against a real local server.

Flow: import fixture -> approve -> search -> inspect passage -> start demo exercise ->
answer -> revise -> export.   Uses only SYNTHETIC fixtures and the demo provider.
Skipped automatically if Playwright or a Chromium binary is unavailable.
"""
import glob
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

playwright_sync = pytest.importorskip("playwright.sync_api")

import uvicorn  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

FIX = ROOT / "fixtures" / "synthetic"
SHOTS = ROOT / "test-artifacts"


def _chromium_path():
    env = os.environ.get("CHROMIUM_PATH")
    if env and Path(env).exists():
        return env
    for pat in ("/opt/pw-browsers/chromium-*/chrome-linux64/chrome",):
        found = sorted(glob.glob(pat))
        if found:
            return found[-1]
    return None  # let Playwright use its own downloaded browser


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    data = tmp_path_factory.mktemp("e2e-data")
    app = create_app(Settings(data_dir=data))
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    t.join(timeout=5)


@pytest.fixture(scope="module")
def page(server):
    with playwright_sync.sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=_chromium_path(), args=["--no-sandbox"])
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Chromium not available: {exc}")
        ctx = browser.new_context(viewport={"width": 1100, "height": 900}, accept_downloads=True)
        pg = ctx.new_page()
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" else None)
        pg.on("dialog", lambda d: d.accept())
        yield pg
        browser.close()


def shot(page, name):
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def test_smoke_flow(page, server):
    page.goto(server)
    page.wait_for_selector("#doc-list")
    assert "Demo mode only" in page.inner_text("#status-chip")

    # --- import three SYNTHETIC fixtures through the real upload form
    uploads = [("synthetic_a_mill_town_notes.md", "Foundations and historical records"),
               ("synthetic_b_workshop_handbook.txt", "Investigation, learning and correcting mistakes"),
               ("synthetic_c_harbour_primer.pdf", "Cadre development")]
    for n, (fname, tag) in enumerate(uploads, start=1):
        page.set_input_files("#file-input", str(FIX / fname))
        page.check(f"#up-tags label:has-text('{tag}') input")
        page.click("#upload-btn")
        page.wait_for_function(f"document.querySelectorAll('.doc-card').length === {n}")
    assert page.locator(".doc-card").count() == 3
    assert page.locator(".badge:has-text('unapproved')").count() == 3
    # duplicate import is refused politely
    page.set_input_files("#file-input", str(FIX / "synthetic_b_workshop_handbook.txt"))
    page.click("#upload-btn")
    page.wait_for_function("document.querySelector('#upload-msg').textContent.includes('exact duplicate')")
    assert page.locator(".doc-card").count() == 3

    # --- unapproved docs are not searchable
    page.click("#nav button[data-view=search]")
    page.fill("#search-q", "contradiction internal conditions")
    page.click("#search-btn")
    page.wait_for_selector("#search-results .muted")
    assert page.locator(".hit").count() == 0

    # --- approve all three
    page.click("#nav button[data-view=library]")
    for _ in range(3):
        page.locator(".approve-btn:has-text('Approve for use')").first.click()
        page.wait_for_timeout(150)
    page.wait_for_function("document.querySelectorAll('.badge.ok').length >= 3")
    assert page.locator(".doc-card .badge:has-text('approved')").count() >= 3
    shot(page, "1-library")

    # --- search and inspect a passage
    page.click("#nav button[data-view=search]")
    page.fill("#search-q", "main constraint conditions facts change")
    page.click("#search-btn")
    page.wait_for_selector(".hit .inspect-btn")
    assert page.locator(".hit").count() >= 2
    page.locator(".inspect-btn").first.click()
    page.wait_for_selector("#modal .target")
    assert page.locator("#modal .target").inner_text().strip()
    assert "primary source" in page.inner_text("#modal-body")
    shot(page, "2-passage")
    page.click("#modal-close")

    # --- start the demo exercise
    page.click("#nav button[data-view=sessions]")
    page.click("#new-exercise-btn")
    page.wait_for_selector("#new-panel .scope-preview")
    page.wait_for_function("document.querySelector('#new-panel .scope-preview').textContent.includes('Resolves to 3 document')")
    assert "UNION" in page.inner_text("#new-panel .scope-preview")
    page.check("#new-panel label:has-text('Cadre development') input")          # tag -> resolved list updates
    page.wait_for_function("document.querySelector('#new-panel .scope-preview').textContent.includes('Resolves to 1 document')")
    assert "tag: Cadre development" in page.inner_text("#new-panel .scope-preview")
    page.uncheck("#new-panel label:has-text('Cadre development') input")
    page.wait_for_function("document.querySelector('#new-panel .scope-preview').textContent.includes('Resolves to 3 document')")
    page.click("#ex-start")
    page.wait_for_selector("#ex-panel")
    assert "Waiting for your first attempt" in page.inner_text("#ex-phase")
    assert "Demo: scripted responses, not live tutoring." in page.inner_text("#conv-view")
    assert page.locator(".block.fiction").count() == 1
    assert "FICTIONAL" in page.locator(".block.fiction").inner_text()
    assert page.locator(".block.question").count() == 1
    page.click("#scope-details summary")
    assert "Documents in scope right now: 3" in page.inner_text("#scope-details")
    page.locator(".evidence summary").first.click()
    assert "Documents in scope this turn" in page.inner_text(".msg.assistant")
    assert page.locator(".block.quote .cites .cite-chip").count() >= 1
    shot(page, "3-exercise-start")

    # --- answer, follow-up, revise
    page.fill("#answer-text", "The teams are in tension because aims differ; I observe sales rose and infer timing. Perhaps another explanation.")
    page.click("#submit-answer")
    page.wait_for_function("document.querySelector('#ex-phase').textContent.includes('follow-up')")
    assert page.locator(".msg.assistant").count() == 2
    page.fill("#answer-text", "If wrong, complaints would not cluster; I would check records.")
    page.click("#submit-answer")
    page.wait_for_function("document.querySelector('#ex-phase').textContent.includes('revision')")
    assert page.locator(".block[data-purpose=complication]").count() == 1
    page.fill("#answer-text", "In light of the new fact I revise my explanation: previously I assumed too much.")
    page.click("#submit-answer")
    page.wait_for_function("document.querySelector('#ex-phase').textContent.includes('Review')")
    shot(page, "4-exercise-revised")

    # --- citation inspection + flag from the conversation
    page.locator(".cite-chip").first.click()
    page.wait_for_selector("#modal .target")
    page.click("#modal-close")
    page.locator(".flag-btn").first.click()   # prompt auto-accepted with default (empty) note
    page.wait_for_selector(".flag-btn:has-text('Flagged')")

    # --- finish and export
    page.click("#finish-btn")
    page.wait_for_function("document.querySelector('#ex-phase').textContent.includes('Finished')")
    with page.expect_download() as dl:
        page.click("#export-btn")
    path = dl.value.path()
    md = Path(path).read_text(encoding="utf-8")
    assert "Manual handoff, not synchronization" in md
    assert "Demo: scripted responses, not live tutoring." in md
    assert "Session reflection" in md and "Source references" in md and "Flagged for review" in md
    shot(page, "5-finished")

    assert page.errors == [], page.errors


def test_live_status_chip_does_not_overclaim(tmp_path, page):
    """Live configured but never called: the badge must not say 'verified'."""
    app = create_app(Settings(data_dir=tmp_path / "d", live_enabled=True, anthropic_api_key="x" * 12,
                              anthropic_model="claude-sonnet-5-5"), lambda kind: (_ for _ in ()).throw(AssertionError("no live call allowed")))
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True); t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    try:
        page.goto(f"http://127.0.0.1:{port}")
        page.wait_for_function("document.querySelector('#status-chip').textContent.length > 0")
        text = page.inner_text("#status-chip")
        assert "API not yet reached" in text and "verified" not in text.lower()
    finally:
        srv.should_exit = True; t.join(timeout=5)
