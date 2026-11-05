"""Browser regressions: scope preview text, modal dialog keyboard behaviour. SYNTHETIC fixtures, demo provider."""
import glob, os, socket, sys, threading, time
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
pw = pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def _chromium():
    env = os.environ.get("CHROMIUM_PATH")
    if env and Path(env).exists():
        return env
    found = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux64/chrome"))
    return found[-1] if found else None


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    app = create_app(Settings(data_dir=tmp_path_factory.mktemp("d")))
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True); t.start()
    while not srv.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True; t.join(timeout=5)


@pytest.fixture(scope="module")
def page(server):
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch(executable_path=_chromium(), args=["--no-sandbox"])
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Chromium not available: {exc}")
        pg = b.new_context(viewport={"width": 1100, "height": 900}).new_page()
        yield pg
        b.close()


def _no_junk(text):
    assert "null" not in text and "undefined" not in text, text


def test_scope_preview_has_no_null_text_eligible_and_empty(page, server):
    page.goto(server); page.wait_for_selector("#doc-list")
    # empty library -> "No eligible documents" branch
    page.click("#nav button[data-view=sessions]"); page.click("#new-chat-btn")
    page.wait_for_function("document.querySelector('#new-panel .scope-preview').textContent.includes('Resolves to 0')")
    _no_junk(page.inner_text("#new-panel .scope-preview"))
    # eligible: load + approve fixtures
    page.click("#nav button[data-view=library]")
    page.click("#fixtures-btn"); page.wait_for_selector(".doc-card")
    while page.locator(".approve-btn:has-text('Approve for use'):not([disabled])").count():
        page.locator(".approve-btn:has-text('Approve for use'):not([disabled])").first.click(); page.wait_for_timeout(200)
    page.click("#nav button[data-view=sessions]"); page.click("#new-chat-btn")
    page.wait_for_function("document.querySelector('#new-panel .scope-preview').textContent.includes('Resolves to 4')")
    _no_junk(page.inner_text("#new-panel .scope-preview"))
    # a selection with an ineligible doc exercises the 'not eligible' list too
    page.check("#new-panel label:has-text('synthetic_secondary_notes') input") if page.locator("#new-panel label:has-text('synthetic_secondary_notes') input").count() else None
    page.wait_for_timeout(300)
    _no_junk(page.inner_text("#new-panel .scope-preview"))


def test_modal_focus_trap_escape_restore_and_name(page, server):
    page.goto(server); page.wait_for_selector(".doc-card")
    page.click("#nav button[data-view=search]")
    page.fill("#search-q", "main constraint conditions facts change"); page.click("#search-btn")
    page.wait_for_selector(".hit .inspect-btn")
    trigger = page.locator(".inspect-btn").first
    trigger.focus(); trigger.press("Enter")
    page.wait_for_selector("#modal .target")
    dlg = page.locator("#modal [role=dialog]")
    assert dlg.get_attribute("aria-modal") == "true"
    name_id = dlg.get_attribute("aria-labelledby")
    assert name_id and page.locator(f"#{name_id}").inner_text().strip()
    assert page.evaluate("document.querySelector('#modal').contains(document.activeElement)")
    for _ in range(40):  # focus never escapes the dialog
        page.keyboard.press("Tab")
        assert page.evaluate("document.querySelector('#modal').contains(document.activeElement)")
    for _ in range(40):
        page.keyboard.press("Shift+Tab")
        assert page.evaluate("document.querySelector('#modal').contains(document.activeElement)")
    # close button not overlapping the title
    cb = page.locator("#modal-close").bounding_box()
    title_right = page.evaluate(f"(() => {{const e=document.getElementById('{name_id}');const r=document.createRange();r.selectNodeContents(e);return r.getBoundingClientRect().right}})()")
    assert title_right <= cb["x"] + 1, (title_right, cb)
    page.keyboard.press("Escape")
    assert page.locator("#modal").is_hidden()
    assert page.evaluate("document.activeElement.classList.contains('inspect-btn')")
