"""Screenshots of the running app (demo provider, SYNTHETIC fixtures only, temp data dir).

Usage: python scripts/make_screenshots.py   -> docs/design/screenshots/
Also asserts there is no horizontal scroll at either width.
"""
import glob, socket, sys, threading, time, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import uvicorn
from playwright.sync_api import sync_playwright
from app.config import Settings
from app.main import create_app

OUT = ROOT / "docs/design/screenshots"; OUT.mkdir(parents=True, exist_ok=True)
app = create_app(Settings(data_dir=Path(tempfile.mkdtemp())))
s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
threading.Thread(target=srv.run, daemon=True).start()
while not srv.started: time.sleep(.05)
URL = f"http://127.0.0.1:{port}"
chrome = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux64/chrome"))[-1]

def scrolls(pg): return pg.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=chrome, args=["--no-sandbox"])
    for tag, w, h in (("desktop", 1280, 900), ("narrow", 390, 844)):
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2,
                            reduced_motion="reduce")
        pg = ctx.new_page(); pg.on("dialog", lambda d: d.accept())
        pg.goto(URL); pg.wait_for_selector("#doc-list")
        if tag == "desktop":
            pg.click("#fixtures-btn"); pg.wait_for_selector(".doc-card")
            # approve every unapproved primary document
            while pg.locator(".approve-btn:has-text('Approve for use'):not([disabled])").count():
                pg.locator(".approve-btn:has-text('Approve for use'):not([disabled])").first.click(); pg.wait_for_timeout(250)
        else:
            pg.reload(); pg.wait_for_selector(".doc-card")
        def shot(name, full=True):
            pg.wait_for_timeout(2500); pg.evaluate('window.scrollTo(0,0)')
            assert not scrolls(pg), f"horizontal scroll: {name} {tag}"
            pg.screenshot(path=str(OUT / f"{name}-{tag}.png"), full_page=full)
        pg.wait_for_selector(".doc-card")
        shot("2-library")
        pg.click("#nav button[data-view=sessions]")
        pg.click("#new-chat-btn"); pg.wait_for_selector("#new-panel .scope-preview")
        pg.wait_for_function("document.querySelector('#new-panel .scope-preview').textContent.includes('Resolves to')")
        shot("3-new-session")
        pg.fill("#nc-title", "Mill town: contradiction and conditions"); pg.click("#nc-start")
        pg.wait_for_selector("#chat-input")
        pg.fill("#chat-input", "What is the main constraint on the workshop, according to the texts?")
        pg.click("#chat-send"); pg.wait_for_selector(".msg.assistant")
        pg.wait_for_timeout(600)
        pg.locator(".evidence summary").first.click()
        shot("1-conversation")
        pg.locator(".cite-chip").first.click(); pg.wait_for_selector("#modal .target")
        shot("1b-passage-panel", full=False)
        pg.click("#modal-close")
        pg.click("#new-chat-btn"); pg.wait_for_selector("#nc-start"); pg.click("#nc-start")  # second session for history
        pg.wait_for_selector("#chat-input")
        pg.click("#nav button[data-view=library]"); pg.click("#nav button[data-view=sessions]")
        shot("4-session-history")
        # keyboard focus visible
        pg.keyboard.press("Tab"); pg.screenshot(path=str(OUT / f"focus-{tag}.png"), clip={"x": 0, "y": 0, "width": w, "height": 160})
        ctx.close()
    b.close()
srv.should_exit = True
print("ok", sorted(x.name for x in OUT.iterdir()))
