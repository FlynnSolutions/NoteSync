#!/usr/bin/env python3
"""
watch.py — auto-sync source docs to the Supernote on change, so you never have to remember
to mirror or push.

Mechanical by design: it reacts to the FILE changing on disk, no matter who edited it (you,
your editor, Claude) — nothing depends on anyone remembering to run anything. Scoped by
design: it watches EXACTLY the docs `mirror` handles (`mirror.collect(scan_roots)` under
source_base) and commits ONLY the changed files (path-scoped via vcs — never `git add -A`),
so your other repos, projects, and markdown are never touched.

On a debounced change it:
  1. mirrors the changed doc(s) -> device (instant while your laptop is on), and
  2. commits + pushes just those files so the cloud container stays current.

Usage:
    python watch.py [--interval 3] [--debounce 8] [--dry-run]

`--dry-run` prints exactly what it would sync (and touches nothing) — run it first to confirm
the scope is only the folders you mirror to the Supernote.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import config
import mirror
import vcs

HERE = Path(__file__).resolve().parent


def _snapshot() -> dict[Path, float]:
    """Each watched doc -> its mtime. The watched set IS what mirror handles, nothing else."""
    return {p: p.stat().st_mtime
            for p in mirror.collect(config.scan_roots()) if p.exists()}


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(config.source_base()))
    except ValueError:
        return str(p)


def _sync(changed: list[Path], dry_run: bool) -> None:
    print(f"change: {', '.join(_rel(p) for p in changed)}")
    if dry_run:
        print("  (dry-run) would mirror these to the device + commit/push just these files")
        return
    # 1. Mirror — incremental + deterministic, so it re-renders only what changed and pushes
    #    the new PDF straight to the device (when this laptop is on).
    subprocess.run([sys.executable, str(HERE / "mirror.py")], cwd=HERE)
    # 2. Commit only the changed source files (path-scoped) and push their repo, so the
    #    cloud container picks them up too. Grouped by repo in case roots span repos.
    by_repo: dict[Path, list[Path]] = {}
    for p in changed:
        root = vcs.repo_root(p)
        if root is not None:
            by_repo.setdefault(root, []).append(p)
    for root, files in by_repo.items():
        if vcs.commit_paths(files, f"notes: autosync ({len(files)} file(s))"):
            pushed = subprocess.run(["git", "-C", str(root), "push"],
                                    capture_output=True, text=True).returncode == 0
            print(f"  committed {len(files)} file(s) in {root.name}"
                  f"{' + pushed' if pushed else ' (push failed — will retry on next change)'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", type=float, default=3, help="seconds between scans (default 3)")
    ap.add_argument("--debounce", type=float, default=8,
                    help="seconds a file must be stable before syncing (default 8)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would sync; mirror/commit/push nothing")
    args = ap.parse_args()

    base, roots = config.source_base(), config.scan_roots()
    print(f"Watching {base} (roots: {roots or 'all'}) for .md changes. Ctrl-C to stop.")
    prev = _snapshot()
    pending: dict[Path, float] = {}    # changed file -> its latest mtime (for debounce)

    while True:
        time.sleep(args.interval)
        cur = _snapshot()
        for p, m in cur.items():
            if prev.get(p) != m:       # new or modified since last scan
                pending[p] = m
        prev = cur
        now = time.time()
        ready = [p for p, m in pending.items()
                 if now - m >= args.debounce and cur.get(p) == m]   # stable for debounce
        if ready:
            _sync(ready, args.dry_run)
            for p in ready:
                pending.pop(p, None)
            if not args.dry_run:
                prev = _snapshot()     # absorb mirror's own rederive writes (no echo loop)


if __name__ == "__main__":
    main()
