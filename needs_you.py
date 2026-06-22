#!/usr/bin/env python3
"""
needs_you.py — generate the "Needs You" doc: one card PER PAGE, so it can be read
**deterministically** (no LLM for the page→item mapping): `format: paged` page-breaks before
each `##` section. Two kinds of card:
  - conflict QUESTIONS (questions.py): a page that got ink = that merge confirmed.
  - parked IDEAS (ideas.py): a captured bigger-picture item to flesh out; write a destination
    ("priority"/"backlog") and it graduates into the PUNCHLIST.
The page→item order (and each item's kind) is written to a sidecar so the read maps ink-on-page-N
back to the right item even as the set changes (see run._process_needs_you). Generated entirely
from the stores; source docs are untouched.
"""
from __future__ import annotations

import json

import config
import ideas
import questions

ORDER = config.state_dir() / "needs_you_order.json"   # [{kind, id}, ...] in page order
_EMPTY = ("---\nformat: notes\n---\n# Needs you\n\n"
          "Nothing needs you right now — all merges were confident and no ideas are parked.\n")


def _q_page(q: dict) -> str:
    """A conflict-question card: tick the box to confirm the merge."""
    return (f"## {q['doc_rel']}  {questions.id_token(q['id'])}\n\n"
            f"Auto-merge wasn't certain. Tick the box to confirm it, or write a correction on "
            f"this doc's own page 1.\n\n"
            f"**{q['question']}**\n\n"
            f"{questions.CONFIRM_LINE}\n\n")


def _idea_page(i: dict) -> str:
    """A parked-idea card: flesh it out, then write a destination to file it."""
    return (f"## Idea  {ideas.id_token(i['id'])}\n\n"
            f"**{i['text']}**\n\n"
            f"Flesh this out below, then write **priority** or **backlog** to file it into your "
            f"Punchlist. Leave it blank to keep it here.\n\n"
            f"_Your notes:_\n\n")


def build() -> str:
    """Write the Needs You doc (one card per page) + the page→item order sidecar. Byte-stable:
    only rewrites the file when content changed (no mirror churn)."""
    open_qs = questions.open_questions()
    open_ideas = ideas.open_ideas()
    pages = [_q_page(q) for q in open_qs] + [_idea_page(i) for i in open_ideas]
    order = ([{"kind": "q", "id": q["id"]} for q in open_qs]
             + [{"kind": "idea", "id": i["id"]} for i in open_ideas])
    text = ("---\nformat: paged\n---\n" + "".join(pages)) if pages else _EMPTY
    ORDER.write_text(json.dumps(order), encoding="utf-8")
    out = config.needs_you()
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists() or out.read_text(encoding="utf-8") != text:
        out.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    build()
