# 04 — Status  `[claude]`

_Last updated: 2026-06-08_

## Built & working

- **Cloud hub** — bidirectional tablet ⇄ Drive ⇄ computer confirmed.
- **Full Markdown round-trip** — `mirror.py` renders the doc tree → device PDFs;
  annotate by hand in any pen; `marklayer.py` reads the ink from the `.mark` layer;
  `read_ink.py` (Claude) interprets it; `reconcile.py` 3-way-merges into the source;
  re-render. Proven end-to-end on real device exports.
- **Deterministic derivation** — counts/totals recomputed in code (`derive.py`), every
  render + post-merge; read-once ledger (`marks.py`) prevents reprocessing re-uploads.
- **Safety net** — source docs in git + an auto-commit per applied edit (`vcs.py`).
- **De-personalized** — all settings via `config.py` (env / `config.toml` / auto-detect).

### Structured annotation pipeline (2026-06 — targeting/recognition upgrade over `read_ink`)

The holistic `read_ink.py` path (read whole page → apply) mis-*targeted* annotations — it merged
spatially-separate notes and snapped them to the nearest heading. A structured pipeline now reads
ink accurately and anchors each note to the exact line. The OLD path still exists; this is the
accurate replacement for the read+apply half.

- **`doc_lines.py`** — a page's text lines + y-positions via `pdftotext -bbox`. The anchor.
- **`read_marks.py`** (Pass 1) — per-note structured read → `{text, mark_type, target (quoted
  line), command, confidence}`. Sends a **registration-corrected ink-only image** + the line-map
  (NOT the rendered composite — that printed text is the wasteful part). Reads the doc in
  **parallel page-chunks** (`--chunk-size/--workers`, default 3/4) → ~5 min/doc on the Max plan and
  attentive per page (a single 24-image batch under-read a page). Output `{pages:[{page,notes}]}`.
- **`synthesize.py`** (Pass 2) — text-only cross-page pass → threads (`duplicate`/`theme`/
  `doc-command`/`standalone`). Cheap (no images); catches links a per-page read can't (validated:
  a "carbon, not carton" dupe across two pages; a billing theme across five).
- **`apply.py`** — **deterministically** string-matches each note's quoted target to the source
  line (difflib, normalized — no model re-find, so it can't drift to a neighbour) and inserts
  `> 🖊️ <note>`; writes `device/<rel>` for the existing gated 3-way merge. `@claude`/unplaced
  action-notes route to a personal `PUNCHLIST.md` (`config.punchlist()`, gitignored) — never into
  a synced/OSS doc.
- **Registration fix** — `marklayer._align_ink` + `config.mark_align` correct a ~10% vertical
  offset in `supernote-tool`'s `.pdf.mark` raster (its DPI metadata is zeroed) so a mark lands on
  the line it was written over. Per-device, config-overridable.
- **QUIRKS marking conventions** (in the gitignored `handwriting/QUIRKS.md`): leader-line (arrow →
  one target, may be another note) vs bracket (no arrow → spanned lines) vs over-text; **one record
  per note, never merge**.

**Two targeting failure points remain** (backlog): (1) **reader run-variance** — the parallel read
occasionally mis-targets a note the ink-only read got right; today this is caught only at the
review gate (a double-read that flags disagreements would auto-catch it). (2) the apply matcher
needs a *contiguous* target quote — the reader's quotes are; a hand-edited target may not be.
Recognition itself is strong across dense pages.

### Parked: DOCS_AUDIT round-trip (2026-06-08)

`RealtimeMFG/Docs/DOCS_AUDIT.md` (the docs-accuracy audit) was fully **read → synthesized →
applied to `device/<rel>`** (63 notes placed; ① "Yup this should be fixed" → sub-items and ②
"Both these last two" → prod-items both verified). The 2 action-notes (billing/early-adopter
mindset; "make this a punchlist addition") were appended to
`RealtimeMFG/deliverables/PUNCHLIST.md` (a `📥 From Supernote` inbox section, **uncommitted** in
that repo — for triage). **NOT merged into the audit doc** — the pending step is
`./sync.sh reconcile RealtimeMFG/Docs/DOCS_AUDIT.md --apply` (gated for review). The marks JSON
(`checkin_review/DOCS_AUDIT_marks_parallel.json`) + `device/<rel>` are gitignored; re-run
`read_marks` → `apply` to regenerate if lost.

## Roadmap

1. ✅ **General renderer** (`render.py`) — any markdown → clean annotatable PDF
   (headings, lists, code, blockquotes, tables, source-path footer).
2. ✅ **Path-preserving full mirror** (`mirror.py`) — walks the doc tree → PDFs into
   `Supernote/Document/Library/` at matching relative paths; writes `manifest.json`
   (PDF → source path + content hash). First run: 68 docs. `sync.sh mirror`.
3. ✅ **Conflict-safe round-trip** — `mirror.py` snapshots source bytes to `base/`;
   `route.py` (run by `sync.sh in`) detects laptop-side drift (hash vs. base) →
   SAFE or 3-WAY MERGE with the diff; `reconcile.py` (`sync.sh reconcile REL`) does
   the real `git merge-file` 3-way merge of device edits into the source — auto-merges
   non-overlapping regions, surfaces true collisions as conflict markers, and on a
   clean `--apply` snapshots + writes + re-mirrors. See ADR-008.
   *(The only model step is Claude reading the ink into `device/<rel>`.)*
4. ⬜ **Google Doc instruction round-trip** — apply `@claude` edits via the Docs API
   (markdown sources don't cover gdocs; they're not in the mirror yet).
5. ⬜ **Cloud autonomy (Phase B)** — run the pipeline in AWS so it works with the
   laptop shut, and turn the Supernote into a Claude remote (`@claude` task → result
   back). Design (refined 2026-05-27):
   - **Lambda** (EventBridge cron) for the deterministic sync loop — rclone for Drive
     (no Drive Desktop on Linux), extract ink from the `.mark` layer (marklayer.py —
     color-independent, replaces red-isolation), **Claude API (Console key)** reads the
     ink, 3-way merge doc edits, write back. Still open before unattended: read_ink is
     non-deterministic, so cloud "apply" should open a PR/review, not mutate source.
   - **Agentic repo tasks → Claude Code Routines** (cloud-hosted Claude Code, wired to
     the GitHub repo, API-triggerable): Lambda fires `POST /v1/claude_code/routines/
     {id}/fire` with the task text → routine works the repo → **opens a PR (never
     merges)** → Lambda writes a summary doc back to Drive → Supernote. This replaces
     the earlier Fargate/clone/Agent-SDK idea — no compute to manage, native PR-not-
     merge (= never-self-merge), no 15-min cap.
   - Guardrail: code tasks output a **PR** (review on device, merge from laptop);
     other tasks output a **doc**. Propose, never mutate/deploy.
   - Caveats: routines need a **claude.ai subscription** (two Claude touchpoints —
     Console key for vision, subscription for routines); routines are research-preview;
     daily run caps. Secrets in a secrets manager, least-priv IAM.

## Known limitations / rough edges (battle-test punch list)

- ✅ **Stale device `.mark` after reconcile** — FIXED via `marks.py`: reconcile logs
  the read mark's content hash instead of deleting it (the device just re-uploads its
  authoritative ink; deleting causes sync churn). `pending.py`/`mirror.py` ignore any
  hash-logged mark, so a re-upload no longer re-surfaces or PROTECTs the doc. New
  strokes change the bytes → new hash → the doc surfaces again. (Cloud loop will back
  the ledger with DynamoDB/S3.) Remaining: adding strokes to an already-read doc without
  clearing on-device reprocesses the *cumulative* ink — true incremental-ink diffing is
  a separate, larger problem.
- Native `.note` files don't sync to Drive (handwritten notebooks stay device +
  Supernote Cloud only).
- Google Docs take interpreted-instruction edits, not literal positional ink (and
  aren't in the mirror yet).
- Mirror currently scoped via `scan_roots` in config.
- ✅ The ink-reading step is now a Claude API call: `read_ink.py` (vision, `claude-opus-4-7`,
  adaptive thinking, prompt-cached base+quirks) → `device/<rel>`. Hands-off path:
  `sync.sh process <rel> --apply` (read ink → 3-way merge → apply → re-mirror). Needs
  `ANTHROPIC_API_KEY`. This is Phase-B step B1, runnable locally now.

## Pilot content

The documentation standard ([`DOC_STANDARD.md`](./DOC_STANDARD.md)) is being
piloted on a private project.
