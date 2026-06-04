# Remote hosting — run the loop with the laptop off

Goal: the sync loop runs unattended in the cloud, so docs mirror out and annotations get
read back without your machine on.

> **This file is the *why* (the architecture decision). For the step-by-step runbook, see
> [EC2-SETUP.md](./EC2-SETUP.md).**
>
> **Status: built, not yet deployed end-to-end.** The image builds and the loop logic is
> verified locally; the live path needs *your* Google Drive OAuth + Claude token (one-time
> interactive steps). Treat it as a tested kit + runbook, not a one-click deploy.

## The decision: a persistent container, not a Lambda

We assumed AWS Lambda. After studying the space (notably `allenporter/supernote`, a mature
self-hosted Supernote server), **Lambda is the wrong tool here**, for concrete reasons:

- **The Google Drive dependency fights serverless.** The whole tool reaches the device
  through the Drive folder. A Lambda has no Drive mount; you'd bolt on `rclone` (a FUSE
  mount, awkward in Lambda) or the Drive API, fighting the 15-minute cap and cold /tmp.
- **This domain deploys as a persistent service.** The reference self-hosted Supernote
  projects run as always-on servers/containers (on a NAS, VPS, or a small box), because
  the work is event-ish and stateful, not a quick stateless function.
- **Our config layer already makes the *container* path trivial.** Set `SUPERNOTE_ROOT`
  to an rclone-mounted Drive path and the existing pipeline runs unchanged — no code
  refactor. (That env override was built for exactly this.)

So: **a small persistent container** (a $5 VPS, a Fargate task, a Pi, or a NAS) that mounts
Drive via rclone and runs the loop on an interval. Cheaper to reason about, no timeout
cliff, and it reuses the tested pipeline as-is.

A note on the *bigger* alternative, for later: the reference projects implement the
**Supernote Private Cloud protocol**, so the device syncs *directly* to their server with
no Google Drive at all. That eliminates the Drive dependency entirely — but it's a large
undertaking (reverse-engineered auth + file-sync protocol + storage). Out of scope now;
flagged as the "someday, if Drive becomes the bottleneck" direction.

## How the container loop works

`entrypoint.sh` (this dir):
1. **Mounts** your Drive at `/drive` via rclone (from a mounted `rclone.conf`).
2. Clones/pulls your **docs git repo** into `/work` (so applied edits are revertible
   commits, per the safety model — and can be pushed back).
3. Loops on an interval: `./sync.sh run` = due digests → `mirror` (render docs → device) →
   drain **every** doc with a pending annotation (read ink → 3-way merge → apply) → push.

Auth is your **Claude subscription**, not the metered API: the container needs
`CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) and deliberately **unsets**
`ANTHROPIC_API_KEY` — if set, it overrides the subscription token and bills the API.

The image bundles the runtime deps: the **Claude Code CLI** (`claude`), `poppler`
(`pdftoppm`), `supernotelib` (`supernote-tool`), the bundled font, and the Python
requirements.

## What only you can do (the hard external dependencies)

These are why this can't be a turn-key autonomous deploy:

1. **Google Drive auth (one-time, interactive):** `rclone config` to create a `gdrive`
   remote (OAuth in a browser). Save the resulting `rclone.conf` as a secret.
2. **A host:** a VPS / Fargate / NAS / Pi that can run a container with FUSE
   (`--cap-add SYS_ADMIN --device /dev/fuse`).
3. **Docs-repo write access:** a deploy key (or token) so the container can pull/push the
   notes git repo.
4. **Claude subscription token** (`claude setup-token`) as a secret — not an API key.
5. **Decide the cadence** (the loop interval) and the review posture — see below.

(The full walkthrough for all five is in [EC2-SETUP.md](./EC2-SETUP.md).)

## Safety posture (carry the local guarantees into the cloud)

- The loop applies ink edits, which are non-deterministic reads. They land as **revertible
  `supernote:` commits** in the notes repo (the container sets its git identity and pushes),
  so any misread is `git revert`-able. Landing them on a review branch instead of `main` is
  a worthwhile hardening if you want a human gate before they're canonical.
- Conflicts already halt (markers in `merge_out/`, no auto-apply) — that protection holds in
  the cloud; the doc stays pending until you resolve the source.
- State that must survive restarts (the read-once `.mark` ledger + digest state) lives under
  `SUPERNOTE_STATE_DIR=/state` on a named volume, or re-uploaded ink reprocesses and digests
  re-fire. The notes repo persists on its own volume.

## Run it locally first (recommended before any cloud)

You can exercise the whole container on your own machine before paying for a host:

```bash
cd deploy
# one-time: create the gdrive rclone remote + a Claude token, then:
cp ~/.config/rclone/rclone.conf ./rclone.conf
cp loop.env.example loop.env && nano loop.env   # CLAUDE_CODE_OAUTH_TOKEN, DOCS_REPO
docker compose up --build                 # mounts Drive, runs the loop
```

If that works on your machine, the same image runs on any container host.
