"""Exercise mode specs. Data only; the engine in exercises.py is shared by all modes.

All scenarios are FICTIONAL and non-political. The rubric is an app-created learning
aid, not a canonical standard.
"""

RUBRIC_NOTE = ("This rubric is an app-created learning aid, not a canonical standard. "
               "Feedback is qualitative; there are no scores.")

RUBRIC = [
    ("evidence", "Evidence versus assumption"),
    ("causal", "Causal explanation"),
    ("relationships", "Relevant relationships and tensions"),
    ("alternatives", "Consideration of alternatives"),
    ("revision", "Appropriate revision after new evidence"),
    ("uncertainty", "Recognition of uncertainty"),
]

MODES = {
    "dialectical": {
        "title": "Dialectical reasoning exercise",
        "seed_query": "contradiction tension internal external conditions change development relationship aspects",
        "objective": ("Practise explaining a situation from its concrete facts: how its parts are related, how it "
                      "has changed, and what evidence supports each claim — using only concepts the selected "
                      "texts supply, attributed to their authors, not a fixed formula."),
        "guidance": ("Focus: investigate the concrete facts, relationships and history of the case. Use a concept only "
                     "in the sense the supplied passages give it, attributed to its author; if the passages do not "
                     "establish a concept, say so."),
        "scenarios": {
            "beginner": ("A small neighbourhood bakery has two teams. The bakers want a slow, careful "
                         "rise; the counter staff want fast stock for the morning queue. Last month "
                         "sales rose, and so did complaints about stale bread. The owner is pleased "
                         "about the sales and worried about the complaints."),
            "intermediate": ("A community orchestra grew from 12 to 40 players in one year. Concerts "
                             "now sell out, but section leaders say the sound has become less "
                             "coherent and several veteran players have quit. In the same year the "
                             "orchestra rented a larger rehearsal hall and changed its audition rules."),
            "advanced": ("A shared bicycle-repair co-op serves three neighbourhoods. Repair times have "
                         "doubled although volunteer hours rose. A new parts supplier is cheaper but "
                         "ships late, two founders disagree about taking paid contracts, and a "
                         "neighbourhood chapter has started its own waiting list."),
        },
        "questions": {
            "first": ("What do you think is driving what is happening here? Please separate what the "
                      "story actually tells us (observations) from what you are inferring."),
            "probe": ("You wrote: “{quote}”. What would you expect to find if your explanation were "
                      "wrong, and how could you check?"),
            "revise": ("Here is a new fact (above). In light of it, how would you revise your "
                       "original explanation — and what, if anything, stays the same?"),
        },
        "complication": ("NEW FACT (fictional): the two groups barely overlap in practice — they work "
                         "different hours, and the complaints cluster on one particular weekday."),
    },
    "belief_test": {
        "title": "Belief Test",
        "seed_query": "evidence investigation facts explanation mistake correct conclusion observation inference",
        "objective": ("Practise testing a belief: generate alternative explanations and look for "
                      "disconfirming evidence, using ideas from the selected texts."),
        "guidance": "Focus: alternative explanations and what evidence would disconfirm a belief.",
        "scenarios": {
            "beginner": ("A neighbour believes the street's new speed bump is why fewer children "
                         "play outside. She has noticed the empty street on three evenings."),
            "intermediate": ("A reading group leader believes attendance fell because the chosen "
                             "books got harder. Attendance did fall after two difficult books."),
            "advanced": ("A repair shop owner believes a new advertising flyer raised sales. Sales "
                         "rose the month after the flyer — and also after a rival shop closed for "
                         "renovations and a local fair took place."),
        },
        "questions": {
            "first": "State the belief, then list at least two other explanations that fit the same facts.",
            "probe": "You wrote: “{quote}”. What evidence would count against your preferred explanation?",
            "revise": "Given the new fact above, how does your ranking of explanations change?",
        },
        "complication": ("NEW FACT (fictional): the change began a week BEFORE the event the belief "
                         "points to."),
    },
    "main_constraint": {
        "title": "Main Constraint",
        "seed_query": "main problem constraint priority decisive contradiction conditions plan facts change",
        "objective": ("Practise naming the main constraint among competing problems and revising "
                      "that choice as information changes."),
        "guidance": "Focus: prioritization under changing information.",
        "scenarios": {
            "beginner": ("A school garden club has four problems: too few tools, a dry month, "
                         "volunteers who miss meetings, and no one to keep the records."),
            "intermediate": ("A neighbourhood tool library has a long waiting list, broken drills, "
                             "a volunteer shortage on weekends and a lease ending in four months."),
            "advanced": ("A community radio station faces a failing transmitter, falling volunteer "
                         "numbers, a sponsor pulling out, and a licence renewal due soon."),
        },
        "questions": {
            "first": "Which problem is the main constraint right now, and why that one rather than the others?",
            "probe": "You wrote: “{quote}”. What would have to change for a different problem to become the main one?",
            "revise": "With the new fact above, would you keep or change your choice of main constraint?",
        },
        "complication": ("NEW FACT (fictional): a donor offers to fund one fix, but only if it is "
                         "chosen within a week."),
    },
    "development_lab": {
        "title": "Development Lab (mentoring, teaching, delegation)",
        "seed_query": "teach learn practice criticism assess fairly delegate responsibility experience mistake comrades",
        "objective": ("Practise fictional mentoring, teaching and delegation: listening first, "
                      "asking clarifying questions, delegating clearly and assessing fairly."),
        "guidance": "Focus: listening, clarifying questions, teaching, delegation and fair assessment.",
        "scenarios": {
            "beginner": ("You coach a new volunteer who cut a delivery route short without telling "
                         "anyone. She says the route was 'obviously' too long."),
            "intermediate": ("You supervise two newcomers. One finishes tasks fast but carelessly; "
                             "the other is slow but thorough. A big task must be split between them."),
            "advanced": ("A capable, impatient team member keeps redoing others' work. You must "
                         "delegate a new responsibility to someone less experienced without "
                         "undermining either person."),
        },
        "questions": {
            "first": "Before advising anyone, what would you ask or listen for first, and why?",
            "probe": "You wrote: “{quote}”. How would you check that you understood their side fairly?",
            "revise": "Given the new fact above, how would you adjust your approach?",
        },
        "complication": ("NEW FACT (fictional): the person tells you privately that the instructions "
                         "they received were unclear and contradictory."),
    },
}

LEVELS = ["beginner", "intermediate", "advanced"]
