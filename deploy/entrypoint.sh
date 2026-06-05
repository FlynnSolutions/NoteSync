#!/usr/bin/env bash
#
# entrypoint.sh — the container's sync runner (laptop-closed hosting). Two modes via RUN_MODE:
#   loop     (default) self-schedules: a pass every LOOP_INTERVAL.
#   oneshot  one pass then exit — for an external trigger (host cron / heartbeat).
#
# NO FUSE: instead of `rclone mount` (which needs the SYS_ADMIN capability), it syncs the
# Supernote Drive folder to a LOCAL working copy with `rclone copy` over the Drive API. So the
# container runs UNPRIVILEGED + with no special capabilities. See ADR-016 / EC2-SETUP.md.
#
# A pass = pull Drive (marks/exports) -> pull the docs repo -> `sync.sh run` (digests -> mirror
# -> drain pending annotations on your Claude subscription, serially) -> push rendered PDFs to
# Drive -> push doc edits. Copies are additive (no deletes) so a concurrent device write is
# never lost; consumed exports linger on Drive but the read-once ledger ignores them.
#
# Auth: CLAUDE_CODE_OAUTH_TOKEN (subscription, not the metered API — the ANTHROPIC_* family is
# unset). Git over an SSH deploy-key (ADR-015). Required: CLAUDE_CODE_OAUTH_TOKEN, DOCS_REPO,
# a mounted rclone.conf (remote $RCLONE_REMOTE, default gdrive), a mounted deploy_key.
set -euo pipefail

: "${CLAUDE_CODE_OAUTH_TOKEN:?set CLAUDE_CODE_OAUTH_TOKEN (run \`claude setup-token\` on a machine with a browser)}"
: "${DOCS_REPO:?set DOCS_REPO (git URL of your notes repo)}"
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL   # force the subscription
RCLONE_REMOTE="${RCLONE_REMOTE:-gdrive}"
DRIVE_PATH="${DRIVE_PATH:-Supernote}"              # the Supernote folder's name in your Drive
REMOTE="${RCLONE_REMOTE}:${DRIVE_PATH}"
export SUPERNOTE_ROOT="/drive/${DRIVE_PATH}"       # local working copy of that folder
INTERVAL="${LOOP_INTERVAL:-300}"
RUN_MODE="${RUN_MODE:-loop}"

mkdir -p "$SUPERNOTE_ROOT" /work /state

# Git auth via a mounted SSH deploy-key (no token in the repo URL/.git/config/logs).
if [ -f /run/secrets/deploy_key ]; then
  chmod 600 /run/secrets/deploy_key 2>/dev/null || true
  export GIT_SSH_COMMAND="ssh -i /run/secrets/deploy_key -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
fi

# Clone/refresh the docs repo (applied edits are revertible commits there).
if [ -d /work/.git ]; then git -C /work pull --ff-only || true
else git clone "$DOCS_REPO" /work; fi
git -C /work config user.name  "${GIT_USER_NAME:-supernote-sync}"
git -C /work config user.email "${GIT_USER_EMAIL:-supernote-sync@localhost}"

cd /app
run_once() {
  # Hybrid: pull just the heartbeat file (cheap) and stand down while the laptop is active.
  # HEARTBEAT_STALE_SECS=0 disables the gate (cloud-only setup, no laptop).
  rclone copy "${REMOTE}/.laptop-alive" "$SUPERNOTE_ROOT/" 2>/dev/null || true
  if [ "${HEARTBEAT_STALE_SECS:-300}" != "0" ] && python3 /app/heartbeat.py alive "${HEARTBEAT_STALE_SECS:-300}"; then
    echo "laptop is active — standing down this tick (it handles sync when it's on)"
    return 0
  fi
  rclone copy "$REMOTE" "$SUPERNOTE_ROOT" || echo "rclone pull failed — continuing" >&2
  git -C /work pull --ff-only || true
  ./sync.sh run || echo "run failed — continuing" >&2
  rclone copy "$SUPERNOTE_ROOT" "$REMOTE" || echo "rclone push failed — continuing" >&2
  git -C /work push || true
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
