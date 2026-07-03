#!/usr/bin/env python3
"""
digest.py — generate configurable "daily reading" digests and write them into the doc
tree so they mirror to the device as a morning skim.

Each digest is a Markdown **recipe** (in config.digest_dir(), default <repo>/digests/).
Its frontmatter declares when it runs and what it looks at; its body is your plain-language
instructions to Claude. Example (see examples/digests/):

    ---
    days: mon-fri                       # daily | mon-fri | mon,wed,fri | mon
    sources: [MyProject/claude]       # folders whose recent activity to summarize
    review: [MyProject/deliverables/PUNCHLIST.md]   # docs to read in full + review
    out: MyProject/digests            # where the digest lands (under source_base)
    ---
    Summarize what changed, then review my punch-list and flag anything actionable.

Usage:
    python digest.py            # run every recipe whose day matches today
    python digest.py NAME       # run one recipe by name, ignoring the day filter

Activity is gathered "since the last run" of each recipe (tracked in digest_state.json;
first run looks back 7 days). The Claude call goes through backend.py — by default your
Claude subscription (no API tokens). Output mirrors to the device on the next `sync.sh
mirror` (the recipe's `out:` must be under a scan_root to reach the device).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import backend
import config
import vcs
from render import _parse_frontmatter

HERE = Path(__file__).resolve().parent
STATE = config.state_dir() / "digest_state.json"
_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

_SYSTEM = """\
You write a short personal "daily reading" digest the user skims on an e-ink tablet each \
morning. Be concise and scannable — lead with what matters, use headings and tight bullets, \
no filler. Follow the user's instructions for this digest exactly. Base it only on the \
provided context (recent activity + documents to review); don't invent. Output ONLY the \
digest markdown — no preamble, no code fences."""


# --- recipe parsing -------------------------------------------------------
def _as_list(val: str) -> list[str]:
    val = val.strip()
    if val.startswith("[") and val.endswith("]"):
        val = val[1:-1]
    return [x.strip().strip('"').strip("'") for x in val.split(",") if x.strip()]


def _runs_today(days: str, today: int) -> bool:
    days = days.strip().lower()
    if not days or days == "daily":
        return True
    if "-" in days:                                  # a range like mon-fri
        a, b = (_DAYS.index(d.strip()) for d in days.split("-", 1))
        return a <= today <= b
    return _DAYS[today] in [d.strip() for d in days.split(",")]


# --- context gathering ----------------------------------------------------
def _git_activity(folder: Path, since: datetime) -> str:
    """Recent commits + changed files touching `folder`, via its git repo (if any)."""
    root = vcs.repo_root(folder)
    if root is None:
        # Non-git: list files modified since `since`.
        changed = [str(p.relative_to(folder)) for p in folder.rglob("*")
                   if p.is_file() and datetime.fromtimestamp(p.stat().st_mtime) >= since]
        return "Changed files:\n" + "\n".join(f"- {c}" for c in sorted(changed)[:40]) if changed else ""
    rel = str(folder.relative_to(root))
    iso = since.strftime("%Y-%m-%d %H:%M:%S")

    def _git(*args: str) -> str:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
        return r.stdout.strip()

    commits = _git("log", f"--since={iso}", "--pretty=format:- %s (%cs)", "--", rel)
    files = _git("log", f"--since={iso}", "--name-only", "--pretty=format:", "--", rel)
    uniq = sorted({f for f in files.splitlines() if f.strip()})
    out = []
    if commits:
        out.append("Commits:\n" + commits)
    if uniq:
        out.append("Changed files:\n" + "\n".join(f"- {f}" for f in uniq[:40]))
    return "\n".join(out)


def _gather(recipe: dict, base: Path, since: datetime) -> str:
    parts = [f"## Recent activity (since {since.strftime('%Y-%m-%d')})"]
    for src in recipe.get("sources", []):
        folder = base / src
        if not folder.exists():
            continue
        activity = _git_activity(folder, since)
        parts.append(f"### {src}\n{activity or '(no changes)'}")
    review = recipe.get("review", [])
    if review:
        parts.append("\n## Documents to review (full content)")
        for doc in review:
            p = base / doc
            if p.exists():
                parts.append(f"### {doc}\n{p.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


# --- generation -----------------------------------------------------------
def _state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def _claude_digest(instructions: str, context: str) -> str:
    # Only load .env / the API key on the metered backend; the default subscription path
    # never touches it (so a stray key can't leak into the claude_code call).
    if config.backend() == "api":
        import read_ink
        read_ink._load_env()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("backend is 'api' but ANTHROPIC_API_KEY not set (env or "
                             "NoteSync/.env, or switch to the default claude_code backend)")
    style = f"Emoji preference: {config.emoji()}."
    user = f"{instructions}\n\n{style}\n\n--- CONTEXT ---\n{context}\n--- END CONTEXT ---\n\nWrite the digest."
    system = [{"type": "text", "text": _SYSTEM}]
    return backend.read(system, [{"type": "text", "text": user}], max_tokens=4000).strip()


def run_recipe(path: Path, base: Path, force: bool, state: dict, today: int) -> Path | None:
    """Generate one recipe's digest if it runs today (or force). Returns the output path."""
    meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
    name = path.stem
    if not force and not _runs_today(meta.get("days", "daily"), today):
        return None
    recipe = {k: _as_list(v) for k, v in meta.items() if k in ("sources", "review")}
    last = state.get(name)
    since = datetime.fromisoformat(last) if last else datetime.now() - timedelta(days=7)

    context = _gather(recipe, base, since)
    digest = _claude_digest(body.strip(), context)

    out_rel = meta.get("out", "digests")
    out_dir = base / out_rel
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}-{datetime.now():%Y-%m-%d}.md"
    out_path.write_text(digest.rstrip() + "\n", encoding="utf-8")
    state[name] = datetime.now().isoformat(timespec="seconds")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", nargs="?", help="run one recipe by name (ignores the day filter)")
    args = ap.parse_args()

    recipes_dir = config.digest_dir()
    if not recipes_dir.exists():
        raise SystemExit(f"no digest recipes in {recipes_dir} (copy one from examples/digests/)")
    base = config.source_base()
    today = datetime.now().weekday()
    state = _state()

    recipes = sorted(recipes_dir.glob("*.md"))
    if args.name:
        recipes = [r for r in recipes if r.stem == args.name] or \
            [Path(args.name)]  # allow a direct path too
    wrote = []
    for path in recipes:
        out = run_recipe(path, base, force=bool(args.name), state=state, today=today)
        if out:
            print(f"  wrote {out}")
            wrote.append(out)
    STATE.write_text(json.dumps(state, indent=2))
    if not wrote:
        print("No digests due today.")
    else:
        vcs.commit_paths(wrote, f"supernote: daily digest ({len(wrote)})")
        print(f"\n{len(wrote)} digest(s) written. Run `./sync.sh mirror` to push to the device.")


if __name__ == "__main__":
    main()
