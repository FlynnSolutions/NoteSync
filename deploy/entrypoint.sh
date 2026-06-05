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
# one per scan_root); SUPERNOTE_SCAN_ROOTS (the matching subpaths); GITHUB_TOKEN (a fine-grained
# PAT with write access to those repos); plus a mounted rclone.conf.
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

# Git identity + auth. A fine-grained PAT via the credential helper keeps the token out of any
# repo URL / .git/config / log, and works for any number of repos with one secret (ADR-015).
git config --global user.name  "${GIT_USER_NAME:-supernote-sync}"
git config --global user.email "${GIT_USER_EMAIL:-supernote-sync@localhost}"
if [ -n "${GITHUB_TOKEN:-}" ]; then
  git config --global credential.helper store
  printf 'https://x-access-token:%s@github.com\n' "$GITHUB_TOKEN" > "$HOME/.git-credentials"
  chmod 600 "$HOME/.git-credentials"
fi

# Clone (first run) or fast-forward each notes repo into /work/<subpath>.
sync_repos_down() {
  local pair sub url dir
  IFS=',' read -ra _repos <<< "$DOCS_REPOS"
  for pair in "${_repos[@]}"; do
    sub="${pair%%=*}"; url="${pair#*=}"; dir="/work/${sub}"
    if [ -d "$dir/.git" ]; then git -C "$dir" pull --ff-only || true
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

cd /app
run_once() {
  # Hybrid: pull just the heartbeat (cheap) and stand down while the laptop is active.
  rclone copy "${REMOTE}/.laptop-alive" "$SUPERNOTE_ROOT/" 2>/dev/null || true
  if [ "${HEARTBEAT_STALE_SECS:-300}" != "0" ] && python3 /app/heartbeat.py alive "${HEARTBEAT_STALE_SECS:-300}"; then
    echo "laptop is active — standing down this tick (it handles sync when it's on)"
    return 0
  fi
  rclone copy "$REMOTE" "$SUPERNOTE_ROOT" || echo "rclone pull failed — continuing" >&2
  sync_repos_down
  ./sync.sh run || echo "run failed — continuing" >&2
  rclone copy "$SUPERNOTE_ROOT" "$REMOTE" || echo "rclone push failed — continuing" >&2
  push_repos_up
}

if [ "$RUN_MODE" = "oneshot" ]; then
  echo "One-shot run (backend: $(python3 config.py backend))."
  run_once
  exit 0
fi

echo "Sync loop every ${INTERVAL}s (backend: $(python3 config.py backend)). Ctrl-C to stop."
while true; do
  run_once
  sleep "$INTERVAL"
done
