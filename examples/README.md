# Examples

Runnable companions to [`../RECIPES.md`](../RECIPES.md). Render any of them to see how the
frontmatter and auto-styling land on the page:

```bash
python render.py examples/punchlist.md /tmp/out.pdf && open /tmp/out.pdf
```

- `punchlist.md` — `format: checklist` (status legend + styled checkboxes)
- `the-novel/01-the-beginning.md` — `format: book` (clean prose footer)
- `repo-docs/04-status.md` — plain `notes`, checkboxes still auto-style

They're generic samples — copy one as a starting point and make it yours.
