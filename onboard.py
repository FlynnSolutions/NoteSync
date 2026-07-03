#!/usr/bin/env python3
"""
setup.py — interactive onboarding. Walks through config.toml + preferences with sensible
defaults and writes them, so a new user doesn't have to hand-edit TOML. Re-runnable to
update (it pre-fills the current values). Non-interactive use still works: hand-edit
config.toml, or set SUPERNOTE_* env vars (config.py's resolution order is unchanged).

    python setup.py        # or: ./sync.sh init

Accepting every default (just pressing Enter) yields a working local config.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "config.toml"
ENV = HERE / ".env"
EMOJI = ("none", "minimal", "liberal")
DENSITY = ("compact", "normal", "roomy")


def _ask(prompt: str, default: str = "") -> str:
    """Prompt with a shown default; Enter (or piped EOF) accepts the default."""
    suffix = f" [{default}]" if default else ""
    try:
        ans = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        ans = ""
    return ans or default


def _choice(prompt: str, options: tuple[str, ...], default: str) -> str:
    shown = "/".join(f"*{o}*" if o == default else o for o in options)
    while True:
        ans = _ask(f"{prompt} ({shown})", default)
        if ans in options:
            return ans
        print(f"  pick one of: {', '.join(options)}")


def _toml_list(items: list[str]) -> str:
    return "[" + ", ".join(f'"{i}"' for i in items) + "]"


def _write_config(values: dict) -> None:
    roots = _toml_list([r.strip() for r in values["scan_roots"].split(",") if r.strip()])
    CONFIG.write_text(
        "# NoteSync config (written by setup.py — edit freely; re-run `sync.sh init`).\n"
        "# Any value can be overridden by a SUPERNOTE_* env var.\n\n"
        f'source_base = "{values["source_base"]}"\n'
        f"scan_roots = {roots}\n"
        f'supernote_root = "{values["supernote_root"]}"\n'
        f'checklist = "{values["checklist"]}"\n\n'
        "[preferences]\n"
        f'emoji = "{values["emoji"]}"      # none | minimal | liberal (how Claude writes notes)\n'
        f'density = "{values["density"]}"  # compact | normal | roomy (render spacing)\n',
        encoding="utf-8",
    )


def main() -> None:
    cur = tomllib.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    prefs = cur.get("preferences", {})
    print("NoteSync setup — press Enter to accept each [default].\n")

    print("Where things live:")
    values = {
        "source_base": _ask("  Folder your notes live in", cur.get("source_base") or "~/Documents/notes"),
        "scan_roots": _ask("  Subfolders to mirror, comma-separated (blank = all)",
                           ", ".join(cur.get("scan_roots", []))),
        "supernote_root": _ask("  Supernote sync root (blank = auto-detect Google Drive)",
                               cur.get("supernote_root", "")),
        "checklist": _ask("  Optional checklist for `sync.sh out` (blank = none)",
                         cur.get("checklist", "")),
    }
    print("\nPreferences:")
    values["emoji"] = _choice("  Emoji in notes Claude writes", EMOJI, prefs.get("emoji", "minimal"))
    values["density"] = _choice("  Render spacing", DENSITY, prefs.get("density", "normal"))
    _write_config(values)
    print(f"\nWrote {CONFIG.name}")

    have_key = ENV.exists() and "ANTHROPIC_API_KEY" in ENV.read_text() and "sk-" in ENV.read_text()
    if not have_key:
        key = _ask("\nAnthropic API key for reading ink (blank to add later)")
        if key:
            with ENV.open("a", encoding="utf-8") as fh:
                fh.write(f"\nANTHROPIC_API_KEY={key}\n")
            print(f"Saved to {ENV.name}")

    print("\nFonts default to the bundled DejaVu Sans — set font_regular/bold/italic in "
          "config.toml to use your own.\nDone. Next: ./sync.sh mirror")


if __name__ == "__main__":
    main()
