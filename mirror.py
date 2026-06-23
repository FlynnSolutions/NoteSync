#!/usr/bin/env python3
"""
mirror.py — render the document tree → PDFs into the Supernote-synced Drive folder,
preserving the SAME relative path structure as the source (so device navigation
matches the desktop). Code is never rendered. Writes a manifest mapping each PDF
back to its source (path + content hash) for deterministic trip-back routing.

    <source_base>/notes/todo.md
 -> <Drive>/Supernote/Document/Library/notes/todo.pdf

`--prune` self-cleans the managed library: any rendered PDF (plus its base snapshot and
consumed .mark) no longer in the freshly-written manifest is an orphan from a source
rename/delete/move and gets removed. If any orphan still carries UNPROCESSED ink (un-applied
handwriting on a doc whose source moved) the whole prune aborts untouched, so you reconcile
that ink first; `--force-prune` overrides, pruning the rest while STILL never deleting a
pending mark. Pruning only ever touches the library namespace and the tool's own base
snapshots — never the device's own Document/EXPORT/Note content.

Usage:
    python mirror.py [--root <dir> ...] [--prune | --force-prune] [--dry-run]
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

import capture
import config
import derive
import marks
import needs_you
import questions
import vcs
from render import render_bytes

# --- config ---------------------------------------------------------------
BASE = config.source_base()                      # paths are mirrored relative to here
SCAN_ROOTS = config.scan_roots()                 # which top-level dirs to mirror ([]=all)
EXTENSIONS = {".md", ".markdown"}                # doc types to render (code excluded)
EXCLUDE_DIRS = {
    ".git", "node_modules", ".venv", "venv", "dist", "build", ".next", "out",
    "coverage", "__pycache__", ".turbo", ".cache", "cdk.out", ".pytest_cache",
    "worktrees", "archive", ".github", ".claude", "packages", "site-packages",
    ".agents",
}
# Personal "don't review this on the tablet" dir patterns — fnmatch globs (e.g. '_evidence*'),
# config-driven so the repo stays de-personalized.
USER_EXCLUDE = list(config.mirror_exclude())


def _user_excluded(dirname: str) -> bool:
    return any(fnmatch.fnmatch(dirname, pat) for pat in USER_EXCLUDE)


def _is_noise(p: Path) -> bool:
    name = p.name.upper()
    if name.startswith("LICENSE") or name in {"CODE_OF_CONDUCT.MD", "CONTRIBUTING.MD"}:
        return True
    return any(part.endswith(".dist-info") for part in p.parts)
MANIFEST = Path(__file__).resolve().parent / "manifest.json"
# Exact bytes each PDF was rendered from = the merge BASE for conflict-safe check-in.
BASE_DIR = Path(__file__).resolve().parent / "base"


def _gdrive_library() -> Path | None:
    return config.library()


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def _manifest_entry(pdf_rel: Path, src: Path, rel: Path, sha: str, rendered_at: str,
                    q_fp: str = "") -> dict:
    """One manifest row: maps a rendered PDF back to its source (path + content hash). q_fp is
    a fingerprint of the doc's open conflict questions, so a question added/cleared re-renders
    the PDF (the injected page-1) even when the source itself didn't change."""
    return {"pdf": str(pdf_rel), "source": str(src), "source_rel": str(rel),
            "sha256": sha, "rendered_at": rendered_at, "q_fp": q_fp}


def _qfp(rel: Path) -> str:
    """Fingerprint of a doc's open questions (empty if none) — folded into change detection."""
    ids = sorted(q["id"] for q in questions.for_doc(str(rel)))
    return hashlib.sha256("\0".join(ids).encode()).hexdigest()[:8] if ids else ""


def _rederive_in_place(src: Path) -> bool:
    """Recompute the doc's self-labeled counts/totals from its own items and write back
    if they changed. Runs on every render — derived values are a pure function of the
    doc, so they stay honest on a plain desktop edit, not only after a device merge.
    No-op for docs without count lines. Returns True if the source was rewritten."""
    text = src.read_text(encoding="utf-8")
    new = derive.rederive(text)
    if new != text:
        src.write_text(new, encoding="utf-8")
        return True
    return False


def collect(roots: list[str]) -> list[Path]:
    # No roots configured => mirror everything under source_base.
    starts = [BASE / r for r in roots] if roots else [BASE]
    found: list[Path] = []
    for start in starts:
        if not start.exists():
            print(f"  WARN: {start} not found", file=sys.stderr)
            continue
        for dirpath, dirnames, filenames in os.walk(start):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not _user_excluded(d)]
            for f in filenames:
                p = Path(dirpath) / f
                if p.suffix.lower() in EXTENSIONS and not _is_noise(p) and not _user_excluded(f):
                    found.append(p)
    return sorted(found)


def _remove_empty_dirs(dirs: set[Path], roots: set[Path]) -> list[Path]:
    """Remove now-empty directories, climbing toward (but never removing) the roots.
    Re-checks emptiness at each step so a parent emptied by its last child also goes."""
    removed: list[Path] = []
    for start in dirs:
        d = start
        while d not in roots and d.is_dir() and not any(d.iterdir()):
            parent = d.parent
            d.rmdir()
            removed.append(d)
            d = parent
    return removed


def prune(library: Path, valid: set[str], dry_run: bool, force: bool = False) -> None:
    """Delete rendered PDFs (+ their base snapshot and already-consumed .mark) that no
    longer map to any current source doc — the orphans a source rename/delete/move leaves
    behind. ONLY touches the library namespace and the tool's own base snapshots, never the
    device's native content, and NEVER an unprocessed .mark.

    Pending ink is sacred: an orphan whose ink we haven't read is un-applied handwriting on
    a doc whose source moved. By default ANY such orphan aborts the whole prune (nothing is
    deleted) so the user reconciles first — pruning *around* it gutted the tree before, and
    Drive then swept the husk, ink and all. `force=True` (--force-prune) prunes the safe
    orphans anyway, still skipping the pending ones; pending ink is never deleted either way."""
    safe: list[tuple[str, Path, Path | None]] = []       # (rel, pdf, consumed-mark-or-None)
    pending: list[str] = []
    for pdf in sorted(library.rglob("*.pdf")):           # *.pdf.mark ends in .mark, not matched
        rel = str(pdf.relative_to(library))
        if rel in valid:
            continue
        mark = config.mark_for(pdf)
        if mark.exists() and not marks.is_processed(mark):
            pending.append(rel)
            continue
        # Orphan with no ink, or ink we've already consumed -> safe to remove.
        safe.append((rel, pdf, mark if mark.exists() else None))

    if pending and not force:
        for rel in pending:
            print(f"  PENDING INK: {rel}", file=sys.stderr)
        print(f"prune ABORTED: {len(pending)} orphan(s) carry unread handwriting — reconcile "
              f"them (./sync.sh process <rel> --apply), or re-run with --force-prune to prune "
              f"the other {len(safe)} (pending ink is never deleted either way).",
              file=sys.stderr)
        return

    pruned: list[str] = []
    touched: set[Path] = set()
    for rel, pdf, mark in safe:
        victims = [pdf]
        if mark is not None:
            victims.append(mark)                         # consumed sidecar goes with its pdf
        for suf in (".md", ".markdown"):                 # source could be either extension
            base = BASE_DIR / Path(rel).with_suffix(suf)
            if base.exists():
                victims.append(base)
        for v in victims:
            print(f"  {'would prune' if dry_run else 'pruned'}: {v}")
            touched.add(v.parent)
            if not dry_run:
                v.unlink()
        pruned.append(rel)

    removed_dirs = [] if dry_run else _remove_empty_dirs(touched, {library, BASE_DIR})
    verb = "Would prune" if dry_run else "Pruned"
    summary = f"{verb} {len(pruned)} orphan(s)"
    if pruned:
        summary += ": " + ", ".join(pruned)
    if removed_dirs:
        summary += f" [removed {len(removed_dirs)} empty dir(s)]"
    if pending:                                          # only reached under --force-prune
        summary += (f"; SKIPPED {len(pending)} with pending ink (reconcile first): "
                    + ", ".join(pending))
    print(summary)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", action="append", help="override SCAN_ROOTS (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="list what would render, don't write")
    ap.add_argument("--force", action="store_true",
                    help="re-render all docs even if unchanged (after a renderer change)")
    ap.add_argument("--prune", action="store_true",
                    help="delete orphaned device PDFs/snapshots no longer in the manifest "
                         "(left by a renamed/deleted/moved source); aborts untouched if any "
                         "orphan has unprocessed ink")
    ap.add_argument("--force-prune", action="store_true",
                    help="prune even when some orphans have unprocessed ink — those are still "
                         "never deleted, just skipped (implies --prune)")
    args = ap.parse_args()
    do_prune = args.prune or args.force_prune

    library = _gdrive_library()
    if library is None and not args.dry_run:
        sys.exit("Google Drive mount not found.")

    if not args.dry_run:
        needs_you.build()   # refresh the "Needs You" doc so open questions ride out with this mirror
        capture.ensure()    # keep the blank Capture page present so it mirrors to the device

    roots = args.root or SCAN_ROOTS
    docs = collect(roots)
    print(f"Found {len(docs)} docs under {roots}")

    # Incremental: only re-render docs whose SOURCE changed since last mirror, so
    # unchanged PDFs keep their bytes and the device doesn't re-sync the whole tree.
    prev = {}
    if MANIFEST.exists():
        prev = {e["source_rel"]: e for e in json.loads(MANIFEST.read_text())}

    manifest = []
    rederived_docs: list[Path] = []
    rendered = skipped = protected = unchanged_out = 0
    for src in docs:
        rel = src.relative_to(BASE)
        # Keep derived counts current on every render (not just on a merge) — they're a
        # pure function of the doc. Recompute + write back before hashing so the change
        # flows into the rendered PDF. No-op unless the doc has self-labeled counts.
        if not args.dry_run and _rederive_in_place(src):
            print(f"  rederived counts: {rel}")
            rederived_docs.append(src)
        pdf_rel = rel.with_suffix(".pdf")
        cur_hash = _sha256(src)
        cur_qfp = _qfp(rel)
        if args.dry_run:
            pe = prev.get(str(rel), {})
            unchanged = pe.get("sha256") == cur_hash and pe.get("q_fp", "") == cur_qfp
            print(f"  [{'unchanged' if unchanged else 'render'}] {rel}")
            continue

        dst = library / pdf_rel
        mark = config.mark_for(dst)                     # pending annotation sidecar
        entry = prev.get(str(rel))

        # Never overwrite a doc the user is mid-annotation on (unprocessed .mark).
        # An already-read mark (device re-upload of ink we've consumed) does NOT
        # protect — otherwise the doc would freeze forever. See marks.py.
        if mark.exists() and not marks.is_processed(mark):
            print(f"  PROTECTED (pending marks, not re-rendered): {rel}")
            protected += 1
            manifest.append(entry or _manifest_entry(pdf_rel, src, rel, cur_hash, "(protected)", cur_qfp))
            continue

        # Unchanged source + same question state + PDF present → skip (stops the full re-sync).
        if (entry and entry["sha256"] == cur_hash and entry.get("q_fp", "") == cur_qfp
                and dst.exists() and not args.force):
            manifest.append(entry)
            skipped += 1
            continue

        try:
            new_bytes = render_bytes(src.read_text(encoding="utf-8"), str(rel),
                                     questions=questions.for_doc(str(rel)))
            # Write the PDF ONLY if its bytes actually differ. Rendering is
            # deterministic, so an unchanged doc (even under --force) produces
            # identical bytes -> we don't touch the file -> Google Drive sees no
            # change -> the device doesn't re-download it. This is what stops the
            # full re-syncs: a renderer change re-syncs only the docs it truly alters.
            if dst.exists() and dst.read_bytes() == new_bytes:
                manifest.append(
                    _manifest_entry(pdf_rel, src, rel, cur_hash, "(unchanged-output)", cur_qfp))
                unchanged_out += 1
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(new_bytes)
            base_path = BASE_DIR / rel
            base_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, base_path)
            manifest.append(
                _manifest_entry(pdf_rel, src, rel, cur_hash, time.strftime("%Y-%m-%dT%H:%M:%S"), cur_qfp))
            rendered += 1
        except Exception as e:
            print(f"  FAIL {rel}: {e}", file=sys.stderr)

    if args.dry_run:
        if do_prune and library is not None:
            # No manifest is rewritten in dry-run, so derive the valid set from the docs
            # just collected — identical strings to what the manifest would hold.
            valid = {str(src.relative_to(BASE).with_suffix(".pdf")) for src in docs}
            prune(library, valid, dry_run=True, force=args.force_prune)
        return
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    # Commit any count-rederives as one revertible restore point in the docs repo.
    if rederived_docs:
        rels = ", ".join(str(p.relative_to(BASE)) for p in rederived_docs)
        if vcs.commit_paths(rederived_docs,
                            f"supernote: rederive counts ({len(rederived_docs)} doc(s))\n\n{rels}"):
            print(f"  committed rederived counts: {len(rederived_docs)} doc(s)")
    print(f"Rendered {rendered}, skipped {skipped} unchanged, {unchanged_out} identical-output, "
          f"protected {protected}. Manifest: {len(manifest)} entries -> {library}")

    if do_prune:
        prune(library, {e["pdf"] for e in manifest}, dry_run=False, force=args.force_prune)


if __name__ == "__main__":
    main()
