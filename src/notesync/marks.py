#!/usr/bin/env python3
"""
marks.py — a ledger of annotation layers we've already read, keyed by content hash.

Why this exists: consuming a `.mark` on the Drive side does NOT clear the annotation
on the *device*. The device treats its local ink as authoritative and re-uploads the
`.mark` on its next sync. Without a ledger that re-upload would (a) re-surface the doc
as "pending" and (b) make mirror.py re-PROTECT it — freezing the doc from re-renders
forever. With a human in the loop you notice; in the unattended Phase-B loop it's a
silent reprocess / permanent-protection failure.

So instead of deleting the `.mark` (which just triggers another device re-upload), we
record its content hash here and LEAVE it on Drive — device and Drive then agree, so
there's no churn. `pending.py` and `mirror.py` ignore any `.mark` whose hash is logged.
New strokes change the bytes -> new hash -> the doc surfaces again. This is the local
JSON form; the cloud loop will back it with DynamoDB/S3 (same key: the ink hash).

Two hashes per mark. The **raw** hash (file bytes) is the fast common-case key — the
device usually re-uploads a `.mark` verbatim. But Drive/Supernote can re-touch a file
(re-save it with identical strokes but different bytes: new internal timestamps/metadata),
which changes the raw hash and would wrongly re-surface an already-read doc. So we also
key on an **ink** hash — the rendered strokes, metadata-invariant — as a fallback: same
ink, different bytes ⇒ still "read." `is_processed` self-heals by recording the new raw
hash on an ink match, so it fast-paths next time.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import time
from pathlib import Path

from notesync import config

LEDGER = config.state_dir() / "processed_marks.json"


def raw_hash(mark: Path) -> str:
    """Fast hash of the file bytes — the common case (device re-uploads verbatim)."""
    return hashlib.sha256(mark.read_bytes()).hexdigest()[:16]


def ink_hash(mark: Path) -> str | None:
    """Metadata-invariant hash of the INK itself: render the `.mark`'s strokes (ink only)
    and hash the raw pixels, so a byte-level re-touch with identical strokes yields the same
    value. Returns None if the ink can't be rendered (caller then matches on raw hash alone).
    Only invoked when the raw hash misses, so the render cost is paid rarely."""
    try:
        from PIL import Image

        from notesync import marklayer  # lazy: keeps this widely-imported module light + avoids a hard dep here
        with tempfile.TemporaryDirectory() as td:
            pngs = marklayer._convert(mark, Path(td) / "ink", transparent=True)
            h = hashlib.sha256()
            for p in pngs:
                h.update(Image.open(p).convert("RGBA").tobytes())
        return h.hexdigest()[:16]
    except (Exception, SystemExit):   # missing supernote-tool, unreadable mark, etc. → degrade to raw-only
        return None


def _load() -> list[dict]:
    if LEDGER.exists():
        try:
            return json.loads(LEDGER.read_text())
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def _save(ledger: list[dict]) -> None:
    LEDGER.write_text(json.dumps(ledger, indent=2))


def is_processed(mark: Path) -> bool:
    """True if this annotation layer was already read — by raw-bytes hash (fast), or, if the
    bytes changed but the strokes didn't (a re-touch), by ink hash. On an ink match we record
    the new raw hash so the next check hits the fast path."""
    if not mark.exists():
        return False
    ledger = _load()
    rh = raw_hash(mark)
    if any(e.get("mark_sha256") == rh for e in ledger):
        return True
    ih = ink_hash(mark)
    if ih and (hit := next((e for e in ledger if e.get("ink_sha256") == ih), None)):
        ledger.append({"rel": hit.get("rel"), "mark_sha256": rh, "ink_sha256": ih,
                       "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "note": "re-touch (same ink)"})
        _save(ledger)
        return True
    return False


def record(pdf_rel: str, mark: Path) -> None:
    """Log that we've read this annotation layer, so it won't reprocess on re-upload/re-touch."""
    if not mark.exists():
        return
    rh = raw_hash(mark)
    ledger = _load()
    if any(e.get("mark_sha256") == rh for e in ledger):
        return
    ledger.append({"rel": pdf_rel, "mark_sha256": rh, "ink_sha256": ink_hash(mark),
                   "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    _save(ledger)
