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

## When the user syncs marks (the round-trip — do this every time)

When the user says they've synced/annotated notes, drive every pending `.mark` through the
full loop — don't just read the ink and summarize it back in chat.

- **Every note is a command — no `@claude` tag needed.** Treat every mark as if it were prefixed
  with `@claude`: it's an instruction whose *intent* you carry out, never literal text you splice
  into the printed doc. The user should never have to tag a note to get it acted on. (Enforced in
  the ink-reading prompts — `read_marks.py` rule 4, `read_ink.py` — which now default every mark to
  a command.)
- **Rebuild the doc to honor the notes; don't splice.** Take the notes as authorial intent and
  *rewrite the sections they touch* so the doc comes back as one coherent piece — a worksheet
  answered in the margins returns as a finished document, not an annotated form. Preserve sections
  the notes don't touch and never drop content the user didn't ask to remove; leave derived counts
  to `derive.py`.
- **Act on each mark in the docs, not in chat.** Capture-page to-dos → the project tracker;
  ideas → Needs You; doc edits/answers → merged into the source doc; Open-Question answers →
  written into the doc. The default driver is `./sync.sh run` (drains all pending annotations
  through the real pipeline: read → route → reconcile → consume). Reach for the manual
  per-doc path (`marklayer.py` → edit source → `reconcile._consume_marks` → `mirror.py`) only
  when you need finer control; if you do, replicate what `run.py` does — don't skip steps.
- **Respond to the user in the Needs You doc, never in chat.** Open decisions, clarifying
  questions, and "here's what I applied" go to Needs You as cards via the `ideas` / `questions`
  stores, then `needs_you.build()` + `mirror.py` push them to the device. Chat is for status
  only ("synced N docs, 5 cards in Needs You"). Needs You is **generated** from the stores —
  never hand-edit `NEEDS-YOU.md`; the next mirror rebuilds it.
- **Always consume the marks** (`reconcile._consume_marks` / the pipeline) so they leave the
  queue and don't reprocess. Device-side ink is **not** auto-cleared — say so; the user erases
  it on the tablet (see Gotchas; deleting the Drive `.mark` just makes the device re-upload it).

## Gotchas

- A `.pdf.mark` sidecar is a native Supernote document; ink is read from its layer
  (colour-independent), not by colour-filtering pixels.
- A read `.mark` is logged by content hash (`marks.py`) so device re-uploads don't
  reprocess — don't "fix" that by deleting the mark.
- The renderer maps unicode/emoji to latin-1 (`common.py:sanitize`); it has no emoji glyphs.
- Roadmap and open items: [docs/04-status.md](./docs/04-status.md) and
  [docs/backlog.md](./docs/backlog.md).
