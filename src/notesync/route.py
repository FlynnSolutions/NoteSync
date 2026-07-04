#!/usr/bin/env python3
"""
route.py — map an annotated export back to its source (via the manifest) and
report whether the source moved since the PDF was rendered.

This is the conflict-detection half of the round-trip:
  - SAFE       — source unchanged since render; device marks apply directly.
  - 3-WAY MERGE — source changed on the laptop too; shows the laptop-side diff
                  (base -> current) so the merge is auditable. (Resolution is step 3.)

Usage:
    python route.py EXPORTED_FILENAME_OR_PATH
"""
from __future__ import annotations

import difflib
import hashlib
import json
import sys
from pathlib import Path

from notesync import config

HERE = Path(__file__).resolve().parent
MANIFEST = config.data_dir() / "manifest.json"
BASE_DIR = config.data_dir() / "base"


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: route.py EXPORTED_FILENAME_OR_PATH")
    if not MANIFEST.exists():
        sys.exit("No manifest.json — run `sync.sh mirror` first.")

    arg = Path(sys.argv[1])
    manifest = json.loads(MANIFEST.read_text())
    # Match by full relative path when given a Library PDF (many docs share a basename like
    # README/CLAUDE); fall back to basename only for a bare filename.
    library = config.library()
    rel = None
    if library is not None:
        try:
            rel = str(arg.relative_to(library))
        except ValueError:
            rel = None
    hits = ([e for e in manifest if e["pdf"] == rel] if rel is not None
            else [e for e in manifest if Path(e["pdf"]).stem == arg.stem])

    if not hits:
        print(f"  No manifest entry for '{arg.name}'.")
        print("  (Likely the legacy checklist or a file not produced by `mirror`.)")
        return
    if len(hits) > 1:
        print(f"  AMBIGUOUS: {len(hits)} sources share the name '{arg.name}':")
        for h in hits:
            print(f"    - {h['source_rel']}")
        print("  Disambiguate by relative path before applying.")
        return

    entry = hits[0]
    src = Path(entry["source"])
    print(f"  Source: {entry['source_rel']}")
    print(f"          {src}")

    if not src.exists():
        print("  WARNING: source file no longer exists (moved/deleted).")
        return

    current = _sha256(src)
    if current == entry["sha256"]:
        print("  Status: SAFE — source unchanged since render. Marks apply directly.")
        return

    # Source moved since render → both sides may have changed → 3-way merge territory.
    print("  Status: 3-WAY MERGE — source changed on the laptop since this PDF was rendered.")
    base_path = BASE_DIR / entry["source_rel"]
    if not base_path.exists():
        print("  (No base snapshot found — re-mirror to capture a base for clean merges.)")
        return
    base_lines = base_path.read_text(encoding="utf-8").splitlines(keepends=True)
    cur_lines = src.read_text(encoding="utf-8").splitlines(keepends=True)
    diff = list(difflib.unified_diff(base_lines, cur_lines,
                                     fromfile="base (rendered)", tofile="current (laptop)"))
    print(f"\n  Laptop-side changes since render ({len(diff)} diff lines):")
    for line in diff:
        print("    " + line.rstrip("\n"))
    print("\n  -> Reconcile device marks against CURRENT, watching these regions for collisions.")


if __name__ == "__main__":
    main()
