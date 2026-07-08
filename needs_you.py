#!/usr/bin/env python3
"""
needs_you.py — generate the "Needs You" doc: a count cover (page 1, glanceable from the file
thumbnail — the filename stays stable so its Supernote favorite survives), then one card PER
PAGE, so it can be read **deterministically** (no LLM for the page→item mapping): `format:
paged` page-breaks before each `##` section. Two kinds of card:
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
_EMPTY = ("---\nformat: notes\ndevice: true\n---\n# Needs you\n\n"   # device: true even when empty —
          # hiding-when-empty deleted the device PDF, which broke its Supernote favorite every cycle
          "Nothing needs you right now — all merges were confident and no ideas are parked.\n")


def _q_page(q: dict) -> str:
    """A conflict-question card: tick the box to confirm the merge."""
    return (f"## {q['doc_rel']}  {questions.id_token(q['id'])}\n\n"
            f"Auto-merge wasn't certain. Tick the box to confirm it, or write a correction on "
            f"this doc's own page 1.\n\n"
            f"**{q['question']}**\n\n"
            f"{questions.CONFIRM_LINE}\n\n")


def _idea_page(i: dict) -> str:
    """A parked-idea card: flesh it out, then write a destination to file it. Any sub-notes
    captured under the idea are shown so the context isn't lost."""
    subs = "".join(f"- {s}\n" for s in i.get("subs", []))
    proj = (i.get("project") or "").rsplit("/", 1)[-1]   # show which project it came from
    head = f"## Idea — {proj}  {ideas.id_token(i['id'])}" if proj else f"## Idea  {ideas.id_token(i['id'])}"
    return (f"{head}\n\n"
            f"**{i['text']}**\n\n"
            + (subs + "\n" if subs else "")
            + "Flesh this out below, then write a **destination** (e.g. priority / backlog) to file it "
            f"into {proj or 'the project'}'s tracker. Leave it blank to keep it here.\n\n"
            "_Your notes:_\n\n")


def _cover_page(n_qs: int, n_ideas: int) -> str:
    """Page 1: the count, big — glanceable from the file's thumbnail without opening it (the
    filename must stay stable or the device's favorite breaks, so the count lives here)."""
    n = n_qs + n_ideas
    parts = ([f"{n_qs} merge question{'s' if n_qs != 1 else ''}"] if n_qs else []) \
        + ([f"{n_ideas} parked idea{'s' if n_ideas != 1 else ''}"] if n_ideas else [])
    return (f"# {n} need{'s' if n == 1 else ''} you\n\n"
            f"{' · '.join(parts)} — one per page, starting on the next page. "
            "(Ink on this cover does nothing.)\n\n")


def build() -> str:
    """Write the Needs You doc (a count cover, then one card per page) + the page→item order
    sidecar. The cover holds a sentinel slot in the sidecar so page N ↔ order[N-1] stays exact
    (run._process_needs_you ignores non-q/idea kinds). `toc: false` because a "Jump to" block
    would share the deterministic page grid. Byte-stable: only rewrites the file when content
    changed (no mirror churn)."""
    open_qs = questions.open_questions()
    open_ideas = ideas.open_ideas()
    pages = [_q_page(q) for q in open_qs] + [_idea_page(i) for i in open_ideas]
    order = ([{"kind": "q", "id": q["id"]} for q in open_qs]
             + [{"kind": "idea", "id": i["id"]} for i in open_ideas])
    if pages:
        pages.insert(0, _cover_page(len(open_qs), len(open_ideas)))
        order.insert(0, {"kind": "cover"})
        text = "---\nformat: paged\ndevice: true\ntoc: false\n---\n" + "".join(pages)
    else:
        text = _EMPTY
    ORDER.write_text(json.dumps(order), encoding="utf-8")
    out = config.needs_you()
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists() or out.read_text(encoding="utf-8") != text:
        out.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    build()
