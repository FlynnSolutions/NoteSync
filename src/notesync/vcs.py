#!/usr/bin/env python3
"""
vcs.py — commit source-doc edits to the docs repo so every automated change is its own
revertible restore point. The supernote pipeline mutates source markdown in two places
(reconcile --apply writes the merged ink edits; mirror rederives stale counts); this
turns each into a `supernote:`-prefixed commit you can inspect with `git log`/`git diff`
and undo with `git revert`.

Best-effort and path-scoped: it stages and commits ONLY the given files (never sweeps in
your other uncommitted work), and is a silent no-op if the docs aren't in a git repo or
if nothing actually changed — so the pipeline runs fine with or without git.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True)


def repo_root(path: Path) -> Path | None:
    """The git repo a path lives in, or None if it isn't under version control."""
    base = path if path.is_dir() else path.parent
    r = _git(base, "rev-parse", "--show-toplevel")
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def commit_paths(paths: list[Path], message: str) -> bool:
    """Stage + commit ONLY these files in their repo. No-op (returns False) if the docs
    aren't tracked or nothing changed. Never raises — a VCS hiccup must not break a sync."""
    files = [p for p in paths if p.exists()]
    if not files:
        return False
    root = repo_root(files[0])
    if root is None:
        return False
    rels = [str(p) for p in files]
    try:
        _git(root, "add", "--", *rels)
        # Anything actually staged for these paths?
        if _git(root, "diff", "--cached", "--quiet", "--", *rels).returncode == 0:
            return False
        return _git(root, "commit", "-q", "-m", message, "--", *rels).returncode == 0
    except Exception:
        return False
