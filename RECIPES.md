# Recipes

NoteSync syncs *any* Markdown tree — it has no opinion about your folders. Below are
a few structures that work well, each one a suggestion you can ignore or adapt. The only
real conventions are in [`docs/05-conventions.md`](./docs/05-conventions.md): checkboxes
style themselves, and an optional `---` frontmatter block tunes a doc. Runnable versions of
all three live in [`examples/`](./examples/).

---

## 1. A daily punch-list

A single tracker you check off and annotate on the device. The `checklist` format adds a
status legend; the checkboxes render as real boxes either way.

```
~/notes/
└── punchlist.md
```

```markdown
---
format: checklist
---

# Punchlist

## Priority
- [~] Wire up the new dashboard column
- [ ] Draft the Q3 plan

## Backlog
- [ ] Renew the domain
- [!] Migrate the old exports — revisit next month
```

Annotate it on the Supernote (check a box, strike an item, scribble a margin note), and
`./sync.sh in` → `process` folds your marks back into the Markdown.

---

## 2. Write a book

One file per chapter, `format: book` for clean prose pages (page-number-only footer, no
source path).

```
~/notes/
└── the-novel/
    ├── 01-the-beginning.md
    └── 02-the-middle.md
```

```markdown
---
format: book
---

# Chapter 1 — The Beginning

It was a bright cold day in April, and the clocks were striking thirteen...
```

Read and mark up chapters on the device; corrections and margin notes merge back into the
source on check-in.

---

## 3. Review a code repo's docs from the couch

Point `source_base`/`scan_roots` at a project so its docs mirror to the device at matching
paths — read architecture, status, and decisions away from the machine, annotate, and have
the notes flow back. No frontmatter needed (plain `notes` rendering); checkboxes in a
status doc still style themselves.

```
~/Projects/myapp/docs/
├── 00-overview.md
├── 01-architecture.md
└── 04-status.md
```

```toml
# config.toml
source_base = "~/Projects"
scan_roots  = ["myapp"]
```

`./sync.sh mirror` renders the tree → device; annotate `04-status.md`'s checkboxes or leave
an `@claude` instruction; `in` → `process` applies it.

---

These are just starting points — mix them, rename them, or invent your own. The engine
doesn't care; it renders whatever Markdown you give it.
