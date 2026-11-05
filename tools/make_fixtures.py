"""Generate the SYNTHETIC PDF fixtures (needs reportlab: pip install reportlab).

Run:  python tools/make_fixtures.py
Writes fixtures/synthetic/*.pdf. Every file says SYNTHETIC on its pages. The generated
PDFs are committed so the app and tests do not need reportlab at runtime.
"""
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "fixtures" / "synthetic"

PAGES = [
    [
        "SYNTHETIC TEST FIXTURE C - Primer of the Fictional Harbour Cooperative",
        "SYNTHETIC FIXTURE: invented text for software testing. Not a real source.",
        "",
        "Page one. The cooperative's founders held that development has an inner source.",
        "A fishing cooperative changes mainly because of tensions inside it, such as the",
        "tension between boat owners and net menders, and only secondarily because of",
        "outside conditions such as the price of fuel. Outside conditions work through",
        "the inner tensions already present.",
    ],
    [
        "Page two. The primer teaches that a cooperative with many pressing problems must",
        "identify its main constraint. The main constraint is the problem whose resolution",
        "most loosens the others. When the harbour silted up, the main constraint moved",
        "from staffing to access, and the plan had to be revised with the new facts.",
        "The primer warns that the same word can describe different relationships in",
        "different conditions, so each case must be studied concretely.",
    ],
    [
        "Page three. On teaching: a senior member should let a newcomer attempt a task,",
        "ask what the newcomer observed before offering an answer, and give feedback that",
        "separates what was seen from what was inferred. The primer recommends assessing",
        "newcomers fairly, by the same published standard, and listening to their",
        "reasons before correcting them.",
    ],
]


def make_text_pdf(path: Path):
    c = canvas.Canvas(str(path), pagesize=letter)
    for lines in PAGES:
        y = 740
        for line in lines:
            c.drawString(72, y, line)
            y -= 18
        c.showPage()
    c.save()


def make_scanned_like_pdf(path: Path):
    """Pages that only contain drawn shapes: no extractable text (like a bare scan)."""
    c = canvas.Canvas(str(path), pagesize=letter)
    for _ in range(3):
        c.rect(72, 200, 400, 400, stroke=1, fill=0)
        c.line(72, 200, 472, 600)
        c.showPage()
    c.save()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    make_text_pdf(OUT / "synthetic_c_harbour_primer.pdf")
    make_scanned_like_pdf(OUT / "synthetic_e_scanned_like.pdf")
    print("wrote fixtures to", OUT)
