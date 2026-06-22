#!/usr/bin/env python3
"""
ideas.py — store of captured "bigger-picture" ideas awaiting elaboration in Needs You.

Part of the capture flow: the Capture page tags each handwritten item todo|idea. Todos go
straight to the PUNCHLIST; ideas land HERE and render as cards in the Needs You doc
(needs_you.py). When you flesh one out on the device and write a destination ("priority" /
"backlog"), it graduates into the PUNCHLIST (run._process_needs_you) and is resolved here.

JSON store in config.state_dir(), exactly like questions.py.
"""
from __future__ import annotations

import hashlib
import json
import time

import config

STORE = config.state_dir() / "ideas.json"


def id_token(iid: str) -> str:
    """The `[id]` token shown next to an idea on the device."""
    return f"`[{iid}]`"


def _load() -> list[dict]:
    if STORE.exists():
        try:
            return json.loads(STORE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError):
            return []
    return []


def _save(items: list[dict]) -> None:
    STORE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def add(text: str) -> str:
    """Park a captured idea for elaboration. Returns its id."""
    text = text.strip()
    iid = hashlib.sha256(f"{text}\0{time.time()}".encode()).hexdigest()[:12]
    items = _load()
    items.append({"id": iid, "text": text, "status": "open",
                  "created": time.strftime("%Y-%m-%dT%H:%M:%S")})
    _save(items)
    return iid


def open_ideas() -> list[dict]:
    """Every parked idea still awaiting elaboration (for the Needs You doc)."""
    return [i for i in _load() if i["status"] == "open"]


def resolve(iid: str) -> bool:
    """Mark an idea graduated (routed to the PUNCHLIST) — clears it from Needs You. True if found."""
    items = _load()
    hit = False
    for i in items:
        if i["id"] == iid and i["status"] == "open":
            i["status"] = "resolved"
            i["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            hit = True
    if hit:
        _save(items)
    return hit
