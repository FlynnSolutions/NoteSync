#!/usr/bin/env python3
"""
read_marks.py — read a doc's handwritten annotations as STRUCTURED, per-note records, each
anchored to the exact document line it targets. Fixes annotation *targeting* (separate from
recognition): a holistic whole-page read merges distinct notes and snaps them to the nearest
heading; here we force one record per mark and make the model name its target by QUOTING the
doc line, grounded by a computed line-map (doc_lines.py) and the registration-corrected
composite (marklayer).

The ENTIRE document is read in ONE backend call — every page's corrected composite + ink +
line-map go in together, so the model has full-document context (and we pay one agent spin-up,
not one per page). Returns a JSON object keyed by page.

Per page the model gets:
  * the corrected composite (ink over the page, vertically aligned) — for *where* marks sit
  * the ink-only image — ground truth of *what* was written
  * that page's line-map: every doc line with its y% (same y-space as the ink)
…plus the handwriting profile (QUIRKS.md) once, up front.

Usage:
    python read_marks.py PATH/TO/DOC.pdf.mark [--pdf DOC.pdf] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

import backend
import config
import doc_lines
import marklayer

HERE = Path(__file__).resolve().parent
QUIRKS = HERE / "handwriting" / "QUIRKS.md"


def _aligned_ink(src: Path, dst: Path) -> Path:
    """Write a registration-corrected ink-only PNG (black-on-white). We send ONLY ink (no
    printed page) to keep the agent's per-file Read cheap, so the ink's vertical position must
    match the line-map's page-space y% — apply the same affine as the composite, white-filled."""
    scale, offset = config.mark_align()
    im = Image.open(src).convert("RGB")
    if scale != 1.0 or offset != 0.0:
        w, h = im.size
        coeffs = (1, 0, 0, 0, 1.0 / scale, -offset * h / scale)
        im = im.transform((w, h), Image.AFFINE, coeffs, resample=Image.BILINEAR,
                          fillcolor=(255, 255, 255))
    im.save(dst)
    return dst

SYSTEM = """\
You transcribe a person's handwritten annotations on a document into STRUCTURED records.
Accuracy of *targeting* (which line each note is about) matters as much as the words.

You are given the WHOLE document at once — all annotated pages together, so use full-document
context. For each page you get TWO things: the person's INK ONLY (registration-corrected,
black-on-white — exactly what they wrote, positioned where it sits on the page) and that page's
LINE-MAP — every printed line with its vertical position as `[y=NN.N%]`. You do NOT get an image
of the printed page; the LINE-MAP *is* the page's text/structure. Ink and line-map share the
same y-axis, so estimate each note's vertical center as a % from the ink image and match it to
the LINE-MAP entry nearest that % — that's its target line.

HARD RULES:
1. ONE record per spatially-distinct note. NEVER merge two notes because they're near each
   other. Three short notes in one area are three records on three different lines.
2. Each note's target is the line directly under it — match by y% against THAT page's LINE-MAP
   and QUOTE that line. Do not snap to the nearest bold heading or the next paragraph.
3. Mark types:
   - "over-text": written on top of its target line (the default).
   - "bracket": a line beside several rows with NO arrowhead — targets exactly the rows it
     spans; quote the first and last.
   - "leader": a line WITH an arrowhead — targets the ONE thing at the arrowhead, which may be
     a doc line OR another of the person's notes (they chain marks). Say which.
4. "@claude" (a circled-a) marks a COMMAND to the assistant; set "command": true. A directive
   phrase without @claude ("Fix this") is still an edit but command=false.
5. Use the handwriting profile for ambiguous letters.

Output ONLY a JSON object (no prose, no code fences):
{
  "pages": [
    { "page": <int>, "notes": [
        { "text": "<verbatim>", "mark_type": "over-text"|"bracket"|"leader",
          "target_y": <number %>, "target": "<QUOTED doc line(s), or 'note: <other note>' for a leader to another mark>",
          "command": <bool>, "confidence": <0.0-1.0> }
    ] }
  ]
}
Include every annotated page, in order, even if a page has zero notes (empty "notes").
"""


def _parse(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3]
        raw = raw.strip()
    for cand in (raw, raw[raw.find("{"): raw.rfind("}") + 1] if "{" in raw and "}" in raw else ""):
        if not cand:
            continue
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    raise ValueError("could not parse a JSON object from the model reply")


def read_doc(mark: Path, pdf: Path) -> dict:
    """Read every annotated page in ONE batched backend call; return the structured result."""
    quirks = QUIRKS.read_text(encoding="utf-8") if QUIRKS.exists() else "(no profile yet)"
    extracted = marklayer.extract(mark, pdf, HERE / "checkin_pages")   # [(page, full, ink), ...]

    system = [
        {"type": "text", "text": SYSTEM},
        {"type": "text", "text": f"# Handwriting profile\n\n{quirks}"},
    ]
    content: list[dict] = [{"type": "text", "text":
                            f"Document: {pdf.name} — {len(extracted)} annotated page(s) follow."}]
    for page, _full, ink in extracted:
        aligned = _aligned_ink(ink, ink.with_name(f"aligned-{ink.name}"))
        content.append({"type": "text", "text": f"===== PAGE {page} — ink only (corrected) ====="})
        content.append({"type": "image", "path": aligned})
        content.append({"type": "text", "text":
                        f"===== PAGE {page} — LINE-MAP =====\n{doc_lines.lines_block(pdf, page)}"})
    content.append({"type": "text", "text": "Return the JSON object for the whole document."})

    raw = backend.read_text(system, content)
    try:
        result = _parse(raw)
        result.setdefault("doc", pdf.name)
        return result
    except ValueError:
        return {"doc": pdf.name, "error": "parse", "raw": raw[:4000], "pages": []}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mark", type=Path)
    ap.add_argument("--pdf", type=Path, default=None)
    ap.add_argument("--json", type=Path, default=None, help="write the structured result here")
    args = ap.parse_args()
    pdf = args.pdf or config.pdf_for(args.mark)
    if not pdf.exists():
        sys.exit(f"PDF not found: {pdf}")
    result = read_doc(args.mark, pdf)
    text = json.dumps(result, indent=2)
    if args.json:
        args.json.write_text(text, encoding="utf-8")
        n = sum(len(p.get("notes", [])) for p in result.get("pages", []))
        print(f"wrote {args.json} — {len(result.get('pages', []))} pages, {n} notes"
              + ("  [PARSE ERROR — see 'raw']" if result.get("error") else ""))
    else:
        print(text)


if __name__ == "__main__":
    main()
