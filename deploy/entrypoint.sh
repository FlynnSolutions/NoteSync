#!/usr/bin/env bash
#
# entrypoint.sh — the unattended sync loop for the container.
#
# UNVERIFIED SKELETON (see deploy/HOSTING.md). This has not run in a real deploy. The
# shape is right and it reuses the tested pipeline, but the check-in orchestration and the
# git/branch posture need finishing + testing against a live device before you trust it.
#
# Requires (env / secrets): ANTHROPIC_API_KEY, DOCS_REPO (git URL of your notes repo),
# and an rclone remote named by RCLONE_REMOTE (default: gdrive) configured via a mounted
# rclone.conf. Needs FUSE: run with --cap-add SYS_ADMIN --device /dev/fuse.
set -euo pipefail

: "${ANTHROPIC_API_KEY:?set ANTHROPIC_API_KEY}"
: "${DOCS_REPO:?set DOCS_REPO (git URL of your notes repo)}"
RCLONE_REMOTE="${RCLONE_REMOTE:-gdrive}"
INTERVAL="${LOOP_INTERVAL:-300}"

# 1. Mount Google Drive (rclone.conf must be present; FUSE required).
mkdir -p /drive
rclone mount "${RCLONE_REMOTE}:" /drive --daemon --vfs-cache-mode writes
sleep 5

# 2. Clone/refresh the docs repo into the source base (applied edits are git commits).
[ -d /work/.git ] || git clone "$DOCS_REPO" /work

# 3. Loop: render docs out, read back any pending annotations, push doc edits.
cd /app
while true; do
  git -C /work pull --ff-only || true

  python3 mirror.py || true

  # Check-in: process every doc with a pending, unread annotation.
  # NOTE: this is the part to finish — `pending.py` returns ONE doc; a real loop should
  # drain all pending docs, and apply should land on a review branch, not straight to main
  # (see HOSTING.md "Safety posture"). Left explicit rather than faked.
  pdf="$(python3 pending.py 2>/dev/null || true)"
  if [ -n "$pdf" ]; then
    ./sync.sh in "$pdf" || true
    # derive the source rel via route/manifest, then read + merge --apply ... (TODO)
    echo "pending annotation found ($pdf) — wire the read+apply+branch step here"
  fi

  git -C /work push || true
  sleep "$INTERVAL"
done
