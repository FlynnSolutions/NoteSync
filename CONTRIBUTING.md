# Contributing

Thanks for your interest. This is a small, focused tool — contributions that keep it
simple and sharp are very welcome.

## Dev setup

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # ruff (see Code standards)
cp config.example.toml config.toml   # your local settings (gitignored)
cp .env.example .env                 # your Anthropic key (gitignored)
```

You also need the `pdftoppm` binary (poppler). The renderer ships with DejaVu Sans, so it
works out of the box.

## Code standards

The lint config lives in [`pyproject.toml`](./pyproject.toml). Before you push:

```bash
ruff check .
```

- **Style:** ruff with `E, F, W, I, UP, B, C4, SIM`, line length 120. Keep it green.
- **Type hints** on function signatures; `from __future__ import annotations` at the top.
- **Docstrings** on every module and every non-trivial function.
- **The guiding principle:** *the model interprets; code derives.* Use the LLM only for
  the genuinely fuzzy step (reading handwriting). Anything that's a pure function of the
  data — counts, routing, merges — is deterministic code. See
  [`docs/03-decisions.md`](./docs/03-decisions.md) (ADR-010).
- **No test suite, by design** — this is a personal-scale tool and the real round-trip is
  the test. Don't add a test framework unless the scope genuinely grows.
- **Never hardcode paths or settings** — everything machine/user-specific goes through
  `config.py` (env `SUPERNOTE_*` → `config.toml` → default). Personal config, fonts, and
  notes are gitignored; keep them out of commits.

## Submitting changes

1. Fork, branch, and make your change.
2. `ruff check .` clean; the relevant `sync.sh` command still works.
3. Open a pull request describing the what and the why.

Architecture and design rationale live in [`docs/`](./docs/).
