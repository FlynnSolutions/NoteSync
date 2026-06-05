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


@lru_cache(maxsize=1)
def _file_cfg() -> dict:
    f = HERE / "config.toml"
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


# --- source side ----------------------------------------------------------
def source_base() -> Path:
    """Root the source docs are mirrored relative to (e.g. ~/Projects)."""
    return _expand(_str("source_base", "SUPERNOTE_SOURCE_BASE", "~/Projects"))


def scan_roots() -> list[str]:
    """Top-level dirs under source_base to mirror; empty list = every dir."""
    if v := os.environ.get("SUPERNOTE_SCAN_ROOTS"):
        return [r.strip() for r in v.split(",") if r.strip()]
    return list(_file_cfg().get("scan_roots", []))


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
    """Where mirrored PDFs and their `.mark` sidecars live, or None if no root."""
    return _under_root("Document", "Library")


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
    """Folder holding digest recipe files (see digest.py). Default: <repo>/digests."""
    return _expand(_str("digest_dir", "SUPERNOTE_DIGEST_DIR")) or HERE / "digests"


def state_dir() -> Path:
    """Where mutable runtime state lives (the read-once ledger, digest state) — set this to
    a mounted volume in a container so it survives restarts (else re-uploaded ink reprocesses
    and digests re-fire). Default: next to the code."""
    return _expand(_str("state_dir", "SUPERNOTE_STATE_DIR")) or HERE


def inbox() -> Path:
    """The generated "needs you" inbox doc (open conflict questions). Lives under a scan_root
    so it mirrors to the device. Override with SUPERNOTE_INBOX / config `inbox` (relative to
    source_base, or absolute)."""
    v = _str("inbox", "SUPERNOTE_INBOX")
    if v:
        p = Path(os.path.expanduser(v))
        return p if p.is_absolute() else source_base() / v
    roots = scan_roots()
    return source_base() / (roots[0] if roots else "") / "SUPERNOTE-INBOX.md"


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
