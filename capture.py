#!/usr/bin/env python3
"""
capture.py — the blank "Capture" page: an open surface you hand-write ideas & todos on.

Unlike a normal doc, the markdown SOURCE stays a fixed blank template — your writing lives in
the device ink layer. On check-in the ink is read and ROUTED out (clear todos -> PUNCHLIST,
bigger ideas -> Needs You to flesh out), then the page is reset to blank so nothing accumulates
(see run._process_capture — routing is brick 2/3). This module only owns the template: ensure it
exists for mirroring, and reset it after a routing pass. Byte-stable, like needs_you.build().
"""
from __future__ import annotations

import config

TEMPLATE = (
    "---\nformat: notes\n---\n# Capture\n\n"
    "Jot ideas & todos below. On the next sync, clear to-dos go to your PUNCHLIST and bigger "
    "ideas that need fleshing out go to NEEDS YOU. This page clears itself after each sync.\n"
)


def ensure() -> None:
    """Create the capture page if missing (idempotent; only writes when content differs)."""
    out = config.capture()
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists() or out.read_text(encoding="utf-8") != TEMPLATE:
        out.write_text(TEMPLATE, encoding="utf-8")


def reset() -> None:
    """Blank the capture page after its items have been routed out."""
    out = config.capture()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(TEMPLATE, encoding="utf-8")


if __name__ == "__main__":
    ensure()
