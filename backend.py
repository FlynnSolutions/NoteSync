#!/usr/bin/env python3
"""
backend.py — where the ink-reading completion actually runs. Two interchangeable
backends, chosen by config.backend():

  claude_code  shell out to `claude -p` (Claude Code headless) — runs on your Claude
               subscription (Max plan): no metered API tokens, no ANTHROPIC_API_KEY.
  api          the Anthropic SDK (anthropic.Anthropic) — metered, needs ANTHROPIC_API_KEY,
               but supports prompt caching for cheap re-runs.

Both take the same neutral request — a `system` prompt (list of text parts) and a
`content` list of text/image blocks — and return the model's raw text. Image blocks carry
a file PATH, not bytes: the api backend base64-encodes them; the claude_code backend points
Claude at the path to Read. Output post-processing (fence stripping) stays with the caller.
"""
from __future__ import annotations

import base64
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import config

HERE = Path(__file__).resolve().parent
TIMEOUT_S = 1200  # a slow agentic read runs minutes; cap it so a hang can't wedge the loop


def _redact(s: str) -> str:
    """Mask a token embedded in a URL (scheme://user:TOKEN@host) before printing diagnostics."""
    return re.sub(r"(://[^/\s:@]+:)[^@\s/]+(@)", r"\1***\2", s)


def read(system: list[dict], content: list[dict], *, max_tokens: int = 32000) -> str:
    """Run the completion through the configured backend; return the model's raw text."""
    if config.backend() == "api":
        return _api(system, content, max_tokens)
    return _claude_code(system, content)


# --- claude_code: the Max-plan path --------------------------------------
def _claude_code(system: list[dict], content: list[dict]) -> str:
    """Flatten the request into one prompt and run it through `claude -p`. Images are
    referenced by absolute path for Claude to Read.

    Claude Code is an agent, not a raw completion: asked to "return the markdown" it tends
    to add commentary or ask questions. So instead we have it WRITE the edited document to a
    scratch file and we read that file back — its chat reply is then irrelevant. (The temp
    file lives under the repo so Claude's Write tool stays inside its workspace.)"""
    out_dir = HERE / ".backend_out"
    out_dir.mkdir(exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".md", dir=out_dir)
    os.close(fd)
    outfile = Path(tmp)

    parts = [b["text"] for b in system if b.get("type") == "text"]
    parts.append("--- ANNOTATED PAGES ---")
    for b in content:
        if b.get("type") == "image":
            parts.append(f"[Read the image at {Path(b['path']).resolve()}]")
        else:
            parts.append(b.get("text", ""))
    parts.append(
        "IMPORTANT — you are running headless as a document transform, not in a chat. Do "
        "the edit, then use the Write tool to write the COMPLETE edited markdown document to "
        f"this exact path:\n{outfile}\nAlways write the full document, even if the "
        "annotations change nothing. Do not paste the document into your reply; after "
        "writing, reply only with: DONE.")
    prompt = "\n\n".join(parts)

    try:
        # Drop the whole ANTHROPIC_* family (API key, AUTH_TOKEN, BASE_URL) so `claude`
        # authenticates with your Claude subscription (Max plan), not the metered API or a
        # redirected endpoint — Claude Code prefers any of those over the subscription token
        # when present. CLAUDE_CODE_OAUTH_TOKEN (the subscription) is kept.
        env = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_")}
        try:
            proc = subprocess.run(
                ["claude", "-p", prompt, "--allowedTools", "Read", "Write",
                 "--output-format", "text"],
                cwd=HERE, capture_output=True, text=True,
                stdin=subprocess.DEVNULL,  # else `claude -p` blocks waiting on stdin
                env=env, timeout=TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            sys.exit(f"backend(claude_code): `claude -p` timed out after {TIMEOUT_S}s")
        if proc.returncode != 0:
            sys.exit(f"backend(claude_code): `claude -p` failed (exit {proc.returncode}):\n"
                     f"{_redact(proc.stderr.strip() or proc.stdout.strip())}")
        result = outfile.read_text(encoding="utf-8") if outfile.exists() else ""
        if not result.strip():
            sys.exit("backend(claude_code): Claude did not write the edited document "
                     f"(reply was: {_redact(proc.stdout.strip()[:200])!r})")
        return result
    finally:
        outfile.unlink(missing_ok=True)


# --- api: the metered Anthropic SDK path ---------------------------------
def _api(system: list[dict], content: list[dict], max_tokens: int) -> str:
    import anthropic  # local: only the api path needs the SDK installed

    client = anthropic.Anthropic()
    api_content = [_img_block(b["path"]) if b.get("type") == "image" else b for b in content]
    with client.messages.stream(
        model=config.model(),
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=system,
        messages=[{"role": "user", "content": api_content}],
    ) as stream:
        msg = stream.get_final_message()
    u = msg.usage
    print(f"  tokens: in={u.input_tokens} cache_read={getattr(u, 'cache_read_input_tokens', 0)} "
          f"out={u.output_tokens}", file=sys.stderr)
    return "".join(b.text for b in msg.content if b.type == "text")


def _img_block(path: Path) -> dict:
    data = base64.standard_b64encode(Path(path).read_bytes()).decode("utf-8")
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": data}}
