#!/usr/bin/env python3
"""
export.py — render the consolidated TODO markdown checklist into a
Supernote-Nomad-friendly PDF for hand annotation.

Design goals (see NoteSync/README.md):
  * Page sized to the Nomad's 3:4 screen so it fills the display without zoom.
  * Large, hand-drawable checkboxes reflecting each item's state.
  * A "STATUS" banner at the top to enforce the check-out / check-in model.
  * An "INBOX" zone with ruled blank lines for hand-writing new tasks.

The PDF is *ephemeral*: the markdown file remains the source of truth. On
check-in we read the annotated PDF (visually) and fold edits back into the
markdown, then re-export. Annotations are not meant to survive a re-export.

Usage:
    python export.py INPUT.md OUTPUT.pdf [--status "on-device since 2026-05-25"]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
from dataclasses import dataclass, field

from fpdf import FPDF

from notesync.common import FONT, register_fonts

# --- Nomad geometry -------------------------------------------------------
# Screen is 1404 x 1872 px (3:4). We pick a physical page with the same ratio.
PAGE_W_MM = 132.0
PAGE_H_MM = 176.0
MARGIN_MM = 7.0

# --- item state -> how to draw the checkbox -------------------------------
# (glyph drawn inside the box, short label for the legend)
STATE_META = {
    " ": ("",  "not started"),
    "~": ("/",  "in PR"),
    "x": ("X",  "shipped"),
    "!": ("!",  "deferred"),
    "-": ("-",  "declined"),
}


@dataclass
class Item:
    state: str
    title: str
    subs: list[str] = field(default_factory=list)  # PR / Notes / nested bullets


@dataclass
class Section:
    title: str
    intro: list[str] = field(default_factory=list)  # prose paragraphs under header
    items: list[Item] = field(default_factory=list)


# --- inline markdown cleanup ---------------------------------------------
_LINK_RE = re.compile(r"\[([^\]]+)\]\((?:[^)]*)\)")   # [text](url) -> text
_CODE_RE = re.compile(r"`([^`]*)`")                    # `code` -> code
_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")          # images -> drop

# The core PDF fonts are latin-1 only; map the unicode we actually emit to ASCII
# rather than bundling a TTF (this is a hand-annotation doc — ASCII is plenty).
_UNICODE_MAP = {
    "—": "-", "–": "-", "→": "->", "×": "x",
    "“": '"', "”": '"', "‘": "'", "’": "'",
    "…": "...", "•": "*", " ": " ", "✅": "(done)",
}


def sanitize(text: str) -> str:
    """Reduce text to latin-1-safe characters for the core PDF fonts."""
    for uni, asc in _UNICODE_MAP.items():
        text = text.replace(uni, asc)
    return text.encode("latin-1", "ignore").decode("latin-1")


def clean_inline(text: str) -> str:
    """Strip markdown that fpdf2's markdown renderer can't handle.

    Leaves ``**bold**`` intact (fpdf2 multi_cell markdown=True renders it),
    but resolves links to their label, unwraps inline code, and drops images.
    Also normalises the emoji checkmark sometimes left on PR lines.
    """
    text = _IMG_RE.sub("", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _CODE_RE.sub(r"\1", text)
    return sanitize(text).strip()


def parse(md: str) -> list[Section]:
    """Parse the checklist markdown into sections of items.

    Recognised structure:
      ``## Heading``                     -> new section
      ``- [s] text``                     -> item (s is one of STATE_META)
      ``  - ...`` (indented bullet)      -> sub-line attached to current item
      plain prose under a heading        -> section intro
    The top-of-file blockquote and the legend tables are intentionally skipped
    (reference material the user already knows; omitting it saves device space).
    """
    sections: list[Section] = []
    cur_section: Section | None = None
    cur_item: Item | None = None
    in_legend = False

    item_re = re.compile(r"^- \[(.)\]\s*(.*)$")
    sub_re = re.compile(r"^\s{2,}- (.*)$")

    for raw in md.splitlines():
        line = raw.rstrip()

        if line.startswith("## "):
            heading = sanitize(line[3:].strip())
            # Skip the two legend sections wholesale.
            in_legend = heading.lower() in ("status legend", "tag legend (inherited from source)")
            if in_legend:
                cur_section = None
                cur_item = None
                continue
            cur_section = Section(title=heading)
            sections.append(cur_section)
            cur_item = None
            continue

        if in_legend or cur_section is None:
            continue

        m = item_re.match(line)
        if m:
            state = m.group(1)
            if state not in STATE_META:
                state = " "
            cur_item = Item(state=state, title=clean_inline(m.group(2)))
            cur_section.items.append(cur_item)
            continue

        m = sub_re.match(line)
        if m and cur_item is not None:
            sub = clean_inline(m.group(1))
            # Skip empty placeholder notes/PRs — they're noise on the device.
            low = sub.lower()
            if low in ("notes: none yet", "notes: _none yet_", "pr: none open", "pr: _none open_"):
                continue
            cur_item.subs.append(sub)
            continue

        # Plain prose -> section intro (only before any item in the section).
        if (line.strip() and not line.startswith("#") and not line.startswith(">")
                and cur_item is None):
            cur_section.intro.append(clean_inline(line.strip()))

    return sections


class Checklist(FPDF):
    def header(self):  # noqa: D401 - fpdf hook
        pass

    def footer(self):
        self.set_y(-6)
        self.set_font(FONT, "", 6)
        self.set_text_color(140)
        legend = "  ".join(
            f"[{g or ' '}] {label}" for ch, (g, label) in STATE_META.items()
        )
        self.cell(0, 4, f"{legend}    -  pg {self.page_no()}", align="C")
        self.set_text_color(0)


def _draw_checkbox(pdf: Checklist, x: float, y: float, size: float, state: str) -> None:
    glyph, _ = STATE_META[state]
    pdf.set_draw_color(0)
    pdf.set_line_width(0.35)
    pdf.rect(x, y, size, size)
    if glyph:
        pdf.set_font(FONT, "B", size * 2.4)
        pdf.set_xy(x, y - 0.4)
        pdf.cell(size, size, glyph, align="C")


def render(sections: list[Section], out_path: str, status: str) -> None:
    pdf = Checklist(orientation="P", unit="mm", format=(PAGE_W_MM, PAGE_H_MM))
    register_fonts(pdf)
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.set_margins(MARGIN_MM, MARGIN_MM, MARGIN_MM)
    pdf.add_page()
    usable_w = PAGE_W_MM - 2 * MARGIN_MM

    # --- STATUS banner ----------------------------------------------------
    pdf.set_fill_color(20)
    pdf.set_text_color(255)
    pdf.set_font(FONT, "B", 9)
    pdf.cell(0, 7, f"  STATUS: {status}", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(1)
    pdf.set_font(FONT, "", 7)
    pdf.set_text_color(90)
    pdf.multi_cell(0, 3.4, "Working copy on device. Check off / annotate / add to INBOX. "
                           "Do not edit the laptop markdown until this is checked back in.")
    pdf.set_text_color(0)
    pdf.ln(2)

    box = 4.2          # checkbox edge length (mm) — large enough to ink
    gap = 2.0          # gap between box and text
    text_x = MARGIN_MM + box + gap
    text_w = usable_w - box - gap

    for sec in sections:
        # keep heading with at least its first item
        if pdf.get_y() > PAGE_H_MM - 30:
            pdf.add_page()
        pdf.set_font(FONT, "B", 11)
        pdf.ln(1)
        pdf.cell(0, 6, sec.title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(0)
        pdf.set_line_width(0.25)
        y = pdf.get_y()
        pdf.line(MARGIN_MM, y, PAGE_W_MM - MARGIN_MM, y)
        pdf.ln(1.5)

        for intro in sec.intro:
            pdf.set_font(FONT, "I", 7.5)
            pdf.set_text_color(110)
            pdf.multi_cell(0, 3.6, intro)
            pdf.set_text_color(0)
            pdf.ln(0.5)

        for item in sec.items:
            box_y = pdf.get_y() + 0.6
            _draw_checkbox(pdf, MARGIN_MM, box_y, box, item.state)

            pdf.set_xy(text_x, pdf.get_y())
            pdf.set_font(FONT, "", 9)
            strike = item.state in ("x", "-")
            # multi_cell with markdown renders **bold** key phrases.
            pdf.multi_cell(text_w, 4.4, item.title, markdown=True)

            if strike:
                # subtle strike-through across the first line of done/declined items
                ly = box_y + 2.0
                pdf.set_draw_color(150)
                pdf.set_line_width(0.2)
                pdf.line(text_x, ly, text_x + text_w * 0.96, ly)

            for sub in item.subs:
                pdf.set_x(text_x + 2)
                pdf.set_font(FONT, "I", 7)
                pdf.set_text_color(105)
                pdf.multi_cell(text_w - 2, 3.3, sub)
                pdf.set_text_color(0)
            pdf.ln(2.2)

    # --- INBOX zone -------------------------------------------------------
    pdf.add_page()
    pdf.set_font(FONT, "B", 12)
    pdf.cell(0, 8, "+  INBOX  -  write new tasks here", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, "I", 7.5)
    pdf.set_text_color(110)
    pdf.multi_cell(0, 3.6, "New items written here get promoted into the right section on check-in. "
                           "One task per line. Empty checkbox = open.")
    pdf.set_text_color(0)
    pdf.ln(3)
    line_h = 9.0
    y = pdf.get_y()
    while y < PAGE_H_MM - 14:
        _draw_checkbox(pdf, MARGIN_MM, y, box, " ")
        pdf.set_draw_color(205)
        pdf.set_line_width(0.15)
        pdf.line(text_x, y + box, PAGE_W_MM - MARGIN_MM, y + box)
        y += line_h
        pdf.set_y(y)

    pdf.output(out_path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="path to the checklist markdown")
    ap.add_argument("output", help="path to write the PDF")
    ap.add_argument("--status", default=None,
                    help="STATUS banner text (default: on-device since <today>)")
    args = ap.parse_args()

    status = args.status or f"on-device since {_dt.date.today().isoformat()}"
    with open(args.input, encoding="utf-8") as fh:
        sections = parse(fh.read())
    render(sections, args.output, status)

    n_items = sum(len(s.items) for s in sections)
    print(f"Wrote {args.output}: {len(sections)} sections, {n_items} items.")


if __name__ == "__main__":
    main()
