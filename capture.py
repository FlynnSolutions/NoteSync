#!/usr/bin/env python3
"""
capture.py — the blank "Capture" page: an open surface you hand-write ideas & todos on.

One per project (config.capture_pages() → `<scan_root>/CAPTURE.md`), so notes you jot stay scoped
to that project. Unlike a normal doc, the markdown SOURCE stays a fixed blank template — your
writing lives in the device ink layer. On check-in the ink is read and ROUTED out (clear todos ->
that project's tracker, bigger ideas -> the global Needs You to flesh out), then the page is reset
to blank so nothing accumulates (see run._process_capture). This module owns only the template:
ensure the pages exist for mirroring, and reset one after a routing pass. Byte-stable.
"""
from __future__ import annotations

from pathlib import Path

import config


def _template(project: str) -> str:
    return (
        f"---\nformat: notes\ndevice: true\n---\n# Capture — {project}\n\n"
        f"Jot {project} ideas & todos below. On the next sync, clear to-dos go to this project's "
        f"tracker and bigger ideas go to NEEDS YOU to flesh out. This page clears itself after "
        f"each sync.\n"
    )


def ensure() -> None:
    """Create each project's capture page if missing (idempotent; only writes when content differs)."""
    for p in config.capture_pages():
        text = _template(p.parent.name)
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists() or p.read_text(encoding="utf-8") != text:
            p.write_text(text, encoding="utf-8")


def reset(path: Path) -> None:
    """Blank one capture page after its items have been routed out."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_template(path.parent.name), encoding="utf-8")


if __name__ == "__main__":
    ensure()
