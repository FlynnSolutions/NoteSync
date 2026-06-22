#!/usr/bin/env python3
"""
read_capture.py — read the Capture page's handwriting into tagged items.

Transcribes each thing the person hand-wrote on the blank Capture page and tags it
`todo` (concrete, actionable, day-to-day) or `idea` (bigger-picture / needs fleshing out).
When unsure, tags `idea` — so it routes to the Needs You review queue, never silently filed.
Output is a JSON array [{"text", "kind"}] written to --out; run._process_capture routes it
deterministically (todos -> PUNCHLIST Priority, ideas -> Needs You). The model reads the ink
(its job); placement is code (lists.py / ideas.py).

Usage:  python read_capture.py --out items.json [--pages checkin_pages]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import backend
import config

HERE = Path(__file__).resolve().parent

SYSTEM = """\
You read a person's handwriting on a blank "Capture" page — a place they jot ideas and to-dos.
You are given, per page: the full page (printed template with their ink on top) for context, and \
an ink-only image (just their handwriting) as ground truth.

Transcribe each distinct item they hand-wrote. IGNORE the printed template — the "# Capture" \
heading and the instruction paragraph beneath it are not theirs; only transcribe their ink.

Classify each item:
- "todo": a concrete, actionable, day-to-day task.
- "idea": a bigger-picture or vague item that needs fleshing out before it is actionable.
If you are unsure which, use "idea".

Output ONLY a JSON array of objects: [{"text": "<verbatim item>", "kind": "todo"|"idea"}, ...].
If nothing was written, output []. No prose, no code fences — just the JSON array.\
"""


def _load_env() -> None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _parse_items(raw: str) -> list[dict]:
    """Parse the model's JSON array, tolerating accidental ``` fences."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    s = s.strip()
    try:
        data = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        sys.exit(f"read_capture: model did not return JSON:\n{raw[:300]}")
    if not isinstance(data, list):
        sys.exit(f"read_capture: expected a JSON array, got {type(data).__name__}")
    out = []
    for d in data:
        if isinstance(d, dict) and str(d.get("text", "")).strip():
            kind = d.get("kind") if d.get("kind") in ("todo", "idea") else "idea"
            out.append({"text": str(d["text"]).strip(), "kind": kind})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True, help="where to write the JSON items")
    ap.add_argument("--pages", type=Path, default=HERE / "checkin_pages")
    args = ap.parse_args()

    if config.backend() == "api":
        _load_env()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("backend is 'api' but ANTHROPIC_API_KEY not set")

    ink_dir = args.pages / "ink"
    ink_pages = sorted(ink_dir.glob("*.png")) if ink_dir.exists() else []
    if not ink_pages:
        args.out.write_text("[]", encoding="utf-8")
        print("read_capture: no ink pages — nothing to read")
        return

    content: list[dict] = [{"type": "text", "text":
        "Capture page(s) — full page for context, then ink-only ground truth:"}]
    for ink in ink_pages:
        full = args.pages / ink.name
        content.append({"type": "text", "text": f"--- {ink.stem}: full page ---"})
        if full.exists():
            content.append({"type": "image", "path": full})
        content.append({"type": "text", "text": f"--- {ink.stem}: ink only ---"})
        content.append({"type": "image", "path": ink})
    content.append({"type": "text", "text": "Output the JSON array of items."})

    items = _parse_items(backend.read_text([{"type": "text", "text": SYSTEM}], content))
    args.out.write_text(json.dumps(items), encoding="utf-8")
    print(f"read_capture: {len(items)} item(s) (backend: {config.backend()})")


if __name__ == "__main__":
    main()
