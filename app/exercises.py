"""Exercise engine (shared by all modes).

State machine (stored in conversations.exercise as JSON):

    attempt --answer--> probe --answer--> revision --answer--> review --answer--> review ...
       |                  |                  |                    |
       +---- hint / clarify / pause<->resume / show_analysis (confirmed if no attempt yet) ----+
       +---- finish (needs >= 1 attempt) --> done (reflection)

Turn-taking and reveal gating are enforced HERE, not left to the model:
  * each turn may contain only blocks whose ``purpose`` is allowed for that action,
  * "analysis" is only allowed on an explicit show_analysis action,
  * at most ONE "question" block per turn is kept; if a waiting turn has none, an
    app-authored fallback question is appended,
  * the learner cannot be advanced without submitting an attempt (answers while paused
    or done are refused with HTTP 409).
This cannot stop a model from leaking an answer inside free-text feedback; that is a
prompt-level guard and is part of the manual live-model checklist.
"""
from __future__ import annotations

import json

from . import prompts
from .conversations import (add_message, build_history, conversation_to_dict, create_conversation,
                            get_row, update_conversation)
from .errors import AppError
from .modes import LEVELS, MODES, RUBRIC, RUBRIC_NOTE
from .providers import GenRequest
from .retrieval import Scope, describe_scope, resolve_scope
from .tutor import (Services, app_block, fetch_snapshots, generate_validated, snapshot,
                    snapshots_with_cited)

MAX_ANSWER_CHARS = 6000
WAITING_PHASES = ("attempt", "probe", "revision", "review")

# purposes allowed per action key, and whether the turn must end with exactly one question
RULES = {
    "open":            ({"source_basis", "objective", "scenario", "question"}, "objective", True),
    "answer:attempt":  ({"feedback", "question"}, "feedback", True),
    "answer:probe":    ({"feedback", "complication", "question"}, "feedback", True),
    "answer:revision": ({"feedback", "next_steps"}, "feedback", False),
    "answer:review":   ({"feedback", "next_steps"}, "feedback", False),
    "hint":            ({"hint"}, "hint", False),
    "clarify":         ({"clarification"}, "clarification", False),
    "analysis":        ({"analysis"}, "analysis", False),
    "reflection":      ({"reflection"}, "reflection", False),
}
FALLBACK_Q = {
    "attempt": "What is your explanation of what is going on, separating what the scenario states from what you infer?",
    "probe": "What would you expect to find if your explanation were wrong, and how could you check?",
    "revision": "In light of the new fact, how would you revise your original explanation?",
}
TASK = {"open": "exercise_open", "hint": "exercise_hint", "clarify": "exercise_clarify",
        "analysis": "exercise_analysis", "reflection": "exercise_reflection"}


def available_actions(ex: dict) -> list[str]:
    ph = ex["phase"]
    if ph in WAITING_PHASES:
        acts = ["answer", "hint", "clarify", "pause", "show_analysis"]
        if ex["attempts"]:
            acts.append("finish")
        return acts
    if ph == "paused":
        return ["resume"]
    if ph == "done" and not ex.get("analysis_shown"):
        return ["show_analysis"]
    return []


def public_exercise(ex: dict) -> dict:
    spec = MODES[ex["mode"]]
    return {**ex, "available_actions": available_actions(ex), "mode_title": spec["title"],
            "rubric": [{"key": k, "label": l} for k, l in RUBRIC], "rubric_note": RUBRIC_NOTE}


def _make_post(key: str):
    allowed, default, _ = RULES[key]
    stripped: list[str] = []

    def post(blocks):
        out, questions = [], 0
        for b in blocks:
            purpose = b.get("purpose") or ("scenario" if b["type"] == "fiction" and "scenario" in allowed else default)
            if purpose not in allowed:
                stripped.append(purpose)
                continue
            if purpose == "question":
                questions += 1
                if questions > 1:
                    stripped.append("extra_question")
                    continue
            out.append({**b, "purpose": purpose})
        return out
    return post, stripped


def _exercise_system(ex: dict, scope_desc: str, key: str, extra: str = "") -> str:
    spec = MODES[ex["mode"]]
    allowed = ", ".join(sorted(RULES[key][0]))
    lines = [prompts.EXERCISE_RULES,
             f"MODE: {spec['title']}. {spec['guidance']}",
             f"LEVEL: {ex['level']}. SCENARIO KIND: {ex['scenario_kind']}."
             + (" Historical case: use ONLY the supplied passages; add no outside historical detail."
                if ex["scenario_kind"] == "historical" else ""),
             f"ALLOWED block purposes THIS turn: {allowed}.",
             "RUBRIC (app-created): " + "; ".join(l for _, l in RUBRIC)]
    if ex.get("scenario"):
        lines.append("SCENARIO SHOWN TO THE LEARNER (app state): " + ex["scenario"])
    if ex.get("objective"):
        lines.append("OBJECTIVE: " + ex["objective"])
    if ex.get("complication"):
        lines.append("COMPLICATION ALREADY INTRODUCED: " + ex["complication"])
    if extra:
        lines.append(extra)
    return prompts.build_system(scope_desc, "", "\n".join(lines))


def _ctx(ex: dict, **kw) -> dict:
    return {"mode": ex["mode"], "level": ex["level"], "scenario_kind": ex["scenario_kind"],
            "multi_source": ex.get("multi_source", True), "phase": ex["phase"],
            "attempts": [a["text"] for a in ex["attempts"]], "hints_used": ex["hints_used"],
            "turn": ex["turn"], "objective": ex.get("objective", ""),
            "scenario": ex.get("scenario", ""), **kw}


def _texts(blocks, purpose):
    return " ".join(b["text"] for b in blocks if b.get("purpose") == purpose and b["type"] != "withheld" and b["text"])


def _generate(svc, provider, ex, key, scope, scope_ids, scope_desc, passages, learner_text,
              user_note="", intent="exercise", extra=""):
    allowed, default, need_q = RULES[key]
    post, stripped = _make_post(key)
    task = TASK.get(key, "exercise_answer")
    history = ex.get("_history", [])   # prior turns, supplied by exercise_action
    req = GenRequest(
        task=task, system=_exercise_system(ex, scope_desc, key, extra), passages=passages,
        messages=[*history, {"role": "user", "content": prompts.build_user_turn(
            passages, learner_text, intent, note=user_note)}],
        context=_ctx(ex, user_text=learner_text))
    blocks, report = generate_validated(svc, provider, req, scope_ids, post=post)
    fallback = False
    if need_q and not any(b.get("purpose") == "question" and b["type"] != "withheld" for b in blocks):
        phase = "attempt" if key == "open" else key.split(":")[1]
        blocks.append(app_block(FALLBACK_Q[phase], "question"))
        fallback = True
    report["engine"] = {"stripped_purposes": sorted(set(stripped)), "fallback_question": fallback,
                        "rubric_note": RUBRIC_NOTE}
    return blocks, report


def _basis_and_extra(svc, c, ex, scope, scope_ids, query=None):
    passages = fetch_snapshots(c, ex["basis_ids"], scope_ids)
    if not passages:
        raise AppError("The source basis for this exercise is no longer available (its documents "
                       "were unapproved, removed, or are outside the scope). Start a new exercise.", 409)
    if query:
        res = svc.retriever.search(c, f"{query} {MODES[ex['mode']]['seed_query']}", scope, limit=3)
        have = {p["id"] for p in passages}
        for h in res.hits:
            if h["id"] not in have and len(passages) < 7:
                passages.append(snapshot(h))
    return passages


def _new_state(config: dict, basis_ids: list[str]) -> dict:
    return {"mode": config["mode"], "level": config["level"], "scenario_kind": config["scenario_kind"],
            "multi_source": config["multi_source"], "focus": config["focus"],
            "historical_topic": config["historical_topic"], "phase": "attempt", "resume_phase": None,
            "turn": 0, "basis_ids": basis_ids, "objective": "", "scenario": "", "complication": "",
            "current_question": "", "attempts": [], "hints_used": 0, "analysis_shown": False,
            "analysis": [], "reflection": None, "limitation": ""}


# --------------------------------------------------------------------------- start
def start_exercise(svc: Services, cfg: dict) -> dict:
    mode = cfg.get("mode") or "dialectical"
    level = cfg.get("level") or "beginner"
    kind = cfg.get("scenario_kind") or "fictional"
    if mode not in MODES:
        raise AppError("Unknown exercise mode.", 400)
    if level not in LEVELS:
        raise AppError("Level must be beginner, intermediate or advanced.", 400)
    if kind not in ("fictional", "historical"):
        raise AppError("scenario_kind must be 'fictional' or 'historical'.", 400)
    focus = (cfg.get("focus") or "").strip()[:200]
    topic = (cfg.get("historical_topic") or "").strip()[:200]
    if kind == "historical" and not topic:
        raise AppError("A historical case needs a topic to look for in the selected library.", 400)
    multi = bool(cfg.get("multi_source", True))
    scope = Scope.from_dict(cfg.get("scope"))
    provider_kind = cfg.get("provider") or "demo"
    provider = svc.make_provider(provider_kind)     # raises a setup message if live not configured

    with svc.db.tx() as c:
        scope_ids = set(resolve_scope(c, scope))
        scope_desc = describe_scope(c, scope)
        query = (topic + " " + focus) if kind == "historical" else (MODES[mode]["seed_query"] + " " + focus)
        res = svc.retriever.search(c, query, scope, limit=5, min_docs=2 if multi else 1)
        hits = list(res.hits)
        titles = sorted({h["doc_title"] for h in hits})
    if not scope_ids:
        return {"status": "blocked", "message": (
            "No approved documents are in the selected scope. Approve documents in the Library "
            "(or widen the selection) before starting an exercise.")}
    if kind == "historical":
        strong = [h for h in hits if h["coverage"] >= 0.5]
        if len(strong) < 3:
            return {"status": "blocked", "message": (
                f"The selected library documents “{topic}” too thinly for a historical case "
                f"(found {len(strong)} well-matching passage(s); at least 3 are required). "
                "I will not invent details. Try a fictional scenario, or add/select more documentation.")}
        hits = strong
    if not hits:
        return {"status": "blocked", "message": (
            "I found no passages in the selected documents that relate to this exercise's concepts. "
            "The selected library does not appear to cover them. Add a focus term that appears in "
            "your texts, or select different documents.")}
    limitation = ""
    if multi and res.distinct_docs < 2 and kind != "historical":
        if not cfg.get("allow_single_source"):
            return {"status": "needs_confirmation", "message": (
                f"A multi-source exercise needs relevant passages from at least two selected "
                f"documents, but only {res.distinct_docs} ({', '.join(titles) or 'none'}) "
                "has them. I will not manufacture multi-source support. I can run a "
                "single-source exercise instead — confirm to continue."), "titles": titles}
        multi = False
        limitation = (f"Single-source exercise: only “{titles[0]}” had relevant passages in the "
                      "selected library, so no cross-text comparison is possible.")
    if res.strength == "weak":
        limitation = (limitation + " " if limitation else "") + (
            "The retrieved passages only weakly match the exercise concepts; treat the source "
            "basis with caution.")

    config = {"mode": mode, "level": level, "scenario_kind": kind, "multi_source": multi,
              "focus": focus, "historical_topic": topic}
    ex = _new_state(config, [h["id"] for h in hits])
    ex["limitation"] = limitation
    passages = [snapshot(h) for h in hits]
    blocks, report = _generate(svc, provider, ex, "open", scope, scope_ids, scope_desc, passages,
                               "Begin the exercise.", intent="exercise_open")
    if limitation:
        blocks.insert(0, app_block("Limitation: " + limitation, "limits"))
    ex["objective"] = _texts(blocks, "objective")
    ex["scenario"] = _texts(blocks, "scenario")
    ex["current_question"] = _texts(blocks, "question")
    ex["turn"] = 1
    title = f"{MODES[mode]['title']} — {level}"
    with svc.db.tx() as c:
        cid = create_conversation(c, title, "exercise", provider_kind, scope.to_dict(), ex)
        add_message(c, cid, "assistant", "", blocks=blocks, evidence=snapshots_with_cited(passages, report),
                    report=report, provider_label=provider.label, purpose="exercise_open")
        row = get_row(c, cid)
        conv = conversation_to_dict(c, row)
    conv["exercise"] = public_exercise(conv["exercise"])
    return {"status": "started", "conversation": conv}


# --------------------------------------------------------------------------- actions
def exercise_action(svc: Services, cid: str, action: str, text: str = "", confirm: bool = False) -> dict:
    text = (text or "").strip()
    with svc.db.tx() as c:
        row = get_row(c, cid)
        if row["mode"] != "exercise":
            raise AppError("This session is not an exercise.", 409)
        ex = json.loads(row["exercise"])
        scope = Scope.from_dict(json.loads(row["scope"]))
        scope_ids = set(resolve_scope(c, scope))
        scope_desc = describe_scope(c, scope)
        _, history = build_history(c, cid)
    ex["_history"] = history
    provider_kind = row["provider"]
    phase = ex["phase"]
    legal = available_actions(ex)
    if action not in ("answer", "hint", "clarify", "pause", "resume", "show_analysis", "finish"):
        raise AppError("Unknown exercise action.", 400)
    if action not in legal:
        why = {"paused": "The exercise is paused — resume it first.",
               "done": "This exercise is finished."}.get(phase, "That action is not available right now.")
        if action == "finish" and not ex["attempts"]:
            why = "Make at least one attempt first (or use Show analysis)."
        raise AppError(why, 409)

    def save_state(c):
        ex.pop("_history", None)
        update_conversation(c, cid, exercise=ex)

    # --- actions that need no model ------------------------------------------------
    if action == "pause":
        ex["resume_phase"], ex["phase"] = phase, "paused"
        blocks = [app_block("Paused. Your progress is saved in this session; resume whenever you like.")]
        return _persist_app(svc, cid, ex, blocks, "(paused the exercise)", "pause", save_state)
    if action == "resume":
        ex["phase"], ex["resume_phase"] = ex["resume_phase"] or "attempt", None
        blocks = [app_block("Welcome back. Your current question:"), app_block(ex["current_question"], "question")]
        return _persist_app(svc, cid, ex, blocks, "(resumed the exercise)", "resume", save_state)
    if action == "show_analysis" and not ex["attempts"] and not confirm:
        return {"status": "needs_confirmation", "message": (
            "You haven't made an attempt yet. Seeing the analysis first removes the chance to "
            "reason it through yourself. Show it anyway?")}
    if action in ("answer", "clarify") and not text:
        raise AppError("Write your answer first." if action == "answer" else "Write your clarifying question first.", 400)
    if len(text) > MAX_ANSWER_CHARS:
        raise AppError(f"Text is too long (max {MAX_ANSWER_CHARS} characters).", 400)

    provider = svc.make_provider(provider_kind)
    key = {"answer": f"answer:{phase}", "hint": "hint", "clarify": "clarify",
           "show_analysis": "analysis", "finish": "reflection"}[action]
    learner_text = {"answer": text, "clarify": text,
                    "hint": "I would like a hint (do not give the answer).",
                    "show_analysis": "Please show your analysis of this scenario.",
                    "finish": "I want to finish. Please write the end-of-session reflection."}[action]
    if action == "hint":
        ex["hints_used"] += 1
    with svc.db.tx() as c:
        passages = _basis_and_extra(svc, c, ex, scope, scope_ids, query=text if action in ("answer", "clarify") else None)
    blocks, report = _generate(svc, provider, ex, key, scope, scope_ids, scope_desc, passages, learner_text,
                               intent=action, user_note=(
                                   "The learner is revising after a new fact." if phase in ("revision", "review") else ""))

    # --- state transitions ---------------------------------------------------------
    if action == "answer":
        ex["attempts"].append({"n": len(ex["attempts"]) + 1, "phase": phase, "text": text})
        ex["phase"] = {"attempt": "probe", "probe": "revision", "revision": "review", "review": "review"}[phase]
        comp = _texts(blocks, "complication")
        if comp:
            ex["complication"] = comp
        q = _texts(blocks, "question")
        if q:
            ex["current_question"] = q
    elif action == "show_analysis":
        ex["analysis_shown"] = True
        ex["analysis"] = [b["text"] for b in blocks if b.get("purpose") == "analysis" and b["type"] != "withheld"]
    elif action == "finish":
        ex["phase"] = "done"
        ex["reflection"] = [b for b in blocks if b.get("purpose") == "reflection" and b["type"] != "withheld"]
    if action in ("hint", "clarify"):
        blocks.append(app_block("Your current question (unchanged):"))
        blocks.append(app_block(ex["current_question"], "question"))
    ex["turn"] += 1
    user_text = {"hint": "(asked for a hint)", "show_analysis": "(asked to see the analysis)",
                 "finish": "(finished the session)"}.get(action, text)
    user_purpose = {"answer": "attempt" if phase == "attempt" else ("revision" if phase in ("revision", "review") else "answer"),
                    }.get(action, action)
    with svc.db.tx() as c:
        add_message(c, cid, "user", user_text, purpose=user_purpose)
        add_message(c, cid, "assistant", "", blocks=blocks, evidence=snapshots_with_cited(passages, report),
                    report=report, provider_label=provider.label, purpose=f"exercise_{action}")
        save_state(c)
        conv = conversation_to_dict(c, get_row(c, cid))
    conv["exercise"] = public_exercise(conv["exercise"])
    return {"status": "ok", "conversation": conv}


def _persist_app(svc, cid, ex, blocks, user_text, purpose, save_state):
    report = {"blocks": [], "invalid_count": 0, "ok": True, "repair_attempted": False,
              "note": "App-authored message; no model call was made."}
    with svc.db.tx() as c:
        add_message(c, cid, "user", user_text, purpose=purpose)
        add_message(c, cid, "assistant", "", blocks=blocks, evidence=[], report=report,
                    provider_label="App", purpose=f"exercise_{purpose}")
        save_state(c)
        conv = conversation_to_dict(c, get_row(c, cid))
    conv["exercise"] = public_exercise(conv["exercise"])
    return {"status": "ok", "conversation": conv}
