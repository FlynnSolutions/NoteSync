#!/usr/bin/env python3
"""
resolve_provenance.py — the auto-resolve half of the doc-provenance loop.

check_provenance.py DETECTS drift; this REGENERATES the stale derived views. For each
derived doc whose `at:` SHA fell behind its canonical, it sends the derived body plus the
current canonical section(s) to the Claude backend, gets an updated body back, and bumps
the `at:` SHA(s) deterministically — the model interprets the content; code derives the
provenance (the model never edits the frontmatter).

Dry-run by default (prints a unified diff, writes nothing), mirroring `process … --apply`.
Pass --write to apply. This is the resolver core; the git-push trigger that runs it on the
persistent container is separate — see docs/research/doc-provenance-convention.md.

Usage:
    python docs/tools/resolve_provenance.py [ROOT]            # preview the refresh
    python docs/tools/resolve_provenance.py [ROOT] --write    # apply it
"""
from __future__ import annotations

import argparse
import difflib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for backend/config
from check_provenance import (  # noqa: E402
    _ANCHOR_COMMENT,
    _FM,
    _HEADING,
    _slugify,
    iter_findings,
)

import backend  # noqa: E402

RESOLVE_SYSTEM = (
    "You are refreshing a DERIVED documentation view whose canonical source changed. You are "
    "given the derived document's body and the CURRENT canonical section(s) it derives from. "
    "Rewrite the derived body so it accurately reflects the current canonical, while PRESERVING "
    "the derived document's structure, headings, formatting, ordering, and every link/pointer "
    "(especially `[text](path#anchor)` references — keep them exactly). Only change content that "
    "derives from the canonical; leave everything else untouched. No commentary. Output the "
    "COMPLETE updated body.")


def _split_fm(text: str) -> tuple[str | None, str]:
    m = _FM.match(text)
    return (m.group(1), text[m.end():]) if m else (None, text)


def _section(path: str, anchor: str) -> str:
    """The canonical section a pointer targets: the matching heading (or the heading under a
    `<!-- canonical: -->` comment) down to the next heading of the same/higher level. Falls
    back to the whole file when there's no anchor or no match."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    if not anchor:
        return "\n".join(lines).strip()
    a = anchor.lower()
    start, level = None, 6
    for i, ln in enumerate(lines):
        m = _HEADING.match(ln)
        if m and _slugify(m.group(2)) == a:
            start, level = i, len(m.group(1))
            break
        c = _ANCHOR_COMMENT.search(ln)
        if c and c.group(1).lower() == a:
            # the comment marks the FOLLOWING heading's section — start at that heading so
            # the body is included, not just the (invisible) comment line.
            start, level = i, 6
            for j in range(i + 1, len(lines)):
                hm = _HEADING.match(lines[j])
                if hm:
                    start, level = j, len(hm.group(1))
                    break
            break
    if start is None:
        return "\n".join(lines).strip()
    out = [lines[start]]
    for ln in lines[start + 1:]:
        hm = _HEADING.match(ln)
        if hm and len(hm.group(1)) <= level:
            break
        out.append(ln)
    return "\n".join(out).strip()


def _bump_fm(fm_text: str, new_ats: dict[str, str]) -> str:
    """Set `at:` to the current SHA for each pointer path in new_ats (matched by the preceding
    `path:` line). Provenance is code-derived, never left to the model."""
    out, cur_path = [], None
    for line in fm_text.splitlines():
        pm = re.match(r"\s*-\s*path:\s*(.+?)\s*$", line)
        if pm:
            cur_path = pm.group(1).strip().strip("\"'")
            out.append(line)
            continue
        am = re.match(r"(\s*at:\s*)(.+?)\s*$", line)
        if am and cur_path in new_ats:
            out.append(f"{am.group(1)}{new_ats[cur_path]}")
            continue
        out.append(line)
    return "\n".join(out)


def regenerate(body: str, canon_blocks: list[str]) -> str:
    """Ask the backend to rewrite the derived body from the current canonical. Injectable so
    the plumbing can be exercised without a model call."""
    system = [{"type": "text", "text": RESOLVE_SYSTEM}]
    content = [{"type": "text",
                "text": "# DERIVED BODY (update this)\n\n" + body
                        + "\n\n# CURRENT CANONICAL SOURCE(S)\n\n" + "\n\n".join(canon_blocks)}]
    return backend.read(system, content).strip() + "\n"


def resolve(root: str, write: bool = False) -> int:
    stale_by_md: dict[str, list[dict]] = {}
    for f in iter_findings(root):
        if f["status"] == "STALE":
            stale_by_md.setdefault(f["md"], []).append(f)
    if not stale_by_md:
        print("No stale derived views. Nothing to resolve.")
        return 0
    for md, finds in stale_by_md.items():
        old = Path(md).read_text(encoding="utf-8")
        fm, body = _split_fm(old)
        rel = os.path.relpath(md, root)
        if fm is None:
            print(f"skip {rel}: no frontmatter")
            continue
        blocks, new_ats = [], {}
        for f in finds:
            blocks.append(f"## Canonical: {f['path']}\n\n{_section(f['resolved'], f['anchor'])}")
            new_ats[f["path"]] = f["current"]
        new_doc = f"---\n{_bump_fm(fm, new_ats)}\n---\n\n{regenerate(body, blocks)}"
        if write:
            Path(md).write_text(new_doc, encoding="utf-8")
            print(f"WROTE  {rel}  (bumped at: -> {', '.join(sorted(set(new_ats.values())))})")
        else:
            diff = list(difflib.unified_diff(
                old.splitlines(), new_doc.splitlines(),
                fromfile=f"a/{rel}", tofile=f"b/{rel}", lineterm=""))
            print("\n".join(diff) if diff else f"(no change) {rel}")
    if not write:
        print("\nDry run — pass --write to apply.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--write", action="store_true", help="apply the regenerated docs (else preview)")
    args = ap.parse_args()
    sys.exit(resolve(args.root, args.write))


if __name__ == "__main__":
    main()
