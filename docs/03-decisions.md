# 03 — Decisions (ADR log)  `[claude]`

Why the key choices were made. Newest first.

### ADR-017 — `@claude` instruction marks are repo-aware; plain marks stay single-doc
A plain mark is applied to the one document, faithfully (ADR-010 — apply what's written, don't
editorialize). But an `@claude …` instruction often depends on the rest of the project
("reconcile with the punchlist", "match the new schema"). Decision: when the model carries out an
`@claude` mark it **may read other files in that doc's repository for context** — passed the repo
root in the prompt; the `claude_code` backend is Claude Code (an agent with a Read tool) and reads
by absolute path, so **no cwd change or extra plumbing was needed** (verified: it reads files
outside its working dir). Scope is deliberately narrow: **read-only context, and only for `@claude`
marks** — literal marks stay single-doc and faithful (feeding them the whole repo would invite
over-editing). The agent never modifies other files; its only output is the edited markdown, and
the source change still flows through `reconcile` + a revertible commit (ADR-001). On the `api`
backend (no agent) the read can't happen, so repo-awareness is claude_code-only. This keeps docs
**coupled to their projects** (no decoupled notes repo) and is the foundation for "scribble a task
on the device → run it in the project." Verified live: an `@claude` instruction read a sibling
file in the repo and incorporated it into the edit.

### ADR-016 — Cloud Drive access via `rclone copy`, not a FUSE mount  *(unprivileged container)*
The container reaches Google Drive by **syncing** the Supernote folder to a local working copy
with `rclone copy` (the Drive **API**) — pull device writes before a pass, push rendered PDFs
after — instead of `rclone mount`. Why: *mounting a filesystem* is what forced the **`SYS_ADMIN`**
capability (+ `/dev/fuse`, + `apparmor:unconfined`), which is near-root and the easiest container
→ host escape path; an audit flagged it, and the author may run the box (a Pi) for other things
too. Dropping the mount lets the container run **unprivileged** (`cap_drop: ALL` +
`no-new-privileges`). Bonus: FUSE-in-a-container also requires the *host* to allow `--device
/dev/fuse`, which managed platforms like Fargate refuse — `rclone copy` runs anywhere. Trade:
copies are **additive (no deletes)** so a concurrent device write is never clobbered by a
sync-with-delete; the cost is that consumed exports linger on Drive, which is harmless because
the read-once ledger (`marks.py`) already ignores them. (Running as a non-root *user* is a
further step, deferred — it needs the rclone.conf path + volume ownership reworked.)

### ADR-015 — Cloud git auth: keep the token out of the URL (PAT-via-credential-helper for N repos)
The container needs write access to the notes repo(s). The notes can span **several** repos (one
per `scan_root`), and GitHub deploy keys are **one-per-repo**, so a single deploy-key doesn't
scale. Decision: a **fine-grained PAT** (scoped to those repos, Contents read+write) supplied via
git's **credential helper** — one secret for any number of repos, and the token never lands in a
repo URL, `.git/config`, or log (the helper holds it in a `600` file). Rejected: HTTPS-token-**in
the URL** (`https://user:token@host`), which an audit found leaks into `.git/config` and error
output (→ CloudWatch/journald). For a **single** repo an **SSH deploy-key** is an equally clean
alternative (also no token in URL/log). Defense-in-depth: the backend still redacts
`scheme://user:TOKEN@host` from any diagnostic. (Git auth is for the *notes repos* — unrelated to
the device, which only talks to Google Drive.)

### ADR-014 — Conflict resolution: eager auto-merge, then ask via injected surfaces  *(extends ADR-008)*
A true same-region collision no longer stops at conflict markers. The system (1) **eagerly**
asks Claude to resolve the diff3 and **applies** the result — the doc keeps moving — and (2) if
Claude isn't confident, logs an open **question** for review (it never silently ships an unsure
merge unflagged). Questions surface on two device-facing surfaces, both **generated** from a
sidecar store (`questions.py`): a "needs you" inbox doc, and a page-1 overlay injected at render
onto the conflicted doc. Hard constraint: a question is **never written into the source `.md`** —
only injected at render — so no later merge can bake it in permanently (more robust than
write-then-strip; satisfies "don't let a merge make the question permanent"). A question clears
**only when actually answered**, detected **deterministically by page ink** (`marklayer.has_ink`)
— never by an LLM round-trip and never on an unrelated edit. Page-1 ink on the conflicted doc
answers it in context; the inbox renders **one question per page** (`format: inbox`) so a page
that got ink confirms that question (a page→id order sidecar maps them), and unanswered pages
stay open and come back. So an ignored question is never silently lost, and a partial inbox is
fine.
Mirror folds a question fingerprint into change-detection so the overlay appears/clears even with
no source change. Everything stays a revertible `supernote:` commit (ADR-001). Rejected:
hard-stop-on-conflict (blocks the doc in an unattended loop); writing the question into the doc
(entangles future merges). Author's tuning: auto-merge is **eager** (apply optimistically, flag
when unsure), not conservative.

### ADR-013 — Local-first, with the cloud as a deferring standby
The round-trip can run on the laptop (free, no server) or on an always-on host (for when the
laptop is off). Decision: **local-first** — `sync.sh watch` on the laptop is the primary engine
(both directions + the renderer + the heartbeat), and the container is an **opt-in standby** that
acts only when the laptop is off. Coordination is a heartbeat file: the laptop stamps a hidden
`.laptop-alive` timestamp in the Drive folder (the one medium both machines see) on a dedicated
thread, and the standby stands down while it's fresh, working only once it goes stale — fail-safe
(crashed laptop → stale → standby takes over), no double-processing. The device export is the
trigger either way (a short poll is indistinguishable from event-driven here). Rejected: cloud as
the primary (pays for a server you don't need); a naive heartbeat stamped on the work thread (a
multi-minute read let it go stale → the cloud double-processed — fixed by the dedicated thread).

### ADR-012 — Pluggable AI backend; default the Claude subscription via `claude -p`  *(revises ADR-009)*
ADR-009 planned a hard dependency on the **metered** Claude API for the one model step (reading
ink). Revised: the model call goes through a small pluggable backend (`backend.py`), chosen by
config — `claude_code` (default): shell out to `claude -p` (Claude Code headless), which runs on
the user's Claude **subscription** (no per-token cost, no API key); `api`: the metered Anthropic
SDK (prompt-cached, needs a key), kept for high volume. Why: a personal daily-driver shouldn't
meter every handwriting read, and most users already pay for a subscription. Gotchas that shaped
it: Claude Code is an agent, not a raw completion — asked to "return the doc" it adds commentary,
so the claude_code path has it **write the doc to a scratch file** and reads that back (the same
trick carries the conflict-resolution verdict); `claude -p` blocks on stdin (pass `/dev/null`);
and Claude Code **bills the metered API over the subscription whenever any `ANTHROPIC_*`
credential is visible**, so the subprocess env strips the whole family and `.env` is only loaded
on the `api` backend. Note (2026-06): headless `claude -p` is explicitly allowed on subscriptions
and, from 2026-06-15, draws a separate monthly Agent SDK credit — "included up to a cap," not
literally free.

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
