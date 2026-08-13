#!/usr/bin/env python3
"""Import explicit Codex Desktop prompts into .ai-log/session.jsonl.

Codex Desktop persists conversations locally as JSONL files under
``~/.codex/sessions``.  The old repository hook expected Claude-style events
from ``.codex/hooks.json``, which Codex Desktop never sends.  This scanner is
run before a push instead, so it can reliably collect the actual prompts from
the local Codex transcript.

Only sessions whose recorded working directory belongs to the current Git
repository are imported.  Each prompt receives a stable entry id, making the
scanner safe to run repeatedly.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator


VN_TZ = timezone(timedelta(hours=7))
DEFAULT_HOURS = 24 * 7
AUTOMATED_PROMPT_PREFIXES = (
    "<recommended_plugins>",
    "<environment_context>",
    "<app-context>",
    "<skills_instructions>",
    "<permissions instructions>",
    "<collaboration_mode>",
    "<apps_instructions>",
    "<plugins_instructions>",
)


def git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def normalize_path(value: str) -> str:
    return value.strip().lower().replace("/", "\\").rstrip("\\")


def belongs_to_repo(session_cwd: str, repo_root: str) -> bool:
    session = normalize_path(session_cwd)
    repo = normalize_path(repo_root)
    return bool(session and repo and (
        session == repo
        or session.startswith(repo + "\\")
        or repo.startswith(session + "\\")
    ))


def parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def display_timestamp(value: str) -> str:
    parsed = parse_timestamp(value)
    return parsed.astimezone(VN_TZ).isoformat() if parsed else datetime.now(VN_TZ).isoformat()


def user_text(payload: dict) -> str:
    """Return only text blocks typed by the user in a Codex response item."""
    if payload.get("type") != "message" or payload.get("role") != "user":
        return ""
    content = payload.get("content", [])
    if isinstance(content, str):
        return content.strip()
    parts: list[str] = []
    if not isinstance(content, list):
        return ""
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") in {"input_text", "text"}:
            text = block.get("text", "")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    prompt = "\n".join(parts).strip()
    # Desktop stores its injected runtime context as role=user messages too.
    # These envelopes are not prompts written by the person using Codex.
    if prompt.lower().startswith(AUTOMATED_PROMPT_PREFIXES):
        return ""
    return prompt


def read_session(path: Path, repo_root: str, cutoff: datetime | None) -> Iterator[dict]:
    session_id = ""
    session_cwd = ""
    try:
        with path.open(encoding="utf-8") as transcript:
            for line in transcript:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("type") == "session_meta":
                    meta = item.get("payload", {})
                    if isinstance(meta, dict):
                        session_id = str(meta.get("session_id") or meta.get("id") or "")
                        session_cwd = str(meta.get("cwd") or "")
                    break
    except OSError:
        return

    if not belongs_to_repo(session_cwd, repo_root):
        return

    try:
        with path.open(encoding="utf-8") as transcript:
            for line in transcript:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                timestamp = str(item.get("timestamp") or "")
                when = parse_timestamp(timestamp)
                if cutoff and when and when < cutoff:
                    continue
                payload = item.get("payload", {})
                if not isinstance(payload, dict):
                    continue
                prompt = user_text(payload)
                if not prompt:
                    continue
                message_id = str(payload.get("id") or "")
                if not message_id:
                    message_id = hashlib.sha256(
                        f"{session_id}|{timestamp}|{prompt}".encode("utf-8")
                    ).hexdigest()[:24]
                metadata = payload.get("internal_chat_message_metadata_passthrough", {})
                turn_id = metadata.get("turn_id", "") if isinstance(metadata, dict) else ""
                yield {
                    "session_id": session_id or path.stem,
                    "message_id": message_id,
                    "turn_id": str(turn_id),
                    "timestamp": timestamp,
                    "prompt": prompt,
                }
    except OSError:
        return


def logged_ids(log_file: Path) -> set[str]:
    ids: set[str] = set()
    if not log_file.exists():
        return ids
    try:
        with log_file.open(encoding="utf-8-sig") as log:
            for line in log:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                entry_id = entry.get("entry_id")
                if isinstance(entry_id, str):
                    ids.add(entry_id)
    except OSError:
        pass
    return ids


def session_directories() -> list[Path]:
    """Find the Codex Desktop transcript folder in Windows, Git Bash, or WSL."""
    candidates: list[Path] = []
    override = os.environ.get("CODEX_SESSION_DIR")
    if override:
        candidates.append(Path(override))
    candidates.append(Path.home() / ".codex" / "sessions")

    # Git Bash normally exposes USERPROFILE; this keeps the launcher pointed
    # at the Windows profile even if HOME was changed by the shell.
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        candidates.append(Path(user_profile) / ".codex" / "sessions")

    # Manual `bash` invocations on Windows can resolve to WSL, whose HOME is
    # unrelated to Codex Desktop. Look through mounted Windows profiles too.
    if os.name != "nt":
        candidates.extend(Path("/mnt/c/Users").glob("*/.codex/sessions"))

    found: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved.exists() and resolved not in found:
            found.append(resolved)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Codex Desktop prompts into .ai-log/session.jsonl."
    )
    parser.add_argument("--auto", action="store_true", help="Scan recent sessions (default mode).")
    parser.add_argument("--hours", type=int, default=DEFAULT_HOURS,
                        help=f"Recent window in hours (default: {DEFAULT_HOURS}).")
    parser.add_argument("--all", action="store_true", help="Scan all sessions for this repository.")
    parser.add_argument("--dry-run", action="store_true", help="Preview entries without writing.")
    args = parser.parse_args()

    session_dirs = session_directories()
    if not session_dirs:
        print("[codex-log] No Codex session directory found.", file=sys.stderr)
        return

    repo_root = git("rev-parse", "--show-toplevel") or str(Path.cwd())
    remote = git("remote", "get-url", "origin")
    repo = remote.rstrip("/").split("/")[-1].removesuffix(".git") or Path(repo_root).name
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    commit = git("rev-parse", "--short", "HEAD")
    student = git("config", "user.email") or os.environ.get("USERNAME", "unknown")
    cutoff = None if args.all else datetime.now(timezone.utc) - timedelta(hours=args.hours)

    log_dir = Path(os.environ.get("AI_LOG_DIR", ".ai-log"))
    log_file = log_dir / "session.jsonl"
    known_ids = logged_ids(log_file)
    entries: list[dict] = []
    for session_dir in session_dirs:
        for transcript in session_dir.rglob("*.jsonl"):
            for prompt in read_session(transcript, repo_root, cutoff):
                entry_id = f"codex-{prompt['session_id']}-{prompt['message_id']}"
                if entry_id in known_ids:
                    continue
                entries.append({
                    "ts": display_timestamp(prompt["timestamp"]),
                    "tool": "codex",
                # Match Claude's user-prompt event name. `entry_id` remains
                # Codex-only because transcript scanning can be repeated.
                "event": "UserPromptSubmit",
                    "entry_id": entry_id,
                    "session_id": prompt["session_id"],
                    "turn_id": prompt["turn_id"],
                    "model": "codex",
                    "repo": repo,
                    "branch": branch,
                    "commit": commit,
                    "student": student,
                    "prompt": prompt["prompt"],
                    "response_summary": "",
                })
                known_ids.add(entry_id)

    entries.sort(key=lambda entry: entry["ts"])
    if args.dry_run:
        for entry in entries:
            print(f"[{entry['ts'][:19]}] {entry['prompt'].replace(chr(10), ' ')[:120]}")
        print(f"[codex-log] Would log {len(entries)} prompt(s).", file=sys.stderr)
        return

    if not entries:
        print("[codex-log] No new Codex prompts.", file=sys.stderr)
        return
    log_dir.mkdir(exist_ok=True)
    with log_file.open("a", encoding="utf-8") as log:
        for entry in entries:
            log.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[codex-log] Logged {len(entries)} Codex prompt(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
