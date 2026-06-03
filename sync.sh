#!/usr/bin/env bash
#
# sync.sh — one-command check-out / check-in for the Supernote TODO loop.
#
#   ./sync.sh out         export the markdown -> PDF, push to the Nomad's Document folder
#   ./sync.sh in [FILE]   convert an annotated export -> page PNGs for Claude to read
#                         (FILE optional; defaults to the newest file in EXPORT/)
#   ./sync.sh mirror      render the whole doc tree -> PDFs into the Drive Library (matching paths) + manifest
#   ./sync.sh reconcile REL [--apply]   3-way merge device edits into the source doc (conflict-aware)
#   ./sync.sh process REL [--apply]     hands-off: read ink via Claude API -> merge -> apply (needs ANTHROPIC_API_KEY)
#   ./sync.sh snapshot    commit the current checklist into the versioned safety-net mirror
#   ./sync.sh status      show what's in the device Document/ and EXPORT/ folders
#
set -euo pipefail

# --- config ---------------------------------------------------------------
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$HERE/.venv/bin/python"
# Resolve a setting via config.py (config.toml / SUPERNOTE_* env / auto-detected
# Google Drive for Desktop mount). The device mirrors its folder tree to a Supernote/
# folder in Drive; the sync is BIDIRECTIONAL (writing Document/ pushes to the device,
# the device writes annotated exports to EXPORT/). Resolved lazily, per command.
cfg() { "$PY" "$HERE/config.py" "$1"; }

cmd="${1:-help}"

case "$cmd" in
  out)
    CHECKLIST="$(cfg checklist)"
    [ -n "$CHECKLIST" ] || { echo "No 'checklist' configured (set it in config.toml or \$SUPERNOTE_CHECKLIST)."; exit 1; }
    base="$(basename "$CHECKLIST" .md)"
    PDF_OUT="$HERE/out/$base.pdf"
    mkdir -p "$HERE/out"
    "$PY" "$HERE/export.py" "$CHECKLIST" "$PDF_OUT" --status "on-device since $(date +%Y-%m-%d\ %H:%M)"
    DOC_DIR="$(cfg document_dir)"
    if [ -n "$DOC_DIR" ] && [ -d "$DOC_DIR" ]; then
      cp "$PDF_OUT" "$DOC_DIR/$base.pdf"
      echo "Pushed to Drive Supernote/Document/ — syncs to the device automatically (give it a few seconds)."
    else
      echo "Supernote folder not found; PDF is at: $PDF_OUT"
    fi
    ;;

  mirror)
    # Render the whole doc tree -> PDFs into the device-synced Drive Library at
    # matching relative paths, and write the manifest for trip-back routing.
    "$PY" "$HERE/mirror.py" "${@:2}"
    ;;

  reconcile)
    # 3-way merge the device's edits (device/<rel>, written by Claude from the ink)
    # into the live source. Clean -> --apply writes + re-mirrors; conflicts
    # -> markers in merge_out/ for resolution. See ADR-008.
    "$PY" "$HERE/reconcile.py" "${@:2}"
    ;;

  process)
    # Hands-off: read the ink via the Claude API -> device/<rel>, then 3-way
    # merge + apply + re-mirror. Needs ANTHROPIC_API_KEY (env or .env). $2 = rel.
    rel="${2:?usage: sync.sh process REL [--apply]}"
    "$PY" "$HERE/read_ink.py" --rel "$rel" || exit 1
    "$PY" "$HERE/reconcile.py" "$rel" "${@:3}"
    ;;

  in)
    src="${2:-}"
    if [ -z "$src" ]; then
      # "What's new" = docs with a pending .mark sidecar (not just newest in EXPORT).
      src="$("$PY" "$HERE/pending.py")" || {
        echo "Nothing to process — no doc has pending annotations. Annotate a doc and"
        echo "Export-with-annotations on the device first."; exit 1; }
      echo "Pending annotation -> $src"
    fi
    # Resolve the .mark annotation layer and its source PDF from whatever was given
    # (a Library PDF or the .mark itself).
    case "$src" in
      *.mark) mark="$src"; pdf="${src%.mark}";;
      *)      pdf="$src";  mark="${src}.mark";;
    esac
    if [ ! -f "$mark" ]; then
      echo "No .mark annotation layer next to: $pdf"; exit 1
    fi
    # Extract the user's ink straight from the .mark layer (color-independent) and
    # composite it over the original PDF page for layout context. This replaces the
    # old rasterize-export + red-pixel isolation — no red pen required, exact marks.
    rm -rf "$HERE/checkin_pages"
    "$PY" "$HERE/marklayer.py" "$mark" --pdf "$pdf" --out "$HERE/checkin_pages"
    # Route the annotated file to its source AND detect laptop-side drift (conflict check).
    echo; echo "Trip-back routing + conflict check:"
    "$PY" "$HERE/route.py" "$pdf"
    echo
    echo "Next: automated  -> ./sync.sh process <rel> --apply   (reads ink via Claude API + merges)"
    echo "      or manual   -> Claude reads checkin_pages/ink/*.png and writes device/<rel>, then reconcile"
    ;;

  snapshot)
    # Commit the current canonical checklist into the versioned mirror so every
    # reconcile is recoverable (the safety net under auto-apply). Reverting a bad
    # handwriting read = `git -C <repo> revert` / copy an old snapshots/ version back.
    CHECKLIST="$(cfg checklist)"
    [ -n "$CHECKLIST" ] || { echo "No 'checklist' configured (set it in config.toml or \$SUPERNOTE_CHECKLIST)."; exit 1; }
    msg="${2:-checklist snapshot $(date +%Y-%m-%d\ %H:%M)}"
    mkdir -p "$HERE/snapshots"
    cp "$CHECKLIST" "$HERE/snapshots/$(basename "$CHECKLIST")"
    git -C "$HERE" add -A snapshots
    if git -C "$HERE" diff --cached --quiet; then
      echo "No checklist changes since last snapshot."
    else
      git -C "$HERE" commit -q -m "$msg" && echo "Snapshot committed: $msg"
    fi
    ;;

  status)
    DOC_DIR="$(cfg document_dir)"; EXPORT_DIR="$(cfg export_dir)"
    echo "Document/ (drop PDFs here to annotate):"
    [ -n "$DOC_DIR" ] && ls -t "$DOC_DIR" 2>/dev/null | head || echo "  (folder not found)"
    echo
    echo "EXPORT/ (device exports land here):"
    [ -n "$EXPORT_DIR" ] && ls -t "$EXPORT_DIR" 2>/dev/null | head || echo "  (folder not found)"
    ;;

  *)
    grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -9
    ;;
esac
