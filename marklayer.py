#!/usr/bin/env python3
"""
marklayer.py — extract a user's handwritten ink straight from the Supernote
``.mark`` annotation layer, instead of color-filtering a flattened export.

A ``.pdf.mark`` sidecar is itself a native Supernote document (same SN_FILE_VER
format as ``.note``, ``FILE_TYPE:MARK``). Its ink is stored as RATTA_RLE bitmap
layers, fully separated from the underlying PDF — so it is COLOR-INDEPENDENT.
Writing in black works exactly as well as red; no "export as red" step, and no
fragile red-pixel heuristic — this replaces the old rasterize-and-colour-filter
path for annotated PDFs.

Page mapping: the ``.mark`` footer lists ``PAGE<N>`` keys for the (1-based) PDF
pages that actually have ink, in order. ``supernote-tool convert -a`` emits one
PNG per annotated page (``_0, _1, ...``) in that same order. So output ``_i``
corresponds to PDF page = the i-th sorted ``PAGE<N>`` key.

For each annotated page this writes, into the pages dir (read_ink.py's layout):
  * ``<stem>-p<N>.png``       — full page: PDF page N + ink overlaid (layout context)
  * ``ink/<stem>-p<N>.png``   — ink only, black-on-white (ground truth of what was written)

Usage:
    python marklayer.py PATH/TO/DOC.pdf.mark [--pdf DOC.pdf] [--out checkin_pages]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

import config

HERE = Path(__file__).resolve().parent


def _align_ink(ink: Image.Image) -> Image.Image:
    """Fix the `.mark` ink's vertical registration against the PDF page before compositing.

    supernote-tool rasterizes the ink in a canvas whose vertical mapping to the PDF is a
    slight affine (ink too high near the top, ~aligned at the bottom — its DPI metadata is
    zeroed, so it guesses the geometry). We remap so `pdf_fraction = scale*ink + offset`:
    for each output row y the source row is (y - offset*H)/scale. Identity at (1.0, 0.0).
    Coefficients come from config.mark_align() (per-device, overridable). Applied ONLY to the
    composited context image — the ink-only ground truth stays undistorted for recognition."""
    scale, offset = config.mark_align()
    if scale == 1.0 and offset == 0.0:
        return ink
    w, h = ink.size
    coeffs = (1, 0, 0, 0, 1.0 / scale, -offset * h / scale)   # output(x,y) <- input(x, (y-offset*h)/scale)
    return ink.transform((w, h), Image.AFFINE, coeffs, resample=Image.BILINEAR)


def _need(binary: str) -> str:
    # Prefer a copy next to this interpreter (supernote-tool lives in .venv/bin,
    # which isn't on PATH when invoked as `.venv/bin/python marklayer.py`).
    local = Path(sys.executable).parent / binary
    if local.exists():
        return str(local)
    path = shutil.which(binary)
    if not path:
        sys.exit(f"error: required tool '{binary}' not found on PATH")
    return path


def annotated_pdf_pages(mark: Path) -> list[int]:
    """1-based PDF page numbers that carry ink, in the order supernote-tool emits them.

    Read from the ``.mark`` footer's ``PAGE<N>`` keys (sorted by N). This is the
    same footer supernote-tool parses, so the ordering matches its ``_0,_1,...``.
    """
    tool = _need("supernote-tool")
    out = subprocess.run([tool, "analyze", str(mark)], check=True,
                         capture_output=True, text=True).stdout
    footer = json.loads(out).get("__footer__", {})
    pages = sorted(int(m.group(1)) for k in footer
                   if (m := re.fullmatch(r"PAGE(\d+)", k)))
    return pages


def _convert(mark: Path, out_prefix: Path, *, transparent: bool) -> list[Path]:
    """Render every annotated page of a .mark to PNG; return them in emit order."""
    tool = _need("supernote-tool")
    cmd = [tool, "convert", "-t", "png", "-a"]
    if transparent:
        cmd.append("--exclude-background")
    cmd += [str(mark), str(out_prefix) + ".png"]
    subprocess.run(cmd, check=True, capture_output=True)
    # supernote-tool writes <prefix>_0.png, <prefix>_1.png, ...
    found = sorted(out_prefix.parent.glob(f"{out_prefix.name}_*.png"),
                   key=lambda p: int(p.stem.rsplit("_", 1)[1]))
    return found


def render_pdf_page(pdf: Path, page: int, size: tuple[int, int], dst: Path) -> None:
    """Rasterize one (1-based) PDF page to an exact pixel size via pdftoppm."""
    _need("pdftoppm")
    w, h = size
    with tempfile.TemporaryDirectory() as td:
        prefix = Path(td) / "pg"
        subprocess.run(
            ["pdftoppm", "-png", "-f", str(page), "-l", str(page),
             "-scale-to-x", str(w), "-scale-to-y", str(h), str(pdf), str(prefix)],
            check=True, capture_output=True,
        )
        outs = list(Path(td).glob("pg-*.png"))
        if not outs:
            sys.exit(f"error: pdftoppm produced no output for page {page} of {pdf}")
        Image.open(outs[0]).convert("RGB").save(dst)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mark", type=Path, help="the DOC.pdf.mark annotation sidecar")
    ap.add_argument("--pdf", type=Path, default=None,
                    help="the annotated PDF (default: strip .mark from the sidecar path)")
    ap.add_argument("--out", type=Path, default=HERE / "checkin_pages",
                    help="output dir for page PNGs (ink/ subdir gets ground truth)")
    args = ap.parse_args()

    mark: Path = args.mark
    if not mark.exists():
        sys.exit(f"error: {mark} not found")
    pdf = args.pdf or Path(str(mark)[:-len(".mark")])
    if not pdf.exists():
        sys.exit(f"error: source PDF not found: {pdf}")

    try:
        for pdf_page, full, ink in extract(mark, pdf, args.out):
            print(f"page {pdf_page}: {full}  +  {ink}")
    except ValueError as e:
        sys.exit(str(e))


def extract(mark: Path, pdf: Path, out_dir: Path) -> list[tuple[int, Path, Path]]:
    """Extract ink from a .mark layer into out_dir; return (pdf_page, full, ink) per page.

    ``full`` = PDF page + ink composited (layout context); ``ink`` = ink-only ground
    truth (black-on-white), under ``out_dir/ink/``. Both named ``<stem>-p<N>.png`` by
    the real (1-based) PDF page number — NOT the .mark's internal index.
    """
    pages = annotated_pdf_pages(mark)
    if not pages:
        raise ValueError("no annotated pages found in the .mark (footer has no PAGE<N> keys)")

    ink_dir = out_dir / "ink"
    out_dir.mkdir(parents=True, exist_ok=True)
    ink_dir.mkdir(parents=True, exist_ok=True)
    stem = pdf.stem
    results: list[tuple[int, Path, Path]] = []

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        ink_bw = _convert(mark, tdp / "ink", transparent=False)      # black-on-white
        ink_tr = _convert(mark, tdp / "inkT", transparent=True)      # transparent ink
        if not (len(ink_bw) == len(ink_tr) == len(pages)):
            raise ValueError(
                f"page-count mismatch: footer says {len(pages)} annotated page(s), "
                f"supernote-tool emitted {len(ink_bw)} — refusing to guess mapping")

        for i, pdf_page in enumerate(pages):
            ink = Image.open(ink_tr[i]).convert("RGBA")
            name = f"{stem}-p{pdf_page}.png"
            ink_path, full_path = ink_dir / name, out_dir / name

            # Ground truth: ink only, black-on-white.
            Image.open(ink_bw[i]).convert("RGB").save(ink_path)

            # Full context: the actual PDF page (same pixel size) with ink composited on top.
            base_png = tdp / f"base-{pdf_page}.png"
            render_pdf_page(pdf, pdf_page, ink.size, base_png)
            base = Image.open(base_png).convert("RGBA")
            if base.size != ink.size:
                ink = ink.resize(base.size)
            ink = _align_ink(ink)   # vertical registration fix: land marks on the line written over
            Image.alpha_composite(base, ink).convert("RGB").save(full_path)
            results.append((pdf_page, full_path, ink_path))
    return results


if __name__ == "__main__":
    main()
