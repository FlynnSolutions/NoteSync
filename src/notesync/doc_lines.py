#!/usr/bin/env python3
"""
doc_lines.py — extract a PDF page's text lines with their vertical positions, so the
ink reader can ANCHOR each handwritten note to the exact line it sits on (or points at)
instead of guessing. This is the fix for targeting errors: a note's job is "which line",
and the only way to get that right is to know where every line actually is.

Each line is returned as ``(y, text)`` where ``y`` is the line's vertical center as a
fraction of page height (0=top, 1=bottom) — the SAME coordinate space the ink uses after
the registration fix (see marklayer._align_ink). So a note at y=0.43 maps to the doc line
nearest 0.43.

Backed by poppler's ``pdftotext -bbox`` (already a dependency via pdftoppm); no new libs.

Usage:
    from notesync.doc_lines import page_lines
    for y, text in page_lines(pdf_path, page_number):   # 1-based page
        ...
"""
from __future__ import annotations

import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Words whose vertical centers fall within this fraction of page height are one line.
_LINE_MERGE_TOL = 0.012


def _pdftotext() -> str:
    exe = shutil.which("pdftotext")
    if not exe:
        sys.exit("error: 'pdftotext' not found on PATH (install poppler)")
    return exe


def page_lines(pdf: Path, page: int) -> list[tuple[float, str]]:
    """Return ``[(y_fraction, line_text), ...]`` top-to-bottom for one (1-based) PDF page.

    ``y_fraction`` is the line's vertical center / page height. Words on the same visual
    line (centers within ``_LINE_MERGE_TOL``) are joined left-to-right into one entry.
    """
    out = subprocess.run(
        [_pdftotext(), "-bbox", "-f", str(page), "-l", str(page), str(pdf), "-"],
        capture_output=True, text=True,
    ).stdout

    page_h: float | None = None
    words: list[tuple[float, float, str]] = []   # (ymid_frac, xmin, text)
    for ln in out.splitlines():
        if "<page " in ln:
            m = re.search(r'height="([\d.]+)"', ln)
            page_h = float(m.group(1)) if m else None
        w = re.search(
            r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="[\d.]+" yMax="([\d.]+)">(.*?)</word>',
            ln,
        )
        if w and page_h:
            ymid = (float(w.group(2)) + float(w.group(3))) / 2 / page_h
            words.append((ymid, float(w.group(1)), html.unescape(w.group(4))))

    words.sort(key=lambda t: (t[0], t[1]))            # by line, then left-to-right
    lines: list[tuple[float, str]] = []
    cur_y: float | None = None
    cur: list[str] = []
    for y, _x, text in words:
        if cur_y is None or y - cur_y < _LINE_MERGE_TOL:
            cur.append(text)
            if cur_y is None:
                cur_y = y
        else:
            lines.append((cur_y, " ".join(cur)))
            cur, cur_y = [text], y
    if cur and cur_y is not None:
        lines.append((cur_y, " ".join(cur)))
    return lines


def lines_block(pdf: Path, page: int) -> str:
    """The line-map as a compact text block to drop into the reader prompt."""
    rows = page_lines(pdf, page)
    return "\n".join(f"[y={y*100:.1f}%] {text}" for y, text in rows)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: doc_lines.py PDF PAGE")
    print(lines_block(Path(sys.argv[1]), int(sys.argv[2])))
