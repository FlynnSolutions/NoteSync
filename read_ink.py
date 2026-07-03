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

The model call goes through backend.py, which by default uses your Claude subscription
(`claude -p`, no API tokens). Set backend = "api" (config) to use the metered Anthropic
SDK instead, which then needs `pip install anthropic` + ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import backend
import config
import questions
import vcs

HERE = Path(__file__).resolve().parent
BASE_DIR = HERE / "base"
DEVICE_DIR = HERE / "device"
QUIRKS = HERE / "handwriting" / "QUIRKS.md"

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
- Treat EVERY mark as if it were prefixed with "@claude" — always a COMMAND to carry out, \
never content to transcribe. Do what each mark INTENDS: a check/strike means done/remove per \
context; a margin phrase means "make this change"; a directive means "do this"; new lines in a \
blank/INBOX area are new content to fold in. Do NOT transcribe the literal instruction text (or \
any "@claude" prefix) into the document, and if a mark sits in a prompt/placeholder area (e.g. a \
"(write here)" line), carry out its intent — don't leave the raw words as the answer.
- Treat the person's notes as authorial INTENT: rebuild and rewrite the sections they touch so \
the document reads as one coherent piece authored WITH those notes in mind — not a clean draft \
with handwriting spliced in beside it. A worksheet answered in the margins should come back as a \
finished document, not an annotated form.
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
- Preserve sections the notes don't touch, and NEVER drop information the person didn't ask to \
remove — but you MAY freely restructure and rewrite the sections the notes DO touch so the result \
is coherent (this is a rebuild, not a byte-for-byte splice).
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rel", required=True, help="source rel path, e.g. notes/todo.md")
    ap.add_argument("--pages", type=Path, default=HERE / "checkin_pages",
                    help="dir with rendered pages + a red/ subdir")
    ap.add_argument("--out", type=Path, default=None, help="output markdown (default: device/<rel>)")
    args = ap.parse_args()

    # Only touch .env / the API key on the metered backend — the default claude_code path
    # never loads it, so a stray key can't leak into the subscription call.
    if config.backend() == "api":
        _load_env()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("backend is 'api' but ANTHROPIC_API_KEY not set (export it, put it in "
                     "NoteSync/.env, or switch to the default claude_code backend)")

    rel = args.rel
    if Path(rel).is_absolute() or ".." in Path(rel).parts:
        sys.exit(f"unsafe rel (absolute or contains '..'): {rel}")
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
            content.append({"type": "image", "path": full})
        content.append({"type": "text", "text": f"--- {ink.stem}: ink only ---"})
        content.append({"type": "image", "path": ink})
    content.append({"type": "text", "text":
        f"Apply these annotations to the markdown source for `{rel}` and return the "
        "complete edited markdown."})

    # Stable prefix (instructions + quirks + base doc); the api backend prompt-caches it.
    system = [
        {"type": "text", "text": SYSTEM_INSTRUCTIONS},
        {"type": "text", "text": f"Style: {_EMOJI_GUIDE.get(config.emoji(), _EMOJI_GUIDE['minimal'])}"},
        {"type": "text", "text": f"# Handwriting profile for this person\n\n{quirks}"},
        {"type": "text", "text": f"# Current markdown source ({rel})\n\n{base_md}",
         "cache_control": {"type": "ephemeral"}},
    ]

    # If this doc carries a conflict question, its rendered PDF has an injected page-1 overlay
    # (NOT document content). The user's ink there is their ANSWER to a recent uncertain merge.
    open_qs = questions.for_doc(rel)
    if open_qs:
        qlist = "\n".join(f"- [{q['id']}] {q['question']}" for q in open_qs)
        system.insert(1, {"type": "text", "text":
            "CONFLICT-QUESTION OVERLAY: the FIRST page of this doc is an injected question "
            "overlay (it begins '# Needs you' and is NOT part of the document). It asks the "
            "user to clarify a recent uncertain auto-merge. Treat their handwriting on page 1 "
            "as the ANSWER: apply that clarification to the document, and do NOT transcribe the "
            "page-1 question text (or its checkbox/prompt lines) into the output. Pages 2+ are "
            "the real document — annotate them normally.\nOpen question(s):\n" + qlist})

    # Repo awareness: every mark is now an instruction (treated as `@claude`), so tell the agent
    # where this doc's repo is and let it read relevant files to carry any note out in context.
    # Only on the claude_code backend (the api backend can't read files).
    repo = vcs.repo_root(config.source_base() / rel)
    if config.backend() == "claude_code" and repo is not None:
        system.insert(1, {"type": "text", "text":
            "REPO AWARENESS: this document lives in the repository rooted at:\n"
            f"  {repo}\n"
            "To carry out any note accurately and consistently with the rest of the project, you "
            "MAY use the Read tool on other files in that repository (by absolute path under that "
            "root) — pull in context whenever a note's intent depends on information beyond this "
            "page. For a purely local mark (a check, a strike, a verbatim new line) you don't need "
            "to; just apply it. Never modify any other file; your only output is this document's "
            "edited markdown."})

    edited = backend.read(system, content).strip()
    # Strip accidental code fences if the model added them.
    if edited.startswith("```"):
        edited = edited.split("\n", 1)[1] if "\n" in edited else edited
        if edited.rstrip().endswith("```"):
            edited = edited.rstrip()[:-3]
    edited = edited.rstrip() + "\n"

    out = args.out or (DEVICE_DIR / rel)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(edited, encoding="utf-8")
    print(f"Wrote {out}  (backend: {config.backend()})")
    print(f"  next: ./sync.sh reconcile {rel} --apply")


if __name__ == "__main__":
    main()
