# supernote-sync

Edit your Markdown notes by **hand on a Supernote e-ink tablet**, and have the
changes flow back into the source files automatically — checkboxes ticked, lines
struck, margin notes applied — read by Claude from your actual handwriting.

Your Markdown is the source of truth. The tool renders it to PDFs on the device,
you annotate in ink, and on check-in it extracts your strokes, has Claude interpret
them, and 3-way-merges the result back into the source. Write in **any pen colour**;
counts and tallies stay correct on their own; every automated edit is a revertible
git commit.

```
   render (mirror)                annotate by hand            read ink (.mark layer)
 Markdown ──────────► PDF on Supernote ──────────► your ink ──────────► Claude reads it
    ▲      source = truth      │  (Google Drive sync)      │                    │
    │                          ▼                           ▼                    ▼
    └────────── 3-way merge into source ◄── recompute derived counts ◄── interpret + apply
                (auto-commit, revertible)
```

## Why it works the way it does

- **Markdown is canonical.** The PDF on the device is a disposable view; edits are
  folded back into the `.md` and a fresh PDF is re-rendered.
- **Ink comes from the `.mark` layer, not pixels.** A Supernote annotation sidecar
  (`<doc>.pdf.mark`) is a native Supernote document whose strokes live in a layer
  separate from the page — so we extract them directly with `supernote-tool`. This is
  **colour-independent** (black pen works as well as red) and exact, with none of the
  fragility of trying to colour-filter a flattened export.
- **The LLM interprets; code derives.** Claude only does the genuinely fuzzy part —
  reading handwriting and deciding what a mark *means*. Anything that's a pure function
  of the document (e.g. a "Quick stats" tally of `[x]`/`[ ]`/`[!]` items) is recomputed
  deterministically in code, so it can't drift or become a merge conflict.
- **Conflict-safe + revertible.** Device edits and desktop edits are reconciled with a
  real 3-way merge (true collisions surface as conflict markers rather than auto-
  applying). Source docs live in git, and every automated edit is its own commit.

## Requirements

- **Python 3.11+** (uses `tomllib`)
- **poppler** — provides `pdftoppm` (`brew install poppler` / `apt install poppler-utils`)
- **An Anthropic API key** — for the handwriting read (`ANTHROPIC_API_KEY`)
- **A Supernote tablet** synced to a cloud folder your computer can see (the reference
  setup is Google Drive for Desktop; any path works via config)

## Setup

```bash
git clone <this-repo> supernote-sync && cd supernote-sync
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# Config: copy the example and edit it (config.toml is gitignored).
cp config.example.toml config.toml      # set source_base, scan_roots, supernote_root

# API key:
cp .env.example .env                     # paste your Anthropic key

# Put your notes under version control so every auto-edit is revertible:
git -C "$(python config.py source_base)" init   # if not already a repo
```

It renders out of the box with the bundled **DejaVu Sans**. To use your own font, point
`font_regular` / `font_bold` / `font_italic` in `config.toml` at your TTFs.

Every setting can also be supplied via environment (handy for headless/cloud runs),
which overrides `config.toml`: `SUPERNOTE_SOURCE_BASE`, `SUPERNOTE_SCAN_ROOTS`
(comma-separated), `SUPERNOTE_ROOT`, `SUPERNOTE_MODEL`, `SUPERNOTE_CHECKLIST`.

## Usage

```bash
./sync.sh mirror                 # render the whole notes tree -> PDFs on the device
#   ... annotate a doc by hand on the tablet, then "Export with annotations" ...
./sync.sh in                     # extract your ink, route it, report any drift
./sync.sh process <rel> --apply  # Claude reads the ink -> 3-way merge -> apply -> re-render
./sync.sh status                 # show the device Document/ and EXPORT/ folders
```

- `<rel>` is the source path relative to `source_base`, e.g. `notes/todo.md`.
- Run `process` without `--apply` first to preview; it only writes with `--apply`.
- A clean merge applies and re-renders; a real collision writes conflict markers to
  `merge_out/` for you to resolve, then re-mirror.

## How the round-trip works

1. **`mirror`** walks `source_base` (limited to `scan_roots`), renders each Markdown doc
   to a tablet-shaped PDF at the matching path under the Supernote sync folder, snapshots
   the exact source bytes to `base/`, and writes `manifest.json` (PDF → source + hash). It
   also recomputes any self-labelled count lines so tallies stay honest.
2. **You annotate** the PDF on the device in any pen, then *Export with annotations* —
   the explicit "I'm done" signal.
3. **`in`** pulls your strokes straight from the `.mark` layer (`marklayer.py`), composites
   them over the source page for context, and routes the doc back to its source, flagging
   whether the source also changed on the desktop (`route.py`).
4. **`process`** has Claude read the ink against the page + a handwriting-quirks profile
   (`read_ink.py`), then 3-way-merges its interpretation into the live source with the
   original render as the common ancestor (`reconcile.py`). Counts are re-derived, the
   edit is committed, and the doc re-renders to the device.

Once a `.mark` has been read it's logged by content hash (`marks.py`), so the device
re-uploading the same ink never reprocesses or freezes the doc.

### Marks vs. `@claude` instructions

How you annotate decides how the edit is applied:

- **A plain mark** — a check, a strike, a margin note, lines written in a blank area — is
  applied **literally, to that one document**: exactly what you wrote, with no awareness of the
  rest of the repo. This is the safe default and keeps edits faithful.
- **Prefix a note with `@claude`** — e.g. `@claude reconcile this with the punchlist`, or
  `@claude update this section to match the new schema` — and Claude **carries the instruction
  out with awareness of the whole repository the doc lives in**: it reads the relevant files in
  that repo for context, then applies the edit. **Use `@claude` whenever the change depends on
  information elsewhere in the project, not just this page.**

(The `@claude` text is treated as an instruction, not transcribed into the doc; case doesn't
matter. Repo-awareness uses the `claude_code` backend — the default.)

## Document formatting

It syncs *any* Markdown tree — folders carry no special meaning. Two light conventions:
- **Checkboxes style themselves** — `- [ ]` / `[~]` / `[x]` / `[!]` / `[-]` render as real
  boxes on the device, in any doc, no setup.
- **Optional frontmatter** — a `---` block at the top (parsed and **stripped**, never shown
  on the PDF) tunes a doc: `format: checklist` adds a status legend, `format: book` gives a
  clean prose layout. Most docs need none.

See [`docs/05-conventions.md`](./docs/05-conventions.md) for the details and
[`RECIPES.md`](./RECIPES.md) for worked structures (a punch-list, a book, reviewing a repo's
docs) with runnable [`examples/`](./examples/).

## Project layout

| File | Role |
|------|------|
| `config.py` | All environment/user settings (env > `config.toml` > auto-detect) |
| `mirror.py` | Render the notes tree → device PDFs + manifest |
| `marklayer.py` | Extract ink from the `.mark` layer, composite over the page |
| `read_ink.py` | Claude reads the handwriting → interpreted Markdown |
| `reconcile.py` | 3-way merge device edits into the source |
| `derive.py` | Recompute derived counts/totals deterministically |
| `marks.py` | Ledger of already-read annotations (by content hash) |
| `vcs.py` | Auto-commit each applied edit (revertible restore points) |
| `pending.py` / `route.py` | Find pending annotations / route back to source |
| `render.py` / `export.py` | Markdown → tablet-shaped PDF |
| `sync.sh` | One-command orchestration of the above |

Design notes and decisions live in [`docs/`](./docs/).

## Status

The local check-out/check-in loop is complete and battle-tested. Running it unattended
(so it works with the laptop shut) is designed but not yet deployed — a persistent
container that rclone-mounts Drive and runs the loop; see
[`deploy/HOSTING.md`](./deploy/HOSTING.md) and [`docs/04-status.md`](./docs/04-status.md).

## License

MIT — see [LICENSE](./LICENSE). The bundled DejaVu Sans font is under its own permissive
license ([assets/fonts/DejaVu-LICENSE.txt](./assets/fonts/DejaVu-LICENSE.txt)).
