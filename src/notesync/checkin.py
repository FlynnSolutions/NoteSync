#!/usr/bin/env python3
"""
checkin.py — turn an annotated Supernote file into page PNGs that Claude can
read visually, so device edits can be folded back into the markdown.

Handles both round-trip formats:
  * ``.note``  — native Supernote document, converted via ``supernote-tool``.
  * ``.pdf``   — a PDF that was imported to the device and annotated, then
                 exported flattened from Supernote; rasterized via ``pdftoppm``.

We deliberately do NOT use the Nomad's on-device handwriting recognition (it's
unreliable on this user's hand) — Claude reads the rendered PNGs directly.

Usage:
    python checkin.py ANNOTATED.note   [--out OUTDIR] [--dpi 200]
    python checkin.py ANNOTATED.pdf    [--out OUTDIR] [--dpi 200]

Prints the list of generated PNG paths (one per page).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _need(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        sys.exit(f"error: required tool '{binary}' not found on PATH")
    return path


def from_note(src: Path, out_dir: Path, dpi: int) -> list[Path]:
    """Convert a .note to one PNG per page via supernote-tool."""
    tool = _need("supernote-tool")
    stem = out_dir / src.stem
    # supernote-tool writes <stem>_0.png, <stem>_1.png, ... for --all pages.
    subprocess.run(
        [tool, "convert", "-t", "png", "-a", str(src), str(stem)],
        check=True,
    )
    pages = sorted(out_dir.glob(f"{src.stem}_*.png"))
    if not pages:  # single-page notes may emit just <stem>.png
        single = out_dir / f"{src.stem}.png"
        if single.exists():
            pages = [single]
    return pages


def from_pdf(src: Path, out_dir: Path, dpi: int) -> list[Path]:
    """Rasterize a (flattened, annotated) PDF to one PNG per page."""
    _need("pdftoppm")
    prefix = out_dir / src.stem
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), str(src), str(prefix)],
        check=True,
    )
    return sorted(out_dir.glob(f"{src.stem}-*.png"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path, help="annotated .note or .pdf file")
    ap.add_argument("--out", type=Path, default=Path("checkin_pages"),
                    help="output directory for page PNGs")
    ap.add_argument("--dpi", type=int, default=200, help="raster resolution")
    args = ap.parse_args()

    src: Path = args.input
    if not src.exists():
        sys.exit(f"error: {src} not found")
    args.out.mkdir(parents=True, exist_ok=True)

    ext = src.suffix.lower()
    if ext == ".note":
        pages = from_note(src, args.out, args.dpi)
    elif ext == ".pdf":
        pages = from_pdf(src, args.out, args.dpi)
    else:
        sys.exit(f"error: unsupported input '{ext}' (expected .note or .pdf)")

    if not pages:
        sys.exit("error: no pages were produced — check the input file")
    print(f"Rendered {len(pages)} page(s):")
    for p in pages:
        print(p)


if __name__ == "__main__":
    main()
