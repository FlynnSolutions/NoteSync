#!/usr/bin/env python3
"""
cli.py — the ``notesync`` console entry point (installed via ``pip install -e .``).

A thin wrapper that hands off to ``sync.sh``, the canonical orchestrator, so
``notesync <cmd> ...`` is exactly ``./sync.sh <cmd> ...`` (mirror, run, in, process,
reconcile, status, init, digest, calibrate, ...). Keeping one orchestrator avoids drift
between a Python CLI and the shell entry point.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    sync = Path(__file__).resolve().parent / "sync.sh"
    if not sync.exists():
        sys.exit(
            f"notesync: sync.sh not found next to the package ({sync}).\n"
            "Install from a source checkout with `pip install -e .` (editable)."
        )
    os.execvp("bash", ["bash", str(sync), *sys.argv[1:]])


if __name__ == "__main__":
    main()
