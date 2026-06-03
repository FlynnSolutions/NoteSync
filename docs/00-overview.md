# 00 — Overview  `[human]`

**What:** a system that makes every non-code document reviewable and annotatable
on a Supernote Nomad, kept in sync with Google Drive and the Mac.

**Why:** The author steers code via documentation rather than writing it. The docs need
to be reviewable anywhere — including mornings at a coffee shop with only the
Supernote — with notes and instructions flowing back into the source.

## The workflow it enables

1. Documents (markdown, Google Docs, etc.) live in Google Drive / the project tree.
2. A path-preserving renderer mirrors them → PDFs into the device-synced Drive
   folder, at the **same relative paths** — so the Supernote navigation is
   identical to the desktop. Code is excluded.
3. On the device, you browse the whole tree, read, and annotate in **any pen**
   — including `@claude …` instructions.
4. On export, annotations are read from the `.mark` layer (colour-independent),
   routed to the exact source via the manifest, and 3-way-merged into the Markdown.
5. Re-render → the updated docs reappear on the device. One lifecycle.

(Google-Docs sources and `@claude`-instruction round-trips are sketched in the
roadmap, not yet built — see [04-status](./04-status.md).)

## Scope & boundaries

- **In:** markdown, docs, research, status, to-dos — anything non-code.
- **Out:** code files (stay in `~/Projects`, synced by git, never uploaded).
- **Source of truth:** the markdown/source doc. The PDF on the device is always
  *derived*; it is never copied back over the source.

## Status

The Markdown round-trip over the full document tree works end-to-end. Cloud
autonomy (running unattended) is in progress — see [04-status](./04-status.md).
