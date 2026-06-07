# Doc provenance & pointers — recommended convention

> Research + design, 2026-06-06. Backed by a multi-agent deep-research run
> (101 agents, 7 high-signal sources, 25 claims adversarially verified → 22
> confirmed, 3 refuted). The refutations shaped the design as much as the
> confirmations — see *What the research ruled out*. Normative rules from this doc
> live in [`../DOC_STANDARD.md`](../DOC_STANDARD.md); this file is the rationale,
> the tooling, and the worked cases.

## The problem

Across the venture's repos + hub, docs reference, derive from, summarize, and
consolidate each other — but the relationships aren't marked. So: (1) you can't
tell the **canonical source** from a **derived view**; (2) editing one silently
drifts the others; (3) consolidation **duplicates** content because the original
is hard to find; (4) links go stale with no detection.

## The recommendation in one line

**Single source of truth, expressed as plain-text metadata: one canonical home per
fact, link everywhere else, declare provenance in frontmatter, and let one CI check
detect drift** — because in plain Git, you cannot auto-*propagate*, so you auto-*detect* instead.

## The three rules

**1. One canonical home per fact.** Exactly one doc (or one section) is the place a
fact is edited. This is the single-source-of-truth principle: "every data element is
mastered (or edited) in only one place," whose named benefits are exactly preventing
"a duplicate value/copy somewhere being forgotten" and "greatly simplified version
control."[^ssot] Borrow the web's canonical-URL model: declare one preferred target so
references consolidate onto it, and **never** declare two conflicting canonicals for the
same content — resolution becomes unpredictable.[^canon]

**2. Reference, don't copy.** A pointer is a plain Markdown link to the canonical.
Reference-based reuse "cannot drift" because every reader resolves to the source;
copy-based reuse "fragments content into multiple divergent files with no way to tell
which is canonical or current."[^reuse] Only copy content into a derived view when you
genuinely must (a consolidated PUNCHLIST, an offline mirror) — and then **mark it
non-canonical and edit it only at the source** (a read-only derived view). The moment
both the source and the copy are editable, you have signed up for a reconciliation/merge
mechanism — which *is* the drift problem.[^readonly]

**3. Declare provenance in frontmatter.** A canonical doc carries nothing special
(absence of `derived_from` **means** canonical). A derived doc declares where it came
from, so both a human and Claude can see it at a glance and a script can check it.

## The frontmatter schema (minimal)

```yaml
---
owner: claude                 # existing auto | claude | human label
derived_from:                 # presence ⇒ this doc is a DERIVED VIEW, not canonical
  - path: ../ops/LEARNINGS.md#auth-retry-policy
    at: 7c868f2               # canonical's git short-SHA when last synced — the drift sentinel
kind: consolidation           # consolidation | summary | mirror | view
---
```

- **Canonical doc:** omit `derived_from` entirely. If it's a heavily-referenced anchor
  target, optionally add `id: <slug>` so links survive a rename.
- **`at:` is the drift sentinel** — the canonical's short-SHA at the moment you derived.
  Plain text, diff-able, and the whole basis of stale-pointer detection below.
- **Canonical *section*** (not a whole file): mark it with an HTML anchor comment the
  renderer already strips — `<!-- canonical: auth-retry-policy -->` above the heading —
  and link to `LEARNINGS.md#auth-retry-policy`. Degrades to nothing on the e-ink mirror.

This rides on the maintenance labels already in `DOC_STANDARD.md`: an `auto`/`claude`
derived view is safe to regenerate; a `human` canonical is the one that needs care.

## The minimal tooling (git-native, low-dependency)

1. **`lychee`** in pre-commit + CI — a fast Rust link/anchor checker that catches broken
   cross-repo references and stale heading anchors automatically.[^doccode] Run it from a
   checkout where sibling repos are present (the hub, or a superdirectory), so
   `../backend/docs/...` resolves; for repos that aren't co-located, point the canonical
   at its **hosted URL** and let lychee check reachability. (The research found **no**
   evidence-backed mandate to prefer absolute over relative paths — choose on what your
   link checker can actually resolve.[^canon])

2. **The provenance lint** — [`docs/tools/check_provenance.py`](../tools/check_provenance.py)
   (built; stdlib + git, no dependencies). For every doc with `derived_from` it (a) asserts
   each `path` resolves and any `#anchor` exists in the canonical; (b) compares the recorded
   `at:` SHA to the canonical's current last-touching commit (`git log -1 --format=%h -- <path>`);
   if the canonical advanced it prints `STALE … recorded at <old>, canonical now at <new>` and
   exits non-zero. Run it as `python docs/tools/check_provenance.py [ROOT]`; wire into
   pre-commit or CI. This is the deliberate answer to the hard truth below: plain Markdown
   **does not** auto-update derived copies, so the system **detects** drift and forces a
   conscious refresh instead of silently rotting.

3. **No transclusion.** Build-time includes (Obsidian embeds, MkDocs/Redocly snippets,
   DITA conref) are real single-sourcing, but they rely on non-standard directives a
   toolchain must resolve and **degrade to unreadable raw syntax** in a plain Markdown
   viewer — i.e. on the e-ink mirror.[^transclude] Provenance-by-metadata + plain links
   degrades to a readable path, which is why it's the right fit here.

> **Device link support (verified on a Nomad, 2026-06-06).** The Supernote honors
> **intra-document** PDF links — a clickable TOC or "back to top" jumps pages on a
> **finger** tap (the pen doesn't trigger links). It does **not** honor **cross-document**
> PDF→PDF links: tapping a pointer to another file does nothing. So a doc-to-doc pointer
> stays a *readable path* on the device (the safe floor); only *within-doc* navigation can
> be made tappable. Don't build cross-PDF jumps. See [[supernote-pdf-links]].

## Auto-resolution — the loop should close itself

The tooling above only *detects* drift and asks for a manual refresh. That's the
fallback, not the goal. **Manually reviewing every flagged pointer defeats the point of
an AI-maintained knowledge base** — low-maintenance is a hard constraint, not a
nice-to-have.

The intended end-state: **a `git push` triggers a remote server we run, which resolves
the drift itself and commits the refresh — the human only sees the result.** Concretely:

1. The fast **local checker** stays as the pre-commit signal (instant, no network).
2. On push, a **server-side hook** fires on the persistent container (the parked cloud
   standby — see [[local-sync-engine]], [[related-projects-and-hosting]]). For each
   derived view whose `at:` SHA fell behind its canonical, the server re-reads the
   current canonical, has Claude regenerate that view, bumps the `at:` SHA, and commits.
3. The human reviews a single resulting diff (or nothing, if it's trivially correct) —
   not a chore per pointer.

This turns the detect-only checker into a **detect-then-auto-resolve** loop. It's the
same shape as this repo's existing ink pipeline (read a source of truth, regenerate a
derived artifact, commit) — the open question below is whether to reuse `reconcile.py` /
`marks.py` rather than build new. Tracked in memory as [[doc-provenance-auto-update]].

**Built so far:** both the detect half ([`check_provenance.py`](../tools/check_provenance.py))
and the **resolver core** ([`resolve_provenance.py`](../tools/resolve_provenance.py)). The
resolver finds each stale view, sends its body + the current canonical section to the Claude
backend, gets an updated body back, and bumps the `at:` SHA deterministically — **dry-run by
default** (prints a diff; `--write` applies), mirroring `process … --apply`. Its plumbing is
verified end-to-end (detect → resolve → re-check clean); a live model run and the
push-trigger + auto-commit on the container are what remain.

## What the research ruled out (so we don't relearn it)

- **Referencing a canonical does NOT make derived copies update automatically** in plain
  Git — that only holds inside a transclusion build system, which the e-ink constraint
  excludes. *Refuted 0–3.* → We never promise auto-sync; we detect drift (tool #2).
- **Co-locating docs with code does not by itself prevent duplication.** *Refuted 0–3.*
  → Co-location helps, but you still need the explicit canonical marker + the checker.
- **No mandate to use absolute paths** for cross-repo pointers. *Refuted 0–3.* → Pick
  paths on link-checker grounds.

## Worked case (a): PUNCHLIST consolidated from upstream notes

The master `PUNCHLIST.md` is consolidated from engagement checklists, LEARNINGS, and
ad-hoc notes. Under this convention it is a **derived view**, not a source:

```yaml
---
owner: claude
kind: consolidation
derived_from:
  - path: deliverables/acme-2026-05/CHECKLIST.md     # canonical per-item detail
    at: 91e6f96
  - path: ops/LEARNINGS.md#flaky-deploy
    at: 7c868f2
---
```

- Each PUNCHLIST line **links back** to its canonical home; the authoritative detail
  lives in the engagement checklist / LEARNINGS, exactly as `DOC_STANDARD.md` already
  says ("engagement folders hold authoritative per-item detail… link the bulk backlog
  rather than duplicating it").
- You **prioritize** in the PUNCHLIST but **edit item substance upstream**, then refresh
  the view (and bump the `at:` SHAs). The provenance lint flags any source that advanced
  past its recorded `at:` so you know which lines are stale.
- If you insist on hand-editing item text directly in the PUNCHLIST, you've chosen an
  editable copy and owe a reconciliation step — note that this repo's existing 3-way
  merge (`reconcile.py`) is exactly that machinery, and the open question below asks
  whether to generalize it for docs.

## Worked case (b): a plan doc absorbs a single task-list item

A backlog item ("rework auth retry") grows into a full `plans/auth-retry.md`. The wrong
move is to copy the item's text into the plan and leave it in the list — now two
editable copies drift. The convention says **move canonicality**:

1. The new plan section becomes the **canonical home** for that item's detail
   (`<!-- canonical: auth-retry -->`).
2. The origin list item is **replaced by a pointer**: `- [ ] Auth retry → see [plan](../plans/auth-retry.md)`.
3. No `derived_from` is needed on the plan (it's now canonical); the list, if it carries
   copied detail anywhere, points instead.

Net: exactly one editable home, a link from the old location, nothing to drift.

## Drop-in CLAUDE.md rules

Paste into any repo's `CLAUDE.md` (or the shared one). Phrased as verifiable instructions
per Claude Code's own memory guidance:

```markdown
## Provenance & pointers (when editing docs)
- Before writing a fact, grep the docs for its canonical home. If it exists, LINK to it — never paste a second copy.
- One canonical home per fact. A canonical doc omits `derived_from`. A derived view declares `derived_from: [{path, at}]` and is edited ONLY at its source.
- Consolidating (e.g. PUNCHLIST from notes): mark the result `kind: consolidation`, list each source in `derived_from` with the source's current git short-SHA in `at:`, and link each item back to its canonical home. Edit item substance upstream, then refresh.
- Absorbing one doc into another (e.g. a plan absorbs a task item): MOVE canonicality — the destination section becomes canonical, and replace the origin with a pointer link. Never leave two editable copies.
- After changing a canonical doc, grep for `derived_from` pointing at it; refresh each derived view and bump its `at:` SHA, or flag it stale.
- Never use transclusion/embed syntax — it doesn't survive the e-ink mirror. Plain Markdown links only.
```

## Open questions (carried from the research)

- **Generalize `reconcile.py` / `marks.py` to docs?** The read-once ledger (content hash)
  and 3-way merge already solve "editable copy + reconciliation" for ink. The consolidated
  PUNCHLIST is the same shape — worth considering reusing that machinery rather than
  building new.
- **Cross-repo checking when siblings aren't checked out.** Hub-level aggregate check vs.
  hosted-URL canonicals vs. a CI step that clones siblings — needs a call based on how the
  repos are actually laid out on disk and in CI.
- **`at:`-SHA drift granularity.** Last-commit-touching-file is coarse (any edit to the
  canonical file flags every derived view of it, even if the referenced section didn't
  change). Acceptable at solo scale; revisit if it gets noisy.

[^ssot]: *Single source of truth* — https://en.wikipedia.org/wiki/Single_source_of_truth (secondary, textbook-grade; 3-0). "Every data element is mastered… in only one place"; "the master data is never copied and instead only references to it are made."
[^canon]: Google Search Central, *Consolidate duplicate URLs* — https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls (primary; 3-0). Canonicalization consolidates signals onto one preferred URL; ranked declaration strengths; "don't specify different URLs as canonical… using different techniques." Absolute-path claim refuted 0-3.
[^reuse]: Paligo, *What is SSOT* — https://paligo.net/blog/content-reuse/what-is-single-source-of-truth-ssot/ + Svensson, *5 principles of single-sourcing* (blog; reference-vs-copy 3-0, DRY framing 2-1). "True SSOT uses reference-based reuse, not copy-based reuse."
[^readonly]: *Single source of truth* (read-only-derived-view pattern) — https://en.wikipedia.org/wiki/Single_source_of_truth (3-0). "The master data is copied but the copies are only read and only the master data is updated"; editable copies "need a reconciliation mechanism."
[^doccode]: scand.com, *Documentation as code* — https://scand.com/company/blog/documentation-as-code-agile-one-source-of-truth/ (blog; 3-0), corroborated by lychee / Vale / markdownlint. Docs-as-code tooling can "automatically find broken links… or obsolete references." Note: co-location-prevents-duplication was refuted 0-3.
[^transclude]: Redocly, *Reusing content* — https://redocly.com/docs-legacy/developer-portal/guides/reusing-content (secondary; 3-0). Snippets embed via a non-standard `<embed src=…>` tag the build must resolve; "nested snippets and cyclical file references are not supported" — and degrade to raw syntax outside the toolchain.
