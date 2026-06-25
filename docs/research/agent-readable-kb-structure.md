# Structuring a Markdown knowledge base for human + agent retrieval

> Research snapshot, 2026-06-06. Synthesized from a multi-agent deep-research run
> (112 agents, 29 sources, 134 claims → 25 adversarially verified, 23 confirmed).
> The run's automated synthesis step failed on a transient API overload; this
> write-up was assembled by hand from the verified claims, so every assertion below
> traces to a confirmed source with a majority verification vote. Two claims were
> *killed* in verification and are recorded at the bottom so we don't repeat them.

## The one-line answer

The convergent, evidence-backed pattern is: **plain Markdown atoms in Git + a small
always-loaded index + the rest loaded just-in-time, with frontmatter as the relevance
signal and typed links for traversal.** This is — almost exactly — the pattern
NoteSync already uses (one-fact-per-file, frontmatter `description:`, a loaded
`MEMORY.md`/`INDEX.md`, `[[wikilinks]]`). The research validates it and points to three
specific refinements (typed links, a `status:` field, and a load-on-demand split).

## Lens 1 — what makes a base *agent*-retrievable

**Context is a finite resource; minimize loaded tokens.** Anthropic's own guidance
frames context as subject to diminishing returns ("context rot") — the goal is "the
smallest possible set of high-signal tokens," not pre-loading everything.[^anthropic]

**Retrieve just-in-time.** The recommended pattern is for the agent to hold *lightweight
identifiers* — file paths, queries, links — and load the underlying content at runtime
via tools, rather than stuffing it all into context up front.[^anthropic][^claudemem]
This is the single most important architectural fact: it directly justifies an
index-of-pointers + on-demand file reads, and it's why a fat monolithic doc is worse
than many small linked ones.

**Folder hierarchy, naming, and timestamps are themselves retrieval signals** — they
tell both human and agent *when and how* to use a piece of information.[^anthropic] So
naming and directory layout are not cosmetic; they're part of the retrieval interface.

**Claude Code's own memory architecture is one-index-plus-topic-files.** `MEMORY.md` is
a concise index loaded every session; topic files (`debugging.md`, etc.) are **not**
loaded at startup and are read on demand.[^ccmem] Only the **first 200 lines / 25 KB**
of `MEMORY.md` load at session start — content past that threshold simply doesn't load,
which is *why* detail must move into separate topic files.[^ccmem] This is the
authoritative spec our `INDEX.md` pattern should mirror.

**Keep instruction files small and specific.** Target **under 200 lines** per
`CLAUDE.md`; longer files consume context and *reduce* adherence. Critically,
`@path` imports aid organization but **do not reduce context** — imported files still
load at launch.[^ccmem] And instructions should be concrete enough to verify ("API
handlers live in `src/api/handlers/`", not "keep files organized").[^ccmem]

**External note-taking is a proven long-horizon memory technique** — having the agent
persist notes outside the context window and retrieve them later enables coherent
multi-hour strategies, validating the one-fact-per-file external-memory pattern.[^claudemem]

**The index *is* the retrieval mechanism (no vector DB needed at our scale).** Karpathy's
LLM-wiki pattern: `index.md` is a catalog of every page — link + one-line summary +
optional metadata; the agent reads the index first to find relevant pages, then drills
in. This is explicitly offered as an alternative to semantic/RAG search and is claimed
to work well to **~100 sources / hundreds of pages**.[^karpathy] The base is "just a git
repo of markdown files" plus a `CLAUDE.md`/`AGENTS.md` schema doc that makes the LLM a
"disciplined maintainer rather than a generic chatbot."[^karpathy]

**Research-system implementations converge on the same shape.** A-Mem applies the
Zettelkasten atomicity principle to agent memory — each note is a single self-contained
unit[^amem] — with LLM-generated keywords, tags, and a contextual description per
note.[^amem] Production Zettelkasten repos store **Markdown + YAML frontmatter as the
source of truth**, with a SQLite FTS5 index layered on for search[^josh]; their note
frontmatter carries `id, title, summary, tags, typed links, timestamps, status`[^josh];
and they use **typed bidirectional links** (supports/supported_by, refines/refined_by,
contradicts/contradicted_by, …) plus a backlinks endpoint, going beyond plain
wikilinks.[^josh]

## Lens 2 — which PKM methodologies actually transfer

**PARA** organizes everything into four buckets — Projects, Areas, Resources, Archives —
on the principle of **actionability** (what you're committed to *now*), not topic.[^para1][^para2]
*Transfers well:* the actionability axis maps cleanly onto an agent's "is this live or
archived?" decision, and Archives-don't-delete keeps stale content from poisoning
retrieval. *Transfers badly:* nothing major — PARA is about top-level placement, which is
orthogonal to atomicity.

**Atomic / evergreen notes** (Matuschak): a note is about **one thing, but captures the
entirety of that thing.**[^matu1] Atomicity is what makes the link network useful —
right-sized notes multiply connections; mis-sized ones fragment or obscure them.[^matu2]
Crucially, **there is no perfect granularity formula** — the atomic unit is a judgment
call between too-broad and too-fragmented.[^matu1] *Transfers well:* atomicity = file
granularity, and it's the enabler of precise retrieval and clean diffs. *Caveat:* don't
codify a rigid "exactly one concept" rule (see killed claims) — it's judgment, not a
hard spec.

**What's human-only:** MOCs / maps-of-content and graph aesthetics are navigation aids
for human eyes; epistemic-status labels (seedling/evergreen) only help the agent if
promoted to *structured frontmatter the agent is told to honor*. (Cross-referenced from
the [[ai-pkm-landscape]] scan.)

## Implications for NoteSync's existing pattern

| Existing pattern | Verdict | Refinement |
|---|---|---|
| One-fact-per-file | ✅ Matches atomic-note + A-Mem consensus | Keep granularity a judgment call, not a rigid rule |
| Frontmatter `description:` for relevance | ✅ Matches A-Mem contextual-description + Karpathy index summaries | Consider adding LLM-friendly `keywords`/`tags` |
| Loaded `INDEX.md` / `MEMORY.md` | ✅ Matches Claude Code's own architecture | Respect the **200-line / 25 KB** budget; push detail to topic files read on demand |
| `[[wikilinks]]` | ✅ Matches the traverse-don't-embed consensus | **Refine to typed links** (supports / refines / derived-from / contradicts) so relationships are machine-meaningful |
| (none yet) | — | Add a `status:` field (e.g. live / archived / superseded) — recurs across every production implementation |
| Git as substrate | ✅ "Just a git repo of markdown files" is the recommended substrate | Already have it, plus 3-way merge — ahead of the field |

**One finding bridges directly into the provenance work:** the `llm-atomic-wiki` system
treats **atoms as the source of truth and wiki pages as *derived artifacts*.**[^atomic]
That canonical-vs-derived distinction is exactly the spine of the provenance/pointer
problem — see [[doc-provenance-convention]] once that research lands.

## Killed claims (do not repeat)

- **"Accuracy degrades because attention is n-squared, every token attends to every
  other"** — the *mechanism* framing was refuted 1–2 (the phenomenon of context rot
  still holds per Anthropic; the n-squared causal story did not survive verification).
- **"Atomic notes should be scoped to exactly one concept, neither broader nor more
  fragmented"** — refuted 0–3. Atomicity is a judgment tradeoff, not a rigid one-concept
  rule; this directly contradicts Matuschak's own "no perfect formula" point.

[^anthropic]: Anthropic, *Effective context engineering for AI agents* — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents (primary; 3-0).
[^ccmem]: Claude Code memory docs — https://code.claude.com/docs/en/memory (primary; 3-0). Version-sensitive — re-check the 200-line/25 KB figures against current docs.
[^claudemem]: claude-mem, *Context engineering* — https://docs.claude-mem.ai/context-engineering (primary; 3-0).
[^karpathy]: Karpathy, LLM-wiki gist — https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f (primary; 3-0).
[^amem]: A-Mem — https://arxiv.org/html/2502.12110v11 (primary; atomicity & metadata 3-0; LLM-linked network 2-1).
[^josh]: joshylchen/zettelkasten — https://github.com/joshylchen/zettelkasten (primary; 3-0).
[^atomic]: cablate/llm-atomic-wiki — https://github.com/cablate/llm-atomic-wiki (primary; 3-0).
[^para1]: Forte Labs, *PARA* — https://fortelabs.com/blog/para/ (primary; 3-0).
[^para2]: Forte Labs, *PARA* (actionability principle) — https://fortelabs.com/blog/para/ (primary; 3-0).
[^matu1]: Matuschak, evergreen notes — https://notes.andymatuschak.org/z4Rrmh17vMBbauEGnFPTZSK3UmdsGExLRfZz1 (primary; 3-0).
[^matu2]: Matuschak, *Evergreen notes should be atomic* — https://notes.andymatuschak.org/Evergreen_notes_should_be_atomic (primary; 3-0).
