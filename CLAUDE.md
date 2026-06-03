# CLAUDE.md

Context for working on this repo with Claude Code (or any AI assistant).

## What this is

Edit Markdown notes by hand on a Supernote tablet; the strokes are read from the `.mark`
layer, interpreted by Claude, and 3-way-merged back into the source Markdown. See
[README.md](./README.md) and [docs/01-architecture.md](./docs/01-architecture.md).

## Where things are

| Concern | File |
|---------|------|
| Settings (paths, model, fonts) | `config.py` |
| Render Markdown → device PDFs + manifest | `mirror.py`, `render.py`, `export.py` |
| Extract ink from the `.mark` layer | `marklayer.py` |
| Read handwriting via Claude | `read_ink.py` |
| 3-way merge into source | `reconcile.py` |
| Deterministic counts | `derive.py` |
| Read-once ledger / auto-commit | `marks.py`, `vcs.py` |
| Orchestration | `sync.sh` |

## Conventions (please follow)

- **The model interprets; code derives.** Use the LLM only for reading handwriting.
  Counts, routing, and merges are deterministic code — never have the model compute them.
- **Never hardcode paths or settings.** Everything machine/user-specific resolves through
  `config.py` (`SUPERNOTE_*` env → `config.toml` → default). Don't reintroduce literal
  `~/...` or account-specific paths.
- **Lint before committing:** `ruff check .` (config in `pyproject.toml`). Keep it green.
- **No test suite, by design.** Don't add one unless the scope grows materially.
- **Gitignored = personal.** `config.toml`, `.env`, `handwriting/QUIRKS.md`, `snapshots/`,
  and the user's notes repo never get committed.

## Gotchas

- A `.pdf.mark` sidecar is a native Supernote document; ink is read from its layer
  (colour-independent), not by colour-filtering pixels.
- A read `.mark` is logged by content hash (`marks.py`) so device re-uploads don't
  reprocess — don't "fix" that by deleting the mark.
- The renderer maps unicode/emoji to latin-1 (`common.py:sanitize`); it has no emoji glyphs.
- Roadmap and open items: [docs/04-status.md](./docs/04-status.md) and
  [docs/backlog.md](./docs/backlog.md).
