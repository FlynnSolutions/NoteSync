# Documentation Standard

A shared skeleton every codebase under `~/Projects/` follows, so navigation is
**identical everywhere** — desktop, Google Drive, and the Supernote mirror — and
so the documentation (not the code) is the reliable instrument for steering work.

Lives here (versioned with the doc-lifecycle system) and is pointed to from the
cross-project index [`BRAINS.md`](../../BRAINS.md) so it's discoverable from
anywhere. `BRAINS.md` indexes cross-project *knowledge*; this file defines the
cross-project *documentation shape*.

## Why this exists

Code is increasingly written by Claude, not by hand. That makes the **docs about
the code the primary lever** — how the human stays oriented, reviews state, and
directs changes (often from the Supernote, away from the machine). A consistent,
navigable structure is therefore load-bearing, not nice-to-have.

## The layered skeleton

Documentation is **fractal**: the same shape at the system level and, for larger
projects, repeated lightly per component (repo / sub-app).

### System level — one `docs/` (or equivalent) per project

| Slot | File | Purpose |
|------|------|---------|
| Overview | `00-overview.md` | What this is, who it's for, status at a glance |
| Architecture | `01-architecture.md` | Components and how they connect |
| Data model | `02-data-model.md` | Entities, schemas, contracts |
| Decisions | `03-decisions.md` | ADR log — *why* choices were made |
| Status | `04-status.md` | **Where we're at**: active work, done, next |
| Conventions | `05-conventions.md` | Patterns, standards, gotchas |
| Runbook | `06-runbook.md` | How to run / deploy / test |
| Glossary | `07-glossary.md` | Domain language — shared vocabulary |
| Index | `INDEX.md` | "You are here" map of all docs + gaps |

Additional high-value slots as needed: `open-questions.md` (undecided, distinct
from decided), `risks.md` (known issues / tech debt), `integrations.md`
(external boundaries).

### Work tracking — a `deliverables/` hub

The **Status** slot answers "where we're at" in prose. Projects with real
ongoing work (a live to-do list, client commitments, a shipped history) get a
dedicated structure for it — the working surface of the Status slot:

| Piece | File / shape | Purpose |
|-------|--------------|---------|
| Master list | `PUNCHLIST.md` | The owner's one daily driver across everything, sectioned **Priority / In Progress / Backlog / Recently shipped**. Source of truth for what *you're* working on. |
| Engagement | one folder per client/initiative (e.g. `<client>-<date>/`) | `SCOPE.md` (frozen, what was committed) + `CHECKLIST.md` (live tracker, canonical within the engagement) + `OPEN.md` / `COMPLETED.md` (reporting cuts refreshed from the checklist). |
| Archive | `archive/` | Per-release shipped batches (`shipped-vX.Y.Z.md`, swept on each ship) + whole engagements graduated once closed. Keeps the live docs lean. |

Direction of truth: the master list is where you prioritize across everything;
engagement folders hold authoritative per-item detail and are the surface you
report from. Pull engagement items *up* into the master list as you commit; link
the bulk backlog rather than duplicating it, so the two don't drift.

### Component level — a lighter `docs/` per repo/area

`00-overview.md`, local architecture notes, `04-status.md`, gotchas. Just enough
to orient someone (or Claude) working in that component.

## Maintenance labels — what keeps a big tree from rotting

Every doc declares an owner in its frontmatter or first line:

- **`auto`** — Claude regenerates from code/git (e.g. a module map, `04-status`).
  Can't drift; never hand-edit.
- **`claude`** — Claude maintains as it works (architecture, decisions).
- **`human`** — you own it (conventions, glossary, priorities).

The `auto` + `claude` layers stay current on their own; only the small `human`
core needs discipline.

## Provenance & canonical sources — no copy without a pointer

Docs constantly reference, derive from, and consolidate each other. Left unmarked,
that drifts: you can't tell the source from a derived view, consolidation duplicates
content, and links rot. The discipline (rationale, tooling, and worked cases in
[`research/doc-provenance-convention.md`](./research/doc-provenance-convention.md)):

- **One canonical home per fact.** Exactly one doc/section is the place a fact is
  *edited*. A canonical doc carries no special marker — **absence of `derived_from`
  means canonical.**
- **Reference, don't copy.** Everywhere else links to the canonical. Only copy content
  into a derived view when you must (a consolidated `PUNCHLIST`, an e-ink mirror), and
  then mark it non-canonical and edit it **only at the source**.
- **Declare provenance in frontmatter** on any derived view:

  ```yaml
  derived_from:
    - path: ../ops/LEARNINGS.md#auth-retry-policy
      at: 7c868f2          # canonical's git short-SHA when last synced (drift sentinel)
  kind: consolidation       # consolidation | summary | mirror | view
  ```

- **Moving content = moving canonicality.** When a plan absorbs a task-list item, the
  plan section becomes canonical and the origin becomes a pointer link — never two
  editable copies.
- **No transclusion / embeds** — they degrade to raw syntax on the e-ink mirror. Plain
  Markdown links only (they degrade to a readable path). Frontmatter is stripped on
  render, so provenance never shows on the device.

Plain Git can't auto-*propagate* a canonical change to its derived views, so the
system **detects** drift instead: a link/anchor checker (`lychee`) plus a small
provenance lint that flags any derived view whose `at:` SHA has fallen behind its
canonical. Smallest enforcement that works; no heavyweight platform.

## How it reaches the Supernote

A path-preserving renderer mirrors this tree → PDFs into the device-synced Drive
folder at the **same relative paths**, so the Supernote navigation matches the
desktop exactly. Code is never rendered. Annotations route back to the source
via a manifest (see [`01-architecture`](./01-architecture.md)). The markdown
source is always the source of truth; the PDF is derived.

## Adoption

Projects don't fill every slot day one — the skeleton is a **contract** (the
slots exist and mean the same thing everywhere), populated as content becomes
real. First pilot: a private project.
