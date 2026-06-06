#!/usr/bin/env python3
"""
apply.py — turn read_marks's structured notes into edits on the source markdown.

This is the apply half of the round-trip, but driven by the *structured* per-note records
(text + quoted target + type) instead of a holistic re-read — so edits land on the right line.
Two kinds of note get different treatment:
  * content notes (command == false) -> applied to the document: a correction edits the target
    line; a check/strike toggles it; a comment/question/directive ("fix this", "correct") is
    inserted right under the target as a `> 🖊️ ...` blockquote so the response is captured in place.
  * command notes (command == true, i.e. "@claude ...") -> NOT doc edits. They're peeled off into
    an ACTIONS list (punchlist items, policy/mindset) for the owner to route.

Output is written to `device/<rel>` — the input to the existing 3-way merge. apply.py does NOT
touch the source; review, then run `sync.sh reconcile <rel> --apply` to merge + re-mirror.

Usage:
    python apply.py PATH/TO/marks.json [--rel SRC_REL] [--actions actions.md]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import backend
import reconcile

HERE = Path(__file__).resolve().parent
DEVICE_DIR = HERE / "device"
MANIFEST = HERE / "manifest.json"

SYSTEM = """\
You apply a person's reviewed handwritten annotations to a Markdown document. You are given the
document SOURCE and a list of ANNOTATIONS — each has the note text, the document line it targets
(quoted), and a type. Apply EACH annotation at its target:
- a correction / edit -> change the target line accordingly.
- a checkbox toggle / strike / "done" -> update that line's marker.
- a comment, question, or directive ("fix this", "correct", "lets discuss", "we should …") ->
  insert it on a new line DIRECTLY UNDER the target line as a blockquote: `> 🖊️ <note text>`.
  Keep the target line; you're annotating it, not replacing it.
- "bracket" notes apply to the whole quoted range; "leader" notes apply at their stated target.

Match each quoted target to the closest line in the SOURCE (the quote came from a render, so
markdown syntax may differ slightly). Preserve everything else BYTE-FOR-BYTE. Do NOT hand-edit
summary/aggregate counts. Output ONLY the complete edited markdown — no preamble, no fences."""


def _source_for(doc_pdf_name: str, rel: str | None) -> tuple[str, Path]:
    """Resolve (source_rel, source_path). Prefer an explicit --rel; else match the PDF name in the manifest."""
    if MANIFEST.exists():
        for e in json.loads(MANIFEST.read_text()):
            if rel and e["source_rel"] == rel:
                return e["source_rel"], Path(e["source"])
            if not rel and Path(e["pdf"]).name == doc_pdf_name:
                return e["source_rel"], Path(e["source"])
    if rel:
        return rel, reconcile.source_path(rel)
    sys.exit(f"could not resolve a source for {doc_pdf_name!r}; pass --rel SRC_REL")


def _split(marks: dict) -> tuple[list[dict], list[dict]]:
    """(content notes to apply, command notes -> actions), each tagged with its page."""
    edits, actions = [], []
    for p in marks.get("pages", []):
        for n in p.get("notes", []):
            (actions if n.get("command") else edits).append({**n, "page": p["page"]})
    return edits, actions


def build_device_doc(marks: dict, source_md: str, rel: str) -> tuple[str, list[dict]]:
    edits, actions = _split(marks)
    ann = "\n".join(
        f'- p{n["page"]} [{n.get("mark_type", "over-text")}] note: "{n.get("text", "").strip()}"'
        f'  -> target: "{(n.get("target") or "").strip()[:120]}"'
        for n in edits)
    system = [{"type": "text", "text": SYSTEM}]
    content = [
        {"type": "text", "text": f"# SOURCE ({rel})\n\n{source_md}"},
        {"type": "text", "text": f"# ANNOTATIONS to apply ({len(edits)})\n\n{ann}"},
    ]
    edited = backend.read(system, content).strip()
    if edited.startswith("```"):
        edited = edited.split("\n", 1)[1] if "\n" in edited else edited
        if edited.rstrip().endswith("```"):
            edited = edited.rstrip()[:-3]
    return edited.rstrip() + "\n", actions


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("marks_json", type=Path)
    ap.add_argument("--rel", default=None, help="source rel path (else resolved from the manifest)")
    ap.add_argument("--actions", type=Path, default=None, help="write the actions list here (md)")
    args = ap.parse_args()

    marks = json.loads(args.marks_json.read_text())
    rel, src_path = _source_for(marks.get("doc", ""), args.rel)
    if not src_path.exists():
        sys.exit(f"source not found: {src_path}")

    edited, actions = build_device_doc(marks, src_path.read_text(encoding="utf-8"), rel)
    out = DEVICE_DIR / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(edited, encoding="utf-8")
    print(f"wrote {out}")

    if actions:
        lines = ["# Actions (route these — NOT document edits)\n"]
        for a in actions:
            lines.append(f"- **p{a['page']}**: {a.get('text', '').strip()}"
                         + (f"  _(re: {(a.get('target') or '').strip()[:80]})_" if a.get("target") else ""))
        block = "\n".join(lines) + "\n"
        if args.actions:
            args.actions.write_text(block, encoding="utf-8")
            print(f"wrote {args.actions} — {len(actions)} action(s)")
        else:
            print("\n" + block)
    print(f"\nReview, then merge:  ./sync.sh reconcile {rel} --apply")


if __name__ == "__main__":
    main()
