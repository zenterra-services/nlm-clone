#!/usr/bin/env python3
"""Shared helpers for the nlm-clone toolkit.

No credentials are handled here. Authentication lives entirely inside the
`nlm` CLI (see README), which stores browser session cookies in
~/.notebooklm-mcp-cli/ — outside this project. This toolkit only ever passes a
*profile name* to `nlm`; it never reads, writes, logs, or transmits tokens.
"""
import json
import subprocess
import sys

# Titles NotebookLM ends up with when a re-fetch is served a bot wall or an
# error page instead of the real article. Lowercase substring match.
BLOCK_MARKERS = (
    "temporarily unavailable", "just a moment", "checking your browser",
    "access denied", "403 forbidden", "attention required", "are you a robot",
    "captcha", "request could not be satisfied", "error 404", "page not found",
    "site not found", "verify you are human", "cloudflare", "too many requests",
    "service unavailable", "bot detection", "unusual traffic",
)


def looks_blocked(title):
    """True if a source title looks like a bot-block or error page."""
    t = (title or "").lower()
    return any(m in t for m in BLOCK_MARKERS)


def nlm(args, profile=None, check=False, timeout=900):
    """Run the nlm CLI. `profile` is a profile *name*, never a credential."""
    cmd = ["nlm"] + list(args)
    if profile:
        cmd += ["--profile", profile]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(f"nlm {' '.join(args[:3])} failed "
                           f"(exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
    return proc


def nlm_json(args, profile=None, timeout=900):
    """Run an nlm command with --json. Returns None if the output won't parse.

    Callers MUST treat None as an error (usually an expired session) and fail
    loudly — degrading it to an empty list makes a dead session look like
    'nothing found', which silently reports broken data as clean.
    """
    proc = nlm(list(args) + ["--json"], profile=profile, timeout=timeout)
    try:
        return json.loads(proc.stdout)
    except Exception:
        return None


def notebooks(profile):
    """List notebooks, exiting with a clear message if the session is dead."""
    nbs = nlm_json(["notebook", "list"], profile=profile)
    if not nbs:
        sys.exit(f"ERROR: cannot list notebooks for profile '{profile}'. The "
                 f"session has probably expired — run:\n"
                 f"    nlm login -p {profile} --force")
    return nbs


def sources(notebook_id, profile, strict=True):
    """List a notebook's sources. With strict=True, exit on a read failure."""
    ss = nlm_json(["source", "list", notebook_id], profile=profile)
    if ss is None and strict:
        sys.exit(f"ERROR: cannot read sources of {notebook_id} "
                 f"(profile '{profile}') — session probably expired.")
    return ss
