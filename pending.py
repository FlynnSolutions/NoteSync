#!/usr/bin/env python3
"""
pending.py — find docs with PENDING annotations, i.e. a `.mark` sidecar in the
Library. That's the real "what's new to process" signal (vs. "newest file in
EXPORT", which can grab a stale unrelated export).

A flattened EXPORT still gates "ready" — it's the user's explicit "I'm done,
process me" signal (so we don't read a doc mid-annotation). Its *pixels* are no
longer used, though: ink is now read straight from the `.mark` layer
(see marklayer.py), so the export can be plain black — no red setting needed.

Prints the chosen Library PDF path (the original that has the `.mark` sidecar,
newest pending with an export ready) to stdout; notes to stderr. Exits non-zero
if nothing is ready.
"""
from __future__ import annotations

import argparse
import sys

import config
import marks as marks_ledger


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true",
                    help="list ALL ready pending PDFs (one per line), not just the newest")
    args = ap.parse_args()

    library, export_dir = config.library(), config.export_dir()
    if library is None or export_dir is None:
        sys.exit("Supernote root not found (set supernote_root in config.toml or "
                 "SUPERNOTE_ROOT, or sign in to Google Drive for Desktop).")

    # Already-read marks (device re-uploads of ink we've consumed) are not pending.
    mark_files = [m for m in library.rglob("*.mark") if not marks_ledger.is_processed(m)]
    if not mark_files:
        print("No pending annotations (no unread .mark sidecars in the Library).", file=sys.stderr)
        sys.exit(2)

    ready, awaiting = [], []
    for mk in mark_files:
        pdf = config.pdf_for(mk)                     # the PDF this .mark belongs to
        export = export_dir / f"{pdf.stem}.pdf"      # flattened "export with annotations"
        (ready if export.exists() else awaiting).append((pdf, export))

    for pdf, _ in awaiting:
        print(f"  pending but no export yet (do Export-with-annotations): {pdf.name}", file=sys.stderr)

    if not ready:
        sys.exit(2)

    ready.sort(key=lambda pe: pe[1].stat().st_mtime, reverse=True)
    if args.all:
        for pdf, _ in ready:                         # newest first, one per line
            print(pdf)
        return
    if len(ready) > 1:
        print(f"{len(ready)} docs have pending annotations; processing newest: {ready[0][0].name}", file=sys.stderr)
        for pdf, _ in ready[1:]:
            print(f"  also pending: {pdf.name}", file=sys.stderr)
    print(ready[0][0])   # chosen Library PDF (has the .mark sidecar) -> stdout


if __name__ == "__main__":
    main()
