"""Measure WCAG contrast for the token pairs in app/static/style.css.

Usage: python scripts/check_contrast.py [--markdown]
Exits non-zero if any pair misses its target (4.5 text, 3.0 UI/large).
"""
import re, sys
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "app/static/style.css"

def parse():
    css = CSS.read_text()
    light = dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", css.split("@media")[0]))
    dark_block = css.split("@media (prefers-color-scheme: dark)")[1].split("/* =====")[0]
    dark = {**light, **dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", dark_block))}
    return light, dark

def lum(hexs):
    c = [int(hexs[i:i+2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in c]
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]

def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + .05) / (lb + .05)

# (label, foreground token, background token, target)
PAIRS = [
    ("Body text on page", "ink", "bg", 4.5), ("Body text on reading surface", "ink", "panel", 4.5),
    ("Muted text on page", "muted", "bg", 4.5), ("Muted text on reading surface", "muted", "panel", 4.5),
    ("Primary button text on peony", "btn-ink", "btn", 4.5),
    ("Approve button text on matcha", "leaf-ink", "leaf", 4.5),
    ("Olive text on page", "leaf-text", "bg", 4.5),
    ("Passage highlight / step number text", "hl-ink", "hl", 4.5),
    ("Ink on butter (warning, question, passage target)", "ink", "butter", 4.5),
    ("Ink on sky (cite chip)", "ink", "sky", 4.5),
    ("Ink on lilac (tag chip, cite hover)", "ink", "lilac", 4.5),
    ("Link peony-deep on surface", "accent", "panel", 4.5),
    ("Link peony-deep on page", "accent", "bg", 4.5),
    ("Text on blush (user message, selected, passage)", "blush-ink", "blush", 4.5),
    ("Body text on blush (nav hover)", "ink", "blush", 4.5),
    ("Warning notice", "warn-ink", "warn-bg", 4.5), ("Error / withheld notice", "bad-ink", "bad-bg", 4.5),
    ("OK notice / live chip", "ok-ink", "ok-bg", 4.5),
    ("Label: quotation", "quote", "panel", 4.5), ("Label: interpretation", "interp", "panel", 4.5),
    ("Label: synthesis", "synth", "panel", 4.5), ("Label: fiction", "fiction", "panel", 4.5),
    ("Label: app coaching", "coach", "panel", 4.5), ("Label: limits", "limits", "panel", 4.5),
    ("Input / button boundary vs surface (UI 3:1)", "line-strong", "panel", 3.0),
    ("Input boundary vs page (UI 3:1)", "line-strong", "bg", 3.0),
    ("Focus ring vs page (UI 3:1)", "focus", "bg", 3.0), ("Focus ring vs surface (UI 3:1)", "focus", "panel", 3.0),
    ("Outline vs page (UI 3:1)", "line-strong", "bg", 3.0),
]

def main():
    md = "--markdown" in sys.argv
    light, dark = parse()
    bad = 0
    if md:
        print("| Pairing | Target | Light | Dark |\n|---|---|---|---|")
    for label, fg, bg, tgt in PAIRS:
        rl, rd = ratio(light[fg], light[bg]), ratio(dark[fg], dark[bg])
        ok = rl >= tgt and rd >= tgt
        bad += not ok
        if md:
            print(f"| {label} (`{fg}` on `{bg}`) | {tgt}:1 | {rl:.2f} | {rd:.2f} |")
        else:
            print(f"{'ok ' if ok else 'FAIL'} {label:55} {rl:5.2f} {rd:5.2f} (>= {tgt})")
    sys.exit(1 if bad else 0)

main()
