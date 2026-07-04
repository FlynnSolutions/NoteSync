#!/usr/bin/env python3
"""
derive.py — recompute values that are DERIVED from the document, deterministically.

Principle: the LLM interprets (reads ink); CODE derives (counts, sums). Anything that
is a pure function of the document's own content we recompute ourselves — never an
LLM, never a merge guess. reconcile runs this as a post-merge step, so an item-status
change (from ink or from the laptop) keeps the summary counts honest with nobody hand-
counting and without the stats block ever becoming a merge conflict.

No per-document rules: a count line is its own spec. The backticked marker says what it
counts, so the same code works in any doc that uses the convention:

    - **Items shipped (`[x]`):** 24      -> count of "- [x] " items
    - **Items deferred (`[!]`):** 2      -> count of "- [!] " items
    - **Total items:** 75                -> sum of all item-checkbox lines

Only the NUMBER is rewritten; trailing prose (PR lists, descriptions) is preserved.
Authored prose lines (the "Last updated" stamp, etc.) are untouched.
"""
from __future__ import annotations

import re
from collections import Counter

# A top-level checklist item: "- [x] ...", "- [ ] ...". Sub-bullets are indented, and
# the stats lines start with "- **Items", so neither is matched here.
_ITEM = re.compile(r"^- \[(?P<marker>.)\] ")
# A self-labeling count line: "- **<label> (`[x]`):** <n><rest>". The marker it counts
# is captured from the backticks, so we never hard-code which line counts what.
_COUNT = re.compile(r"^(?P<prefix>\s*[-*]\s+\*\*.*?\(`\[(?P<marker>.)\]`\):\*\*\s*)\d+(?P<rest>.*)$")
# The total line: "- **Total items:** <n><rest>".
_TOTAL = re.compile(r"^(?P<prefix>\s*[-*]\s+\*\*Total items:\*\*\s*)\d+(?P<rest>.*)$")


def item_counts(text: str) -> Counter:
    """Tally top-level checklist items by their status marker."""
    return Counter(m["marker"] for line in text.splitlines()
                   if (m := _ITEM.match(line)))


def rederive(text: str) -> str:
    """Rewrite self-labeled count lines + the Total to match the document's own items."""
    counts = item_counts(text)
    total = sum(counts.values())
    out: list[str] = []
    for line in text.splitlines():
        if m := _COUNT.match(line):
            out.append(f"{m['prefix']}{counts.get(m['marker'], 0)}{m['rest']}")
        elif t := _TOTAL.match(line):
            out.append(f"{t['prefix']}{total}{t['rest']}")
        else:
            out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")
