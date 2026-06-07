# AI-native note-taking & PKM tooling — landscape

> Research snapshot, 2026-06-06. Multi-agent web scan (5 category researchers →
> synthesis) run to inform supernote-sync's evolution into a unified human+Claude
> knowledge architecture. Claims flagged `[single-source]` or listed under
> *Verification needed* are not yet triangulated — treat as leads, not facts.

**Executive summary.** Across four families — local-first Markdown PKM, AI-native cloud apps, digital gardens, and agent-memory frameworks — the field is splitting along one decisive axis for a human+agent knowledge base: *is the canonical store plain Markdown on disk, or a proprietary store reached only through an API?* Plain-Markdown tools (Obsidian, Foam, Quartz, the LLM-wiki / docs-as-code pattern) are trivially agent-retrievable because the agent and the human share the same files; AI-native apps (Mem, Reflect, Notion, Tana) deliver strong agent access too, but via first-party MCP/REST rather than file reads, trading vault portability for vendor lock-in. The 2025–2026 inflection is the formalization of *agent-facing conventions on top of plain files* — AGENTS.md, llms.txt, frontmatter-gated rules, and loaded index/map files — which is exactly the territory supernote-sync already occupies. The substrate (files) retrieves trivially; the semantics (what's atomic, why two notes link, which fact is current) remain human authorial judgment that no tool yet encodes as an enforced, agent-trustable spec.

## Taxonomy

**Local-first Markdown PKM** (Obsidian, Logseq, Foam, Dendron, Zettlr, SilverBullet). *Optimizes for:* ownership, portability, longevity, offline use — the canonical store is plain `.md` on local disk with no database between the user (or an agent) and the data. Shared primitives: `[[wikilinks]]` + automatic backlinks, YAML frontmatter, daily/journal notes, tags, graph view. The category's internal fault line is whether Markdown *stays* the source of truth (Obsidian Bases keeps everything in frontmatter) or *becomes* an export target (Logseq's 2025 SQLite DB version — the key defection that erodes direct agent reads).

**AI-native note / PKM apps** (Mem, Reflect, Notion AI, Tana, Capacities, Saga). *Optimizes for:* the AI organizing for you — auto-tagging, semantic/graph retrieval, "the app files your notes." Almost all reject the plain-Markdown vault for a proprietary cloud store (vector index, encrypted graph, block model, node+supertag graph). Markdown, where present, is import/export, not truth. Agent-retrievability here hinges *not* on file access but on whether the vendor ships a first-party API/MCP server — Mem, Reflect, Notion, Tana, Capacities all do; Saga lags (export-only).

**Digital gardens & evergreen notes** (Quartz, Andy Matuschak's evergreen-notes philosophy, Maggie Appleton's framework, Foam, the Roam/Logseq networked-thought lineage). *Optimizes for:* long-horizon thinking and serendipitous cross-linking — atomic, concept-oriented notes ("topography over timelines"), published imperfect with growth/epistemic status (seedling → budding → evergreen), navigated by links/MOCs not chronology. This is a *philosophy + static-site tooling* layer more than an app category. Crucial split: the **substrate** is maximally agent-friendly (plain MD + frontmatter + wikilinks in Git), but the **semantics** that make a garden a garden are human judgment encoded loosely in prose, with no enforced schema.

**Agent memory & context-engineering frameworks** — two sub-families. *Runtime memory* (Letta/MemGPT, mem0, LangGraph/LangMem): memory as a managed DB store the agent reads/writes mid-session, a small always-in-context "core" tier plus a large out-of-context tier retrieved by semantic similarity + metadata. *Optimizes for:* token efficiency at scale and statefulness across sessions; **not** file-readable by an outside agent. *Coding-agent "memory file" conventions* (CLAUDE.md + auto memory, AGENTS.md, Cursor `.mdc`, Windsurf rules): human-curated (or agent-appended) Markdown loaded into the prompt. *Optimizes for:* portable, version-controllable, plain-text instruction sets — converging on **a small always-loaded index + topic files loaded on demand, with frontmatter governing relevance.**

**Plain-text / Git-native KBs + "Markdown-for-agents" conventions** (AGENTS.md, llms.txt, Org-roam, the LLM-wiki "second brain," docs-as-code + Spec Kit). *Optimizes for:* a *single human-readable source of truth that is simultaneously what the human edits and what the agent retrieves against* — no separate AI index that can drift. This is the synthesis category supernote-sync sits in.

## Comparison

| Tool | Plain-MD source of truth | Local-first | Agent-retrievable | Collaboration | Key organizing patterns |
|---|---|---|---|---|---|
| **Obsidian** | Yes (frontmatter; Bases stays in-file) | Yes | High (files; only link syntax to interpret) | Single-user; async via Sync/Git | Wikilinks+backlinks, tags, frontmatter, daily notes, graph, Bases |
| **Logseq** | Partial → No (2025 SQLite DB version) | Yes | Medium (file ver.) / Low (DB ver., export-only) | Single-user; DB rewrite targets collab | Outliner blocks, `key:: value`, journals, block refs, queries |
| **Foam** | Yes (no app layer) | Yes | High (agent shares the VS Code workspace) | Single-user; Git | Wikilinks+backlinks, daily notes, graph, templates |
| **Dendron** | Yes (dot-hierarchy filenames) | Yes | High (hierarchy parseable from filenames) | Single-user; Git | Dot-notation hierarchy, schemas, stable note IDs *(maintenance mode)* |
| **Zettlr** | Yes (Pandoc/academic) | Yes | High (standard frontmatter + citation keys) | Single-user; Git | Zettelkasten IDs, citations `[@cite]`, backlinks |
| **SilverBullet** | Yes (derived index, not authoritative) | Yes (self-hosted Docker) | High (files; embedded queries/Lua are opaque) | Mostly single-user (web-accessible) | Wikilinks, embedded query lang, Space Lua scripting |
| **Mem** | No (vector/graph cloud) | No | High (first-party API + **MCP**) | Single-user | Anti-folders, auto-tagging, AI Related Notes |
| **Reflect** | Partial (E2E-encrypted graph) | Partial | High (official **MCP** for Claude Code/Cursor) | Single-user | Daily notes, graph-aware AI, AI-added backlinks |
| **Notion AI** | No (block/data-source model) | No | High (mature API + hosted **MCP**) | Strongly collaborative | Blocks, databases/properties, relations, enterprise search |
| **Tana** | No (node+edge graph) | No | High (Local API/**MCP**; consumes *structured* schema) | Collaborative + solo | Supertags (typed fields), outliner, live queries |
| **Capacities** | Partial (clean MD export, MD-returning API) | Partial ("offline-first") | High (REST + OAuth 2.1 **MCP**) | Mostly single-user | Typed objects (Person/Project/Book), two-way property links |
| **Saga** | Partial (export only) | No | Low–Medium (no clear API/MCP) | Strongly collaborative (teams 2–15) | Pages/tasks, backlinks; simpler-Notion |
| **Quartz** | Yes (content/ is `.md`) | Yes | High (Git repo of MD; backlinks derived at build) | Single-user; Git PRs | Obsidian-flavored MD, transclusions, graph, tag pages |
| **Org-roam** | Partial (`.org`, not MD; SQLite cache) | Yes | Medium (greppable, but Org syntax + DB graph) | Single-user; Git | Zettelkasten IDs, `[[id:]]` backlinks, capture templates |
| **LLM-wiki / "second brain"** | Yes (Obsidian-flavored vault) | Yes | High (architected for LLM to maintain+retrieve) | Single-user; Git | inbox→wiki pipeline, master `index.md`, `log.md`, lint skill |
| **Docs-as-code + Spec Kit** | Yes | Yes (Git is the store) | High (START_HERE + KNOWLEDGE_GRAPH + AGENTS.md) | Collaborative | Spec-as-source, numbered prefixes, date-prefixed notes, archive-with-banner |
| **CLAUDE.md + auto memory** | Yes | Yes | High (Read/Grep directly) | Both (project shared / memory local) | Load-ordered hierarchy, `@imports`, path-scoped rules, MEMORY.md index |
| **AGENTS.md** | Yes | Yes | High (predictable repo-root path) | Collaborative | Single root file + nested per-package; three-tier boundaries |
| **Cursor `.mdc` rules** | Partial (MD body + YAML) | Yes | High (frontmatter encodes *when* relevant) | Collaborative | `description`/`globs`/`alwaysApply` activation gating |
| **mem0 / Letta / LangMem** | No (vector/graph/KV DB) | Partial | Low–Medium (API-only; nothing to grep) | Multi-user (namespaced) | Core vs archival tiers; ADD/UPDATE/DELETE conflict resolution; semantic/episodic/procedural |

## Emerging LLM/agent-integration patterns

**Stable entry point + explicit map.** The strongest convergent pattern: don't make the agent blindly grep. Give it one authoritative starting file — `AGENTS.md` (repo-root project rules, now a Linux Foundation standard, 60k+ repos), `llms.txt` (a curated, context-window-sized link map so an LLM fetches the few authoritative docs instead of crawling a whole site), `START_HERE.md`/`KNOWLEDGE_GRAPH.md`/`index.md` inside a repo, or `MEMORY.md` as a loaded index pointing to topic files read on demand. The map-file idea recurs identically across web docs (llms.txt) and personal vaults (LLM-wiki `index.md`).

**Small always-loaded core + large load-on-demand tier.** Both runtime frameworks and file conventions land on the same architecture. Letta: always-in-context core blocks vs paged archival/recall. CLAUDE.md: only the first ~200 lines / 25KB of MEMORY.md load at start, the rest read on demand. This is the file-world echo of MemGPT's "LLM-as-OS paging."

**Frontmatter as the relevance/activation gate.** The richest model is Cursor `.mdc`: `description` (agent reads it to decide whether to pull the rule in), `globs` (auto-attach on matching files), `alwaysApply` (load every turn). Claude Code's `.claude/rules/*.md` `paths:` globs do the same. This is the explicit anti-bloat mechanism — load by relevance, not all at once. supernote-sync's `description:` field is precisely this pattern.

**Traverse via links, don't re-embed.** Wikilinks + backlinks + one-line relationship descriptions let an agent walk the graph deterministically rather than running similarity search. Backlinks/graphs in plain-MD tools are *derived at build time from the same link syntax*, so an agent can reconstruct them. mem0's 2026 "hybrid memory" reaches for the same idea inside a DB (vector + graph traversal).

**Git as audit log, merge engine, and provenance.** Diffs make AI edits reviewable and revertible; 3-way merge resolves human/agent concurrent edits; date- and number-prefixed filenames give deterministic navigation; `archive/`-don't-delete with non-authoritative banners keeps stale docs from poisoning retrieval.

**Explicit conflict resolution on write.** mem0's write path classifies each candidate fact as ADD / UPDATE / DELETE / NOOP — the strongest answer to stale memory in the field. Most file conventions lack this entirely.

**Documented failure modes (universal across both families):**
- **Context bloat** — low-value context crowds out reasoning. Mitigations: target <200 lines / <200 words per rule; relevance-gated loading; hard character caps (Windsurf's blunt 6k global / 12k workspace). Note: `@imports` *don't* reduce context — they still load at launch.
- **Stale memory / conflict** — old facts treated as authoritative as fresh input; "conflicting instructions across files → the agent picks arbitrarily." Few file systems version or reconcile; mem0's UPDATE/DELETE step is the exception.
- **Retrieval miss** — embeddings return similar-but-wrong text; index gaps; misconfigured frontmatter silently disables a rule ("silently ignored" when globs absent or `alwaysApply:false` with a vague description).
- **Index drift** — the map file falls out of sync with reality; the LLM-wiki pattern answers this with a lint/health-check skill for broken links and index inconsistency.

## What translates to a Claude-readable Markdown base

**Borrow these (they directly help agent retrieval):**
- **A loaded index/map file** (MEMORY.md / index.md / KNOWLEDGE_GRAPH.md) as the agent's stable entry point — supernote-sync already does this.
- **Frontmatter relevance metadata** — a `description:` (Cursor's "agent-requested" mode) plus optional path/glob scoping; this is the field-world's only real anti-bloat lever.
- **One-fact / one-concept per file** — atomic notes give precise retrieval and clean diffs; already in place here.
- **Wikilinks + backlinks with a one-line "why linked"** so the agent traverses instead of re-embedding.
- **Deterministic naming** — numbered prefixes for reading order, date prefixes for episodic notes.
- **Archive-don't-delete with a non-authoritative banner** + a **lint/health-check** routine to fight index drift and broken links (from the LLM-wiki and docs-as-code patterns).
- **Explicit ADD/UPDATE/DELETE-on-write discipline** (borrowed from mem0) to attack stale facts — the field's clearest unsolved gap in file-based systems.
- **Three-tier boundaries** (always-do / ask-first / never-do, from AGENTS.md) for any instruction-style memory.
- **Git 3-way merge as the reconciliation engine** — supernote-sync already merges this way; it's the right substrate for human+agent concurrent edits.

**Human-only — won't help agent retrieval (don't over-invest for the agent's sake):**
- **Growth/epistemic status labels** (seedling/budding/evergreen) — authorial judgment, no enforced spec; useful to humans, opaque to agents unless promoted to *structured* frontmatter the agent is told to honor.
- **"Atomic" and "concept-oriented" as principles** — meaningful only because a human applied judgment; no schema makes them machine-trustable.
- **MOCs / Maps of Content, graph-view aesthetics, Canvas** — navigation aids for human eyes, not retrieval primitives.
- **Outliner/block models** (Logseq, Roam) — block-ID indirection (`((uuid))`) *adds* parsing friction for a flat-prose-reading agent rather than helping.
- **Vector/embedding RAG as the primary store** — for a single-founder Git base it's overkill and introduces the retrieval-miss + stale-embedding failure modes; link traversal + grep over plain files is more transparent and revertible at this scale.
- **Proprietary-app MCP servers** (Mem/Notion/Tana) — strong access *if* you live in their cloud, but they reintroduce the lock-in and drift the plain-files bet exists to avoid.

## Whitespace & positioning

**The gap.** Almost every tool optimizes for one of two users: the *human second-brain* (local-first Markdown PKM, gardens — agent access is an afterthought you bolt on) or the *agent* (runtime memory frameworks — nothing for a human to read; DB-bound). The AI-native cloud apps serve both but only inside a proprietary store reached via MCP. The genuinely underserved position is **a solo technical founder who wants ONE Git-tracked Markdown base that is simultaneously their own second brain and their coding agent's durable memory** — plain files as the single source of truth, no separate AI index that can drift, with the agent as a first-class read/write actor. Only a handful of patterns aim here: the LLM-wiki "second brain," docs-as-code + Spec Kit, and the CLAUDE.md/AGENTS.md memory-file conventions. None of these is a polished product — they're conventions and reference repos. That's the whitespace.

**Where supernote-sync is positioned.** Its existing memory pattern — *one-fact-per-file, a frontmatter `description:` for relevance matching, a loaded INDEX file, `[[wikilinks]]`* — is essentially the convergent best-practice the whole agent-facing-Markdown movement is independently arriving at:
- **One-fact-per-file** = atomic notes (gardens) + topic-per-file (CLAUDE.md auto memory, `.claude/rules`) → precise retrieval, clean diffs. **Already right.**
- **Frontmatter `description:` for relevance** = Cursor `.mdc`'s "agent-requested" mode, the richest relevance gate in the field. **Already right — and ahead of AGENTS.md**, which has *no* relevance mechanism beyond file location.
- **Loaded INDEX file** = MEMORY.md / llms.txt / KNOWLEDGE_GRAPH.md — the small-always-loaded-core tier. **Already right.**
- **`[[wikilinks]]`** = the universal traverse-don't-embed primitive. **Already right.**
- **Plus a structural edge the convention crowd lacks:** supernote-sync already uses **Git 3-way merge** as its reconciliation engine — exactly the mechanism needed for human+agent concurrent edits, which the memory-file conventions (last-write-wins, "agent picks arbitrarily") don't have.

**What to refine:**
1. **Add explicit write-time conflict resolution.** The field's clearest gap is stale memory; borrow mem0's ADD/UPDATE/DELETE/NOOP discipline so superseded facts get updated/retired, not silently duplicated. Your Git 3-way merge handles *concurrent* edits but not *semantic supersession*.
2. **Make the INDEX self-healing.** Add a lint/health-check (broken wikilinks, index drift, orphan files) — the LLM-wiki pattern's answer to the index-drift failure mode.
3. **Promote relevance frontmatter to also gate loading**, not just match — consider a `paths:`/glob-style scope (Cursor/Claude-rules) so topic files load only when relevant, formalizing the small-core/large-on-demand split.
4. **Keep growth-status/MOC ambitions human-facing only.** If you adopt seedling/evergreen labels, treat them as structured frontmatter the agent is *explicitly told* to honor, or they're decoration.
5. **Resist the embedding-RAG temptation.** At solo scale, link traversal + grep over atomic files is more transparent, revertible, and drift-free than a vector index — keep files the single source of truth.

## Verification needed

- **mem0's "91% p95 latency reduction / ~26% accuracy gain over OpenAI built-in memory"** — vendor-published benchmark, single-source; treat as a marketing claim until independently reproduced.
- **AGENTS.md adoption counts** — research data gives both "20,000+" and "60,000+ by end of 2025"; the figures conflict and are date-dependent. Verify the current number before citing.
- **Saga's agent-retrievability** — research explicitly flags "no prominent first-party API or MCP surfaced; verify before relying on any API." Confirm directly.
- **Reflect "first note-taking AI that understands your entire note graph" (Sept 2025)** — vendor positioning claim, single-source.
- **Capacities AI model specifics ("OpenAI GPT-4.1 / 4.1-nano")** and **Saga "GPT-4o"** — exact model bindings change frequently; verify current providers.
- **Logseq DB-version export fidelity** ("drops timestamps and some properties") — verify against current Logseq DB release, as this is a moving target mid-transition.
- **Claude Code memory specifics** — "first 200 lines / 25KB of MEMORY.md," "`@import` recursion max depth 4," "~150–200 instruction practical ceiling": cited to docs but version-sensitive; confirm against current docs before treating as hard limits.
- **Windsurf character caps** (6,000 global / 12,000 workspace) — single-source; verify against current Windsurf docs.
- **Dendron and the Logseq DB pivot** are both transitional/maintenance states as of the research; re-check status before recommending either for a new build.
