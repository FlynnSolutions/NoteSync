#!/usr/bin/env python3
"""
read_ink.py — the automated "brain": call the Claude API (vision) to read a doc's
handwritten annotations and emit the edited markdown (base + interpreted edits) for
the 3-way merge. This replaces the human-in-the-loop reading step (ADR-009).

For each page it sends BOTH the full rendered page (for layout context — which line
a mark sits on) and the ink-only page (ground-truth: only the user's ink, extracted
from the Supernote .mark layer; see marklayer.py), plus the base markdown and the
handwriting QUIRKS profile. The model returns the complete edited markdown, which we
write to device/<rel> for reconcile.py.

Stable context (QUIRKS + base doc) is prompt-cached, so re-running on the same doc
is cheap.

Usage:
    python read_ink.py --rel notes/todo.md \
        [--pages checkin_pages] [--out device/<rel>]

Requires:  pip install anthropic   and   ANTHROPIC_API_KEY (env or supernote-sync/.env)
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

import anthropic

import config

HERE = Path(__file__).resolve().parent
BASE_DIR = HERE / "base"
DEVICE_DIR = HERE / "device"
QUIRKS = HERE / "handwriting" / "QUIRKS.md"
MODEL = config.model()  # high-res vision + literal instruction-following

_EMOJI_GUIDE = {
    "none": "Do not use emoji in anything you write into the document.",
    "minimal": "Use emoji sparingly — only where it genuinely adds clarity.",
    "liberal": "Emoji are welcome where they add clarity or warmth.",
}

SYSTEM_INSTRUCTIONS = """\
You read a person's handwritten annotations on a document and apply them to the \
document's markdown source.

You are given, per page: the full rendered page (the printed document with the \
person's ink drawn on top) for context, and an ink-only version (only their \
handwriting, isolated from the printed page and rendered black-on-white) as ground \
truth for exactly what they wrote. You are also given the document's current markdown \
SOURCE and a profile of this person's handwriting quirks.

Rules:
- Only act on the handwritten ink. The printed text is the existing document, not an \
edit. In the full page, the ink is the marks drawn ON TOP of the printed document; \
the ink-only image shows exactly those marks with nothing else.
- Apply each mark faithfully: a check/strike means done/remove per context; a margin \
note is an edit or comment on that line; new lines written in a blank/INBOX area are \
new content.
- An "@claude ..." mark is a COMMAND to carry out, not content. Make the edit it \
describes, but do NOT transcribe the literal "@claude ..." text into the document — \
it is an instruction to you. If it was written into a prompt/placeholder area (e.g. \
a "(write here)" line), leave that placeholder unchanged; don't fill it with the command.
- Use the handwriting quirks profile to resolve ambiguous letters.
- When a mark points at, brackets, circles, or underlines specific content, identify \
EXACTLY what it targets — report that literally. Do not substitute the nearest \
"meaningful" text if the mark actually points at something else. If a mark targets \
text that looks garbled, clipped, or isn't present in the markdown source, say so \
plainly (it may be a rendering artifact) rather than guessing at a nearby element.
- Apply the ink to the ITEMS themselves (a status marker like [x]/[!], a note on the \
line). Do NOT hand-update summary/aggregate counts — a "Quick stats" block, or any line \
like "Items shipped (`[x]`): N" / "Total items: N". Those are recomputed from the \
document automatically after your edit; if you change them you'll just fight the merge. \
Change what the ink targets and leave the tallies alone.
- Preserve everything in the source that wasn't annotated, byte-for-byte where possible.
- If a mark is genuinely illegible, leave that part of the source unchanged and add an \
HTML comment <!-- read_ink: unsure about "<your best guess>" --> next to it.

Output ONLY the complete edited markdown document. No preamble, no code fences, no \
commentary — just the markdown.\
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


def _img_block(path: Path) -> dict:
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": data}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rel", required=True, help="source rel path, e.g. notes/todo.md")
    ap.add_argument("--pages", type=Path, default=HERE / "checkin_pages",
                    help="dir with rendered pages + a red/ subdir")
    ap.add_argument("--out", type=Path, default=None, help="output markdown (default: device/<rel>)")
    args = ap.parse_args()

    _load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY not set (export it, or put it in supernote-sync/.env)")

    rel = args.rel
    base_path = BASE_DIR / rel
    if not base_path.exists():
        sys.exit(f"no base snapshot for {rel} (run `sync.sh mirror` first): {base_path}")
    quirks = QUIRKS.read_text(encoding="utf-8") if QUIRKS.exists() else "(no profile yet)"
    base_md = base_path.read_text(encoding="utf-8")

    # Annotated pages — pair each full page with its ink-only ground-truth version.
    ink_dir = args.pages / "ink"
    ink_pages = sorted(ink_dir.glob("*.png")) if ink_dir.exists() else []
    if not ink_pages:
        sys.exit(f"no ink-only pages in {ink_dir} (run `sync.sh in` first)")

    # Build the volatile user content: per page, full (context) + ink-only (ground truth).
    content: list[dict] = [{"type": "text", "text":
        "Here are the annotated pages (full page for context, then ink-only ground truth):"}]
    for ink in ink_pages:
        full = args.pages / ink.name
        content.append({"type": "text", "text": f"--- {ink.stem}: full page ---"})
        if full.exists():
            content.append(_img_block(full))
        content.append({"type": "text", "text": f"--- {ink.stem}: ink only ---"})
        content.append(_img_block(ink))
    content.append({"type": "text", "text":
        f"Apply these annotations to the markdown source for `{rel}` and return the "
        "complete edited markdown."})

    client = anthropic.Anthropic()
    # Stable prefix (instructions + quirks + base doc) is cached; images stay volatile.
    system = [
        {"type": "text", "text": SYSTEM_INSTRUCTIONS},
        {"type": "text", "text": f"Style: {_EMOJI_GUIDE.get(config.emoji(), _EMOJI_GUIDE['minimal'])}"},
        {"type": "text", "text": f"# Handwriting profile for this person\n\n{quirks}"},
        {"type": "text", "text": f"# Current markdown source ({rel})\n\n{base_md}",
         "cache_control": {"type": "ephemeral"}},
    ]

    with client.messages.stream(
        model=MODEL,
        max_tokens=32000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=system,
        messages=[{"role": "user", "content": content}],
    ) as stream:
        msg = stream.get_final_message()

    edited = "".join(b.text for b in msg.content if b.type == "text").strip()
    # Strip accidental code fences if the model added them.
    if edited.startswith("```"):
        edited = edited.split("\n", 1)[1] if "\n" in edited else edited
        if edited.rstrip().endswith("```"):
            edited = edited.rstrip()[:-3]
    edited = edited.rstrip() + "\n"

    out = args.out or (DEVICE_DIR / rel)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(edited, encoding="utf-8")
    u = msg.usage
    print(f"Wrote {out}")
    print(f"  tokens: in={u.input_tokens} cache_read={getattr(u, 'cache_read_input_tokens', 0)} "
          f"out={u.output_tokens}")
    print(f"  next: ./sync.sh reconcile {rel} --apply")


if __name__ == "__main__":
    main()
