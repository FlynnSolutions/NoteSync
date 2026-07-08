#!/usr/bin/env python3
"""
render_one.py — render a single doc to PDF bytes in an isolated subprocess.

fpdf2 leaks ~25MB/doc that never frees in a long in-process loop, so a full mirror
(200+ docs) climbed past 3GB and OOM-wedged the host. mirror.py invokes this per doc
so the OS reclaims that memory on each exit. Stdout is the raw PDF; keep it clean.

Usage: render_one.py <src-path> <rel-label>
"""
from __future__ import annotations

import sys
from pathlib import Path

import questions
from render import render_bytes


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: render_one.py <src-path> <rel-label>")
    src, rel = sys.argv[1], sys.argv[2]
    pdf = render_bytes(Path(src).read_text(encoding="utf-8"), rel,
                       questions=questions.for_doc(rel))
    sys.stdout.buffer.write(pdf)


if __name__ == "__main__":
    main()
