#!/usr/bin/env python3
"""
run.py — the one-shot "do all the due work" pass that a scheduler/heartbeat triggers.

This is the unattended check-in that deploy/entrypoint.sh sketched, finished and made safe:

  1. generate any digests due today (digest.py)
  2. mirror the whole doc tree to the device, so file edits — yours or a fresh digest's —
     show up on the Supernote (mirror.py)
  3. drain EVERY doc with a pending annotation: extract the ink, read it on your Claude
     subscription (read_ink.py via backend.py), 3-way merge, and apply (reconcile.py)

Conflicts are NOT force-applied — reconcile leaves markers and the doc stays pending for
you to resolve. Each step is best-effort and reported; one failure doesn't abort the rest.
Safe to run repeatedly: the read-once ledger (marks.py) keeps re-uploaded ink from
reprocessing, and mirror only rewrites PDFs whose bytes changed.

Usage:  python run.py [--no-digest]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import config
import marks

HERE = Path(__file__).resolve().parent
PY = sys.executable
MANIFEST = HERE / "manifest.json"
CHECKIN = HERE / "checkin_pages"


def _script(name: str, *a: str) -> int:
    """Run one of our scripts, inheriting stdout so the user sees live progress."""
    return subprocess.run([PY, str(HERE / name), *a], cwd=HERE).returncode


def _pending_all() -> list[Path]:
    r = subprocess.run([PY, str(HERE / "pending.py"), "--all"],
                       cwd=HERE, capture_output=True, text=True)
    return [Path(line) for line in r.stdout.splitlines() if line.strip()]


def _rel_for(pdf: Path) -> str | None:
    """Source rel for a Library PDF via the manifest; None if absent or ambiguous."""
    if not MANIFEST.exists():
        return None
    hits = [e for e in json.loads(MANIFEST.read_text())
            if Path(e["pdf"]).stem == pdf.stem]
    return hits[0]["source_rel"] if len(hits) == 1 else None


def _process_one(pdf: Path) -> tuple[str, str]:
    """Extract → read (on the subscription) → merge+apply one pending doc.
    Returns (label, status) where status is applied | conflict | skipped."""
    rel = _rel_for(pdf)
    if rel is None:
        return (pdf.name, "skipped")          # no/ambiguous manifest entry
    mark = config.mark_for(pdf)

    shutil.rmtree(CHECKIN, ignore_errors=True)   # isolate this doc's ink
    if _script("marklayer.py", str(mark), "--pdf", str(pdf), "--out", str(CHECKIN)) != 0:
        return (rel, "skipped")
    if _script("read_ink.py", "--rel", rel) != 0:
        return (rel, "skipped")
    _script("reconcile.py", rel, "--apply")
    # reconcile returns 0 for both clean-apply and conflict; the ledger is the truth:
    # _consume_marks records the mark ONLY on a clean apply.
    return (rel, "applied" if marks.is_processed(mark) else "conflict")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-digest", action="store_true", help="skip the digest step")
    args = ap.parse_args()

    print(f"== supernote-sync run (backend: {config.backend()}) ==")

    if not args.no_digest:
        print("\n[1/3] digests due today")
        _script("digest.py")

    print("\n[2/3] mirror docs -> device")
    if _script("mirror.py") != 0:
        print("  mirror failed (Supernote root not found?) — continuing")

    print("\n[3/3] pending annotations")
    pending = _pending_all()
    if not pending:
        print("  none pending")
        return
    print(f"  {len(pending)} doc(s) with pending ink")
    results = [_process_one(pdf) for pdf in pending]

    print("\n== summary ==")
    for label, status in results:
        print(f"  {status:>8}  {label}")
    applied = sum(1 for _, s in results if s == "applied")
    conflict = sum(1 for _, s in results if s == "conflict")
    skipped = sum(1 for _, s in results if s == "skipped")
    print(f"  applied={applied} conflict={conflict} skipped={skipped}")
    if conflict:
        print("  conflicts left markers in merge_out/ — resolve in the source, then re-run")


if __name__ == "__main__":
    main()
