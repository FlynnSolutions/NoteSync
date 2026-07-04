#!/usr/bin/env python3
"""
config.py — single source of truth for environment/user-specific settings, so the
pipeline isn't bolted to one machine (and can be open-sourced + run in a Lambda).

Resolution order, first match wins:
  1. environment variable (SUPERNOTE_*)  — headless / Lambda / one-off override
  2. config.toml next to this file        — your local config (gitignored; copy the
                                            committed config.example.toml to start)
  3. built-in default / auto-detection    — zero-config local use still "just works"
                                            (e.g. auto-find the Google Drive mount)

The Supernote folder layout under the sync root (Document/Library, EXPORT) is fixed by
the Supernote+Drive convention, so only the ROOT is configurable; the subdirs derive.

Shell access: `python config.py <key>` prints a resolved value (used by sync.sh), e.g.
  python config.py supernote_root | export_dir | source_base | checklist
"""
from __future__ import annotations

import os
import sys
import tomllib
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
# <repo>/src/notesync -> <repo>. Only meaningful in a source checkout; an installed wheel lives
# under site-packages, where none of these marker files exist, so it falls through to XDG dirs.
_REPO_ROOT = HERE.parent.parent
_IS_CHECKOUT = any((_REPO_ROOT / m).exists() for m in (".git", "sync.sh", "pyproject.toml"))


@lru_cache(maxsize=1)
def _file_cfg() -> dict:
    f = config_path()
    if f.exists():
        try:
            return tomllib.loads(f.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError) as e:
            print(f"config.py: ignoring bad config.toml ({e})", file=sys.stderr)
    return {}


def _str(key: str, env: str, default: str = "") -> str:
    if v := os.environ.get(env):
        return v
    v = _file_cfg().get(key)
    return str(v) if v not in (None, "") else default


def _expand(p: str) -> Path | None:
    return Path(os.path.expanduser(p)).resolve() if p else None


def _xdg(env: str, default_sub: str) -> Path:
    """A per-user base dir following the XDG spec, namespaced under `notesync/`."""
    base = os.environ.get(env) or str(Path.home() / default_sub)
    return Path(base).expanduser() / "notesync"


def config_path() -> Path:
    """Where config.toml lives. Explicit `SUPERNOTE_CONFIG` wins; a source checkout uses the repo
    root (backward-compatible); an installed package uses the user config dir (~/.config/notesync)."""
    if v := os.environ.get("SUPERNOTE_CONFIG"):
        return Path(os.path.expanduser(v))
    return (_REPO_ROOT / "config.toml") if _IS_CHECKOUT else _xdg("XDG_CONFIG_HOME", ".config") / "config.toml"


def data_dir() -> Path:
    """Root for all mutable runtime state — `base/`, `device/`, `snapshots/`, `merge_out/`,
    `manifest.json`, the read-once ledger, digests. Explicit `SUPERNOTE_DATA_DIR`/config `data_dir`
    wins; a source checkout keeps it in the repo (backward-compatible); an installed package uses
    the user data dir (~/.local/share/notesync)."""
    return _expand(_str("data_dir", "SUPERNOTE_DATA_DIR")) or (
        _REPO_ROOT if _IS_CHECKOUT else _xdg("XDG_DATA_HOME", ".local/share"))


def env_path() -> Path:
    """The `.env` file (holds `ANTHROPIC_API_KEY` for the api backend) — lives alongside config.toml."""
    return config_path().parent / ".env"


# --- source side ----------------------------------------------------------
def source_base() -> Path:
    """Root the source docs are mirrored relative to (e.g. ~/Projects)."""
    return _expand(_str("source_base", "SUPERNOTE_SOURCE_BASE", "~/Projects"))


def scan_roots() -> list[str]:
    """Top-level dirs under source_base to mirror; empty list = every dir."""
    if v := os.environ.get("SUPERNOTE_SCAN_ROOTS"):
        return [r.strip() for r in v.split(",") if r.strip()]
    return list(_file_cfg().get("scan_roots", []))


def mirror_exclude() -> list[str]:
    """Directory NAMES skipped when mirroring to the device — personal clutter you don't review
    on the tablet (e.g. '_evidence', 'signals', 'claude'). Sources are untouched; the docs just
    don't render to the device. SUPERNOTE_MIRROR_EXCLUDE (comma-sep) or config `mirror_exclude`."""
    if v := os.environ.get("SUPERNOTE_MIRROR_EXCLUDE"):
        return [r.strip() for r in v.split(",") if r.strip()]
    return list(_file_cfg().get("mirror_exclude", []))


def mirror_include() -> list[str]:
    """Glob patterns that FORCE a doc onto the device even in pinned mode — the override for a
    dropped-in doc (e.g. a design doc you want to read once) without editing its frontmatter.
    Matched against the source-relative path AND the filename, so both `*-TDD.md` and `_review/*`
    work. SUPERNOTE_MIRROR_INCLUDE (comma-sep) or config `mirror_include`."""
    if v := os.environ.get("SUPERNOTE_MIRROR_INCLUDE"):
        return [r.strip() for r in v.split(",") if r.strip()]
    return list(_file_cfg().get("mirror_include", []))


def mirror_pinned() -> bool:
    """When true, mirror ONLY docs whose frontmatter has `device: true` — a curated device view.
    Everything else stays in the repo as reference (read on the laptop, not shown on the tablet).
    Default false (mirror everything under scan_roots). SUPERNOTE_MIRROR_PINNED / config."""
    v = os.environ.get("SUPERNOTE_MIRROR_PINNED")
    if v is None:
        v = str(_file_cfg().get("mirror_pinned", "")).strip()
    return v.strip().lower() in ("1", "true", "yes", "on")


# --- Supernote / Drive side ----------------------------------------------
@lru_cache(maxsize=1)
def supernote_root() -> Path | None:
    """The Supernote sync root. Explicit config wins; else auto-detect the Google
    Drive for Desktop mount (<mount>/My Drive/Supernote). Cached (the glob is not free)."""
    if explicit := _str("supernote_root", "SUPERNOTE_ROOT"):
        return _expand(explicit)
    mounts = list(Path.home().glob("Library/CloudStorage/GoogleDrive-*"))
    return (mounts[0] / "My Drive" / "Supernote") if mounts else None


def _under_root(*parts: str) -> Path | None:
    r = supernote_root()
    return r.joinpath(*parts) if r else None


def library() -> Path | None:
    """Where mirrored PDFs and their `.mark` sidecars live, or None if no root. Default
    `Document/Library`; set `library_subdir = ""` (config / SUPERNOTE_LIBRARY_SUBDIR) to render
    straight into `Document/` — fewer taps, but then the prune namespace IS the whole Document
    folder, so never drop manual files there."""
    # An explicit "" means flatten (render into Document/); absent means the "Library" default.
    # (Can't use _str — it treats empty-string as unset and would fall back to the default.)
    env = os.environ.get("SUPERNOTE_LIBRARY_SUBDIR")
    if env is not None:
        sub = env.strip()
    else:
        cfg = _file_cfg()
        sub = str(cfg.get("library_subdir", "Library")).strip() if "library_subdir" in cfg else "Library"
    parts = ["Document", sub] if sub else ["Document"]
    return _under_root(*parts)


def document_dir() -> Path | None:
    """The device's Document folder (drop a PDF here to read it), or None."""
    return _under_root("Document")


def export_dir() -> Path | None:
    """Where the device writes annotated exports, or None if no root."""
    return _under_root("EXPORT")


def mark_for(pdf: Path) -> Path:
    """The `.mark` annotation sidecar path for a PDF."""
    return pdf.with_name(pdf.name + ".mark")


def pdf_for(mark: Path) -> Path:
    """The PDF a `.mark` sidecar belongs to (strips the .mark suffix)."""
    return mark.with_name(mark.name[: -len(".mark")])


# --- misc -----------------------------------------------------------------
def backend() -> str:
    """Which AI backend reads ink: claude_code (your Claude subscription via `claude -p`,
    the default — no metered tokens) | api (Anthropic SDK, needs ANTHROPIC_API_KEY)."""
    return _str("backend", "SUPERNOTE_BACKEND", "claude_code")


def model() -> str:
    """Claude model for the `api` backend (the claude_code backend uses your Claude Code
    model setting). Ignored when backend is claude_code."""
    return _str("model", "SUPERNOTE_MODEL", "claude-opus-4-7")


def checklist() -> Path | None:
    """Optional single doc for the legacy `sync.sh out` flow."""
    return _expand(_str("checklist", "SUPERNOTE_CHECKLIST"))


def punchlist() -> Path | None:
    """Optional personal master list to append review actions/TODOs to (e.g. a PUNCHLIST.md).
    It lives OUTSIDE this repo; the path is configured here (config.toml is gitignored), so neither
    the destination nor the personal items it collects ever enter this repo's git. None = disabled
    (actions fall back to a local, gitignored file)."""
    return _expand(_str("punchlist", "SUPERNOTE_PUNCHLIST"))


def letterhead_builder() -> Path | None:
    """Optional external Markdown→PDF builder for docs with `renderer: letterhead` frontmatter
    (e.g. a branded-letterhead Node script taking `<input.md> <output.pdf>`). Lives OUTSIDE this
    repo; configured here so the path stays out of git. None = feature off (those docs fall back
    to the built-in renderer)."""
    return _expand(_str("letterhead_builder", "SUPERNOTE_LETTERHEAD_BUILDER"))


def mark_align() -> tuple[float, float]:
    """Vertical registration correction for compositing ink over the PDF page.

    The Supernote rasterizes a `.pdf.mark`'s ink in a canvas whose vertical mapping to
    the PDF page is a slight affine — ink lands too high, ~aligned at the page bottom and
    drifting up toward the top. When overlaying we remap `pdf_fraction = scale*ink + offset`
    so a mark sits on the line it was written over. Defaults measured on the Nomad; override
    per device in config.toml under `[mark_align]` (scale/offset) or via SUPERNOTE_MARK_ALIGN_*.
    (1.0, 0.0) = no correction."""
    cfg = _file_cfg().get("mark_align", {})

    def _f(key: str, env: str, default: float) -> float:
        v = os.environ.get(env) or cfg.get(key)
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    return (_f("scale", "SUPERNOTE_MARK_ALIGN_SCALE", 0.863),
            _f("offset", "SUPERNOTE_MARK_ALIGN_OFFSET", 0.133))


# --- fonts ----------------------------------------------------------------
# The renderer needs a regular/bold/italic TTF. Defaults to the bundled DejaVu Sans;
# point any of these at your own font to restyle the device PDFs.
_FONT_DIR = HERE / "assets" / "fonts"


def _font(key: str, env: str, bundled: str) -> Path:
    return _expand(_str(key, env)) or _FONT_DIR / bundled


def font_regular() -> Path:
    """Regular-weight TTF (bundled DejaVu Sans unless overridden)."""
    return _font("font_regular", "SUPERNOTE_FONT_REGULAR", "DejaVuSans.ttf")


def font_bold() -> Path:
    """Bold TTF (bundled DejaVu Sans unless overridden)."""
    return _font("font_bold", "SUPERNOTE_FONT_BOLD", "DejaVuSans-Bold.ttf")


def font_italic() -> Path:
    """Italic/oblique TTF (bundled DejaVu Sans unless overridden)."""
    return _font("font_italic", "SUPERNOTE_FONT_ITALIC", "DejaVuSans-Oblique.ttf")


# --- preferences ----------------------------------------------------------
def _pref(key: str, env: str, default: str) -> str:
    if v := os.environ.get(env):
        return v
    return str(_file_cfg().get("preferences", {}).get(key, default))


def emoji() -> str:
    """Emoji usage in notes Claude writes: none | minimal | liberal."""
    return _pref("emoji", "SUPERNOTE_EMOJI", "minimal")


def density() -> str:
    """Render spacing: compact | normal | roomy."""
    return _pref("density", "SUPERNOTE_DENSITY", "normal")


def digest_dir() -> Path:
    """Folder holding digest recipe files (see digest.py). Default: <data_dir>/digests."""
    return _expand(_str("digest_dir", "SUPERNOTE_DIGEST_DIR")) or data_dir() / "digests"


def state_dir() -> Path:
    """Where mutable runtime state lives (the read-once ledger, digest state) — set this to
    a mounted volume in a container so it survives restarts (else re-uploaded ink reprocesses
    and digests re-fire). Default: the data dir."""
    return _expand(_str("state_dir", "SUPERNOTE_STATE_DIR")) or data_dir()


def needs_you() -> Path:
    """The generated "Needs You" doc (open conflict questions). Lives under a scan_root so it
    mirrors to the device. Override with SUPERNOTE_NEEDS_YOU / config `needs_you` (relative to
    source_base, or absolute)."""
    v = _str("needs_you", "SUPERNOTE_NEEDS_YOU")
    if v:
        p = Path(os.path.expanduser(v))
        return p if p.is_absolute() else source_base() / v
    roots = scan_roots()
    return source_base() / (roots[0] if roots else "") / "NEEDS-YOU.md"


def capture_pages() -> list[Path]:
    """One blank Capture page per project (scan_root): `<root>/CAPTURE.md`. Each is `device: true`,
    so it shows at Document/<Area>/CAPTURE.pdf and routes notes into THAT project (run._process_capture)."""
    return [source_base() / root / "CAPTURE.md" for root in scan_roots()]


def capture_targets() -> dict[str, str]:
    """Map of scan_root -> the project's work tracker that captured to-dos append to, under a
    `## 📥 From Supernote` section (config `[capture_targets]`). Captured ideas instead go to the
    global Needs You tagged with the project, then graduate back to this same tracker."""
    return {str(k): str(v) for k, v in _file_cfg().get("capture_targets", {}).items()}


def capture_root_for(rel: str) -> str | None:
    """Which scan_root a capture page (source-relative `<root>/CAPTURE.md`) belongs to."""
    for root in scan_roots():
        if rel == f"{root}/CAPTURE.md":
            return root
    return None


def capture_target_for_root(root: str | None) -> Path | None:
    """The tracker doc a project's captured items route to (absolute or source_base-relative)."""
    tgt = capture_targets().get(root or "")
    if not tgt:
        return None
    p = Path(os.path.expanduser(tgt))
    return p if p.is_absolute() else source_base() / tgt


# --- shell bridge ---------------------------------------------------------
_KEYS = {
    "source_base": source_base, "supernote_root": supernote_root,
    "library": library, "document_dir": document_dir, "export_dir": export_dir,
    "model": model, "backend": backend, "checklist": checklist,
    "scan_roots": lambda: " ".join(scan_roots()),
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in _KEYS:
        sys.exit(f"usage: config.py <{' | '.join(_KEYS)}>")
    val = _KEYS[sys.argv[1]]()
    print(val if val is not None else "")
