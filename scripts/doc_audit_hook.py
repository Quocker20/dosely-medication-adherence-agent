#!/usr/bin/env python3
"""Stop hook: when a turn touches code under src/, web/, or android/, block
stopping once and ask Claude to audit docs/*.md (excluding docs/guide/,
generic cohort boilerplate) against the change, fixing anything now stale.

Loop safety: Claude Code sets stop_hook_active=true on the Stop event that
follows this hook's own block, so that case always exits 0 (never re-blocks).
On top of that, a state file records the git status snapshot of the watched
directories at the last block, so an unrelated later Stop with the same
uncommitted diff (nothing new since the last prompt) also exits 0 quietly.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = REPO_ROOT / ".claude" / ".doc-audit-state"
WATCHED_DIRS = ["src", "web", "android"]

REASON = (
    "This turn touched code under src/, web/, or android/. Before ending the "
    "turn, audit docs/*.md (excluding docs/guide/, which is generic cohort "
    "boilerplate, not project-specific) against the code you just changed, "
    "and fix anything now stale or inconsistent with it - the same way "
    "staleness was found and fixed earlier in this session (comparing docs "
    "against the real src/ code and correcting drift). If the change doesn't "
    "affect anything documented in docs/, say so briefly and stop."
)


MAX_READ_BYTES = 200_000


def code_signature() -> str:
    """Content-aware signature of everything uncommitted under WATCHED_DIRS.

    `git status --porcelain` alone only reflects which files changed status
    (clean->modified, or a new untracked path appearing) - it does NOT change
    when an already-dirty or already-new file is edited again, which would
    let repeated edits to the same file across turns slip past undetected.
    Combine tracked-file diff content with untracked-file content directly.
    """
    parts: list[str] = []

    try:
        diff = subprocess.run(
            ["git", "diff", "HEAD", "--", *WATCHED_DIRS],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
        parts.append(diff)
    except Exception:
        pass

    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all", "--", *WATCHED_DIRS],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
    except Exception:
        status = ""

    for line in sorted(status.splitlines()):
        if not line.startswith("??"):
            continue
        rel_path = line[3:].strip()
        parts.append(rel_path)
        try:
            data = (REPO_ROOT / rel_path).read_bytes()[:MAX_READ_BYTES]
            parts.append(data.decode("utf-8", errors="replace"))
        except Exception:
            pass

    return "\n".join(parts)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    if payload.get("stop_hook_active"):
        # Already continuing from our own block - never re-block, but keep the
        # state file current so a genuinely new change is still caught later.
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_bytes(code_signature().encode("utf-8"))
        except Exception:
            pass
        return 0

    current = code_signature()
    previous = ""
    if STATE_FILE.exists():
        try:
            # Binary read/write, not write_text/read_text: text-mode newline
            # translation on Windows is not a lossless round-trip when the
            # signature already contains literal \r\n (from git diff output
            # or a CRLF-line-ended source file), which silently corrupted the
            # state file and caused spurious re-blocks - see git history.
            previous = STATE_FILE.read_bytes().decode("utf-8")
        except Exception:
            previous = ""

    if not current or current == previous:
        return 0

    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_bytes(current.encode("utf-8"))
    except Exception:
        pass

    print(json.dumps({"decision": "block", "reason": REASON}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
