# 01 — Architecture  `[claude]`

## Components

| Piece | Role |
|-------|------|
| Cloud sync folder | The hub. Bidirectional with the tablet (its `Supernote/` folder) and mirrored to the computer (reference: Google Drive for Desktop). Path is configurable. |
| `config.py` | Single source of truth for settings (env `SUPERNOTE_*` > `config.toml` > auto-detect). |
| `render.py` / `export.py` | Render any Markdown → tablet-shaped PDF (headings, lists, code, tables, footer). |
| `mirror.py` | Walk the source tree → PDFs into the device folder at matching paths; write the manifest; snapshot source bytes to `base/`; re-derive counts. |
| `marklayer.py` | Extract ink straight from the `.mark` annotation layer (`supernote-tool`) and composite it over the source page. |
| `read_ink.py` | Claude reads the ink (vision) against the page + a handwriting profile → interpreted Markdown. |
| `reconcile.py` | 3-way merge the device's interpreted edits into the live source. |
| `derive.py` | Recompute derived counts/totals deterministically from the doc. |
| `marks.py` | Ledger of already-read annotations (by content hash). |
| `vcs.py` | Auto-commit each applied edit to the docs repo (revertible restore points). |
| `pending.py` / `route.py` | Find pending annotations / route an export back to its source via the manifest. |
| `sync.sh` | `out` / `mirror` / `in` / `process` / `reconcile` / `snapshot` / `status` orchestration. |

## The round-trip

```
 source.md ──render──▶ Supernote/.../source.pdf ──annotate (any pen)──▶ source.pdf.mark
     ▲                                                                        │
     └──── 3-way merge into source ◀── Claude reads ◀── ink from .mark layer ◀┘
                        │
                    re-render ▶ updated PDF back on device
```

## Detecting the right file (the trip back) — the key reliability concern

Two halves, deliberately separated:

- **Routing — deterministic.** The mirror preserves relative paths *and* writes a
  **manifest** recording, per rendered PDF: its source path, a content hash of the
  source at render time, and the render timestamp. On check-in an annotated PDF is
  matched to its source by manifest lookup (path + hash), so routing is exact even
  if files moved. (`route.py`)
- **Application — interpretive.** Reading ink → edits is the one fuzzy step; made
  safe by the safety net below. Everything that *can* be deterministic (counts,
  routing, merging) is — only the handwriting read uses the model.

## Safety net (why interpretive edits are trustworthy)

1. **Source Markdown is always truth; the PDF is derived.** Source is never
   blind-overwritten by a copy.
2. **Real 3-way merge.** Device edits merge into the *current* source with the
   original render as the common ancestor, so a doc edited on the computer meanwhile
   isn't clobbered — and genuine collisions surface as conflict markers in `merge_out/`
   rather than auto-applying.
3. **Everything is committed + revertible.** Source docs live in git; every applied
   edit is its own `supernote:` commit (`vcs.py`), and a pre-apply snapshot is taken.
   A misread is a one-command `git revert` with a visible diff.
4. **Ink from the layer, not pixels.** Strokes come from the `.mark` layer, isolated
   from the printed page by the file format — colour-independent and exact, so Claude
   acts only on what was actually written.
5. **The model interprets; code derives.** Counts/totals are recomputed in code
   (`derive.py`), never guessed — so they can't drift or become a conflict.
6. **Read-once ledger.** A processed `.mark` is logged by content hash (`marks.py`),
   so a device re-upload of the same ink never reprocesses or freezes the doc.

## Format-specific round-trip fidelity

- **Markdown** — full fidelity. Marks + `@claude` instructions → regenerated source.
- **Other originals (PDF/docx)** — read + annotate + capture; no in-place source edit.

## Dependencies

Python: `fpdf2`, `supernotelib`, `Pillow` (see `requirements.txt`). System: `poppler`
(`pdftoppm`). Font: DejaVu Sans bundled in `assets/fonts/` (override via config).
