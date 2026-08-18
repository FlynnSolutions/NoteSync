#!/usr/bin/env bash
#
# entrypoint.sh — the container's sync runner (laptop-closed hosting). Modes via RUN_MODE:
#   loop (default) — a pass every LOOP_INTERVAL; oneshot — one pass then exit.
#
# NO FUSE: syncs the Supernote Drive folder to a local /drive working copy via `rclone copy`
# (Drive API), so the container runs UNPRIVILEGED (ADR-016). Supports MULTIPLE notes repos.
#
# A pass = pull Drive (marks/exports) -> pull each notes repo -> `sync.sh run` (mirror + drain
# pending annotations on your Claude subscription, serially) -> push PDFs to Drive -> push each
# notes repo. Copies are additive so a concurrent device write is never lost. See EC2-SETUP.md.
#
# Required (via loop.env): CLAUDE_CODE_OAUTH_TOKEN; DOCS_REPOS (comma list of `subpath=URL`,
# one per scan_root); a GitHub PAT with Contents:write on those repos — GITHUB_TOKEN (one owner)
# or GITHUB_TOKENS="owner:token,..." (repos spanning owners); plus a mounted rclone.conf.
set -euo pipefail

: "${CLAUDE_CODE_OAUTH_TOKEN:?set CLAUDE_CODE_OAUTH_TOKEN (run \`claude setup-token\`)}"
: "${DOCS_REPOS:?set DOCS_REPOS (comma list of subpath=git-url, one per scan_root)}"
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL   # force the subscription
RCLONE_REMOTE="${RCLONE_REMOTE:-gdrive}"
DRIVE_PATH="${DRIVE_PATH:-Supernote}"              # the Supernote folder's name in your Drive
REMOTE="${RCLONE_REMOTE}:${DRIVE_PATH}"
export SUPERNOTE_ROOT="/drive/${DRIVE_PATH}"       # local working copy of that folder
INTERVAL="${LOOP_INTERVAL:-300}"
RUN_MODE="${RUN_MODE:-loop}"

# The folders to mirror ARE the DOCS_REPOS subpaths — derive them so you don't repeat (or
# mismatch) the list. Override SUPERNOTE_SCAN_ROOTS only in the rare case they should differ.
_subs=""; IFS=',' read -ra _r <<< "$DOCS_REPOS"
for _p in "${_r[@]}"; do _subs="${_subs:+$_subs,}${_p%%=*}"; done
export SUPERNOTE_SCAN_ROOTS="${SUPERNOTE_SCAN_ROOTS:-$_subs}"

mkdir -p "$SUPERNOTE_ROOT" /work /state

# rclone must rewrite its config to persist the OAuth access token it refreshes (~hourly), so
# it needs a WRITABLE config — a read-only/bind-mounted file can't be renamed (rclone saves
# atomically), which would 401 mid-run once the token expired. Seed a writable copy from the
# read-only mount once; thereafter the live copy (with refreshed tokens) is kept on its volume.
mkdir -p "$HOME/.config/rclone"
if [ ! -f "$HOME/.config/rclone/rclone.conf" ] && [ -f /seed/rclone.conf ]; then
  cp /seed/rclone.conf "$HOME/.config/rclone/rclone.conf"
fi

# Git identity + auth. Tokens go through the credential helper, never into a repo URL /
# .git/config / log (ADR-015). Two shapes:
#   GITHUB_TOKEN  — one PAT for every repo (all repos under a single owner).
#   GITHUB_TOKENS — "owner:token,owner:token" when repos span owners; fine-grained PATs are
#                   owner-scoped, so each owner needs its own. Matched per-repo by exact path.
git config --global user.name  "${GIT_USER_NAME:-NoteSync}"
git config --global user.email "${GIT_USER_EMAIL:-NoteSync@localhost}"
if [ -n "${GITHUB_TOKENS:-}" ]; then
  git config --global credential.helper store
  git config --global credential.useHttpPath true   # so a per-repo path picks the right token
  : > "$HOME/.git-credentials"; chmod 600 "$HOME/.git-credentials"
  declare -A _tok; IFS=',' read -ra _pairs <<< "$GITHUB_TOKENS"
  for _p in "${_pairs[@]}"; do _tok["${_p%%:*}"]="${_p#*:}"; done
  IFS=',' read -ra _repos <<< "$DOCS_REPOS"
  for pair in "${_repos[@]}"; do
    rest="${pair#*=}"; rest="${rest#https://github.com/}"   # OWNER/REPO.git
    token="${_tok[${rest%%/*}]:-${GITHUB_TOKEN:-}}"
    [ -n "$token" ] || { echo "no token for owner ${rest%%/*} — add it to GITHUB_TOKENS" >&2; continue; }
    printf 'https://x-access-token:%s@github.com/%s\n' "$token" "$rest" >> "$HOME/.git-credentials"
  done
elif [ -n "${GITHUB_TOKEN:-}" ]; then
  git config --global credential.helper store
  printf 'https://x-access-token:%s@github.com\n' "$GITHUB_TOKEN" > "$HOME/.git-credentials"
  chmod 600 "$HOME/.git-credentials"
fi

# Clone (first run) or fast-forward each notes repo into /work/<subpath>.
# Device pages (CAPTURE.md and friends) are regenerated every pass, so a checkout is
# perpetually dirty. An --ff-only pull REFUSES when an incoming commit touches one of
# them, and with the old `|| true` that failure was invisible: hq and imbas each sat
# wedged for a month (imbas 43 commits behind, 2026-07-21 -> 2026-08-18) while the device
# kept mirroring stale docs. Discarding is safe because uncommitted == regenerated output:
# anything worth keeping is committed by vcs.commit_paths during `sync.sh run`. Untracked
# files are left alone, and a pull that still fails is now LOUD.
sync_repos_down() {
  local pair sub url dir
  IFS=',' read -ra _repos <<< "$DOCS_REPOS"
  for pair in "${_repos[@]}"; do
    sub="${pair%%=*}"; url="${pair#*=}"; dir="/work/${sub}"
    if [ -d "$dir/.git" ]; then
      git -C "$dir" checkout -- . 2>/dev/null || true   # drop regenerated dirt, keep untracked
      git -C "$dir" pull --ff-only \
        || echo "ERROR: pull failed for $sub — it is diverging and the device will go stale" >&2
    else git clone "$url" "$dir" || echo "clone failed: $sub" >&2; fi
  done
}
push_repos_up() {
  local pair sub
  IFS=',' read -ra _repos <<< "$DOCS_REPOS"
  for pair in "${_repos[@]}"; do
    sub="${pair%%=*}"; git -C "/work/${sub}" push || true
  done
}

# The rendered-library namespace on Drive, matching config.library(): SUPERNOTE_LIBRARY_SUBDIR
# unset -> the "Library" default; explicitly empty -> straight into Document/ (the flattened
# layout). Set it in loop.env to whatever the laptop's config.toml uses, or the two sides
# mirror DIFFERENT trees and the device syncs both.
_lib_sub="${SUPERNOTE_LIBRARY_SUBDIR-Library}"
LIB_REL="Document${_lib_sub:+/${_lib_sub}}"

# Self-healing backstop: the rendered library is a DERIVED artifact — every PDF is reproducible
# from the repos — so duplicate names there can never be unique data. A transient error mid-push
# can make Drive twin a folder (Drive allows same-name siblings), which then blocks the device's
# sync. Merging identical duplicates each pass clears that automatically. Scoped to the rendered
# library namespace ONLY — never EXPORT/Note, where your ink lives.
dedupe_library() {
  rclone lsf "${REMOTE}/${LIB_REL}" >/dev/null 2>&1 || return 0   # nothing rendered yet
  rclone dedupe --dedupe-mode newest "${REMOTE}/${LIB_REL}" 2>&1 \
    | grep -i 'duplicate' >&2 || true
}

# Propagate Drive-side DELETIONS into the local working copy for the derived library files
# (rendered *.pdf + their *.pdf.mark sidecars). Both transfer legs are additive `rclone copy`,
# so without this a file the laptop prunes from Drive lives on in /drive forever and the next
# push RESURRECTS it — the device then re-downloads the whole tree every cycle. Runs BEFORE
# mirror renders (a fresh local render is local-only and a sync here would delete it). The
# filter keeps it inside the library namespace, and a device-written mark exists remote-side
# first, so syncing DOWN can never drop unread ink.
sync_library_down() {
  rclone lsf "${REMOTE}/${LIB_REL}" >/dev/null 2>&1 || return 0   # nothing rendered yet
  rclone sync "${REMOTE}/${LIB_REL}" "${SUPERNOTE_ROOT}/${LIB_REL}" \
    --include "*.pdf" --include "*.pdf.mark"
}

cd /app
run_once() {
  local rc=0
  # Hybrid: pull just the heartbeat (cheap) and stand down while the laptop is active.
  rclone copy "${REMOTE}/.laptop-alive" "$SUPERNOTE_ROOT/" 2>/dev/null || true
  if [ "${HEARTBEAT_STALE_SECS:-300}" != "0" ] && python3 /app/heartbeat.py alive "${HEARTBEAT_STALE_SECS:-300}"; then
    echo "laptop is active — standing down this tick (it handles sync when it's on)"
    return 0
  fi
  rclone copy "$REMOTE" "$SUPERNOTE_ROOT" || { echo "ERROR: rclone pull failed" >&2; rc=1; }
  sync_library_down || { echo "ERROR: library deletion-sync failed" >&2; rc=1; }
  sync_repos_down
  ./sync.sh run || { echo "ERROR: sync.sh run failed" >&2; rc=1; }
  # Push, then dedupe the derived Library so a partial push never leaves the device blocked.
  if rclone copy "$SUPERNOTE_ROOT" "$REMOTE"; then
    dedupe_library
  else
    echo "ERROR: rclone push failed — Drive may be partial; deduping defensively" >&2
    dedupe_library
    rc=1
  fi
  push_repos_up
  return $rc
}

if [ "$RUN_MODE" = "oneshot" ]; then
  echo "One-shot run (backend: $(python3 config.py backend))."
  if run_once; then exit 0; else echo "ERROR: one-shot pass had failures (see above)" >&2; exit 1; fi
fi

echo "Sync loop every ${INTERVAL}s (backend: $(python3 config.py backend)). Ctrl-C to stop."
while true; do
  run_once || echo "ERROR: pass had failures (see above) — retrying next tick in ${INTERVAL}s" >&2
  sleep "$INTERVAL"
done
