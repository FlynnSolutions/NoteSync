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

Hashing the raw `.mark` bytes assumes the device re-uploads the file verbatim (it does
— it's syncing the same file, not re-authoring it). If we ever observe the same ink
reprocessing, switch `mark_hash` to hash the extracted ink instead (metadata-invariant).
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

LEDGER = Path(__file__).resolve().parent / "processed_marks.json"


def mark_hash(mark: Path) -> str:
    return hashlib.sha256(mark.read_bytes()).hexdigest()[:16]


def _load() -> list[dict]:
    if LEDGER.exists():
        try:
            return json.loads(LEDGER.read_text())
        except (json.JSONDecodeError, ValueError):
            return []
    return []


def is_processed(mark: Path) -> bool:
    """True if this exact annotation layer (by content hash) was already read."""
    if not mark.exists():
        return False
    h = mark_hash(mark)
    return any(e.get("mark_sha256") == h for e in _load())


def record(pdf_rel: str, mark: Path) -> None:
    """Log that we've read this annotation layer, so it won't reprocess on re-upload."""
    if not mark.exists():
        return
    h = mark_hash(mark)
    ledger = _load()
    if any(e.get("mark_sha256") == h for e in ledger):
        return
    ledger.append({"rel": pdf_rel, "mark_sha256": h,
                   "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    LEDGER.write_text(json.dumps(ledger, indent=2))
