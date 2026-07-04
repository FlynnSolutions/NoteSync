#!/usr/bin/env python3
"""
apply.py — turn read_marks's structured notes into edits on the source markdown.

Placement is DETERMINISTIC: each note carries the reader's quoted target line, so we
string-match that quote to the actual source line and insert the response right there —
no model re-find, so apply can't drift to a neighbouring line (the bug that put a
prod-items note under item-access-page). This also means apply needs no backend call: it's
instant, and the only targeting risk left is the reader's own (caught at review).

Note handling:
  * content note (command == false) -> inserted under its target line as `> 🖊️ <text>`
    (capturing the response in place). Multiple notes on one line stack in order.
  * command note (command == true, "@claude ...") -> peeled into an ACTIONS list, not a doc edit.
  * a note whose target is another note ("note: ...") or that can't be matched -> reported as
    UNPLACED for the owner to handle (never silently dropped, never force-placed).

Output is written to `device/<rel>` (input to the gated 3-way merge). apply.py does NOT touch the
source; review, then `sync.sh reconcile <rel> --apply`.

Usage:
    python apply.py PATH/TO/marks.json [--rel SRC_REL] [--actions actions.md]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from datetime import date
from pathlib import Path

from notesync import config, reconcile

HERE = Path(__file__).resolve().parent
DEVICE_DIR = config.data_dir() / "device"
MANIFEST = config.data_dir() / "manifest.json"
MATCH_THRESHOLD = 0.45   # below this, a target is treated as UNPLACED rather than mis-placed


def _source_for(doc_pdf_name: str, rel: str | None) -> tuple[str, Path]:
    if MANIFEST.exists():
        for e in json.loads(MANIFEST.read_text()):
            if rel and e["source_rel"] == rel:
                return e["source_rel"], Path(e["source"])
            if not rel and Path(e["pdf"]).name == doc_pdf_name:
                return e["source_rel"], Path(e["source"])
    if rel:
        return rel, reconcile.source_path(rel)
    sys.exit(f"could not resolve a source for {doc_pdf_name!r}; pass --rel SRC_REL")


def _norm(s: str) -> str:
    """Normalize for matching: drop markdown emphasis/syntax, lowercase, collapse whitespace."""
    s = re.sub(r"[*_`#>]", "", s)
    s = re.sub(r"\s+", " ", s.lower())
    return re.sub(r"[^a-z0-9 ]", "", s).strip()


def _clean_target(target: str) -> str:
    """Strip the reader's prefixes ('first:', 'last:', surrounding quotes) off a target quote."""
    t = target.strip()
    t = re.sub(r'^(first|last)\s*:\s*', "", t, flags=re.I)
    return t.strip().strip('"').strip()


def _match_line(target: str, norm_src: list[str]) -> int | None:
    """Index of the source line that best matches the reader's quoted target, or None."""
    nt = _norm(_clean_target(target))
    if not nt:
        return None
    best_i, best_r = None, 0.0
    for i, nl in enumerate(norm_src):
        if not nl:
            continue
        r = difflib.SequenceMatcher(None, nt, nl).ratio()
        if len(nt) >= 12 and (nt[:30] in nl or nl[:30] in nt):   # containment ⇒ strong match
            r = max(r, 0.85)
        if r > best_r:
            best_r, best_i = r, i
    return best_i if best_r >= MATCH_THRESHOLD else None


def _split(marks: dict) -> tuple[list[dict], list[dict]]:
    edits, actions = [], []
    for p in marks.get("pages", []):
        for n in p.get("notes", []):
            (actions if n.get("command") else edits).append({**n, "page": p["page"]})
    return edits, actions


def build_device_doc(marks: dict, source_md: str) -> tuple[str, list[dict], list[dict]]:
    """Return (edited_markdown, actions, unplaced)."""
    edits, actions = _split(marks)
    src_lines = source_md.splitlines()
    norm_src = [_norm(ln) for ln in src_lines]

    by_line: dict[int, list[dict]] = {}
    unplaced: list[dict] = []
    for n in edits:
        tgt = (n.get("target") or "").strip()
        idx = None if tgt.lower().startswith("note:") else _match_line(tgt, norm_src)
        if idx is None:
            unplaced.append(n)
        else:
            by_line.setdefault(idx, []).append(n)

    out: list[str] = []
    for i, line in enumerate(src_lines):
        out.append(line)
        for n in by_line.get(i, []):
            out.append(f"> 🖊️ {n.get('text', '').strip()}")
    return "\n".join(out).rstrip() + "\n", actions, unplaced


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("marks_json", type=Path)
    ap.add_argument("--rel", default=None)
    ap.add_argument("--actions", type=Path, default=None)
    args = ap.parse_args()

    marks = json.loads(args.marks_json.read_text())
    rel, src_path = _source_for(marks.get("doc", ""), args.rel)
    if not src_path.exists():
        sys.exit(f"source not found: {src_path}")

    edited, actions, unplaced = build_device_doc(marks, src_path.read_text(encoding="utf-8"))
    out = DEVICE_DIR / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(edited, encoding="utf-8")
    placed = sum(1 for p in marks.get("pages", []) for n in p.get("notes", [])
                 if not n.get("command")) - len(unplaced)
    print(f"wrote {out} — {placed} notes placed, {len(unplaced)} unplaced, {len(actions)} actions")

    # Action items = @claude commands + unplaced notes (e.g. "make this a punchlist addition").
    # These aren't document edits; route them to the personal PUNCHLIST (config, gitignored) so
    # they land in YOUR list, never in a synced/OSS doc. Append-only under a dated inbox section.
    todo = actions + unplaced
    pl = config.punchlist()
    if todo and pl is not None:
        if not pl.exists():
            sys.exit(f"punchlist configured but not found: {pl}")
        lines = [f"\n## 📥 From Supernote — {date.today().isoformat()} ({marks.get('doc','?')})\n"]
        for it in todo:
            tgt = (it.get("target") or "").strip()
            tgt = tgt[len("note:"):].strip() if tgt.lower().startswith("note:") else tgt
            ctx = f"  _(re: {tgt[:70]})_" if tgt else ""
            lines.append(f"- [ ] {it.get('text','').strip()}{ctx}")
        block = "\n".join(lines) + "\n"
        with pl.open("a", encoding="utf-8") as f:
            f.write(block)
        print(f"\nappended {len(todo)} action(s) to your punchlist ({pl}):")
        print(block)
    elif todo and args.actions:                       # fallback: local gitignored file
        args.actions.write_text("# Actions (route these — NOT document edits)\n\n"
                                + "\n".join(f"- p{a['page']}: {a.get('text','').strip()}" for a in todo) + "\n")
        print(f"\nno punchlist configured; wrote {args.actions} — {len(todo)} action(s)")
    elif todo:
        print("\nACTIONS (no punchlist configured):")
        for a in todo:
            print(f"  - p{a['page']}: {a.get('text','').strip()}")

    print(f"\nReview, then merge:  ./sync.sh reconcile {rel} --apply")


if __name__ == "__main__":
    main()
