#!/usr/bin/env python3
"""
cli.py — the ``notesync`` console entry point (the `notesync` command).

Dispatches ``notesync <command> [args]`` to the matching module's ``__main__`` in-process
(equivalent to ``python -m notesync.<module>``). The everyday loop — ``init``, ``mirror``,
``run`` — is here; the fuller command surface (``in``, ``process``, ``status``, ``out``,
``snapshot``) lives in ``sync.sh`` for source checkouts.
"""
from __future__ import annotations

import runpy
import sys

COMMANDS = {
    "init": "notesync.onboard",       # interactive config wizard
    "mirror": "notesync.mirror",      # render docs -> device PDFs
    "run": "notesync.run",            # heartbeat: digests -> mirror -> drain all pending ink
    "reconcile": "notesync.reconcile",
    "digest": "notesync.digest",
    "calibrate": "notesync.calibrate",
    "repos": "notesync.repos",
    "watch": "notesync.watch",
    "pending": "notesync.pending",
}

_USAGE = (
    "notesync <command> [args]\n\ncommands:\n  "
    + "\n  ".join(f"{c:<10} ({m})" for c, m in COMMANDS.items())
    + "\n\nStart with `notesync init`, then `notesync run`. The fuller surface "
    "(in / process /\nstatus / out / snapshot) is available from a source checkout via ./sync.sh."
)


def main() -> None:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_USAGE)
        return
    cmd, rest = argv[0], argv[1:]
    mod = COMMANDS.get(cmd)
    if mod is None:
        sys.exit(f"notesync: unknown command '{cmd}'\n\n{_USAGE}")
    sys.argv = [f"notesync {cmd}", *rest]
    runpy.run_module(mod, run_name="__main__")


if __name__ == "__main__":
    main()
