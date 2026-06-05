# supernote-sync — persistent container that runs the sync loop with your laptop closed.
# It reads handwriting on your Claude subscription (`claude -p`), so the image bundles the
# Claude Code CLI alongside the Python tool. Multi-arch (amd64 + arm64/Graviton/Lightsail).
# Build from the REPO ROOT:
#   docker build -f deploy/Dockerfile -t supernote-sync .
FROM python:3.13-slim

# Runtime deps: poppler (pdftoppm), rclone (Drive API — copy, NOT a FUSE mount, so no
# SYS_ADMIN needed), git (HTTPS + PAT via credential helper), ripgrep + jq (Claude Code),
# curl/ca-certs (Claude installer), libcairo2 (pycairo via supernotelib -> svglib -> rlpycairo).
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils rclone git ripgrep jq curl ca-certificates libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI — the claude_code backend shells out to `claude -p`. The official
# installer drops a self-contained native binary in ~/.local/bin (no Node runtime needed).
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app
COPY requirements.txt ./
# pycairo has no prebuilt wheels and compiles from source, so install a toolchain + cairo
# headers just for the build, then purge them to keep the image small (libcairo2 stays).
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc pkg-config libcairo2-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y gcc pkg-config libcairo2-dev && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# The app + its bundled font (supernote-tool/pdftoppm resolve on PATH; see marklayer._need).
COPY *.py sync.sh ./
COPY assets/ assets/

# SUPERNOTE_ROOT is a LOCAL working copy of the Supernote Drive folder; the entrypoint sets
# it from DRIVE_PATH and keeps it in sync with `rclone copy`. The other paths are fixed here.
ENV SUPERNOTE_SOURCE_BASE=/work \
    SUPERNOTE_STATE_DIR=/state \
    LOOP_INTERVAL=300

COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
