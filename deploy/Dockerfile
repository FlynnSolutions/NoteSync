# supernote-sync — persistent container that runs the sync loop with the laptop off.
# UNVERIFIED scaffolding (see deploy/HOSTING.md). Build from the REPO ROOT:
#   docker build -f deploy/Dockerfile -t supernote-sync .
FROM python:3.13-slim

# Runtime deps: poppler (pdftoppm), rclone (Google Drive), git, FUSE, certs.
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils rclone git fuse3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# The tool + its bundled font (supernote-tool/pdftoppm resolve on PATH; see marklayer._need).
COPY *.py sync.sh ./
COPY assets/ assets/

ENV SUPERNOTE_SOURCE_BASE=/work \
    SUPERNOTE_ROOT="/drive/My Drive/Supernote" \
    LOOP_INTERVAL=300

COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
