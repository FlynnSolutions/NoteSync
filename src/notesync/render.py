#!/usr/bin/env python3
"""
render.py — general Markdown → Nomad-shaped, annotatable PDF.

Unlike export.py (checklist-specific), this renders arbitrary markdown docs:
headings, paragraphs (bold/italic), bullet/numbered lists, fenced code, block-
quotes, horizontal rules, and pipe tables. The footer shows the source's relative
path so you always know which file you're looking at on the device.

Usage:
    python render.py INPUT.md OUTPUT.pdf [--label "relative/path/to/source.md"]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from notesync import config, questions
from notesync.common import (
    CHECK_STATES,
    FONT,
    MARGIN_MM,
    PAGE_H_MM,
    PAGE_W_MM,
    draw_checkbox,
    register_fonts,
    sanitize,
)

HEADING_SIZE = {1: 15, 2: 12.5, 3: 11, 4: 10, 5: 9.5, 6: 9}
BODY = 8.5
# Spacing density preference -> a gentle multiplier on body line heights / gaps.
_LH = {"compact": 0.9, "normal": 1.0, "roomy": 1.16}.get(config.density(), 1.0)
PARA_LH = 4.3 * _LH
LIST_LH = 4.4 * _LH
TOP_MARGIN_MM = MARGIN_MM + 4  # extra breathing room so heading ascenders don't clip
BOTTOM_MARGIN_MM = 12          # room for the footer + a little annotation space
_FIXED_PDF_DATE = datetime(2001, 1, 1)  # fixed so identical source -> identical bytes

_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
# A within-doc anchor link `[label](#slug)`; and a non-anchor link to degrade to its label.
_ANCHOR_LINK = re.compile(r"\[([^\]]+)\]\(#([A-Za-z0-9._-]+)\)")
_NONANCHOR_LINK = re.compile(r"\[([^\]]+)\]\((?!#)[^)]*\)")
# An invisible anchor target: `<!-- canonical: slug -->` (or `anchor:`), per DOC_STANDARD.
_ANCHOR_COMMENT = re.compile(r"<!--\s*(?:canonical|anchor):\s*([A-Za-z0-9._-]+)\s*-->")
_SEP_ROW = re.compile(r"^\s*\|?[\s:\-\|]+\|?\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_HR = re.compile(r"^\s*([-*_])\1{2,}\s*$")
_LIST = re.compile(r"^(\s*)([-*+]|\d+\.)\s+(.*)$")
_CHECKBOX = re.compile(r"^\[(.)\]\s*(.*)$")  # the `[x] text` inside a task list item
_BLOCK_START = re.compile(r"^(#{1,6}\s|\s*([-*+]|\d+\.)\s|>|```)")
# Frontmatter: an optional leading `---` ... `---` block of `key: value` lines.
_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.S)


def _parse_frontmatter(md_text: str) -> tuple[dict[str, str], str]:
    """Split off a leading `---` frontmatter block. Returns (metadata, body). The block
    is stripped from the body, so it never renders into the PDF (it's instructions, not
    content). Simple flat `key: value` parsing — no YAML dependency."""
    m = _FRONTMATTER.match(md_text)
    if not m:
        return {}, md_text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, val = line.split(":", 1)
            meta[key.strip().lower()] = val.strip()
    return meta, md_text[m.end():]


def _inline(text: str) -> str:
    """Strip what fpdf2's inline markdown can't handle; keep **bold**/*italic*."""
    text = _HTML_COMMENT.sub("", text)  # comments never render (they carry anchors/notes)
    text = _IMG.sub("", text)
    text = _LINK.sub(r"\1", text)      # [label](url) -> label
    text = text.replace("`", "")        # inline code -> plain
    return sanitize(text)


def _slugify(text: str) -> str:
    """GitHub-style heading slug: `## Auth retry policy` -> `auth-retry-policy`, so a
    within-doc `[x](#auth-retry-policy)` link resolves to that heading."""
    t = _LINK.sub(r"\1", text).replace("*", "").replace("`", "")
    t = _HTML_COMMENT.sub("", t).strip().lower()
    t = re.sub(r"[^a-z0-9\s-]", "", t)
    return re.sub(r"\s+", "-", t).strip("-")


def _clean_keep_links(text: str) -> str:
    """Like `_inline` but PRESERVES `[label](#slug)` anchor links and `**bold**` so the
    run-writer can turn anchors into tappable internal links. Non-anchor links degrade
    to their label, as before."""
    text = _HTML_COMMENT.sub("", text)
    text = _IMG.sub("", text)
    text = _NONANCHOR_LINK.sub(r"\1", text)   # external/cross-doc links -> label
    return text.replace("`", "")


def _emit_bold(pdf: DocPDF, seg: str, lh: float) -> None:
    """Write a run of text, honouring `**bold**`, flowing inline via pdf.write()."""
    if not seg:
        return
    bold = False
    for part in seg.split("**"):
        if part:
            pdf.set_font(FONT, "B" if bold else "", BODY)
            pdf.write(lh, sanitize(part))
        bold = not bold
    pdf.set_font(FONT, "", BODY)


def _fit(pdf: DocPDF, text: str, width: float, pad: float = 4.0) -> str:
    """Truncate `text` (with an ellipsis) to fit `width` at the current font."""
    if pdf.get_string_width(text) <= width - pad:
        return text
    while text and pdf.get_string_width(text + "...") > width - pad:
        text = text[:-1]
    return text.rstrip() + "..."


def _link_button(pdf: DocPDF, label: str, lid: int | None, x_left: float, width: float,
                 h: float = 8.5, size: float = 10.5) -> None:
    """A big, obvious, finger-tappable navigation button: a bordered, lightly-filled box
    with a leading arrow. On grayscale e-ink the box + arrow + size carry the affordance,
    not colour."""
    x0, y0 = x_left, pdf.get_y()
    pdf.set_x(x_left)
    pdf.set_draw_color(110)
    pdf.set_line_width(0.3)
    pdf.set_fill_color(231)
    pdf.set_font(FONT, "B", size)
    txt = _fit(pdf, ">  " + sanitize(label), width)
    pdf.cell(width, h, txt, border=1, fill=True, align="L", new_x="LMARGIN", new_y="NEXT")
    # Make the WHOLE box tappable, not just the text: cell(link=) only covers the glyphs,
    # so add an explicit link annotation over the full button rectangle.
    if lid is not None:
        pdf.link(x0, y0, width, h, lid)
    pdf.set_fill_color(255)


def _emit_inline(pdf: DocPDF, text: str, lh: float, x_left: float) -> None:
    """Render a paragraph/list line that contains `[label](#slug)` anchor links, turning
    each resolved anchor into a tappable in-document link (blue) and leaving the rest as
    normal flowing text. Unresolved anchors degrade to plain label text."""
    pdf.set_left_margin(x_left)
    pdf.set_x(x_left)
    links = pdf._anchor_links
    pos = 0
    for m in _ANCHOR_LINK.finditer(text):
        _emit_bold(pdf, text[pos:m.start()], lh)
        label, lid = m.group(1), links.get(m.group(2).lower())
        if lid is not None:
            pdf.set_font(FONT, "U", BODY)   # underline reads on grayscale; colour barely does
            pdf.set_text_color(0, 90, 200)
            pdf.write(lh, sanitize(label), link=lid)
            pdf.set_text_color(0)
            pdf.set_font(FONT, "", BODY)
        else:
            _emit_bold(pdf, label, lh)
        pos = m.end()
    _emit_bold(pdf, text[pos:], lh)
    pdf.ln(lh)
    pdf.set_left_margin(MARGIN_MM)


class DocPDF(FPDF):
    def __init__(self, source_label: str = "", doc_format: str = "notes"):
        super().__init__(orientation="P", unit="mm", format=(PAGE_W_MM, PAGE_H_MM))
        self.source_label = source_label
        self.doc_format = doc_format
        # slug -> fpdf internal-link id, for tappable within-doc navigation. Populated only
        # for anchors that are actually referenced (so link-free docs stay byte-identical).
        self._anchor_links: dict[str, int] = {}
        self._anchor_done: set[str] = set()   # slugs whose destination has been set
        self._heading_pages: dict[str, int] = {}   # heading slug -> the page it renders on

    def footer(self):
        self.set_y(-6)
        self.set_font(FONT, "I", 6)
        self.set_text_color(150)
        # `book` reads cleaner with just a page number; everything else shows the source.
        label = "" if self.doc_format == "book" else self.source_label
        text = f"{label}    -  pg {self.page_no()}" if label else f"pg {self.page_no()}"
        self.cell(0, 4, sanitize(text), align="C")
        self.set_text_color(0)


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _render_lines(pdf: DocPDF, lines: list[str], usable: float) -> None:
    """Render one section's markdown lines at the current cursor position."""
    i, n = 0, len(lines)

    while i < n:
        raw = lines[i]
        line = raw.rstrip()

        # invisible anchor target (`<!-- canonical: slug -->`) — set the link destination
        # here and render nothing. Any other HTML comment line is also dropped.
        if line.lstrip().startswith("<!--"):
            ac = _ANCHOR_COMMENT.search(line)
            if ac:
                s = ac.group(1).lower()
                lid = pdf._anchor_links.get(s)
                if lid is not None and s not in pdf._anchor_done:
                    pdf.set_link(lid, page=pdf.page_no(), y=pdf.get_y())
                    pdf._anchor_done.add(s)
            i += 1
            continue

        # fenced code block
        if line.strip().startswith("```"):
            i += 1
            code = []
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # closing fence
            pdf.ln(1)
            pdf.set_font(FONT, "", 7.5)
            pdf.set_fill_color(243)
            for c in code:
                pdf.set_x(MARGIN_MM + 1)
                pdf.multi_cell(usable - 2, 3.7, sanitize(c) or " ", fill=True)
            pdf.ln(1.5)
            continue

        # pipe table (header row followed by a separator row)
        if "|" in line and i + 1 < n and _SEP_ROW.match(lines[i + 1]) and "|" in lines[i + 1]:
            block = []
            while i < n and "|" in lines[i] and lines[i].strip():
                block.append(lines[i])
                i += 1
            rows = [_cells(block[0])] + [_cells(r) for r in block[2:]]
            pdf.set_font(FONT, "", 7.5)
            try:
                with pdf.table(width=usable, text_align="LEFT", line_height=4,
                               first_row_as_headings=True) as table:
                    for rdata in rows:
                        trow = table.row()
                        for cell in rdata:
                            trow.cell(_inline(cell) or " ")
            except Exception:
                # fallback: render rows as plain lines if table layout fails
                for rdata in rows:
                    pdf.multi_cell(usable, 4, _inline(" | ".join(rdata)))
            pdf.ln(2)
            continue

        # heading
        m = _HEADING.match(line)
        if m:
            lvl = len(m.group(1))
            sz = HEADING_SIZE.get(lvl, 9)
            pdf.ln(2 if lvl <= 2 else 1)
            # if this heading is a referenced anchor, plant the link destination at its top
            s = _slugify(m.group(2))
            pdf._heading_pages.setdefault(s, pdf.page_no())   # for separate-page TOC filtering
            lid = pdf._anchor_links.get(s)
            if lid is not None and s not in pdf._anchor_done:
                pdf.set_link(lid, page=pdf.page_no(), y=pdf.get_y())
                pdf._anchor_done.add(s)
            pdf.set_font(FONT, "B", sz)
            pdf.multi_cell(usable, sz * 0.46 + 1.5, _inline(m.group(2)) or " ")
            if lvl == 1:
                y = pdf.get_y()
                pdf.set_draw_color(0)
                pdf.set_line_width(0.3)
                pdf.line(MARGIN_MM, y, PAGE_W_MM - MARGIN_MM, y)
            pdf.ln(1.2)
            i += 1
            continue

        # horizontal rule
        if _HR.match(line):
            pdf.ln(1)
            y = pdf.get_y()
            pdf.set_draw_color(190)
            pdf.set_line_width(0.2)
            pdf.line(MARGIN_MM, y, PAGE_W_MM - MARGIN_MM, y)
            pdf.ln(2.5)
            i += 1
            continue

        # blockquote
        if line.lstrip().startswith(">"):
            txt = line.lstrip()[1:].strip()
            pdf.set_font(FONT, "I", 8)
            pdf.set_text_color(90)
            pdf.set_x(MARGIN_MM + 3)
            pdf.multi_cell(usable - 3, 4, _inline(txt) or " ")
            pdf.set_text_color(0)
            i += 1
            continue

        # list item — render as one indented block (marker inline), left-aligned.
        # (Doing a separate marker cell + multi_cell mispositions wrapped lines.)
        lm = _LIST.match(raw)
        if lm:
            depth = len(lm.group(1)) // 2
            indent = MARGIN_MM + depth * 5
            cb = _CHECKBOX.match(lm.group(3))            # task item: `- [x] text`?
            is_check = bool(cb) and cb.group(1) in CHECK_STATES
            parts = [cb.group(2) if is_check else lm.group(3)]
            i += 1
            # absorb indented continuation lines (markdown lazy continuation) so a
            # source-wrapped bullet renders as one block, not a stray paragraph.
            while i < n and lines[i].strip() and not _BLOCK_START.match(lines[i]) and "|" not in lines[i]:
                parts.append(lines[i].strip())
                i += 1
            raw_join = " ".join(parts)
            # a plain bullet carrying a within-doc anchor link -> tappable internal link
            if not is_check and _ANCHOR_LINK.search(raw_join):
                marker = (lm.group(2) + " ") if lm.group(2) not in ("-", "*", "+") else "- "
                _emit_inline(pdf, sanitize(marker) + _clean_keep_links(raw_join), LIST_LH, indent)
                pdf.set_left_margin(MARGIN_MM)
                continue
            pdf.set_font(FONT, "", BODY)
            body_text = _inline(raw_join) or " "
            if is_check:
                # Draw a real checkbox; align the (possibly wrapping) text past it.
                box, y = 3.0, pdf.get_y()
                draw_checkbox(pdf, indent, y + 0.5, box, cb.group(1))
                pdf.set_font(FONT, "", BODY)   # draw_checkbox left the font bold for the glyph
                text_x = indent + box + 1.8
                pdf.set_left_margin(text_x)
                pdf.set_xy(text_x, y)
                pdf.multi_cell(PAGE_W_MM - text_x - MARGIN_MM, LIST_LH, body_text,
                               markdown=True, align="L")
            else:
                marker = (lm.group(2) + " ") if lm.group(2) not in ("-", "*", "+") else "- "
                pdf.set_left_margin(indent)  # wrapped lines align under the indent
                pdf.set_x(indent)
                pdf.multi_cell(PAGE_W_MM - indent - MARGIN_MM, LIST_LH,
                               sanitize(marker) + body_text, markdown=True, align="L")
            pdf.set_left_margin(MARGIN_MM)   # restore
            continue

        # blank line
        if not line.strip():
            pdf.ln(2 * _LH)
            i += 1
            continue

        # paragraph (gather consecutive plain lines)
        para = [line]
        i += 1
        while i < n and lines[i].strip() and not _BLOCK_START.match(lines[i]) and "|" not in lines[i]:
            para.append(lines[i].rstrip())
            i += 1
        joined = " ".join(para)
        if _ANCHOR_LINK.search(joined):
            _emit_inline(pdf, _clean_keep_links(joined), PARA_LH, MARGIN_MM)
        else:
            pdf.set_font(FONT, "", BODY)
            pdf.multi_cell(usable, PARA_LH, _inline(joined) or " ", markdown=True, align="L")
        pdf.ln(1.3)


def _split_sections(lines: list[str]) -> list[list[str]]:
    """Group lines into heading-led sections (a heading + its content up to the next)."""
    sections: list[list[str]] = []
    cur: list[str] = []
    for ln in lines:
        if _HEADING.match(ln) and cur:
            sections.append(cur)
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        sections.append(cur)
    return sections


def _new_pdf(doc_format: str = "notes") -> DocPDF:
    pdf = DocPDF(doc_format=doc_format)
    register_fonts(pdf)
    pdf.set_auto_page_break(auto=True, margin=BOTTOM_MARGIN_MM)
    pdf.set_margins(MARGIN_MM, TOP_MARGIN_MM, MARGIN_MM)
    # Deterministic output: a fixed creation date means identical source + renderer
    # produces byte-identical PDFs (so Drive sees no change -> no re-sync).
    pdf.set_creation_date(_FIXED_PDF_DATE)
    return pdf


def _render_legend(pdf: DocPDF, usable: float) -> None:
    """A faint one-line status key, for `format: checklist` docs."""
    key = "   ".join(f"[{m if m.strip() else ' '}] {label}"
                      for m, (_glyph, label) in CHECK_STATES.items())
    pdf.set_font(FONT, "I", 6.5)
    pdf.set_text_color(120)
    pdf.multi_cell(usable, 3.4, sanitize(key))
    pdf.set_text_color(0)
    pdf.ln(1.5)


def _toc_entries(md_text: str) -> list[tuple[int, str, str]]:
    """Level-1/2 headings as (level, title, slug) — the clickable contents index."""
    out = []
    for ln in md_text.splitlines():
        m = _HEADING.match(ln)
        if m and len(m.group(1)) <= 2:
            out.append((len(m.group(1)), _inline(m.group(2)), _slugify(m.group(2))))
    return out


def _anchor_targets(md_text: str) -> set[str]:
    """Every slug something could link to: heading slugs + explicit `<!-- canonical: -->`."""
    targets: set[str] = set()
    for ln in md_text.splitlines():
        m = _HEADING.match(ln)
        if m:
            targets.add(_slugify(m.group(2)))
        ac = _ANCHOR_COMMENT.search(ln)
        if ac:
            targets.add(ac.group(1).lower())
    return targets


def _register_anchors(pdf: DocPDF, md_text: str, toc: list[tuple[int, str, str]]) -> None:
    """Create internal-link ids only for anchors actually referenced (by an in-doc
    `[x](#slug)` link or by the TOC). Link-free docs get an empty map -> identical bytes."""
    targets = _anchor_targets(md_text)
    referenced = {m.group(2).lower() for m in _ANCHOR_LINK.finditer(md_text)}
    referenced |= {slug for _lvl, _t, slug in toc}
    for slug in referenced:
        if slug in targets and slug not in pdf._anchor_links:
            lid = pdf.add_link()
            # Placeholder destination so the link is insertable even though the TOC is laid
            # out before its target heading renders; overwritten with the real page+y then.
            pdf.set_link(lid, page=1, y=0)
            pdf._anchor_links[slug] = lid


def _render_toc(pdf: DocPDF, entries: list[tuple[int, str, str]], usable: float) -> None:
    """A finger-friendly contents index: each entry is a big tappable button (verified to
    jump on the Supernote). Level-2 headings indent and sit slightly smaller."""
    pdf.set_font(FONT, "B", 11)
    pdf.cell(0, 6, "Jump to", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.2)
    for lvl, title, slug in entries:
        lid = pdf._anchor_links.get(slug)
        indent = MARGIN_MM + (lvl - 1) * 5
        width = PAGE_W_MM - indent - MARGIN_MM
        if lvl == 1:
            _link_button(pdf, title, lid, indent, width, h=9.0, size=10.5)
        else:
            _link_button(pdf, title, lid, indent, width, h=7.5, size=9.5)
        pdf.ln(1.6)
    pdf.ln(0.6)
    y = pdf.get_y()
    pdf.set_draw_color(190)
    pdf.set_line_width(0.2)
    pdf.line(MARGIN_MM, y, PAGE_W_MM - MARGIN_MM, y)
    pdf.ln(2.5)


def _section_height(section: list[str], usable: float, doc_format: str = "notes") -> float | None:
    """Render the section into a throwaway PDF to measure its height.
    Returns None if it's taller than one page (can't be kept together)."""
    scratch = _new_pdf(doc_format)
    scratch.add_page()
    start = scratch.get_y()
    _render_lines(scratch, section, usable)
    if scratch.page_no() > 1:
        return None
    return scratch.get_y() - start


def _question_page_lines(qs: list[dict]) -> list[str]:
    """Markdown for the injected page-1 overlay (an open conflict question + answer area).
    Generated from the question store; the source doc is never touched, so no merge can bake
    it in. Deterministic (no timestamps), so it doesn't break mirror's byte-stable output."""
    lines = ["# Needs you — answer below", "",
             "> This doc's last merge wasn't certain. Write your answer under each question,",
             "> then export — it applies on the next sync and this page disappears.", ""]
    for q in qs:
        lines += [f"**Q {questions.id_token(q['id'])}:** {q['question']}", "",
                  questions.CONFIRM_LINE, "",
                  "_Your answer / correction:_", "", "", ""]
    return lines


def _render_body(pdf: DocPDF, sections: list[list[str]], usable: float, bottom: float,
                 doc_format: str) -> None:
    """Render the heading-led sections, keeping each together: if a section won't fit in
    the remaining space (but does fit on a fresh page), page-break BEFORE it rather than
    splitting a heading from its content. Oversized sections render normally. Section
    height is measured by a throwaway render — robust, and handles tables uniformly."""
    for idx, section in enumerate(sections):
        if doc_format == "paged":
            if idx > 0:                  # one section (question) per page: enables deterministic
                pdf.add_page()           # per-page answer detection (no LLM) — see run._process_needs_you
        else:
            h = _section_height(section, usable, doc_format)
            if h is not None and pdf.get_y() > TOP_MARGIN_MM + 0.5 and pdf.get_y() + h > bottom:
                pdf.add_page()
        _render_lines(pdf, section, usable)


def _build(md_text: str, source_label: str = "", doc_format: str = "notes",
           questions: list[dict] | None = None, toc_pref: bool | None = None) -> DocPDF:
    pdf = _new_pdf(doc_format)
    pdf.source_label = source_label
    usable = PAGE_W_MM - 2 * MARGIN_MM
    bottom = PAGE_H_MM - BOTTOM_MARGIN_MM
    sections = _split_sections(md_text.splitlines())
    candidates = _toc_entries(md_text)
    # A TOC entry only earns its place if its heading is on a LATER page than the index — the
    # device won't jump to an anchor already on the visible page (that was the "dead click"). So
    # dry-render the body, see which headings land on page 2+, and list only those. No such
    # headings (a one-page doc) -> no TOC at all. `toc: false` always suppresses.
    toc = []
    if toc_pref is not False and candidates:
        scratch = _new_pdf(doc_format)
        scratch.add_page()
        _render_body(scratch, sections, usable, bottom, doc_format)
        toc = [e for e in candidates if scratch._heading_pages.get(e[2], 1) >= 2]
    want_toc = len(toc) >= 2          # a 1-jump index isn't worth a "Jump to" block
    _register_anchors(pdf, md_text, toc if want_toc else [])
    if questions:
        pdf.add_page()                       # page 1 = question overlay (source untouched)
        _render_lines(pdf, _question_page_lines(questions), usable)
    pdf.add_page()                           # doc content starts on its own page
    if doc_format == "checklist":
        _render_legend(pdf, usable)
    if want_toc and toc:
        _render_toc(pdf, toc, usable)
    _render_body(pdf, sections, usable, bottom, doc_format)
    return pdf


def _render_letterhead(body: str) -> bytes | None:
    """Render markdown through the external branded-letterhead builder set via
    `letterhead_builder` (a Node script taking `<input.md> <output.pdf>`). Returns PDF bytes, or
    None when no builder is configured so the caller falls back to the built-in renderer. A
    configured-but-failing builder raises — a broken branded render should surface, not silently
    ship a mismatched fallback. The round-trip is renderer-agnostic (merge keys off the source
    markdown + manifest, not the PDF), so any valid PDF here is safe for check-in."""
    builder = config.letterhead_builder()
    if builder is None or not builder.exists():
        return None
    with tempfile.TemporaryDirectory() as tmp:
        md_path = Path(tmp) / "doc.md"
        pdf_path = Path(tmp) / "doc.pdf"
        md_path.write_text(body, encoding="utf-8")
        subprocess.run(
            ["node", str(builder), str(md_path), str(pdf_path)],
            cwd=str(builder.parent), check=True, stdout=subprocess.DEVNULL,
        )
        return pdf_path.read_bytes()


def render_bytes(md_text: str, source_label: str = "",
                 questions: list[dict] | None = None) -> bytes:
    """Render to PDF bytes (deterministic for a given source + renderer + questions). A leading
    `---` frontmatter block is parsed for options (e.g. `format:`) and stripped. `questions`
    (open conflict questions for this doc) injects a page-1 overlay; None for normal docs.
    `renderer: letterhead` routes to an external branded builder, except when conflict questions
    are pending (those need the built-in page-1 overlay)."""
    meta, body = _parse_frontmatter(md_text)
    if meta.get("renderer") == "letterhead" and not questions:
        out = _render_letterhead(body)
        if out is not None:
            return out  # else fall through to the built-in renderer
    toc_raw = meta.get("toc")
    toc_pref = None if toc_raw is None else toc_raw.strip().lower() in ("1", "true", "yes", "on")
    return bytes(_build(body, source_label, meta.get("format", "notes"), questions, toc_pref).output())


def render_markdown(md_text: str, out_path: str, source_label: str = "") -> None:
    with open(out_path, "wb") as fh:
        fh.write(render_bytes(md_text, source_label))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--label", default="", help="relative source path shown in the footer")
    args = ap.parse_args()
    with open(args.input, encoding="utf-8") as fh:
        render_markdown(fh.read(), args.output, args.label or args.input)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
