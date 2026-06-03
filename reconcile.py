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

import config
import derive
import marks
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
    ap.add_argument("--apply", action="store_true", help="write the clean merge to the source + re-mirror")
    args = ap.parse_args()

    rel = args.source_rel
    base = BASE_DIR / rel
    src = source_path(rel)
    dev = Path(args.device) if args.device else DEVICE_DIR / rel

    for label, p in (("base", base), ("source", src), ("device", dev)):
        if not p.exists():
            sys.exit(f"missing {label}: {p}\n  (run `sync.sh mirror` for base, and write the device edit first)")

    merged, conflicts = three_way(src, base, dev)
    if conflicts == 0:
        # Derived content (self-labeled counts + Total) is recomputed from the merged
        # doc, never merged or LLM-guessed — so an ink/laptop status change keeps the
        # stats honest and the stats block stops being a conflict source. See derive.py.
        merged = derive.rederive(merged)
    print(f"3-way merge of {rel}: {'CLEAN' if conflicts == 0 else f'{conflicts} CONFLICT region(s)'}")

    if conflicts > 0:
        out = MERGE_OUT / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(merged)
        print(f"  Conflict markers written to: {out}")
        print("  Same region was edited on both the laptop and the device. Resolve the")
        print("  <<<<<<< / ||||||| (base) / ======= / >>>>>>> blocks in the SOURCE, then re-mirror.")
        return

    if not args.apply:
        print("  Clean. Re-run with --apply to write it to the source and re-mirror.")
        return

    snapshot(src, rel)
    src.write_text(merged)
    print(f"  Applied -> {src}")
    if vcs.commit_paths([src], f"supernote: apply ink edits to {rel}"):
        print(f"  committed: {rel} (revertible in the docs repo)")
    _consume_marks(rel)   # mark processed so re-mirror can refresh the PDF (un-protect it)
    subprocess.run([PY, str(HERE / "mirror.py")], check=False)
    print("  Re-mirrored (device PDF + base + manifest refreshed).")


if __name__ == "__main__":
    main()
