#!/usr/bin/env python3
"""
repos.py — your cloud source repos at a glance, and the `DOCS_REPOS` line to paste into the
container's loop.env. Each scan_root under source_base should be a git repo WITH a remote so the
cloud can clone it; this shows which are ready (and whether they're fully pushed) vs. which still
need a remote — so the cloud never silently works on stale source. Re-run after adding a project
and DOCS_REPOS maintains itself.

  python repos.py               # status of each repo + the DOCS_REPOS line
  python repos.py --docs-repos  # just the DOCS_REPOS value (for scripting)
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from notesync import config


def _git(d: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(d), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def survey() -> list[dict]:
    """One row per scan_root: name, whether it's cloud-ready (git repo + remote), the remote
    URL, and how many local commits aren't pushed yet (the 'cloud is behind' signal)."""
    base = config.source_base()
    roots = config.scan_roots() or sorted(
        p.name for p in base.iterdir() if (p / ".git").is_dir())
    rows = []
    for name in roots:
        d = base / name
        if not (d / ".git").is_dir():
            rows.append({"name": name, "ready": False, "note": "not a git repo"})
        elif not (url := _git(d, "remote", "get-url", "origin")):
            rows.append({"name": name, "ready": False, "note": "no 'origin' remote"})
        else:
            ahead = _git(d, "rev-list", "--count", "@{u}..HEAD")  # "" if no upstream tracked
            rows.append({"name": name, "ready": True, "url": url, "ahead": ahead})
    return rows


def docs_repos(rows: list[dict]) -> str:
    return ",".join(f"{r['name']}={r['url']}" for r in rows if r["ready"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs-repos", action="store_true", help="print only the DOCS_REPOS value")
    args = ap.parse_args()

    rows = survey()
    if args.docs_repos:
        print(docs_repos(rows))
        return

    base = config.source_base()
    print("Cloud source repos (each scan_root under source_base):\n")
    for r in rows:
        name = r["name"]                  # scan_root, may be nested (e.g. Projects/Dagda)
        path = base / name                # absolute path to the repo
        if not r["ready"]:
            fix = (f"cd {path} && gh repo create {Path(name).name} "
                   "--private --source=. --remote=origin --push   # add 'ORG/' before the name for an org")
            print(f"  [needs setup] {name:<22} {r['note']}")
            print(f"                  -> {fix}")
        elif r["ahead"] == "0":
            print(f"  [ready]       {name:<22} {r['url']}  (pushed, cloud current)")
        elif r["ahead"] == "":
            print(f"  [check]       {name:<22} {r['url']}  (no upstream)")
            print(f"                  -> git -C {path} push -u origin HEAD")
        else:
            print(f"  [BEHIND]      {name:<22} {r['url']}")
            print(f"                  {r['ahead']} unpushed commit(s) — cloud is stale until you push")

    dr = docs_repos(rows)
    if dr:
        print(f"\nDOCS_REPOS for loop.env:\n\n  DOCS_REPOS={dr}")
    if any(not r["ready"] for r in rows):
        print("\nFix the [needs setup] repos above so the cloud can clone them, then re-run.")


if __name__ == "__main__":
    main()
