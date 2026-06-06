#!/usr/bin/env python3
"""
synthesize.py — Pass 2: cross-page synthesis over the per-note records read_marks (Pass 1)
produced. TEXT ONLY — no images. Cross-page relationships are inherently semantic (you can't
draw a mark from one device page to another), so they live in the words; a cheap text pass sees
the whole set at once, without image tokens competing for attention.

It groups the notes into THREADS: duplicates (same point on multiple pages), themes (a topic that
spans pages), doc-wide commands/mindsets (@claude or stated policy to apply throughout), and
standalones. Every note lands in exactly one thread. This is what the apply path consumes (it
wants deduped, grouped intent — not 65 raw notes).

Usage:
    python synthesize.py PATH/TO/marks.json [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import backend

SYSTEM = """\
You are given EVERY handwritten note a person made while reviewing a multi-page document, as
text, each tagged with its page number and what it targets. Cross-page relationships here are
purely SEMANTIC — the same topic, decision, or correction recurring on different pages (marks
can't physically span pages). Organize the notes into THREADS for the document owner.

For each thread:
  - "title": short label (a few words)
  - "kind": one of
        "duplicate"   - the same point/correction made on 2+ pages
        "theme"       - related notes across pages about one topic/decision
        "doc-command" - an @claude command, OR a stated mindset/policy to apply throughout
        "standalone"  - a single note that doesn't relate to others
  - "pages": [page numbers involved]
  - "notes": [the verbatim note texts]
  - "summary": ONE sentence — the consolidated takeaway / what to do about it

Group across pages wherever notes genuinely relate; keep unrelated notes as their own standalone
threads. EVERY note must appear in exactly one thread (no dropping, no inventing).

Output ONLY JSON (no prose, no code fences):
{ "threads": [ {title, kind, pages, notes, summary}, ... ] }
"""


def _notes_text(marks: dict) -> str:
    lines = []
    for p in marks.get("pages", []):
        for n in p.get("notes", []):
            tgt = (n.get("target") or "").strip()
            cmd = " [@claude]" if n.get("command") else ""
            lines.append(f"- p{p['page']}{cmd}: \"{n.get('text', '').strip()}\""
                         + (f"   (targets: {tgt[:80]})" if tgt else ""))
    return "\n".join(lines)


def _parse(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3]
        raw = raw.strip()
    for cand in (raw, raw[raw.find("{"): raw.rfind("}") + 1] if "{" in raw and "}" in raw else ""):
        if cand:
            try:
                return json.loads(cand)
            except json.JSONDecodeError:
                continue
    raise ValueError("could not parse a JSON object from the synthesis reply")


def synthesize(marks: dict) -> dict:
    note_count = sum(len(p.get("notes", [])) for p in marks.get("pages", []))
    system = [{"type": "text", "text": SYSTEM}]
    content = [{"type": "text", "text":
                f"Document: {marks.get('doc', '?')} — {note_count} notes across "
                f"{len(marks.get('pages', []))} pages:\n\n{_notes_text(marks)}\n\n"
                "Return the JSON object of threads."}]
    raw = backend.read_text(system, content)
    try:
        out = _parse(raw)
        out.setdefault("doc", marks.get("doc"))
        return out
    except ValueError:
        return {"doc": marks.get("doc"), "error": "parse", "raw": raw[:4000], "threads": []}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("marks_json", type=Path, help="the Pass-1 read_marks output")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    marks = json.loads(args.marks_json.read_text())
    result = synthesize(marks)
    text = json.dumps(result, indent=2)
    if args.json:
        args.json.write_text(text, encoding="utf-8")
        print(f"wrote {args.json} — {len(result.get('threads', []))} threads"
              + ("  [PARSE ERROR]" if result.get("error") else ""))
    else:
        print(text)


if __name__ == "__main__":
    main()
