# 03 — Decisions (ADR log)  `[claude]`

Why the key choices were made. Newest first.

### ADR-011 — Read ink from the `.mark` layer, not red-pixel isolation  *(supersedes ADR-004)*
A Supernote `.pdf.mark` sidecar is itself a native Supernote document whose strokes live
in a layer separate from the page, so `supernote-tool` extracts them directly — colour-
independent (black pen works as well as red), exact, and with no flattened-export step.
This replaced the earlier "annotate in red, colour-filter the pixels" approach (ADR-004),
which forced a pen colour and was fragile against anti-aliasing. Page mapping comes from
the `.mark` footer's `PAGE<N>` keys; ink is composited over the rendered page for read
context. (`marklayer.py`)

### ADR-010 — The model interprets; code derives
Anything that is a pure function of the document — counts, totals, routing, the merge —
is computed deterministically in code, never by the LLM. Claude is used only for the one
genuinely fuzzy step: reading handwriting and deciding what a mark means. This keeps the
path predictable and removed a class of bug: derived "Quick stats" tallies were drifting
and colliding in the merge until `derive.py` took them over (recomputed from the doc on
every render and post-merge). Same principle behind the read-once ledger — "is this
`.mark` already processed?" is answered in code by content hash (`marks.py`).

### ADR-009 — Open-source intent: battle-test first, MIT, Claude API for vision
Goal: publish this as an open-source product on GitHub (prior art is all one-way
note→text extraction — sn2md, supernote-obsidian-plugin, supernotelib; the
bidirectional doc-review lifecycle with 3-way merge is novel). Decisions (2026-05-27):
**license MIT**; the ink-reading step will **hard-depend on the Claude API** (simplest,
best quality) rather than a pluggable LLM; **don't publish yet** — battle-test on
the author's own docs and fix rough edges first, then genericize. Productization gaps:
(1) genericize hardcoded paths/account → a `config.toml`; (2) turn the
human-in-the-loop ink reading into a Claude API call; (3) README/LICENSE/CONTRIBUTING;
(4) **first-run onboarding with a handwriting-calibration step** — render the key, user
fills + exports it, system reads it and builds that user's `handwriting/QUIRKS.md`
(every user gets a hand-tuned profile); publish into the awesome-supernote list.

### ADR-008 — Concurrency handled as git-style 3-way merge, not locking
Two writers (device ink, laptop edits) to one doc is a merge problem. The manifest's
per-doc source hash is the **merge base**; `mirror.py` also snapshots the exact source
bytes to `base/`. On check-in, `route.py` compares current source hash vs. the base:
unchanged → apply directly (common fast path); changed → 3-way merge, auto-merging
non-overlapping regions and surfacing only true same-region collisions. Rejected hard
locking (rigid, stateful across 68+ docs) and CRDT/OT (overkill — that's for real-time
co-editing). Git snapshots remain the safety net. Resolution logic (the merge itself)
is implemented: `reconcile.py` runs `git merge-file` (base as ancestor), auto-merges
non-overlapping regions, writes conflict markers for true collisions, and on clean
`--apply` snapshots + writes + re-mirrors. The only model step is interpreting the ink
into `device/<rel>`.

### ADR-007 — Path-preserving PDF mirror, not a synced unified filesystem
A generated mirror (walk doc tree → render PDFs at the same relative paths into
the device folder) gives identical desktop/device navigation **and** excludes code
for free (only docs are rendered). Rejected `rclone`-with-filters (one physical
root, code excluded) as too fragile for the gain. Code stays in `~/Projects`,
git-synced.

### ADR-006 — Manifest for trip-back routing
Routing an annotated PDF back to its source is deterministic via a manifest
(PDF → source path + content hash), so it survives renames/moves. Only the
*application* of marks is interpretive.

### ADR-005 — Markdown is source of truth; PDF is derived
The device PDF is never copied back over the source. Marks are read and applied as
edits to the source, which re-renders. Makes the round-trip safe and versionable.

### ADR-004 — Red ink + isolation as ground truth  *(superseded by ADR-011)*
Original approach: user annotates in **red**, and red pixels are isolated from the
printed page as ground truth (naked-eye reading of the full page conflated ink with
printed glyphs). Superseded by reading the `.mark` layer directly, which is colour-
independent. `@claude` prefix still marks instructions.

### ADR-003 — Google Drive as the hub (bidirectional)
The Nomad auto-mirrors its tree to `My Drive/Supernote/` and the sync is
bidirectional (writing to `Document/` reaches the device). Replaced the dead-end
Partner-app container cache. `.note` files do not sync to Drive — acceptable
because nothing originates on the device under the new lifecycle.

### ADR-002 — Single active editor per document
No concurrent edit of the same doc on laptop + device. Eliminates merge conflicts
without a locking system; edits apply to the live source, not a stale copy.

### ADR-001 — Everything is committed before/after every apply
The safety net that makes auto-apply non-scary: source docs live in their own git repo,
each apply makes a `supernote:` commit (`vcs.py`), and a pre-apply snapshot is taken — so
any misread is a one-command `git revert` with a visible diff.
