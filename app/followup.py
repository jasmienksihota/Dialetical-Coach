"""Follow-up detection and context-aware query building.

A short message such as "How does that change?", "Give another example" or "Why is that
the principal one?" has almost no searchable content of its own. For those we add the
terms of the most recent SUBSTANTIVE learner question (the "anchor") to the search. The
search is still restricted to the session's source scope by ``resolve_scope``; nothing
here can widen it. The anchor is the last non-follow-up question, not simply the previous
message, so a chain of follow-ups does not drift.

"Another / different / more" requests ask for NEW material: passages already supplied in
the previous turn are excluded from retrieval (and not carried over). If the scope has
nothing else, the app says so instead of repeating itself or reaching outside the scope.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .retrieval import query_terms

FILLER = set("""give another example examples more else again different other explain further why how what
about say tell please elaborate clarify mean means one ones thing things bit little simple simpler
still also really actually exactly""".split())
ANAPHORA = set("that this it those these they them he she same above previous earlier former latter one ones".split())
SEEKS_NEW = set("another different other else new alternative additional".split())   # NOT "more": "say more about that" means elaborate


@dataclass
class FollowUp:
    is_followup: bool
    seeks_new: bool
    own_terms: list[str]


def classify(text: str) -> FollowUp:
    words = re.findall(r"[\w'-]+", (text or "").lower())
    own = [t for t in query_terms(text) if t not in FILLER]
    anaphoric = any(w in ANAPHORA for w in words)
    is_fu = len(own) < 2 or (anaphoric and len(words) <= 12 and len(own) < 3)
    seeks_new = any(w in SEEKS_NEW for w in words) and (is_fu or len(words) <= 8)
    return FollowUp(is_fu, seeks_new, own)


def anchor_question(earlier_user_texts: list[str]) -> str:
    """Most recent earlier learner message that was NOT itself a follow-up."""
    for t in reversed(earlier_user_texts):
        if not classify(t).is_followup:
            return t
    return ""


def build_query(text: str, earlier_user_texts: list[str]) -> tuple[str, FollowUp, str]:
    fu = classify(text)
    anchor = anchor_question(earlier_user_texts) if fu.is_followup else ""
    query = f"{text} {anchor}".strip() if anchor else text
    return query, fu, anchor
