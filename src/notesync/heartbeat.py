#!/usr/bin/env python3
"""
heartbeat.py — laptop-liveness coordination for the hybrid (local-first + cloud standby).

The laptop and the cloud box have no direct link, so they coordinate through the one place
both see: the Supernote Google Drive folder. The laptop's watcher writes a timestamp to a
hidden `.laptop-alive` file there (the laptop via Drive-for-Desktop, the cloud reads it via
its rclone mount). The cloud standby checks it each tick and STANDS DOWN while the laptop is
alive — it only works once the heartbeat goes stale (laptop off). Fail-safe: a crashed laptop
just stops writing, the file stales, and the cloud takes over.

  python heartbeat.py write          # laptop: record "I'm alive now"
  python heartbeat.py alive [SECS]    # cloud: exit 0 if the laptop wrote within SECS (default 300)
"""
from __future__ import annotations

import contextlib
import sys
import time
from pathlib import Path

from notesync import config

# The laptop writes ~every 60s; "alive" if seen within 5 min — slack absorbs Drive sync lag
# (rclone dir-cache + upload propagation) and any clock skew between the two machines.
DEFAULT_STALE_S = 300


def _path() -> Path | None:
    """Shared liveness file in the Supernote Drive folder (hidden from the device)."""
    root = config.supernote_root()
    return (root / ".laptop-alive") if root else None


def write() -> None:
    """Stamp 'the laptop is active now'. Best-effort — never breaks the caller."""
    p = _path()
    if p is None:
        return
    with contextlib.suppress(OSError):
        p.write_text(str(time.time()), encoding="utf-8")


def is_laptop_alive(stale_s: float = DEFAULT_STALE_S) -> bool:
    """True if the laptop stamped the heartbeat within `stale_s` seconds (so the cloud defers)."""
    p = _path()
    if p is None or not p.exists():
        return False
    try:
        ts = float(p.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return (time.time() - ts) < stale_s


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "write":
        write()
    elif cmd == "alive":
        stale = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_STALE_S
        sys.exit(0 if is_laptop_alive(stale) else 1)
    else:
        sys.exit("usage: heartbeat.py write | alive [SECS]")


if __name__ == "__main__":
    main()
