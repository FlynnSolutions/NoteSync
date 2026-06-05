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
import inbox
import marklayer
import marks
import questions
import reconcile

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
    """Source rel for a pending Library PDF via the manifest, matched by full RELATIVE PATH —
    not basename. Many docs share a name (README, CLAUDE, CHANGELOG); basename-matching marked
    those ambiguous and silently dropped them from the drain."""
    if not MANIFEST.exists():
        return None
    library = config.library()
    try:
        pdf_rel = str(pdf.relative_to(library)) if library else pdf.name
    except ValueError:
        pdf_rel = pdf.name
    for e in json.loads(MANIFEST.read_text()):
        if e["pdf"] == pdf_rel:
            return e["source_rel"]
    return None


def _is_inbox(rel: str) -> bool:
    try:
        return rel == str(config.inbox().relative_to(config.source_base()))
    except ValueError:
        return False


def _process_inbox(pdf: Path, rel: str, mark: Path) -> tuple[str, str]:
    """The inbox is a question dashboard, not a source doc — so we don't merge it, and we read
    it DETERMINISTICALLY (no LLM): it renders one question per page (format: inbox), so a page
    that got ink = that question confirmed. marklayer gives per-page ink; inbox.ORDER maps page
    N -> question id. Resolve the confirmed ones; unanswered pages stay open and come back next
    inbox. (Free-text corrections go on the conflicted doc's own page-1 instead.)"""
    shutil.rmtree(CHECKIN, ignore_errors=True)
    if _script("marklayer.py", str(mark), "--pdf", str(pdf), "--out", str(CHECKIN)) != 0:
        return (rel, "skipped")
    order = json.loads(inbox.ORDER.read_text()) if inbox.ORDER.exists() else []
    stem = Path(rel).stem
    confirmed = 0
    for i, qid in enumerate(order):                  # question i is rendered on PDF page i+1
        if marklayer.has_ink(CHECKIN / "ink" / f"{stem}-p{i + 1}.png"):
            questions.resolve(qid)
            confirmed += 1
    reconcile._consume_marks(rel)   # mark the inbox annotation read + consume its export
    return (rel, f"inbox: confirmed {confirmed}/{len(order)}")


def _process_one(pdf: Path) -> tuple[str, str]:
    """Extract → read (on the subscription) → merge+apply one pending doc.
    Returns (label, status) where status is applied | conflict | skipped."""
    rel = _rel_for(pdf)
    if rel is None:
        return (pdf.name, "skipped")          # no/ambiguous manifest entry
    mark = config.mark_for(pdf)
    if _is_inbox(rel):                         # the "needs you" dashboard — resolve, don't merge
        return _process_inbox(pdf, rel, mark)

    shutil.rmtree(CHECKIN, ignore_errors=True)   # isolate this doc's ink
    if _script("marklayer.py", str(mark), "--pdf", str(pdf), "--out", str(CHECKIN)) != 0:
        return (rel, "skipped")
    if _script("read_ink.py", "--rel", rel) != 0:
        return (rel, "skipped")
    _script("reconcile.py", rel, "--apply")
    # reconcile returns 0 for both clean-apply and conflict; the ledger is the truth:
    # _consume_marks records the mark ONLY on a clean apply.
    return (rel, "applied" if marks.is_processed(mark) else "conflict")


def drain() -> list[tuple[str, str]]:
    """Process every doc with a pending device annotation (extract -> read -> merge+apply).
    Returns [(label, status)], status in applied|conflict|skipped. Empty if nothing pending.
    Reused by the local watcher (watch.py) so device->desktop runs on the laptop too."""
    before = len(questions.open_questions())
    results = [_process_one(pdf) for pdf in _pending_all()]
    if len(questions.open_questions()) < before:
        # A question cleared this pass (e.g. an inbox confirmation, which unlike reconcile does
        # NOT re-mirror the conflicted doc) — re-mirror so its injected page-1 overlay drops.
        _script("mirror.py")
    return results


def summary(results: list[tuple[str, str]]) -> str:
    counts = {s: sum(1 for _, st in results if st == s) for s in ("applied", "conflict", "skipped")}
    return f"applied={counts['applied']} conflict={counts['conflict']} skipped={counts['skipped']}"


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
    results = drain()
    if not results:
        print("  none pending")
        return
    print("\n== summary ==")
    for label, status in results:
        print(f"  {status:>8}  {label}")
    print(f"  {summary(results)}")
    if any(s == "conflict" for _, s in results):
        print("  conflicts left markers in merge_out/ — resolve in the source, then re-run")


if __name__ == "__main__":
    main()
