#!/usr/bin/env python3
"""
check_provenance.py — drift detector for the doc-provenance convention.

A derived doc declares where it came from in frontmatter:

    ---
    derived_from:
      - path: ../ops/LEARNINGS.md#auth-retry-policy
        at: 7c868f2        # the canonical's git short-SHA when last synced
    kind: consolidation
    ---

This walks a tree of Markdown, and for every `derived_from` entry checks:
  1. the canonical file resolves (broken pointer otherwise);
  2. the `#anchor`, if given, exists in the canonical (heading slug or
     `<!-- canonical: slug -->`);
  3. the recorded `at:` SHA still matches the canonical's last-touching commit
     (`git log -1 -- <file>`) — if the canonical advanced, the derived view is STALE.

Plain Git can't auto-propagate, so this only DETECTS drift and exits non-zero — wire it
into pre-commit / CI as the fast signal. (Auto-resolution is the server's job; see
docs/research/doc-provenance-convention.md.) Pure stdlib + git; no dependencies.

Usage:
    python check_provenance.py [ROOT]      # ROOT defaults to the current directory
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

_FM = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.S)
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_ANCHOR_COMMENT = re.compile(r"<!--\s*(?:canonical|anchor):\s*([A-Za-z0-9._-]+)\s*-->")
_SKIP_DIRS = {".git", "node_modules", "snapshots", ".venv", "base", "merge_out"}


def _slugify(text: str) -> str:
    """GitHub-style heading slug — must match render.py so anchors line up."""
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text).replace("*", "").replace("`", "")
    t = re.sub(r"<!--.*?-->", "", t).strip().lower()
    t = re.sub(r"[^a-z0-9\s-]", "", t)
    return re.sub(r"\s+", "-", t).strip("-")


def _frontmatter(text: str) -> str | None:
    m = _FM.match(text)
    return m.group(1) if m else None


def _parse_derived(fm: str) -> list[dict[str, str]]:
    """Pull the `derived_from:` list of {path, at} out of a frontmatter block."""
    entries: list[dict[str, str]] = []
    cur: dict[str, str] | None = None
    in_block = False
    for line in fm.splitlines():
        if re.match(r"^derived_from:\s*$", line):
            in_block = True
            continue
        if not in_block:
            continue
        if re.match(r"^\S", line):                 # dedent to a new top-level key -> done
            break
        m = re.match(r"\s*-\s*path:\s*(.+?)\s*$", line)
        if m:
            if cur:
                entries.append(cur)
            cur = {"path": m.group(1).strip().strip("\"'")}
            continue
        m = re.match(r"\s*at:\s*(.+?)\s*$", line)
        if m and cur is not None:
            cur["at"] = m.group(1).strip().strip("\"'")
    if cur:
        entries.append(cur)
    return entries


def _anchors_in(path: str) -> set[str]:
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return set()
    out: set[str] = set()
    for ln in text.splitlines():
        m = _HEADING.match(ln)
        if m:
            out.add(_slugify(m.group(2)))
        a = _ANCHOR_COMMENT.search(ln)
        if a:
            out.add(a.group(1).lower())
    return out


def _last_commit_sha(path: str) -> str | None:
    """Short SHA of the last commit that touched `path`, or None if untracked/no repo."""
    repo = os.path.dirname(path) or "."
    try:
        r = subprocess.run(
            ["git", "-C", repo, "log", "-1", "--format=%h", "--", os.path.basename(path)],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        return None
    return r.stdout.strip() or None


def _md_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".md"):
                yield os.path.join(dirpath, fn)


def check(root: str) -> int:
    problems: list[str] = []
    notes: list[str] = []
    checked = 0
    for md in _md_files(root):
        with open(md, encoding="utf-8") as fh:
            fm = _frontmatter(fh.read())
        if not fm:
            continue
        for entry in _parse_derived(fm):
            checked += 1
            rel = os.path.relpath(md, root)
            target, _, anchor = entry["path"].partition("#")
            resolved = os.path.normpath(os.path.join(os.path.dirname(md), target))
            if not os.path.exists(resolved):
                problems.append(f"BROKEN  {rel}\n        derived_from -> {entry['path']} (file not found)")
                continue
            if anchor and anchor.lower() not in _anchors_in(resolved):
                problems.append(f"ANCHOR  {rel}\n        #{anchor} not found in {target}")
            current = _last_commit_sha(resolved)
            recorded = entry.get("at")
            if current is None:
                notes.append(f"UNTRACKED  {rel} -> {target} (not in a git repo on disk; cross-repo?)")
            elif not recorded:
                notes.append(f"NO-SENTINEL  {rel} -> {target} (add `at: {current}` to detect drift)")
            elif recorded != current:
                problems.append(
                    f"STALE   {rel}\n        derived_from {target}: recorded at {recorded}, "
                    f"canonical now at {current} -> re-derive and bump `at:`")
    for n in notes:
        print(n)
    for p in problems:
        print(p)
    print(f"\nchecked {checked} derived_from pointer(s): "
          f"{len(problems)} problem(s), {len(notes)} note(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(check(sys.argv[1] if len(sys.argv) > 1 else "."))
