#!/usr/bin/env bash
#
# entrypoint.sh — the container's sync runner (laptop-closed hosting). Two modes via RUN_MODE:
#   loop     (default) self-schedules: mount Drive once, then run a pass every LOOP_INTERVAL.
#   oneshot  mount, run ONE pass, flush, exit — for an external trigger (host cron for the
#            clockwork, or the heartbeat for on-demand). "scheduled -> cron, on-demand -> heartbeat".
#
# A pass = pull the docs repo, run `sync.sh run` (due digests -> mirror -> drain ALL pending
# annotations, reading ink on your Claude subscription, serially — never bursting), push edits.
# See deploy/EC2-SETUP.md.
#
# Auth: uses CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`) — your subscription, not
# the metered API. ANTHROPIC_API_KEY is deliberately unset: if present it OVERRIDES the
# subscription token (Claude Code credential precedence) and bills the API instead.
#
# Required env/secrets: CLAUDE_CODE_OAUTH_TOKEN, DOCS_REPO (git URL of your notes repo),
# and a mounted rclone.conf with a remote named $RCLONE_REMOTE (default gdrive). Needs
# FUSE: run with --cap-add SYS_ADMIN --device /dev/fuse.
set -euo pipefail

: "${CLAUDE_CODE_OAUTH_TOKEN:?set CLAUDE_CODE_OAUTH_TOKEN (run \`claude setup-token\` on a machine with a browser)}"
: "${DOCS_REPO:?set DOCS_REPO (git URL of your notes repo)}"
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL   # force the subscription
RCLONE_REMOTE="${RCLONE_REMOTE:-gdrive}"
INTERVAL="${LOOP_INTERVAL:-300}"
RUN_MODE="${RUN_MODE:-loop}"       # loop = self-scheduled; oneshot = one pass then exit

mkdir -p /drive /work /state

# 1. Mount Google Drive (rclone.conf must be present; FUSE required). Wait for it to come up.
echo "Mounting ${RCLONE_REMOTE}: -> /drive ..."
rclone mount "${RCLONE_REMOTE}:" /drive --daemon --vfs-cache-mode writes \
    --dir-cache-time 30s --vfs-cache-max-age 1h --vfs-cache-max-size 256M
for _ in $(seq 1 30); do grep -q " /drive " /proc/mounts && break; sleep 1; done
grep -q " /drive " /proc/mounts || { echo "rclone mount failed (check rclone.conf and FUSE caps)" >&2; exit 1; }

# 2. Clone/refresh the docs repo into the source base (applied edits are revertible commits there).
if [ -d /work/.git ]; then git -C /work pull --ff-only || true
else git clone "$DOCS_REPO" /work; fi
git -C /work config user.name  "${GIT_USER_NAME:-supernote-sync}"
git -C /work config user.email "${GIT_USER_EMAIL:-supernote-sync@localhost}"

# 3. Run passes. A pass is serial (run.py drains pending docs one at a time — no bursting,
#    which is what trips the subscription's short-window/concurrency rate limits).
cd /app
run_once() {
  # Hybrid: stand down while the laptop's watcher is active (it stamps .laptop-alive in Drive).
  # The cloud only works when that heartbeat is stale (laptop off). HEARTBEAT_STALE_SECS=0
  # disables the gate (cloud always runs — for a no-laptop / cloud-only setup).
  if [ "${HEARTBEAT_STALE_SECS:-300}" != "0" ] && python3 /app/heartbeat.py alive "${HEARTBEAT_STALE_SECS:-300}"; then
    echo "laptop is active — standing down this tick (it handles sync when it's on)"
    return 0
  fi
  git -C /work pull --ff-only || true
  ./sync.sh run || echo "run failed — continuing" >&2
  git -C /work push || true
}

if [ "$RUN_MODE" = "oneshot" ]; then
  # External trigger (host cron / heartbeat): one pass, flush Drive writes, exit.
  echo "One-shot run (backend: $(python3 config.py backend))."
  run_once
  fusermount3 -u /drive 2>/dev/null || true   # unmount flushes pending rclone uploads
  exit 0
fi

echo "Sync loop every ${INTERVAL}s (backend: $(python3 config.py backend)). Ctrl-C to stop."
while true; do
  # If the FUSE mount died, mirror/pending silently find nothing — bail so the restart
  # policy re-runs startup (and remounts) instead of looping over an empty /drive.
  grep -q " /drive " /proc/mounts || { echo "drive mount lost — exiting to restart" >&2; exit 1; }
  run_once
  sleep "$INTERVAL"
done
