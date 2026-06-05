#!/usr/bin/env python3
"""
read_marks.py — read a doc's handwritten annotations as STRUCTURED, per-note records,
each anchored to the exact document line it targets. This is the targeting fix: rather
than reading the page holistically (which merges separate notes and snaps them to the
nearest heading), we force one record per distinct mark and make the model name its
target by QUOTING the doc line — grounded by a computed line-map (doc_lines.py) and the
registration-corrected composite (marklayer).

Per annotated page the model is given:
  * the corrected composite (ink over the page, vertically aligned) — for *where* marks sit
  * the ink-only image — ground truth of *what* was written
  * the page's line-map: every doc line with its y% (the same y-space the ink uses)
  * the handwriting profile (QUIRKS.md), incl. the marking conventions

…and must return JSON: one object per distinct note. See SYSTEM.

Usage:
    python read_marks.py PATH/TO/DOC.pdf.mark [--pdf DOC.pdf] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import backend
import config
import doc_lines
import marklayer

HERE = Path(__file__).resolve().parent
QUIRKS = HERE / "handwriting" / "QUIRKS.md"

SYSTEM = """\
You transcribe a person's handwritten annotations on a document into STRUCTURED records.
Accuracy of *targeting* (which line each note is about) matters as much as the words.

You are given, per page: the page with their ink drawn on it (aligned — a note sits on the
line it refers to), the ink-only image (exactly what they wrote), and a LINE-MAP listing every
printed line with its vertical position as `[y=NN.N%]`. The ink and the line-map share the same
y-axis, so a note centered at y≈43% targets the line-map entry nearest 43%.

HARD RULES:
1. ONE record per spatially-distinct note. NEVER merge two notes because they're near each
   other. Three short notes in one area are three records on three different lines.
2. Each note's target is the line directly under it — match by y% against the LINE-MAP and
   QUOTE that line. Do not snap to the nearest bold heading or the next paragraph.
3. Mark types:
   - "over-text": written on top of its target line (the default).
   - "bracket": a line beside several rows with NO arrowhead — targets exactly the rows it
     spans; quote the first and last.
   - "leader": a line WITH an arrowhead — targets the ONE thing at the arrowhead, which may be
     a doc line OR another of the person's notes (they chain marks). Say which.
4. "@claude" (a circled-a) marks a COMMAND to the assistant; set "command": true. A directive
   phrase without @claude ("Fix this") is still an edit but command=false.
5. Use the handwriting profile for ambiguous letters.

Output ONLY a JSON array (no prose, no code fences). Each element:
{
  "text": "<verbatim transcription>",
  "mark_type": "over-text" | "bracket" | "leader",
  "target_y": <number, the note's center as a %>,
  "target": "<the QUOTED doc line(s) it's about, or 'note: <other note text>' for a leader to another mark>",
  "command": <true|false>,
  "confidence": <0.0-1.0>
}
"""


def read_page(composite: Path, ink: Path, line_map: str, quirks: str) -> list[dict]:
    system = [
        {"type": "text", "text": SYSTEM},
        {"type": "text", "text": f"# Handwriting profile\n\n{quirks}"},
    ]
    content = [
        {"type": "text", "text": "Page with ink (aligned):"},
        {"type": "image", "path": composite},
        {"type": "text", "text": "Ink only (ground truth of the writing):"},
        {"type": "image", "path": ink},
        {"type": "text", "text": f"LINE-MAP for this page:\n{line_map}"},
        {"type": "text", "text": "Return the JSON array of notes."},
    ]
    raw = backend.read(system, content).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # be forgiving: pull the outermost [...] if the model wrapped it
        a, b = raw.find("["), raw.rfind("]")
        if a >= 0 and b > a:
            return json.loads(raw[a:b + 1])
        raise


def read_marks(mark: Path, pdf: Path) -> dict:
    quirks = QUIRKS.read_text(encoding="utf-8") if QUIRKS.exists() else "(no profile yet)"
    pages_dir = HERE / "checkin_pages"
    extracted = marklayer.extract(mark, pdf, pages_dir)   # [(pdf_page, full, ink), ...]
    result = {"doc": pdf.name, "pages": []}
    for pdf_page, full, ink in extracted:
        line_map = doc_lines.lines_block(pdf, pdf_page)
        notes = read_page(full, ink, line_map, quirks)
        result["pages"].append({"page": pdf_page, "notes": notes})
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mark", type=Path)
    ap.add_argument("--pdf", type=Path, default=None)
    ap.add_argument("--json", type=Path, default=None, help="write the structured result here")
    args = ap.parse_args()
    pdf = args.pdf or config.pdf_for(args.mark)
    if not pdf.exists():
        sys.exit(f"PDF not found: {pdf}")
    result = read_marks(args.mark, pdf)
    text = json.dumps(result, indent=2)
    if args.json:
        args.json.write_text(text, encoding="utf-8")
        print(f"wrote {args.json}")
    else:
        print(text)


if __name__ == "__main__":
    main()
