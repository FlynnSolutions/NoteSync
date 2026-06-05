#!/usr/bin/env python3
"""
reconcile.py — 3-way merge the device's edits into the live source doc.

Versions (see ADR-008):
  BASE   = base/<rel>            (exact bytes the device PDF was rendered from)
  SOURCE = the live source       (may have laptop edits since render)
  DEVICE = device/<rel>          (BASE + Claude's interpretation of the ink)

Uses `git merge-file` with BASE as the common ancestor: non-overlapping laptop and
device changes auto-merge; only same-region collisions become conflicts. The SAFE
case (source unchanged since render) is just a trivial sub-case — base == source, so
the merge is exactly the device edits.

Flow:
  1. sync.sh in EXPORT      -> route + SAFE/3-WAY MERGE report
  2. (Claude) read checkin_pages/ink/*.png, edit a copy of base/<rel> -> device/<rel>
  3. reconcile.py <rel> [--apply]

Usage:
    python reconcile.py SOURCE_REL [--device PATH] [--apply]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import backend
import config
import derive
import marks
import questions
import vcs

HERE = Path(__file__).resolve().parent
BASE_DIR = HERE / "base"
DEVICE_DIR = HERE / "device"
SNAP_DIR = HERE / "snapshots"
MERGE_OUT = HERE / "merge_out"
MANIFEST = HERE / "manifest.json"
PY = str(HERE / ".venv" / "bin" / "python")


def source_path(rel: str) -> Path:
    if MANIFEST.exists():
        for e in json.loads(MANIFEST.read_text()):
            if e["source_rel"] == rel:
                return Path(e["source"])
    return config.source_base() / rel


def three_way(current: Path, base: Path, other: Path) -> tuple[str, int]:
    """Return (merged_text, conflict_count). conflict_count 0 = clean."""
    res = subprocess.run(
        ["git", "merge-file", "-p", "--diff3", str(current), str(base), str(other)],
        capture_output=True, text=True,
    )
    if res.returncode >= 128 or res.returncode < 0:
        sys.exit(f"merge error: {res.stderr.strip()}")
    return res.stdout, res.returncode


def _consume_marks(rel: str) -> None:
    """Mark this annotation as read so the doc is no longer 'pending' and the next
    mirror can re-render it. We DON'T delete the `.mark` — the device would just
    re-upload it (its ink is authoritative), and deleting causes sync churn. Instead
    we log its content hash (marks.record); pending.py/mirror.py then ignore it, and
    device+Drive stay in agreement. The one-shot flattened export IS deleted (the
    device doesn't auto-recreate it). New strokes -> new hash -> doc surfaces again."""
    library, export_dir = config.library(), config.export_dir()
    if library is None or export_dir is None:
        return
    pdf_rel = Path(rel).with_suffix(".pdf")
    mark = config.mark_for(library / pdf_rel)
    export = export_dir / pdf_rel.name
    if mark.exists():
        marks.record(str(pdf_rel), mark)
        print(f"  marked read (kept on Drive): {mark.name}")
    if export.exists():
        export.unlink()
        print(f"  consumed: {export.name}")


_RESOLVE_SYSTEM = """\
You resolve a 3-way merge conflict in a Markdown document. The document is given with git
diff3 conflict markers — for each region: the LAPTOP (desktop) version is between <<<<<<< and
|||||||, the common BASE between ||||||| and =======, and the DEVICE version (the user's
latest handwritten edit) between ======= and >>>>>>>.

Resolve EVERY conflict region into the single edit the user most likely intends. Keep both
sides' independent changes where they don't truly collide; never silently drop content. The
device side is the user's newest handwriting and usually wins on the exact thing it targets.

Output the COMPLETE resolved document with every conflict marker removed — nothing else, no
code fences. Begin your output with EXACTLY ONE line, then the document on the next line:
  <!-- RESOLVE: confident -->                          when the merge is unambiguous
  <!-- RESOLVE: uncertain | <one sentence: what you did + your recommendation> -->   otherwise\
"""


def _resolve(rel: str, conflicted: str) -> tuple[str, bool, str] | None:
    """Ask Claude to resolve diff3 conflict markers (eager). Returns (resolved_doc, confident,
    note); None if the model call failed, so the caller falls back to writing markers."""
    system = [{"type": "text", "text": _RESOLVE_SYSTEM}]
    content = [{"type": "text", "text": f"Resolve the conflicts in `{rel}`:\n\n{conflicted}"}]
    try:
        out = backend.read(system, content).strip()
    except (SystemExit, Exception):
        return None
    if out.startswith("```"):                       # strip accidental code fences
        out = out.split("\n", 1)[1] if "\n" in out else out
        if out.rstrip().endswith("```"):
            out = out.rstrip()[:-3]
    out = out.lstrip()
    confident, note = True, ""
    if out.startswith("<!-- RESOLVE"):
        line, _, out = out.partition("\n")
        confident = "uncertain" not in line.lower()
        if "|" in line:
            note = line.split("|", 1)[1].replace("-->", "").strip()
    else:
        confident, note = False, "auto-merged (no confidence signal returned — please review)"
    return out.strip() + "\n", confident, note


def snapshot(src: Path, rel: str) -> None:
    dst = SNAP_DIR / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    subprocess.run(["git", "-C", str(HERE), "add", "-A", "snapshots"], check=False)
    subprocess.run(["git", "-C", str(HERE), "commit", "-q", "-m",
                    f"pre-reconcile snapshot: {rel} {time.strftime('%Y-%m-%d %H:%M')}"],
                   check=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source_rel", help="path relative to source_base, e.g. notes/todo.md")
    ap.add_argument("--device", help="ink-interpreted markdown (default: device/<rel>)")
    ap.add_argument("--apply", action="store_true",
                    help="write the merge (clean or auto-resolved) to the source + re-mirror")
    args = ap.parse_args()

    rel = args.source_rel
    base = BASE_DIR / rel
    src = source_path(rel)
    dev = Path(args.device) if args.device else DEVICE_DIR / rel

    for label, p in (("base", base), ("source", src), ("device", dev)):
        if not p.exists():
            sys.exit(f"missing {label}: {p}\n  (run `sync.sh mirror` for base, and write the device edit first)")

    prior_qs = questions.for_doc(rel)   # open questions whose page-1 answer is in this read
    merged, conflicts = three_way(src, base, dev)
    print(f"3-way merge of {rel}: {'CLEAN' if conflicts == 0 else f'{conflicts} CONFLICT region(s)'}")

    confident, note, conflict_ctx = True, "", merged   # conflict_ctx = the diff3 text (pre-resolve)
    if conflicts > 0:
        # Try to resolve it ourselves (eager). Only if the model is unavailable do we fall
        # back to the old behavior: write markers and don't apply.
        print("  attempting auto-resolution (eager) ...")
        resolved = _resolve(rel, merged)
        if resolved is None:
            out = MERGE_OUT / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(merged)
            print(f"  auto-resolution unavailable; conflict markers written to: {out}")
            print("  Resolve the <<<<<<< / ======= / >>>>>>> blocks in the SOURCE, then re-mirror.")
            return
        merged, confident, note = resolved

    # Derived content (self-labeled counts + Total) is recomputed from the merged doc, never
    # merged or LLM-guessed — so a status change stays honest and isn't a conflict source.
    merged = derive.rederive(merged)

    if not args.apply:
        if conflicts:
            print(f"  would auto-resolve ({'confident' if confident else 'UNCERTAIN: ' + note}).")
        print("  Re-run with --apply to write it to the source and re-mirror.")
        return

    snapshot(src, rel)
    src.write_text(merged)
    print(f"  Applied -> {src}")
    for q in prior_qs:                  # the user's page-1 answer addressed these -> clear them
        questions.resolve(q["id"])
    if prior_qs:
        print(f"  cleared {len(prior_qs)} answered question(s)")
    if conflicts and not confident:
        # Eager apply done, but it's still uncertain -> flag it (cleared one above may re-open
        # as a new question with fresh context; that's intended — keep asking until it's right).
        qid = questions.record(rel, note or "Please review this auto-merge.", context=conflict_ctx)
        print(f"  uncertain merge — logged question {qid} for your review: {note}")
    if vcs.commit_paths([src], f"supernote: apply ink edits to {rel}"):
        print(f"  committed: {rel} (revertible in the docs repo)")
    _consume_marks(rel)   # mark processed so re-mirror can refresh the PDF (un-protect it)
    subprocess.run([PY, str(HERE / "mirror.py")], check=False)
    print("  Re-mirrored (device PDF + base + manifest refreshed).")


if __name__ == "__main__":
    main()
