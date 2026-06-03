#!/usr/bin/env python3
"""Shared helpers for the Supernote renderers (page geometry, fonts, text cleanup)."""
from __future__ import annotations

from fpdf import FPDF

import config

# --- Nomad geometry (1404x1872 px, 3:4) -----------------------------------
PAGE_W_MM = 132.0
PAGE_H_MM = 176.0
MARGIN_MM = 8.0

# --- Embedded font (core PDF fonts render blank in some viewers/the device) ---
# Defaults to the bundled DejaVu Sans; override the regular/bold/italic TTFs in config.
FONT = "Body"


def register_fonts(pdf: FPDF) -> None:
    """Register the configured (or bundled DejaVu) TTFs as the renderer's font family."""
    pdf.add_font(FONT, "", str(config.font_regular()))
    pdf.add_font(FONT, "B", str(config.font_bold()))
    pdf.add_font(FONT, "I", str(config.font_italic()))


# --- checklist checkboxes (shared by the renderers) -----------------------
# A markdown task item `- [x] text` carries a single-char marker. Map each known
# marker to the glyph drawn inside the box + a human label (for the legend). Any doc's
# checkboxes render as real boxes, no config needed; `format: checklist` adds the legend.
CHECK_STATES = {
    " ": ("", "to do"),
    "~": ("/", "in progress"),
    "x": ("X", "done"),
    "!": ("!", "deferred"),
    "-": ("-", "dropped"),
}


def draw_checkbox(pdf: FPDF, x: float, y: float, size: float, marker: str) -> None:
    """Draw a checklist checkbox — a square with the marker's state glyph — at (x, y)."""
    glyph = CHECK_STATES.get(marker, ("", ""))[0]
    pdf.set_draw_color(0)
    pdf.set_line_width(0.3)
    pdf.rect(x, y, size, size)
    if glyph:
        pdf.set_font(FONT, "B", size * 2.2)
        pdf.set_xy(x, y - 0.5)
        pdf.cell(size, size, glyph, align="C")


# Map the unicode/emoji we emit down to latin-1/ASCII so nothing renders as a blank box
# (the embedded font has no colour-emoji glyphs). The only invisible code points
# (non-breaking space, emoji variation selector) are commented inline.
_UNICODE_MAP = {
    "—": "-", "–": "-", "→": "->", "←": "<-", "×": "x", "·": "-",
    "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "•": "*",
    "✅": "[x]", "⬜": "[ ]", "⚠️": "(!)", "⚠": "(!)", "✍️": "", "✍": "",
    "➕": "+", "↳": "->", "✓": "v", "≥": ">=", "≤": "<=",
    " ": " ",   # non-breaking space
    "️": "",    # emoji variation selector
}


def sanitize(text: str) -> str:
    """Reduce text to characters the embedded font can render (latin-1-safe)."""
    for uni, asc in _UNICODE_MAP.items():
        text = text.replace(uni, asc)
    return text.encode("latin-1", "ignore").decode("latin-1")
