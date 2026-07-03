# 05 — Backlog  `[claude]`

Captured feature ideas not yet built. Each should have enough detail to pick up cold.

---

## Notes ⇆ documentation as one (the knowledge-architecture direction)

**Captured 2026-06-06 — being researched in a separate instance; flagged here to hand over.**

The guiding idea Cory is converging on: **notes and documentation should be the same thing** —
his thoughts and Claude's instructions living *cohesively* in one place, not split into "my
notes" vs "the project docs." Shape he's leaning toward:

- **Canonical home is the per-project repo.** A project's notes/docs/instructions live *in* that
  project's repo (where the code/work is) — that's the source of truth. This is why we kept docs
  in their projects (multi-repo) and made `@claude` repo-aware (ADR-017).
- **Plus an optional GROUPED / curated view** for Cory's own reading — pulling notes across repos
  into one place to think over them together.
- **But the grouped view is for viewing; edits + instructions made there trickle *back down* to
  the canonical per-project repos.** So you can curate a cross-cutting view without it becoming a
  second source of truth.

Open questions for the research instance: how the grouped view is assembled (symlinks? a
generated aggregate? a manifest of pointers?); how edits in the grouped view route back to the
right repo+file; how this composes with the Supernote sync (which already mirrors per-repo).
Relates to: the multi-repo cloud setup, `@claude` repo-awareness, and the README's "knowledge
architecture for human + Claude collaboration" framing.

---

## Device-origin ingestion (create docs ON the device)

**The gap.** Today the device is review-only: docs originate on the desktop (the `.md` is
the source of truth), `mirror.py` renders them out, and the manifest only knows
desktop-originated docs. A file *started on the Supernote* has no source `.md`, no manifest
entry, no format — `route.py` reports "no manifest entry" and it falls outside the system.
Also: native `.note` notebooks don't sync to the Drive folder we watch (Supernote Cloud
only), so there's a "get it off the device" problem first (relates to the unbuilt cloud-fetch).

**What to build.** A device-origin path that: (1) detects a new device file with no manifest
entry, (2) reads it (handwriting → Claude → Markdown, same `.mark`/vision machinery),
(3) **creates a new source `.md` at a path mirroring where the user put it on the device** —
so folder placement is the information that carries over (drop it in `Books/ch3/` on the
device → `<source_base>/Books/ch3/...`), (4) registers it in the manifest so future
round-trips work.

**Format/frontmatter:** a fresh device doc has none — default to `notes`, or auto-detect
(checkbox-heavy → checklist). The user refines `format:` later on the desktop.

**Open questions:** does the user want creation-on-device at all (real plumbing cost)?
On ingest of an unnamed/unformatted doc, ask on next desktop sync vs. drop in as a default?
How to name the new file. Depends on solving `.note`/cloud-fetch retrieval.

---

## Interactive onboarding + preferences (config wizard)

**Status (2026-06-02): mostly BUILT.** `./sync.sh init` (`onboard.py`) collects paths +
preferences and writes `config.toml`/`.env` — done. Preferences wired: `density` →
render line-spacing, `emoji` → read_ink prompt (`config.emoji/density`). Calibration:
`./sync.sh calibrate` generates the scribble sheet (`calibrate.py` — verified). The
calibration **read-back** (`calibrate read` → builds `QUIRKS.md`) is coded but NOT yet
verified against a real filled sheet (needs the physical device). Remaining: more render
prefs if wanted (font size, margins via density), and proving the read-back end-to-end.

**Goal.** First-run onboarding that walks a new user through setup interactively
(instead of hand-editing `config.toml`), and a way to revisit those answers later.
It collects three kinds of things:

1. **Where things live** (today's `config.toml` keys): `source_base`, `scan_roots`
   (their repos/dirs to mirror), `supernote_root`, the Anthropic key (`.env`).
2. **Preferences / style** (NEW): how rendered docs and Claude-written edits should
   look and feel — e.g.
   - **Emoji usage** — none / minimal / liberal (affects both rendering and how
     Claude writes any notes it adds).
   - **Spacing & density** — compact vs. roomy: line spacing, gap between sections,
     page margins, checkbox size.
   - **Font** — size, and which TTFs to use (the `font_regular`/`font_bold`/`font_italic`
     config keys already exist; the wizard should let the user pick their own).
   - Possibly **Claude's writing style** for notes it inserts — terse vs. verbose, tone.
3. **Handwriting calibration** (NEW, important) — the "scribble test". The system renders
   a calibration sheet (alphabet upper/lower, digits, common words, and the marks the
   reader relies on — checks, strikes, arrows, the circled `@claude`); the user fills it
   in by hand and exports it; Claude reads it back and builds that user's per-user
   `handwriting/QUIRKS.md` profile. See its own section below and ADR-009.

**UX.** A `sync.sh init` (or `python config.py --setup`) command that prompts question
by question, writes the answers to `config.toml`, and is **re-runnable** to update them.
Prompt on first run if no `config.toml` exists. Users who prefer can still hand-edit the
file or use `SUPERNOTE_*` env vars (the resolution order in `config.py` is unchanged).

**Where the new prefs plug in (so this is buildable):**
- Add a `[preferences]` (or `[render]`) table to `config.toml` + accessors in
  `config.py`, same env-override pattern (`SUPERNOTE_EMOJI`, `SUPERNOTE_DENSITY`, …).
- **Spacing/density/font** → `render.py` + `common.py`, which currently hardcode the
  layout constants (`PAGE_W_MM`, `PAGE_H_MM`, `MARGIN_MM`, line heights). Make those
  read from preferences.
- **Emoji** → today `common.py:sanitize()` *strips* emoji to ASCII because the embedded
  font has no emoji glyphs (`✅`→`[x]`). An "emoji" preference interacts with that
  constraint — resolve whether to (a) keep stripping, (b) bundle an emoji-capable font,
  or (c) only govern emoji in Claude's *written* output, not the rendered glyphs.
- **Claude writing style** → inject the preference into the `read_ink.py` system prompt
  so notes it adds match the user's chosen tone/emoji level.

### Handwriting calibration (the scribble test)

The reader is only as good as its model of *your* hand. Onboarding should run a one-time
(re-runnable) calibration:

1. **Render a calibration sheet** — a generated PDF with prompts to hand-write: the
   alphabet (upper + lower), digits 0–9, a set of common/ambiguous words, the user's own
   shorthand if they list any, and a row of the *marks* the reader acts on (check, X,
   strike-through, margin arrow, the circled `@claude`).
2. **User fills it in on the device and exports it** (same `.mark`-layer path as any doc).
3. **Claude reads it back** against the known prompts (it knows what each cell *should*
   say), and from the gap between expected and observed builds a profile: which letters
   this person confuses (e.g. `w`↔`v`, `a`↔`o`), how they form digits, their shorthand,
   and how their marks look. Writes/updates `handwriting/QUIRKS.md` (today shipped only
   as `QUIRKS.example.md`; each user generates their own, gitignored).
4. **Re-runnable** to refine over time, and additive — later "tests" can target the
   specific confusions the reader keeps getting wrong (a feedback loop, not a one-shot).

This is the mechanism behind ADR-009's "every user gets a hand-tuned profile." It plugs
into the existing `.mark` read path (`marklayer.py` → `read_ink.py`) — the only new parts
are the calibration-sheet generator and the expected-vs-observed diff that writes QUIRKS.

**Open questions to settle when building:**
- Emoji rendering constraint above (font vs. strip vs. text-only).
- Which knobs are worth exposing vs. sensible-default-only (avoid an overwhelming wizard).
- Whether device geometry (page size for non-Nomad models) belongs in the same wizard.
- Calibration sheet content/length — enough to be useful without being a chore.

**Why deferred:** sequenced after the Phase-B / open-source groundwork; it builds
directly on the `config.py` layer (see [`config.py`] and the de-personalization work).

---

## Automated digests + daily reading docs

**Status (2026-06-02): BUILT.** `digest.py` + `./sync.sh digest [NAME]`. Configurable via
Markdown **recipe** files in `digests/` (gitignored; templates in `examples/digests/`):
frontmatter sets `days` (daily/mon-fri/mon,wed/…), `sources` (folders to summarize),
`review` (docs to read in full + critique), `out` (where it lands under source_base); the
body is the user's plain-language instructions to Claude. Gathers git activity since the
recipe's last run (tracked in `digest_state.json`; first run = 7 days), reads the review
docs, calls Claude, writes `<out>/<name>-<date>.md` (mirrors to device). Verified end-to-end
EXCEPT the live Claude call (the account is out of API credits). Remaining: auto-scheduling
(the container/cron) + digest archiving/retirement.

**Goal.** Auto-generate short summary docs and push them to the device as a quick daily
read — open the Supernote in the morning and skim what changed, what's new, what needs
attention. Per-folder (a daily digest for a given project/area) and/or one global digest.

**What to digest.** Recent changes across the doc tree, git activity in the source repos
(commits, merged PRs), status-doc deltas, open items pulled from punch-lists, anything new
or updated since the last digest. The content is *derived*, so it's `[auto]` — generated,
never hand-edited.

**Mechanism.** A scheduled job (the Phase-B cron/Lambda) gathers the sources (git log,
changed files, the relevant status/punch-list docs), Claude summarizes, writes a generated
doc (e.g. `daily/2026-06-03.md` or a per-folder `DIGEST.md`), and `mirror.py` renders it to
the device like any other doc. Old digests sweep to an archive so the live view stays lean.

**Open questions.** What goes in (and per-folder vs. global); cadence (daily? on-change?);
where generated docs live and how they're named/retired; how much the user can tune the
digest's focus (a preference, see the onboarding wizard).

---

## Backend rate-limit throttle (subscription safety)

**The gap.** `claude -p` on a Claude subscription shares short-window/concurrency rate limits
(before 2026-06-15, the interactive 5-hour + weekly caps; concurrency ~3–4 sessions). Firing
many calls in a burst trips a "rate limit" error far below the monthly cap. `run.py` already
drains serially so it won't burst on its own — but a future caller (parallel docs, a fan-out)
could. Deferred 2026-06-03: Cory has never neared the limit, so not needed yet.

**What to build (when limits actually bite).** A small throttle in `backend.py`: a minimum
gap between `claude -p` calls and/or a concurrency=1 guard, plus retry-with-backoff on a
`rate_limit` error (Claude Code emits a `system/api_retry` event with `error: rate_limit`).
Cheapest version: a process-wide lock + sleep so no two reads ever overlap.

---

## Unattended conflict backoff (container)

**The gap.** When a doc is edited on both the laptop and the device in the same place,
`reconcile` leaves it as a conflict (markers in `merge_out/`, not applied) and it stays
pending. On the always-on container (`deploy/`) nobody resolves it interactively, so every
loop tick re-attempts it — spending one `claude -p` read each time with no progress, until a
human fixes the source. Found in the deploy audit (2026-06-03).

**What to build.** A small backoff/skip: record conflicted `(rel, mark-hash)` and stop
re-reading that exact pair until the source or the ink changes (the marks-ledger pattern,
but for "seen-and-conflicted" rather than "applied"). Or surface conflicts out of the
container (a digest line / notification) so they get resolved instead of silently retried.

---

## Document linking (programmatic vs. on-device)

**Goal.** Links between docs that work *on the device* — a punch-list item that points to
its detail doc, an index that jumps into a chapter — tappable on the Supernote.

**The question to answer.** Can inter-doc links be done **programmatically** (baked into
the rendered PDFs — internal anchors + links from one mirrored PDF to a sibling PDF), or
**only via the Supernote's own on-device linking UI**? Today `render._inline` strips
`[text](url)` down to just `text` (no link), so links render as plain text.

**To explore.** (1) `fpdf2` link support — internal anchors, external URLs, and whether it
can emit a link to another file. (2) Whether the **Supernote honors** links to other PDFs
in the mirrored tree (path-based: `[detail](other.md)` → opens `other.pdf` on the device).
(3) The path mapping (`.md` link target → the rendered `.pdf` at the mirrored path).
(4) Round-trip safety — links are source content and must survive annotation/merge.

**Why it matters / open.** If cross-PDF links work on the device, the punch-list →
detail-doc navigation (the `deliverables/` model) becomes real on the Supernote, not just
on the desktop. On-device feasibility is the unknown — needs a hardware test.

---

## Ask `@claude` a question in a doc (RAG over the tree)

**Goal.** Handwrite a *question* on the device — `@claude what's blocking the migration?` —
and on check-in Claude searches/reads the relevant docs and writes the **answer inline**
(with sources), instead of editing. A natural extension of the existing `@claude` *command*
(which does edits): when the marked instruction is a question, answer it.

**Key point (cost).** At this scale, **no vectorizing/embeddings needed** — Claude can just
be handed the relevant docs (or the whole small tree, or an agentic grep-then-read) and
answer in one cheap call. Embeddings/semantic-index only earn their cost at thousands of
pages (see the search-box item). So this is a small feature, not a pipeline.

**Build sketch.** In `read_ink`, detect a question-form `@claude` mark; gather candidate
docs (by folder / agentic search); add them to the prompt; have Claude write the answer at
that spot in the source. Round-trips like any other edit.

---

## Semantic search box (someday — a fuller productivity tool)

**Goal.** A search box that matches *meaning* not keywords ("budget" → finds "expenses",
"runway"): chunk each doc, embed it, find nearest to the query → ranked snippets + jump
links. Deferred — only worth the embedding-index overhead when the corpus is large and you
want a real query surface (i.e. if this grows into a full productivity tool). The cheaper
"ask Claude a question" path above covers the near-term need.

---

## Structured annotation pipeline — residuals (2026-06-08)

The `read_marks` → `synthesize` → `apply` pipeline (see 04-status) works and is in use; two
targeting gaps + one orchestration nicety remain:

1. **Reader run-variance → double-read + disagreement flag.** `read_marks` (parallel) occasionally
   mis-targets a note a prior read got right (e.g. "Yup this should be fixed" → dashboards vs. the
   correct sub-items line). **Confidence alone won't catch it** — the bad target was ~0.75-confident.
   The catchable signal is *disagreement between two reads*. Build: run targeting twice and flag
   notes whose target differs → focused review. Cost ~2× read. Until then the review gate is the
   only backstop — and it only catches a *plausible-but-wrong* target if the reviewer has ground
   truth (surfaced 2026-06: a wrong target would have merged unnoticed otherwise).
2. **`apply` matcher robustness.** `apply` string-matches the reader's quoted target to the source
   line (difflib + containment). It needs a *contiguous* quote; the reader's quotes are, but a
   hand-edited / non-contiguous target falls to "unplaced." Add a token-overlap fallback so a
   non-contiguous-but-clearly-matching target still anchors.
3. **One-command orchestration.** Wire `read_marks` → `synthesize` → `apply` into a single
   `sync.sh` verb (e.g. `process2 <doc>`) so the structured round-trip runs in one shot (today it's
   three commands). Pairs with the existing `sync.sh process` (old holistic path).
4. **Re-mirror only the changed doc on reconcile.** `reconcile --apply`'s final step re-mirrors the
   *entire* tree (242 docs across 6 repos, ~8 min) when only the one merged doc changed. The merge
   itself is instant; the full re-render is the whole wall-clock cost. `mirror.py` already skips
   unchanged docs by content hash — but reconcile still walks all of them. Add a targeted re-mirror
   (just `<rel>`'s PDF + base + manifest entry) for the single-doc reconcile path; keep the full
   sweep for `sync.sh mirror`. Pure speed; no behavior change.
