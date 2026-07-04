#!/usr/bin/env python3
"""
lists.py — deterministic insertion of items into the PUNCHLIST's sections.

Both capture destinations live in one file (config.punchlist()): the `## 🔥 Priority` and
`## 📋 Backlog` sections. Routing is code, not model: given a section name ("priority" /
"backlog") matched case-insensitively as a substring of a level-2 heading, append a
`- [ ] <text>` line at the END of that section (just before the next `##`/`---`/EOF, after
the section's existing content). Returns False if no punchlist is configured or the section
isn't found — never guesses a location.
"""
from __future__ import annotations

import re
from pathlib import Path

from notesync import config

_H2 = re.compile(r"^##\s")          # a level-2 heading (NOT ### — that's a subsection)
_HR = re.compile(r"^---\s*$")
INBOX = "## 📥 From Supernote"       # the per-project capture sink (created on demand)


def _section_bounds(lines: list[str], section: str) -> tuple[int, int] | None:
    """(heading_index, end_index) for the level-2 section whose heading contains `section`.
    end_index is the line where the section stops (next `##` / `---` / EOF)."""
    start = None
    for i, ln in enumerate(lines):
        if _H2.match(ln) and section.lower() in ln.lower():
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if _H2.match(lines[j]) or _HR.match(lines[j]):
            end = j
            break
    return start, end


def add_item(section: str, text: str, subs: list[str] | None = None) -> bool:
    """Append `- [ ] text` (plus any `subs` as indented sub-bullets) at the end of the named
    PUNCHLIST section. True on success."""
    pl = config.punchlist()
    if pl is None or not pl.exists():
        return False
    lines = pl.read_text(encoding="utf-8").splitlines()
    bounds = _section_bounds(lines, section)
    if bounds is None:
        return False
    _start, end = bounds
    insert = end
    while insert > 0 and not lines[insert - 1].strip():   # sit after the last content line
        insert -= 1
    block = [f"- [ ] {text.strip()}"]
    block += [f"  - {s.strip()}" for s in (subs or []) if s.strip()]
    if insert > 0 and lines[insert - 1].strip():          # blank line before the new item
        block = ["", *block]
    lines[insert:insert] = block
    pl.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return True


def add_to_inbox(target: Path | None, text: str, subs: list[str] | None = None) -> bool:
    """Append `- [ ] text` (+ indented subs) to the `## 📥 From Supernote` section of `target`,
    creating that section at the end of the doc if it's not there yet. Used for per-project capture
    routing (config.capture_target_for_root). True on success; False if no/absent target."""
    if target is None or not target.exists():
        return False
    text = text.strip()
    if not text:
        return False
    lines = target.read_text(encoding="utf-8").splitlines()
    block = [f"- [ ] {text}"] + [f"  - {s.strip()}" for s in (subs or []) if s.strip()]
    bounds = _section_bounds(lines, "From Supernote")
    if bounds is None:                                    # no inbox yet — start one at the end
        if lines and lines[-1].strip():
            lines.append("")
        lines += [INBOX, "", *block]
    else:
        _start, end = bounds
        insert = end
        while insert > 0 and not lines[insert - 1].strip():
            insert -= 1
        if insert > 0 and lines[insert - 1].strip():
            block = ["", *block]
        lines[insert:insert] = block
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return True
