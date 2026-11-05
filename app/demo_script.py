"""Scripted content for the demo provider ("Demo: scripted responses, not live tutoring.").

Everything here is deterministic. Quotations are taken verbatim from the supplied
passages (so they validate). Feedback is KEYWORD matching, not an evaluation of thinking,
and says so. This exists to demonstrate the interaction and to make tests repeatable.
"""
from __future__ import annotations

import re

from .modes import MODES, RUBRIC, RUBRIC_NOTE

_SENT_END = re.compile(r"(?<=[.!?])\s+")

SIGNALS = {
    "evidence": [r"\bobserv", r"\bevidence\b", r"\bassum", r"\binfer", r"\bstated\b", r"\bfacts?\b",
                 r"\bthe (story|text|passage) (says|tells|states)", r"\bwe (are )?told\b"],
    "causal": [r"\bbecause\b", r"\bcaus", r"\bleads? to\b", r"\bdue to\b", r"\bresults? (in|from)\b",
               r"\bdrives?\b", r"\bdriving\b", r"\bso that\b"],
    "relationships": [r"\btension", r"\bconflict", r"\bcontradict", r"\brelationship", r"\bdepends?\b",
                      r"\bbetween\b", r"\btrade-?off", r"\bpull(s|ing)?\b"],
    "alternatives": [r"\balternativ", r"\banother (explanation|possibility|reason)", r"\bcould (also|instead)",
                     r"\brival\b", r"\bor (maybe|perhaps)\b", r"\bother explanation"],
    "revision": [r"\bnew (fact|information|evidence)", r"\bI (now|would now) ", r"\brevis", r"\bin light of\b",
                 r"\bchange my\b", r"\bearlier I\b", r"\bpreviously\b"],
    "uncertainty": [r"\bmight\b", r"\bperhaps\b", r"\bunclear\b", r"\buncertain", r"\bnot sure\b",
                    r"\bprobably\b", r"\bmaybe\b", r"\bI don'?t know\b", r"\bcan'?t be sure\b"],
}
LABEL = dict(RUBRIC)


def analyse(text: str) -> dict:
    return {k: any(re.search(p, text, re.I) for p in pats) for k, pats in SIGNALS.items()}


def lead_excerpt(text: str, min_chars: int = 80, max_chars: int = 260) -> str:
    t = text.strip()
    ends = [m.start() for m in _SENT_END.finditer(t)] + [len(t)]
    cut = ends[0]
    for e in ends[1:]:
        if cut >= min_chars or e > max_chars:
            break
        cut = e
    return t[:cut].strip()[:max_chars]


def _cite(p, quote=None):
    return {"passage_id": p["id"], **({"quote": quote} if quote else {})}


def _quote(p, purpose=None):
    q = lead_excerpt(p["text"])
    return {"type": "quote", "purpose": purpose, "text": q, "citations": [_cite(p, q)]}


def _coach(text, purpose=None):
    return {"type": "coaching", "purpose": purpose, "text": text, "citations": []}


def _two_docs(passages):
    first = passages[0]
    for p in passages[1:]:
        if p["doc_id"] != first["doc_id"]:
            return first, p
    return first, None


# --------------------------------------------------------------------------- chat
def _chat(req):
    ctx, ps = req.context, req.passages
    intent, weak = ctx.get("intent", "ask"), ctx.get("strength") == "weak"
    a, b = _two_docs(ps)
    blocks = [_quote(a)]
    if intent in ("compare", "disagreements") and b:
        blocks.append(_quote(b))
        blocks.append({"type": "synthesis", "text": (
            f"Demo comparison: “{a['doc_title']}” and “{b['doc_title']}” each contain passages "
            "that bear on your question (quoted above). This scripted demo cannot judge whether "
            "they agree; read the two quotations side by side and note where the wording, the "
            "case discussed, or the historical context differs."),
            "citations": [_cite(a), _cite(b)]})
        blocks.append({"type": "limits", "text": (
            "The selected library does not, from these passages alone, establish whether the two "
            "texts would agree, or how their different contexts affect the comparison."),
            "citations": []})
    elif intent == "challenge":
        mine = (ctx.get("user_text") or "")[:160]
        blocks.append({"type": "interpretation", "text": (
            f"Demo challenge: you proposed “{mine}”. The passage above is the closest match in the "
            "selected library. Check which parts of your claim it states directly, which parts you "
            "inferred, and which parts it does not address."), "citations": [_cite(a)]})
        blocks.append(_coach("Which single sentence of your claim would be hardest to defend from "
                             "this passage alone, and why?"))
    else:
        blocks.append({"type": "interpretation", "text": (
            f"Demo reading: the passage ({a['location']}) is relevant to your question because "
            "it uses several of your terms. This scripted demo does not interpret beyond the "
            "quoted words; in live mode a model would explain the passage in context, and you "
            "should still check its readings against the quotation."), "citations": [_cite(a)]})
        blocks.append(_coach("Try restating the quoted passage in your own words, then ask a "
                             "follow-up or challenge my reading."))
    if weak:
        blocks.append({"type": "limits", "text": (
            "The retrieved passages only weakly match your question (few of your terms appear). "
            "The selected library may not address it; try other wording or a wider selection."),
            "citations": []})
    return {"blocks": blocks}


# --------------------------------------------------------------------------- exercises
def _basis_quotes(ps, multi):
    a, b = _two_docs(ps)
    out = [_quote(a, "source_basis")]
    if multi and b:
        out.append(_quote(b, "source_basis"))
    return out


def _scenario_text(ctx):
    spec = MODES[ctx["mode"]]
    return spec["scenarios"][ctx["level"]]


def _open(req):
    ctx, ps = req.context, req.passages
    spec = MODES[ctx["mode"]]
    blocks = _basis_quotes(ps, ctx.get("multi_source", True))
    if ctx.get("scenario_kind") == "historical":
        blocks.append({"type": "interpretation", "purpose": "scenario", "text": (
            "HISTORICAL CASE, limited to what the selected passages document (quoted above). "
            "This scripted demo does not add any detail beyond them."),
            "citations": [_cite(p) for p in ps[:2]]})
    blocks.append(_coach(f"Learning objective: {spec['objective']} {RUBRIC_NOTE}", "objective"))
    if ctx.get("scenario_kind") != "historical":
        blocks.append({"type": "fiction", "purpose": "scenario", "text": (
            "FICTIONAL SCENARIO (invented for this exercise; not from the library): "
            + _scenario_text(ctx)), "citations": []})
    blocks.append(_coach(spec["questions"]["first"], "question"))
    return {"blocks": blocks}


def _seen_missing(text, skip=()):
    seen = analyse(text)
    got = [LABEL[k] for k, _ in RUBRIC if seen[k] and k not in skip]
    miss = [LABEL[k] for k, _ in RUBRIC if not seen[k] and k not in skip]
    return got, miss


def _feedback(req):
    ctx, ps = req.context, req.passages
    spec = MODES[ctx["mode"]]
    phase, text = ctx["phase"], ctx["user_text"]
    skip = () if phase in ("revision", "review") else ("revision",)
    got, miss = _seen_missing(text, skip)
    fb = ("Demo feedback (keyword matching by a script, NOT an evaluation of your thinking). "
          + ("Keyword matches: " + "; ".join(got) + ". " if got else "No rubric keyword matched. ")
          + ("No keyword match for: " + "; ".join(miss) + ". " if miss else "")
          + "A keyword match does not show an idea is supported by evidence or even understood, and no match "
            "does not show it is absent; say explicitly what facts your explanation rests on.")
    if phase in ("revision", "review") and ctx.get("attempts"):
        before = analyse(ctx["attempts"][0])
        now = analyse(text)
        gained = [LABEL[k] for k, _ in RUBRIC if now[k] and not before[k]]
        fb += (" Compared with your first attempt, newly matched keywords: " + "; ".join(gained) + "."
               if gained else " Compared with your first attempt, no new rubric keywords matched; "
               "explain explicitly what the new fact changed (or why it changes nothing).")
    anchor = ps[(ctx.get("turn", 0)) % len(ps)]
    blocks = [_coach(fb, "feedback"), _quote(anchor, "feedback"),
              {"type": "interpretation", "purpose": "feedback", "text": (
                  "The passage above is one of the texts selected for this exercise. A question to "
                  "bring back to your own answer: does it say where the change comes from (inside "
                  "the situation, outside it, or both) and how those are connected? This scripted "
                  "demo cannot judge whether the passage supports your specific answer."),
               "citations": [_cite(anchor)]}]
    snippet = re.sub(r"\s+", " ", text).strip()[:140]
    if phase == "attempt":
        blocks.append(_coach(spec["questions"]["probe"].format(quote=snippet), "question"))
    elif phase == "probe":
        blocks.append(_coach(spec["complication"], "complication"))
        blocks.append(_coach(spec["questions"]["revise"], "question"))
    else:
        blocks.append(_coach("You can revise again, ask for a hint, or finish the session to get a "
                             "reflection.", "next_steps"))
    return {"blocks": blocks}


def _hint(req):
    n = req.context.get("hints_used", 1)
    hints = [
        "Hint 1: Reread the scenario and list, in one column, only what it states. In another, list what you are guessing. Which column is your explanation built from?",
        "Hint 2: Look for two parties or forces in the scenario whose aims pull in different directions. How might each affect the other — and what outside condition changed in the meantime?",
        "Hint 3: I will not narrow it further without giving the answer away. Write your best attempt, mark what you are unsure about, and I will respond to that.",
    ]
    return {"blocks": [_coach(hints[min(n, 3) - 1], "hint")]}


def _clarify(req):
    ctx = req.context
    return {"blocks": [_coach(
        "Demo clarification: I can only restate the scenario as written — I cannot add facts. "
        f"The scenario says: {_scenario_text(ctx) if ctx.get('scenario_kind') != 'historical' else '(historical case: see the quoted passages)'} "
        "If you need a fact that is not stated, say what you would assume and treat it as an "
        "assumption in your answer.", "clarification")]}


def _analysis(req):
    ctx, ps = req.context, req.passages
    blocks = [_quote(ps[0], "analysis"),
              {"type": "interpretation", "purpose": "analysis", "text": (
                  "Demo analysis (one defensible reading, not THE answer): start from what the "
                  "scenario states; identify the parties or forces whose aims differ and how each "
                  "affects the other; separate those internal relations from outside conditions "
                  "and ask how the outside conditions work through them; then say what new facts "
                  "would change which issue is most important. Other readings that fit the facts "
                  "are legitimate if you can show the evidence for them."), "citations": [_cite(ps[0])]},
              _coach("Compare this reading with your own and note where you differ and why.", "analysis")]
    return {"blocks": blocks}


def _reflection(req):
    ctx, ps = req.context, req.passages
    attempts = ctx.get("attempts", [])
    union = {k: False for k, _ in RUBRIC}
    for t in attempts:
        for k, v in analyse(t).items():
            union[k] = union[k] or v
    shown = [LABEL[k] for k, _ in RUBRIC if union[k]]
    todo = [LABEL[k] for k, _ in RUBRIC if not union[k]]
    text = (f"Session reflection (demo; keyword-based, not a measure of ability). You made "
            f"{len(attempts)} attempt(s) and used {ctx.get('hints_used', 0)} hint(s). "
            + ("Keyword matches somewhere in your answers: " + "; ".join(shown) + ". " if shown else "")
            + ("No keyword match for: " + "; ".join(todo) + ". " if todo else "")
            + RUBRIC_NOTE)
    return {"blocks": [_coach(text, "reflection"), _quote(ps[0], "reflection"),
                       _coach("One thing to try next: pick a single claim from your last answer and "
                              "write what evidence would change your mind.", "reflection")]}


def generate(req):
    task = req.task
    if not req.passages and task != "chat":
        raise ValueError("demo provider needs passages")
    if task in ("chat", "repair"):
        return _chat(req)
    return {"exercise_open": _open, "exercise_answer": _feedback, "exercise_hint": _hint,
            "exercise_clarify": _clarify, "exercise_analysis": _analysis,
            "exercise_reflection": _reflection}[task](req)
