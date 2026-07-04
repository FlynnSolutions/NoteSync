#!/usr/bin/env python3
"""
questions.py — the store of open conflict questions, for the "try, then ask" flow.

When reconcile can't safely resolve a 3-way conflict on its own, it records a QUESTION here
instead of guessing. Open questions surface on TWO device-facing surfaces, both GENERATED from
this store — the source `.md` is never touched, so no merge can ever bake a question into a
doc permanently:
  - the "Needs You" doc (all open questions in one place), and
  - an injected page-1 on the conflicted doc itself (render-time only).
Answering on either surface resolves the question and clears it from both.

Persisted as JSON in config.state_dir() (survives restarts, like the read-once ledger).
"""
from __future__ import annotations

import hashlib
import json
import time

from notesync import config

STORE = config.state_dir() / "questions.json"

# The on-device wire format, defined once here so both producers (needs_you.py, render.py) agree.
# (Answers are read deterministically by page ink, not by parsing this back — see
# run._process_needs_you / reconcile — so there's no parser to keep in sync.)
CONFIRM_LINE = "- [ ] looks right as merged"    # the confirm checkbox shown next to a question


def id_token(qid: str) -> str:
    """The `[id]` token shown next to a question on the device."""
    return f"`[{qid}]`"


def _qid(doc_rel: str, context: str) -> str:
    """Stable id from the doc + the conflict context — so the same unresolved conflict
    doesn't pile up duplicate questions across reconcile runs."""
    return hashlib.sha256(f"{doc_rel}\0{context}".encode()).hexdigest()[:12]


def _load() -> list[dict]:
    if STORE.exists():
        try:
            return json.loads(STORE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError):
            return []
    return []


def _save(items: list[dict]) -> None:
    STORE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def record(doc_rel: str, question: str, *, context: str) -> str:
    """Log an open question for an uncertain merge; idempotent on (doc, conflict context).
    `question` is the human-facing ask/recommendation; `context` is the diff3 conflict text
    (shown on the surfaces, and enough to re-resolve if the user clarifies). Returns the id."""
    qid = _qid(doc_rel, context)
    items = _load()
    if any(q["id"] == qid and q["status"] == "open" for q in items):
        return qid
    items.append({
        "id": qid, "doc_rel": doc_rel, "status": "open",
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "question": question, "context": context,
    })
    _save(items)
    return qid


def open_questions() -> list[dict]:
    """Every currently-open question (for the "Needs You" doc)."""
    return [q for q in _load() if q["status"] == "open"]


def for_doc(doc_rel: str) -> list[dict]:
    """Open questions for one source doc (for that doc's injected page-1)."""
    return [q for q in open_questions() if q["doc_rel"] == doc_rel]


def resolve(qid: str) -> bool:
    """Mark a question resolved — clears it from both surfaces on the next render. True if found."""
    items = _load()
    hit = False
    for q in items:
        if q["id"] == qid and q["status"] == "open":
            q["status"] = "resolved"
            q["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            hit = True
    if hit:
        _save(items)
    return hit
