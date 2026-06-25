#!/usr/bin/env python3
"""
run.py — the one-shot "do all the due work" pass that a scheduler/heartbeat triggers.

This is the unattended check-in that deploy/entrypoint.sh sketched, finished and made safe:

  1. generate any digests due today (digest.py)
  2. mirror the whole doc tree to the device, so file edits — yours or a fresh digest's —
     show up on the Supernote, and PRUNE orphaned device files left by a renamed/moved/
     deleted source (mirror.py --prune; a pending-ink orphan aborts the prune, never the mirror)
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

import capture
import config
import ideas
import lists
import marklayer
import marks
import needs_you
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


def _is_needs_you(rel: str) -> bool:
    try:
        return rel == str(config.needs_you().relative_to(config.source_base()))
    except ValueError:
        return False


def _process_needs_you(pdf: Path, rel: str, mark: Path) -> tuple[str, str]:
    """The Needs You doc is a question dashboard, not a source doc — so we don't merge it, and we
    read it DETERMINISTICALLY (no LLM): it renders one question per page (format: paged), so a page
    that got ink = that question confirmed. marklayer gives per-page ink; needs_you.ORDER maps page
    N -> question id. Resolve the confirmed ones; unanswered pages stay open and come back next
    pass. (Free-text corrections go on the conflicted doc's own page-1 instead.)"""
    shutil.rmtree(CHECKIN, ignore_errors=True)
    if _script("marklayer.py", str(mark), "--pdf", str(pdf), "--out", str(CHECKIN)) != 0:
        return (rel, "skipped")
    order = json.loads(needs_you.ORDER.read_text()) if needs_you.ORDER.exists() else []
    stem = Path(rel).stem
    idea_map = {i["id"]: i for i in ideas.open_ideas()}
    confirmed = graduated = 0
    for idx, entry in enumerate(order):              # item idx is rendered on PDF page idx+1
        if isinstance(entry, str):                   # legacy sidecar (ids only) = all questions
            entry = {"kind": "q", "id": entry}
        if not marklayer.has_ink(CHECKIN / "ink" / f"{stem}-p{idx + 1}.png"):
            continue
        if entry["kind"] == "q":                     # a question page with ink = merge confirmed
            questions.resolve(entry["id"])
            confirmed += 1
        elif entry["kind"] == "idea":                # a fleshed-out idea = read it + maybe file it
            if _graduate_idea(stem, idx + 1, entry["id"], idea_map.get(entry["id"], {})):
                graduated += 1
    reconcile._consume_marks(rel)   # mark the Needs You annotation read + consume its export
    return (rel, f"needs-you: {confirmed} confirmed, {graduated} idea(s) filed")


def _graduate_idea(stem: str, pageno: int, iid: str, idea: dict) -> bool:
    """Read a fleshed-out idea card; if it names a destination (you wrote where it goes), file
    "<idea> — <elaboration>" (plus its sub-notes) into the `📥 From Supernote` section of the idea's
    OWN project tracker (idea['project']) and resolve it. False (stays parked) when no destination
    was written or the project has no configured tracker."""
    full = CHECKIN / f"{stem}-p{pageno}.png"
    ink = CHECKIN / "ink" / f"{stem}-p{pageno}.png"
    out = CHECKIN / f"idea_{iid}.json"
    if _script("read_idea.py", "--full", str(full), "--ink", str(ink), "--out", str(out)) != 0:
        return False
    res = json.loads(out.read_text()) if out.exists() else {}
    if not res.get("destination"):
        return False                                 # no destination written -> leave it in Needs You
    elab = (res.get("elaboration") or "").strip()
    idea_text = idea.get("text", "")
    line = f"{idea_text} — {elab}" if (idea_text and elab) else (idea_text or elab)
    target = config.capture_target_for_root(idea.get("project"))
    if line and lists.add_to_inbox(target, line, idea.get("subs", [])):
        ideas.resolve(iid)
        return True
    return False


def _is_capture(rel: str) -> bool:
    return config.capture_root_for(rel) is not None      # any project's <root>/CAPTURE.md


def _process_capture(pdf: Path, rel: str, mark: Path) -> tuple[str, str]:
    """The Capture page isn't a source doc to merge — its ink is ROUTED out. Read each
    hand-written item + its todo|idea tag (read_capture.py), then place deterministically:
    todos -> PUNCHLIST Priority (lists.py); ideas -> Needs You to flesh out (ideas.py). A todo
    that can't be placed (no punchlist / section) falls back to an idea so it's never lost. The
    page is then reset to blank so nothing accumulates."""
    shutil.rmtree(CHECKIN, ignore_errors=True)
    if _script("marklayer.py", str(mark), "--pdf", str(pdf), "--out", str(CHECKIN)) != 0:
        return (rel, "skipped")
    items_path = CHECKIN / "capture_items.json"
    if _script("read_capture.py", "--out", str(items_path)) != 0:
        return (rel, "skipped")
    items = json.loads(items_path.read_text()) if items_path.exists() else []
    root = config.capture_root_for(rel)        # which project this page belongs to
    target = config.capture_target_for_root(root)
    project = Path(rel).parent.name
    todos = ideas_n = 0
    for it in items:
        text = (it.get("text") or "").strip()
        if not text:
            continue
        subs = it.get("subs") or []            # indented sub-notes ride with their parent item
        if it.get("kind") == "todo" and lists.add_to_inbox(target, text, subs):
            todos += 1
        else:                                  # idea, or an unplaceable todo -> Needs You (never lost)
            ideas.add(text, subs, project=root)
            ideas_n += 1
    capture.reset(config.source_base() / rel)  # blank THIS page; next mirror re-renders it empty
    reconcile._consume_marks(rel)              # record the ink read + consume its export
    return (rel, f"capture[{project}]: {todos} todo(s) -> tracker, {ideas_n} idea(s) -> Needs You")


def _process_one(pdf: Path) -> tuple[str, str]:
    """Extract → read (on the subscription) → merge+apply one pending doc.
    Returns (label, status) where status is applied | conflict | skipped."""
    rel = _rel_for(pdf)
    if rel is None:
        return (pdf.name, "skipped")          # no/ambiguous manifest entry
    mark = config.mark_for(pdf)
    if _is_needs_you(rel):                     # the "Needs You" dashboard — resolve, don't merge
        return _process_needs_you(pdf, rel, mark)
    if _is_capture(rel):                       # the Capture page — route its ink out, don't merge
        return _process_capture(pdf, rel, mark)

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
    q_before = len(questions.open_questions())
    i_before = len(ideas.open_ideas())
    results = [_process_one(pdf) for pdf in _pending_all()]
    changed = (len(questions.open_questions()) < q_before        # a merge question got confirmed
               or len(ideas.open_ideas()) != i_before            # idea captured or graduated
               or any(st.startswith("capture") for _, st in results))  # Capture page was routed+reset
    if changed:
        # Needs You / Capture content changed and (unlike reconcile) those paths don't re-mirror
        # the affected docs themselves — re-mirror so the device reflects it (page-1 overlays
        # drop, new idea cards appear, the Capture page goes blank).
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

    print("\n[2/3] mirror docs -> device (+ prune orphans)")
    # --prune self-cleans device files orphaned by a renamed/moved/deleted source. Safe in
    # the unattended loop: an orphan with unread ink aborts only the prune (the mirror still
    # runs), so the heartbeat never deletes around un-applied handwriting. See mirror.py:prune.
    if _script("mirror.py", "--prune") != 0:
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
