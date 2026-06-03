#!/usr/bin/env python3
"""
calibrate.py — the handwriting "scribble test". Generates a calibration sheet for the user
to hand-write on the device; reading it back builds their handwriting/QUIRKS.md profile so
read_ink interprets *their* hand better.

    python calibrate.py sheet OUT.pdf     # generate the sheet to annotate on the device
    python calibrate.py read PAGES_DIR    # build QUIRKS from a filled, ink-extracted sheet

Flow: generate the sheet -> push to the device (drop in Document/) -> hand-write each
prompt -> Export-with-annotations -> `sync.sh in` extracts the ink to checkin_pages/ ->
`calibrate read checkin_pages`. The read-back is re-runnable and additive.

NOTE: `read` calls the Claude API and has not yet been verified against a real filled-in
sheet (that needs the physical device). The sheet generator is fully working.
"""
from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path

from fpdf import FPDF

from common import FONT, MARGIN_MM, PAGE_H_MM, PAGE_W_MM, register_fonts, sanitize

HERE = Path(__file__).resolve().parent
QUIRKS = HERE / "handwriting" / "QUIRKS.md"

# Each prompt: (label shown above the writing space, expected text = ground truth so the
# read-back can diff what was written against what was asked). Empty = freeform prompt.
PROMPTS = [
    ("Lowercase alphabet", "a b c d e f g h i j k l m n o p q r s t u v w x y z"),
    ("Uppercase alphabet", "A B C D E F G H I J K L M N O P Q R S T U V W X Y Z"),
    ("Digits", "0 1 2 3 4 5 6 7 8 9"),
    ("Write these words in your normal hand", "with what would value river minimum money rhythm quay"),
    ("Any shorthand/abbreviations you use a lot", ""),
    ("Make each mark: a check, an X, a strike-through line, an arrow", ""),
    ('Write "@claude" as you would in a margin', "@claude"),
]


def build_sheet(out_path: str) -> None:
    """Render the calibration sheet — a labeled prompt + ruled writing space for each row."""
    pdf = FPDF(orientation="P", unit="mm", format=(PAGE_W_MM, PAGE_H_MM))
    register_fonts(pdf)
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_margins(MARGIN_MM, MARGIN_MM + 2, MARGIN_MM)
    pdf.add_page()
    usable = PAGE_W_MM - 2 * MARGIN_MM

    def cell(text: str, font_style: str, size: float, height: float, grey: int = 0) -> None:
        pdf.set_x(MARGIN_MM)                       # multi_cell leaves X at the right edge
        pdf.set_font(FONT, font_style, size)
        pdf.set_text_color(grey)
        pdf.multi_cell(usable, height, sanitize(text))
        pdf.set_text_color(0)

    cell("Handwriting calibration", "B", 13, 6)
    cell("Hand-write each prompt in the space below it, in your normal hand. Then "
         "Export-with-annotations so the reader can learn how you write.", "", 7.5, 3.8, grey=90)
    pdf.ln(3)

    for label, expected in PROMPTS:
        cell(label, "B", 9, 4.5)
        if expected:
            cell(f"   {expected}", "I", 7.5, 3.6, grey=120)
        y = pdf.get_y() + 9                       # ruled line to write on
        pdf.set_draw_color(205)
        pdf.set_line_width(0.2)
        pdf.line(MARGIN_MM, y, PAGE_W_MM - MARGIN_MM, y)
        pdf.set_y(y + 4)
    pdf.output(out_path)


_SYSTEM = """\
You are calibrating a handwriting reader to one person. You are given, per page, an image \
of a calibration sheet they filled in by hand, plus the list of prompts they were asked to \
write (the ground truth). By comparing what they actually wrote to what was asked, produce \
a concise handwriting profile for this person.

Cover: letters/digits they form ambiguously (e.g. a w that looks like v), any personal \
shorthand, and how their marks look (check / strike / arrow / the @claude mark). Output \
ONLY the markdown for a QUIRKS.md file — short, specific, useful to a future reader. No \
preamble or code fences."""


def _img_block(path: Path) -> dict:
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": data}}


def read(pages_dir: str) -> None:
    """Read a filled-in sheet (ink-extracted PNGs) and (re)write handwriting/QUIRKS.md."""
    import config  # local import keeps the sheet generator dependency-light
    import read_ink  # reuse its .env loader + client conventions

    read_ink._load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY not set (env or supernote-sync/.env)")
    import anthropic

    pages = sorted(Path(pages_dir).glob("*.png"))
    if not pages:
        raise SystemExit(f"no calibration page PNGs in {pages_dir} (run `sync.sh in` first)")

    prompts = "\n".join(f"- {label}: {expected or '(freeform)'}" for label, expected in PROMPTS)
    content: list[dict] = [{"type": "text", "text": f"Prompts the person was asked to write:\n{prompts}"}]
    for p in pages:
        content.append({"type": "text", "text": f"--- {p.stem} ---"})
        content.append(_img_block(p))
    content.append({"type": "text", "text":
                    "Produce the QUIRKS.md profile for this person's handwriting."})

    client = anthropic.Anthropic()
    with client.messages.stream(model=config.model(), max_tokens=4000,
                                system=[{"type": "text", "text": _SYSTEM}],
                                messages=[{"role": "user", "content": content}]) as stream:
        msg = stream.get_final_message()
    profile = "".join(b.text for b in msg.content if b.type == "text").strip() + "\n"
    QUIRKS.parent.mkdir(parents=True, exist_ok=True)
    QUIRKS.write_text(profile, encoding="utf-8")
    print(f"Wrote {QUIRKS}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sheet").add_argument("output")
    sub.add_parser("read").add_argument("pages_dir")
    args = ap.parse_args()
    if args.cmd == "sheet":
        build_sheet(args.output)
        print(f"Wrote {args.output}")
    else:
        read(args.pages_dir)


if __name__ == "__main__":
    main()
