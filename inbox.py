#!/usr/bin/env python3
"""
inbox.py — generate the "needs you" inbox doc: every open conflict question in one place,
mirrored to the device so you can answer them. Generated entirely from questions.py (the
source docs are never touched). Regenerated on every mirror; clears itself when nothing's
open. Each question shows its `[id]` so an answer read back here maps to the right conflict
(brick 5). You can also answer on the conflicted doc's own injected page-1 (brick 4).
"""
from __future__ import annotations

import config
import questions

_FRONT = "---\nformat: notes\n---\n# Needs you\n\n"
_INTRO = ("Auto-merges that weren't certain. Under each, write your answer or correction, then "
          "export — it applies on the next sync and the question clears. (You can also answer "
          "on the first page of the doc itself.)\n")
_EMPTY = _FRONT + "Nothing needs you right now — all merges were confident.\n"


def _block(q: dict) -> str:
    return (f"\n## {q['doc_rel']}  `[{q['id']}]`\n\n"
            f"**{q['question']}**\n\n"
            f"- [ ] looks right as merged\n\n"
            f"_Your answer / correction:_\n\n\n")


def build() -> str:
    """Write the inbox doc (or an 'all clear' if no open questions). Returns its text.
    Byte-stable: only rewrites the file when the content changed, so mirror doesn't churn."""
    open_qs = questions.open_questions()
    text = (_FRONT + _INTRO + "".join(_block(q) for q in open_qs)) if open_qs else _EMPTY
    out = config.inbox()
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists() or out.read_text(encoding="utf-8") != text:
        out.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    build()
