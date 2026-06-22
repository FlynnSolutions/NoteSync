#!/usr/bin/env python3
"""
needs_you.py — generate the "Needs You" doc: every open conflict question, ONE PER PAGE, so
confirmations can be read **deterministically** (no LLM): `format: paged` page-breaks before
each question, and a page that got ink = that question confirmed (see run._process_needs_you).
The page→question-id order is written to a sidecar so the read maps ink-on-page-N back to a
question even if the set changes. Generated entirely from questions.py; source docs are untouched.
"""
from __future__ import annotations

import json

import config
import questions

ORDER = config.state_dir() / "needs_you_order.json"   # [id, ...] in the order pages are rendered
_EMPTY = ("---\nformat: notes\n---\n# Needs you\n\n"
          "Nothing needs you right now — all merges were confident.\n")


def _page(q: dict) -> str:
    """One question = one page (format: paged breaks before each `##` section)."""
    return (f"## {q['doc_rel']}  {questions.id_token(q['id'])}\n\n"
            f"Auto-merge wasn't certain. Tick the box to confirm it, or write a correction on "
            f"this doc's own page 1.\n\n"
            f"**{q['question']}**\n\n"
            f"{questions.CONFIRM_LINE}\n\n")


def build() -> str:
    """Write the Needs You doc (one question per page, or an 'all clear' if none) and the page→id
    order sidecar. Byte-stable: only rewrites the file when content changed (no mirror churn)."""
    open_qs = questions.open_questions()
    text = ("---\nformat: paged\n---\n" + "".join(_page(q) for q in open_qs)) if open_qs else _EMPTY
    ORDER.write_text(json.dumps([q["id"] for q in open_qs]), encoding="utf-8")
    out = config.needs_you()
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists() or out.read_text(encoding="utf-8") != text:
        out.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    build()
