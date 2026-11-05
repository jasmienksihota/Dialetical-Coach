"""Generators for SYNTHETIC extraction stress documents (needs reportlab, a dev dependency).

These imitate layout problems common in real scans/PDFs. They are invented text, not real
sources, and they are NOT real documents: passing them does not establish quality on yours.
"""
from __future__ import annotations

import io

from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

LOREM = ("The fictional cooperative studied its own methods carefully. Members compared what each "
         "committee had observed with what each committee had assumed, and the secretary recorded "
         "every disagreement in the ledger. Where the facts were thin, the members postponed "
         "their conclusions and sent two investigators to the harbour to gather more evidence about "
         "the slow deliveries, the broken winch, and the quarrel over the night shift. ")


import random

POOL = [
    "The members compared what each committee had observed with what each committee had assumed.",
    "The secretary recorded every disagreement in the ledger before the next meeting began.",
    "Where the facts were thin, the members postponed their conclusions and gathered more evidence.",
    "Two investigators were sent to the harbour to study the slow deliveries and the broken winch.",
    "The quarrel over the night shift grew until nobody could ignore its effect on the other disputes.",
    "A new road changed the prices, but the older tension inside the cooperative decided the result.",
    "Newcomers were asked to describe what they had seen before anyone offered an interpretation.",
    "The treasurer insisted that every explanation be tested against the records of the third week.",
    "After the survey, the committee revised its earlier view and wrote down why it had changed.",
    "Teaching happened by letting each apprentice attempt the task and then reviewing the result together.",
    "The harbour master warned that the same word could name different relationships in different seasons.",
    "Fair assessment meant using one standard for every member and publishing it in advance.",
]


def prose(seed, sentences=14):
    """Deterministic, page-specific prose so pages do not share identical lines."""
    rnd = random.Random(seed)
    out = rnd.sample(POOL, len(POOL)) + rnd.sample(POOL, len(POOL))
    return f"Section {seed}. " + " ".join(out[:sentences]) + " "


def wrap(text, width, font="Helvetica", size=10, hyphenate=False):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if stringWidth(trial, font, size) <= width:
            cur = trial
            continue
        if hyphenate and len(w) > 8 and stringWidth(cur + " " + w[:4] + "-", font, size) <= width:
            lines.append((cur + " " + w[:4] + "-").strip())
            cur = w[4:]
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _pdf(draw_pages, **kw):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter, **kw)
    draw_pages(c)
    c.save()
    return buf.getvalue()


def two_column_with_header_footer(pages=4):
    def draw(c):
        for n in range(1, pages + 1):
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(72, 760, "THE FICTIONAL REVIEW  -  VOLUME THREE  -  SYNTHETIC")      # running header
            c.setFont("Helvetica", 10)
            for col_x in (72, 320):                       # left column fully, then right column
                y = 730
                for line in wrap(f"PAGEMARK{n} " + prose(n * 10 + (col_x > 100), 12) + prose(n * 100, 12), 215, hyphenate=True)[:44]:
                    c.drawString(col_x, y, line)
                    y -= 14
            c.drawString(300, 40, f"- {n} -")                                                  # footer page number
            c.showPage()
    return _pdf(draw)


def paragraph_spanning_pages():
    def draw(c):
        para = ("SPANNINGPARA " + prose(1, 12) * 3)
        lines = wrap(para, 440)
        per_page = 12
        for p in range(0, len(lines), per_page):
            y = 700
            for line in lines[p:p + per_page]:
                c.drawString(72, y, line)
                y -= 14
            c.showPage()
    return _pdf(draw)


def with_footnotes():
    def draw(c):
        y = 720
        for line in wrap("The notes argue that the quarrel mattered most.1 A second point follows here in the body text.2 " + prose(3), 440):
            c.drawString(72, y, line)
            y -= 14
        c.setFont("Helvetica", 8)
        c.drawString(72, 90, "1 Footnote one: see the ledger entry for the third week.")
        c.drawString(72, 78, "2 Footnote two: the winch was repaired after the survey.")
        c.showPage()
    return _pdf(draw)


def accents_and_punctuation():
    def draw(c):
        y = 720
        for line in ["Café society — “quoted” speech, naïve readings, and ‘single’ marks.",
                     "The coöperative met in Zürich; the élan of the secretary was remarked upon.",
                     "A long enough sentence is needed here so the paragraph passes the minimum size threshold."]:
            c.drawString(72, y, line)
            y -= 16
        c.showPage()
    return _pdf(draw)


def long_pdf(pages=150):
    def draw(c):
        for n in range(1, pages + 1):
            y = 720
            for line in wrap(f"Page {n} marker-{n}. " + prose(n, 12) + prose(n + 1000, 12), 440)[:40]:
                c.drawString(72, y, line)
                y -= 14
            c.showPage()
    return _pdf(draw)


def mixed_text_and_scanned():
    def draw(c):
        for n in range(1, 6):
            if n in (2, 4):                                       # image-only-like pages
                c.rect(72, 200, 400, 400)
                c.line(72, 200, 472, 600)
            else:
                y = 720
                for line in wrap(f"Real text on page {n}. " + prose(n, 12), 440)[:30]:
                    c.drawString(72, y, line)
                    y -= 14
            c.showPage()
    return _pdf(draw)


def encrypted_pdf():
    from reportlab.lib.pdfencrypt import StandardEncryption
    return _pdf(lambda c: (c.drawString(72, 700, "Secret text that needs a password to open. " * 2), c.showPage()),
                encrypt=StandardEncryption("userpw", ownerPassword="ownerpw"))


def truncated_pdf():
    data = two_column_with_header_footer(2)
    return data[: len(data) // 2]


# ---- text variants -------------------------------------------------------------------
def txt_hard_wrapped():
    paras = [LOREM * 2, LOREM, LOREM * 3]
    return "\n\n".join("\n".join(wrap(p, 330, size=10)) for p in paras).encode()


def txt_single_newline_paragraphs(n=60):
    """No blank lines between paragraphs (common in scraped text): one giant 'paragraph'."""
    return "\n".join(f"Paragraph {i}. " + LOREM for i in range(1, n + 1)).encode()


def txt_cp1252():
    return ("The “cooperative” wasn’t finished — the secretary’s notes explain why. " * 3).encode("cp1252")


def txt_crlf():
    return ("First paragraph of the ledger notes is here and long enough.\r\n\r\n"
            "Second paragraph of the ledger notes is also here and long enough.\r\n").encode()


def md_complex():
    return ("---\ntitle: Front matter should not be a paragraph\n---\n\n# Title\n\n## Section A\n\n"
            "Intro text for section A that is long enough to be a paragraph of its own.\n\n"
            "| col1 | col2 |\n|------|------|\n| a | b |\n\n```python\nprint('code block')\n```\n\n"
            "### Subsection A1\n\nMore body text in the subsection that is long enough to index.\n\n"
            "## Section B\n\nBody text of section B is here and also long enough to index well.\n").encode()
