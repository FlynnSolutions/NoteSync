#!/usr/bin/env bash
#
# sync.sh — one-command check-out / check-in for the Supernote doc loop.
#
#   ./sync.sh init        interactive first-run setup (paths + preferences -> config.toml)
#   ./sync.sh mirror      render the whole doc tree -> PDFs into the Drive Library (matching paths) + manifest
#   ./sync.sh run         do all due work: digests -> mirror -> drain ALL pending annotations (the heartbeat entry point)
#   ./sync.sh watch       local sync engine (run on your laptop): edits -> device, device annotations -> docs, + the hybrid heartbeat
#   ./sync.sh in [FILE]   extract a pending annotation's ink -> page PNGs for Claude to read
#   ./sync.sh process REL [--apply]     hands-off: read ink via Claude API -> merge -> apply (needs ANTHROPIC_API_KEY)
#   ./sync.sh reconcile REL [--apply]   3-way merge device edits into the source doc (conflict-aware)
#   ./sync.sh digest [NAME]      generate "daily reading" digest(s) from recipes in digests/
#   ./sync.sh calibrate [read]   handwriting scribble test: make the sheet (or read a filled one)
#   ./sync.sh out         export the configured checklist -> PDF, push to the device
#   ./sync.sh snapshot    commit the current checklist into the versioned safety-net mirror
#   ./sync.sh status      show what's in the device Document/ and EXPORT/ folders
#
set -euo pipefail

# --- config ---------------------------------------------------------------
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$HERE/.venv/bin/python"
[ -x "$PY" ] || PY="python3"   # fall back to system python (e.g. in a container)
# Resolve a setting via config.py (config.toml / SUPERNOTE_* env / auto-detected
# Google Drive for Desktop mount). The device mirrors its folder tree to a Supernote/
# folder in Drive; the sync is BIDIRECTIONAL (writing Document/ pushes to the device,
# the device writes annotated exports to EXPORT/). Resolved lazily, per command.
cfg() { "$PY" "$HERE/config.py" "$1"; }

cmd="${1:-help}"

case "$cmd" in
  init)
    # Interactive first-run setup: writes config.toml + .env. Re-runnable to update.
    "$PY" "$HERE/setup.py"
    ;;

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

  run)
    # One-shot "do all due work" pass for a scheduler/heartbeat: due digests ->
    # mirror -> drain EVERY pending annotation (read on your Claude subscription,
    # 3-way merge, apply). Conflicts are left for manual resolution. See run.py.
    "$PY" "$HERE/run.py" "${@:2}"
    ;;

  watch)
    # Local sync engine (run on your laptop; keeps the cloud server optional). Both directions:
    # source .md change -> mirror to device + commit/push ONLY that file (scoped to scan_roots);
    # new device annotation -> read back + 3-way merge. Plus the .laptop-alive heartbeat so the
    # cloud standby defers while this runs. `watch --dry-run` first. See watch.py.
    "$PY" "$HERE/watch.py" "${@:2}"
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

  digest)
    # Generate "daily reading" digests from your recipes (digests/), then mirror to push.
    "$PY" "$HERE/digest.py" "${2:-}"
    ;;

  calibrate)
    # Handwriting scribble test. `calibrate` makes the sheet and pushes it to the device;
    # `calibrate read` builds handwriting/QUIRKS.md from a filled sheet's extracted ink.
    if [ "${2:-}" = "read" ]; then
      "$PY" "$HERE/calibrate.py" read "$HERE/checkin_pages"
    else
      mkdir -p "$HERE/out"
      sheet="$HERE/out/handwriting-calibration.pdf"
      "$PY" "$HERE/calibrate.py" sheet "$sheet"
      DOC_DIR="$(cfg document_dir)"
      if [ -n "$DOC_DIR" ] && [ -d "$DOC_DIR" ]; then
        cp "$sheet" "$DOC_DIR/" && echo "Pushed the calibration sheet to the device. Fill it in, then: ./sync.sh in && ./sync.sh calibrate read"
      else
        echo "Sheet is at: $sheet"
      fi
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
    grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -14
    ;;
esac
