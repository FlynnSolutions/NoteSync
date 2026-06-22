#!/usr/bin/env python3
"""
read_idea.py — read ONE fleshed-out idea card from the Needs You doc.

The card shows a printed idea and asks the person to flesh it out and write a destination
("priority" / "backlog"). This reads their handwriting and returns JSON
  {"elaboration": "<their notes, minus the destination word>", "destination": "priority"|"backlog"|null}
The model reads the ink; run._process_needs_you maps the destination word -> a PUNCHLIST section
deterministically (lists.py). destination is null when they wrote no clear destination — the idea
then stays in Needs You.

Usage:  python read_idea.py --full <page.png> --ink <ink.png> --out <json>
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
You read a person's handwriting on ONE review card. The card has printed text (an idea in bold, \
and an instruction to "flesh this out … then write priority or backlog") plus the person's ink.

Read ONLY their ink (use the ink-only image as ground truth). Return a JSON object:
  {"elaboration": "<everything they wrote, as plain text, EXCEPT the destination word>",
   "destination": "priority" | "backlog" | null}

- destination = whichever of "priority" / "backlog" they wrote (case-insensitive). If they wrote \
neither, use null.
- elaboration = their fleshed-out notes with the destination word removed. If they wrote nothing \
beyond the destination word, use "".
- Ignore all printed template text. Output ONLY the JSON object — no prose, no code fences.\
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


def _parse(raw: str) -> dict:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    try:
        d = json.loads(s.strip())
    except (json.JSONDecodeError, ValueError):
        sys.exit(f"read_idea: model did not return JSON:\n{raw[:300]}")
    dest = d.get("destination")
    dest = dest.lower() if isinstance(dest, str) and dest.lower() in ("priority", "backlog") else None
    return {"elaboration": str(d.get("elaboration") or "").strip(), "destination": dest}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--full", type=Path, required=True)
    ap.add_argument("--ink", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    if config.backend() == "api":
        _load_env()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("backend is 'api' but ANTHROPIC_API_KEY not set")

    content: list[dict] = [{"type": "text", "text": "The review card — full page, then ink only:"}]
    if args.full.exists():
        content.append({"type": "image", "path": args.full})
    content.append({"type": "text", "text": "--- ink only ---"})
    content.append({"type": "image", "path": args.ink})
    content.append({"type": "text", "text": "Output the JSON object."})

    result = _parse(backend.read_text([{"type": "text", "text": SYSTEM}], content))
    args.out.write_text(json.dumps(result), encoding="utf-8")
    print(f"read_idea: destination={result['destination']} (backend: {config.backend()})")


if __name__ == "__main__":
    main()
