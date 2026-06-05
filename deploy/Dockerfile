# supernote-sync — persistent container that runs the sync loop with your laptop closed.
# It reads handwriting on your Claude subscription (`claude -p`), so the image bundles the
# Claude Code CLI alongside the Python tool. Multi-arch (amd64 + arm64/Graviton/Lightsail).
# Build from the REPO ROOT:
#   docker build -f deploy/Dockerfile -t supernote-sync .
FROM python:3.13-slim

# Runtime deps: poppler (pdftoppm), rclone (Google Drive mount), git, FUSE, ripgrep +
# jq (used by Claude Code), curl/ca-certs (fetch the Claude installer), libcairo2 (runtime
# for pycairo, pulled in via supernotelib -> svglib -> rlpycairo).
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils rclone git openssh-client fuse3 ripgrep jq curl ca-certificates libcairo2 \
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

# NOTE: rclone's `drive` remote roots at "My Drive" itself, so the Supernote folder sits
# directly under the mount (/drive/Supernote) — there is NO "My Drive" path level like in
# Google Drive for Desktop. Override SUPERNOTE_ROOT in loop.env if your folder differs.
ENV SUPERNOTE_SOURCE_BASE=/work \
    SUPERNOTE_ROOT="/drive/Supernote" \
    SUPERNOTE_STATE_DIR=/state \
    LOOP_INTERVAL=300

COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
