# Remote hosting — run the loop with the laptop off

Goal: the sync loop runs unattended in the cloud, so docs mirror out and annotations get
read back without your machine on.

> **Status: scaffolding, NOT yet deployed or verified.** The artifacts here (Dockerfile,
> entrypoint, compose) are a starting point. Standing this up needs *your* accounts and a
> one-time auth you have to do interactively — see "What only you can do" below. Nothing
> here has run in a real cloud; treat it as a reviewed design + starter kit, not a
> turn-key deploy.

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
1. Writes an `rclone.conf` from a secret and **mounts** your Drive at `/drive`.
2. Exports `SUPERNOTE_ROOT=/drive/My Drive/Supernote`, `SUPERNOTE_SOURCE_BASE=/work`,
   and `ANTHROPIC_API_KEY` (from secrets).
3. Clones/pulls your **docs git repo** into `/work` (so applied edits are revertible
   commits, per the safety model — and can be pushed back).
4. Loops on an interval: `mirror` (render docs → device) → `pending` → `process --apply`
   for any annotations the device has exported → commit/push doc edits.

The image bundles the runtime deps: `poppler` (`pdftoppm`), `supernotelib`
(`supernote-tool`), the bundled font, and the Python requirements.

## What only you can do (the hard external dependencies)

These are why this can't be a turn-key autonomous deploy:

1. **Google Drive auth (one-time, interactive):** `rclone config` to create a `gdrive`
   remote (OAuth in a browser). Save the resulting `rclone.conf` as a secret.
2. **A host:** a VPS / Fargate / NAS / Pi that can run a container with FUSE
   (`--cap-add SYS_ADMIN --device /dev/fuse`).
3. **Docs-repo write access:** a deploy key (or token) so the container can pull/push the
   notes git repo.
4. **Anthropic API key** as a secret.
5. **Decide the cadence** (the loop interval) and the review posture — see below.

## Safety posture (carry the local guarantees into the cloud)

- The loop runs `process --apply`, which is non-deterministic. Per the design, applied doc
  edits should land as **revertible commits**, and ideally on a branch / as a PR rather
  than straight to `main`, so an unattended misread is reviewable. Wire the container's
  git identity + a branch before trusting it fully.
- Conflicts already halt (markers, no auto-apply) — that protection holds in the cloud.
- The read-once `.mark` ledger (`processed_marks.json`) must persist across container
  restarts (mount it on a volume), or re-uploaded ink reprocesses.

## Run it locally first (recommended before any cloud)

You can exercise the whole container on your own machine before paying for a host:

```bash
cd deploy
# one-time: create the gdrive rclone remote, then:
cp ~/.config/rclone/rclone.conf ./rclone.conf
echo "ANTHROPIC_API_KEY=sk-..." > ./loop.env
docker compose up --build      # mounts Drive, runs the loop
```

If that works on your machine, the same image runs on any container host.
