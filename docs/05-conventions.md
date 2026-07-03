# 05 — Conventions  `[claude]`

How a Markdown doc controls the way it renders to the device. Two ideas: **most things
style automatically from content**, and a short optional **frontmatter** block unlocks the
rest. The tool is content-agnostic — these are conventions, not requirements, and they
work in any folder.

## Checkboxes style themselves (no setup)

Any Markdown task item renders as a real checkbox on the device — in *any* doc, with no
frontmatter. The single-character marker picks the glyph:

| You write | Renders as | Means |
|-----------|-----------|-------|
| `- [ ]` | empty box | to do |
| `- [~]` | box with `/` | in progress |
| `- [x]` | box with `X` | done |
| `- [!]` | box with `!` | deferred |
| `- [-]` | box with `-` | dropped |

So a plain notes file with a few `- [ ]` lines already looks like a checklist. Wrapped
item text aligns to the right of the box, not under it.

## Frontmatter — optional, and never shown on the PDF

For anything beyond the defaults, add a small block at the very top of the file, between
two `---` lines:

```markdown
---
format: checklist
---

# My doc
...
```

The renderer **parses and strips** this block — it does **not** appear on the device PDF
(just like Obsidian/Jekyll). You only see it in the raw `.md` on your computer, and it
survives the annotation round-trip untouched (it's instructions, not content). Most docs
need no frontmatter at all.

### `format:` — the document profile

| `format:` | What it does |
|-----------|--------------|
| `notes` *(default)* | General rendering: headings, lists, code, tables, blockquotes; footer shows the source path. |
| `checklist` | Same, plus a faint **status legend** at the top (the marker key above). For punch-lists / trackers. |
| `book` | Prose reading: a clean **page-number-only** footer (no source path), for long-form docs and chapters. |

(Checkboxes auto-style under *every* format — `checklist` only adds the legend.)

## Folders carry no meaning to the renderer

Where a doc lives is up to you; the renderer never inspects the path for behavior. Folder
structure is for *your* navigation (it's mirrored to the device verbatim). See
[`RECIPES`](../RECIPES.md) for useful structures — a punch-list, a book, reviewing a repo's
docs — each is a suggestion, not a rule.

## Annotating: every note is an instruction

You don't tag anything — Claude treats **every mark as if it were prefixed with `@claude`**. It
carries out what the note *intends* (not the literal words), rebuilds the sections you touch so
the doc comes back finished rather than annotated, and reads the rest of the repo for context
whenever a note needs it. Sections you didn't touch — and derived counts — are left alone.

- **Check / strike / status marker** → done / remove, applied as-is.
- **Margin note or directive** ("tighten this", "reconcile with the punchlist") → carried out,
  with whole-repo awareness when the change depends on information beyond this page.
- **New lines in a blank area** → folded in as new content.

`@claude` is still honored as optional emphasis but is no longer required.
Repo-awareness runs on the `claude_code` backend (the default). See ADR-017.
