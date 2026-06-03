# 05 — Backlog  `[claude]`

Captured feature ideas not yet built. Each should have enough detail to pick up cold.

---

## Interactive onboarding + preferences (config wizard)

**Goal.** First-run onboarding that walks a new user through setup interactively
(instead of hand-editing `config.toml`), and a way to revisit those answers later.
It collects two kinds of settings:

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

**Open questions to settle when building:**
- Emoji rendering constraint above (font vs. strip vs. text-only).
- Which knobs are worth exposing vs. sensible-default-only (avoid an overwhelming wizard).
- Whether device geometry (page size for non-Nomad models) belongs in the same wizard.

**Why deferred:** sequenced after the Phase-B / open-source groundwork; it builds
directly on the `config.py` layer (see [`config.py`] and the de-personalization work).
