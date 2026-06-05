#!/usr/bin/env python3
"""
mirror.py — render the document tree → PDFs into the Supernote-synced Drive folder,
preserving the SAME relative path structure as the source (so device navigation
matches the desktop). Code is never rendered. Writes a manifest mapping each PDF
back to its source (path + content hash) for deterministic trip-back routing.

    <source_base>/notes/todo.md
 -> <Drive>/Supernote/Document/Library/notes/todo.pdf

Usage:
    python mirror.py [--root <dir> ...] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

import config
import derive
import inbox
import marks
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
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            for f in filenames:
                p = Path(dirpath) / f
                if p.suffix.lower() in EXTENSIONS and not _is_noise(p):
                    found.append(p)
    return sorted(found)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", action="append", help="override SCAN_ROOTS (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="list what would render, don't write")
    ap.add_argument("--force", action="store_true",
                    help="re-render all docs even if unchanged (after a renderer change)")
    args = ap.parse_args()

    library = _gdrive_library()
    if library is None and not args.dry_run:
        sys.exit("Google Drive mount not found.")

    if not args.dry_run:
        inbox.build()   # refresh the "needs you" doc so open questions ride out with this mirror

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


if __name__ == "__main__":
    main()
