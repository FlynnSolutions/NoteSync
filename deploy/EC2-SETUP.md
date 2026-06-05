# Run it with the laptop closed — a small always-on box

This stands the sync loop up on a cheap always-on host so your annotations get read and
merged **without your laptop on**. You annotate a doc on the Supernote and export it; within
a few minutes the host reads the ink on your **Claude subscription** (no metered tokens),
3-way-merges it into the source, and the updated doc syncs back to the device.

> **Status: built, not yet deployed end-to-end by us.** The image builds and the loop logic
> is verified locally; what's unproven is the live path on a real host, which needs *your*
> Google Drive OAuth and Claude token (steps you must do interactively). Treat this as a
> tested kit + runbook, not a one-click deploy.

**What you need (at a glance):** a small always-on box (Lightsail/EC2, ~$5–10/mo) + **three
credentials** — a Claude subscription token (`claude setup-token`), a Google Drive `rclone.conf`
(`rclone config`), and a GitHub PAT for your notes repo(s). Fill three lines in `loop.env`, mount
`rclone.conf`, `docker compose up`. The detail below is just walking those through.

## How it works (the shape)

```
Supernote ──(Supernote Cloud)──▶ Google Drive ◀──(rclone copy, Drive API)── always-on host
   ▲                                                                         │
   └──────────────── rendered PDFs sync back ◀──── `sync.sh run` every 5 min ┘
                                                   (digests → mirror → drain pending,
                                                    reading ink on your Claude sub)
```

The host runs one container that, every `LOOP_INTERVAL` seconds: pulls your notes repo,
runs `sync.sh run`, and pushes any applied edits back. The export you do on the device is
the real trigger — the loop just notices the new export within a poll interval. (A 60–300s
poll is indistinguishable from "event-driven" for this; there's no value in wiring up Google
push notifications.)

### Hybrid: laptop-first, cloud as standby

If you run the local watcher (`sync.sh watch`) on your laptop, this box should only step in
when the laptop's *off*. It does, automatically: the watcher stamps a hidden `.laptop-alive`
file in your Drive folder every ~60s, and each tick this container checks it — **standing down
while the laptop is active**, working only once the heartbeat goes stale (laptop off, >5 min by
default). No double-processing, no races; fail-safe if the laptop crashes. Tune with
`HEARTBEAT_STALE_SECS` (set `0` for a cloud-only setup with no laptop in the loop).

### Two ways to trigger it (`RUN_MODE`)

- **`loop`** (default): the container self-schedules — a pass every `LOOP_INTERVAL`.
  Simplest; good if this box does nothing else.
- **`oneshot`**: run **one** pass, then exit. Use this when an **external** trigger drives it
  — the "scheduled → cron, on-demand → heartbeat" split. A host crontab handles the clockwork
  (note: **no `--cap-add`/`--device` needed** — there's no FUSE mount):
  ```cron
  */10 * * * * docker run --rm --cap-drop ALL --security-opt no-new-privileges \
      -v /home/ubuntu/supernote-sync/deploy/rclone.conf:/root/.config/rclone/rclone.conf:ro \
      -v sync-work:/work -v sync-state:/state -v sync-drive:/drive \
      --env-file /home/ubuntu/supernote-sync/deploy/loop.env -e RUN_MODE=oneshot supernote-sync
  ```
  and your phone **heartbeat** fires the *same* one-shot on demand. Either way the pass is
  **serial** — `run.py` drains pending docs one at a time, so it never bursts the
  subscription's short-window/concurrency rate limits (the thing that breaks bursty automation).

## What it costs

- **Host:** a Lightsail **1 GB** instance (~$5/mo) or **2 GB** (~$10/mo); equivalently EC2
  `t4g.micro` (~$6/mo) / `t4g.small` (~$12/mo); prices drift, confirm against current AWS
  pricing. **Avoid 512 MB** — expect PDF rendering plus the Claude binary to thrash it (not
  yet measured). arm64 (Graviton/Lightsail) is cheaper and fully supported.
- **AI:** runs on your Claude subscription, no metered API key. Economics shift on a known
  date (verified against Anthropic's [Agent SDK plan article](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan)):
  - **Before 2026-06-15:** `claude -p` draws against your normal subscription limits (the
    5-hour rolling window + weekly caps). Fine for low, **serial** volume like this; the risk
    is only *bursting* many parallel calls — which `run.py` doesn't do.
  - **From 2026-06-15:** `claude -p` draws from a separate monthly **Agent SDK credit**
    (Max 20x = **$200/mo, metered at API rates, no rollover**), decoupled from your interactive
    use. A few doc-reads/day is a tiny fraction of $200, so this stays effectively free — but
    it's "included up to $200/mo," not literally unlimited. Past the credit it bills API rates
    (or stops). To switch a workload to the pay-as-you-go API instead, set `backend = "api"`.

## Prerequisites (one-time, on your laptop)

You need three secrets. Generate them on your laptop (which has a browser); you'll copy two
of them to the host.

1. **Claude subscription token** — authenticates Claude Code headlessly to your plan:
   ```bash
   claude setup-token        # opens a browser; prints a token (valid ~1 year). Copy it.
   ```
   This is **not** an API key. If an `ANTHROPIC_API_KEY` is also present on the host it would
   *override* the subscription and bill the API — the container unsets it, but don't set one.

2. **rclone Google Drive remote** — lets the host mount the Drive folder your Supernote
   syncs to:
   ```bash
   rclone config            # n)ew → name it "gdrive" → type "drive" → OAuth in the browser
   ```
   This writes `~/.config/rclone/rclone.conf`. You'll copy that file to the host.

3. **Your notes repos** — your source `.md` docs, **one private git repo per scan_root** (e.g.
   `RealtimeMFG`, `hq`). If a repo isn't on a remote yet, push it:
   ```bash
   # in each notes repo, e.g. ~/Projects/RealtimeMFG:
   git remote add origin https://github.com/you/realtimemfg.git && git push -u origin HEAD
   ```
   Then create a GitHub **fine-grained PAT** with **Contents: read + write** scoped to those
   repos. In `loop.env` set `DOCS_REPOS=RealtimeMFG=<url>,hq=<url>` and `GITHUB_TOKEN=<the PAT>`
   — that's it; the folders to mirror are taken from the `DOCS_REPOS` subpaths automatically.
   The token is used via a git credential helper — never in a repo URL/`.git/config`/log. (One
   repo only? An SSH deploy-key also works, but a PAT is simplest across several.)

## Stand up the host

### 1. Launch the instance
- **Lightsail:** create an instance → OS-only → Ubuntu LTS → **1 GB** plan → create.
- **EC2:** `t4g.micro` (arm64) or `t3.micro` (x86), Ubuntu LTS, 8 GB disk, a security group
  allowing only SSH in. No inbound ports beyond SSH are needed.

### 2. Install Docker
```bash
ssh ubuntu@<instance-ip>
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
# log out and back in (or run `newgrp docker`) so the group membership takes effect
```

### 3. Get the code + your secrets onto it

**On the host** — get the tool code (clone if the repo is public; otherwise `scp`/`rsync` it
up from your laptop) and fill in `loop.env`:
```bash
git clone https://github.com/FlynnSolutions/supernote-sync.git   # or copy it up if private
cd supernote-sync/deploy
cp loop.env.example loop.env
nano loop.env            # paste CLAUDE_CODE_OAUTH_TOKEN, set DOCS_REPO
```

**On your laptop** (a separate terminal) — copy your Drive credentials up; without this the
container can't reach Drive and step 4 fails at the first sync:
```bash
scp ~/.config/rclone/rclone.conf ubuntu@<instance-ip>:~/supernote-sync/deploy/rclone.conf
```
(`GITHUB_TOKEN` goes in `loop.env`, not a separate file.) `loop.env` and `rclone.conf` are
gitignored — keep them only on the host.

### 4. Run it
```bash
docker compose up --build -d
docker compose logs -f          # watch the first tick: sync → clone → run
```
You should see the first Drive sync, the docs repo clone, and a `== supernote-sync run
(backend: claude_code) ==` pass. `restart: unless-stopped` brings it back after reboots.

## Verify the round trip
1. On the device, annotate a mirrored doc and **Export with annotations**.
2. Wait one `LOOP_INTERVAL` (default 5 min).
3. `docker compose logs --tail=50` should show the doc under `[3/3] pending annotations`
   and an `applied` line in the summary.
4. The merged doc re-mirrors to the device; check it shows your edit. A `supernote:` commit
   lands in your notes repo (revert there if a read was wrong).

## Operating notes
- **Token renewal:** `CLAUDE_CODE_OAUTH_TOKEN` expires ~yearly. When reads start failing on
  auth, run `claude setup-token` again and update `loop.env` + `docker compose up -d`.
- **Conflicts** (you edited a doc on the laptop *and* on the device in the same place) are
  **not** auto-applied — the doc stays pending and markers are written to the container's
  `merge_out/` (transient, lost on restart — so the real signal is the doc staying pending).
  Resolve it in the source and it clears next tick. Until then it's re-attempted every tick
  (one `claude -p` call each), so don't leave conflicts sitting.
- **State that must persist** (the read-once ledger, digest state) lives on the `sync-state`
  volume; the notes repo on `sync-work`. `base/` and `manifest.json` are regenerated by
  `mirror` each pass, so they're intentionally not persisted.
- **Latency:** a doc read takes a few minutes (agentic model call). The loop is for "tap and
  walk away," not instant.

## Security
- `loop.env` holds your Claude token + the GitHub PAT; `rclone.conf` holds Google Drive OAuth.
  Anyone with the host can act as you on all of it — lock SSH down (key-only, restricted source
  IP) and keep the secrets off a shared box.
- The container runs **unprivileged** (`cap_drop: ALL` + `no-new-privileges`, no FUSE/SYS_ADMIN)
  — safe to run alongside other things on the box. Running it as a non-root *user* is a further
  hardening step (needs the rclone.conf path + volume ownership adjusted); not done yet.

## Test locally first (recommended before paying for a host)
The same image runs on your laptop — exercise the whole thing before launching anything:
```bash
cd deploy
cp ~/.config/rclone/rclone.conf ./rclone.conf
cp loop.env.example loop.env && nano loop.env
docker compose up --build
```
If it works here, the identical image runs on any container host.
