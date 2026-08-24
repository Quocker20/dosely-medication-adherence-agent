#!/usr/bin/env python3
"""
Antigravity IDE log scanner — extracts the exact user-typed prompts from
local Antigravity conversation transcripts.

Source of truth:
    ~/.gemini/antigravity-ide/brain/<conv_id>/.system_generated/logs/transcript.jsonl
    (with fallback to the legacy ~/.gemini/antigravity/brain/... layout)

Each transcript line is a JSON object. We emit one log entry per line where
`type == "USER_INPUT"` AND `source == "USER_EXPLICIT"`. The text inside
<USER_REQUEST>...</USER_REQUEST> is the exact prompt the student typed
(auxiliary <ADDITIONAL_METADATA> and <USER_SETTINGS_CHANGE> blocks are
stripped).

Why not other sources we considered?
  - ~/.gemini/antigravity-ide/conversations/<conv>.pb is encrypted.
  - brain/<conv>/task.md / walkthrough.md are AI-generated artifacts, not the
    user's prompt.
  - ~/.gemini/tmp/<slug>/chats/session-*.json is the Gemini CLI, not the
    Antigravity IDE.

Conversation → repo mapping
---------------------------
The brain folder has no .project_root file. We map a conv to the current repo
by scanning its transcript for tool-call `Cwd` values. A conv counts as
belonging to this repo when one of its Cwd values either equals, is an
ancestor of, or is a descendant of the current repo root.

Usage:
  python scripts/log_antigravity.py --auto            # default: last 24h
  python scripts/log_antigravity.py --hours 72
  python scripts/log_antigravity.py --all             # every conv, no cutoff
  python scripts/log_antigravity.py --conv-id <id>    # one conversation
  python scripts/log_antigravity.py --dry-run         # preview only

Env overrides:
  ANTIGRAVITY_BRAIN_DIR  point at a different brain/ directory
  AI_LOG_DIR             where session.jsonl is written (default: .ai-log)
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Load .env variables manually if python-dotenv is not installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_path = Path(".env")
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    if key not in os.environ:
                        os.environ[key] = val

# Fix Windows console encoding so VN diacritics in prompts print cleanly.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

VN_TZ = timezone(timedelta(hours=7))
GEMINI_HOME = Path.home() / ".gemini"

# Antigravity has shipped under two folder names; prefer the newer IDE one.
BRAIN_CANDIDATES = (
    GEMINI_HOME / "antigravity-ide" / "brain",
    GEMINI_HOME / "antigravity" / "brain",
)

USER_REQUEST_RE = re.compile(r"<USER_REQUEST>(.*?)</USER_REQUEST>", re.DOTALL)
AUX_BLOCK_RE = re.compile(
    r"<(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE|SYSTEM_MESSAGE)>"
    r".*?"
    r"</(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE|SYSTEM_MESSAGE)>",
    re.DOTALL,
)


def git(cmd: str) -> str:
    try:
        return subprocess.check_output(
            cmd.split(), shell=False, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Locating brain/
# ---------------------------------------------------------------------------

def get_brain_dirs() -> list[Path]:
    """Brain directories to scan, newest layout first."""
    env = os.environ.get("ANTIGRAVITY_BRAIN_DIR")
    if env:
        p = Path(env)
        return [p] if p.exists() else []
    return [p for p in BRAIN_CANDIDATES if p.exists()]


# ---------------------------------------------------------------------------
# Path normalization + repo gating
# ---------------------------------------------------------------------------

def _normalize(p: str) -> str:
    """Lower-case + backslash form, no trailing separator."""
    if not p:
        return ""
    return p.strip().lower().replace("/", "\\").rstrip("\\")


def _unquote_arg(val):
    """Antigravity stores tool args as JSON-encoded strings. Unwrap them."""
    if not isinstance(val, str):
        return val
    val = val.strip()
    if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return val[1:-1]
    return val


def _conv_cwds(transcript: Path) -> set[str]:
    """All Cwd values that appear in tool calls inside this transcript."""
    cwds: set[str] = set()
    try:
        with open(transcript, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for tc in (entry.get("tool_calls") or []):
                    args = tc.get("args") or {}
                    cwd = args.get("Cwd") or args.get("cwd")
                    cwd = _unquote_arg(cwd)
                    if isinstance(cwd, str):
                        n = _normalize(cwd)
                        if n:
                            cwds.add(n)
    except OSError:
        pass
    return cwds


def _conv_matches_repo(cwds: set[str], repo_root_n: str) -> bool:
    """True if any cwd is equal to, ancestor of, or descendant of the repo."""
    if not repo_root_n or not cwds:
        return False
    for cwd in cwds:
        if cwd == repo_root_n:
            return True
        if cwd.startswith(repo_root_n + "\\"):
            return True
        if repo_root_n.startswith(cwd + "\\"):
            return True
    return False


# ---------------------------------------------------------------------------
# Prompt extraction
# ---------------------------------------------------------------------------

def extract_user_prompt(content: str) -> str:
    """Pull the text between <USER_REQUEST>...</USER_REQUEST>. Fall back to
    stripping known auxiliary blocks if no wrapper is present."""
    if not isinstance(content, str):
        return ""
    m = USER_REQUEST_RE.search(content)
    if m:
        return m.group(1).strip()
    cleaned = AUX_BLOCK_RE.sub("", content)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Reading existing log to avoid duplicates
# ---------------------------------------------------------------------------

def get_logged_entry_ids(log_file: Path) -> set[str]:
    """IDs already in the pending file *or* already submitted+archived —
    submit_log.py empties log_file after each successful submit, so archive/
    must also be checked or already-submitted entries get re-logged forever."""
    logged: set[str] = set()
    candidates = [log_file]
    archive_dir = log_file.parent / "archive"
    if archive_dir.exists():
        candidates.extend(sorted(archive_dir.glob("*.jsonl")))
    for path in candidates:
        if not path.exists():
            continue
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                eid = entry.get("entry_id", "")
                if eid:
                    logged.add(eid)
    return logged


# ---------------------------------------------------------------------------
# Iterating user inputs
# ---------------------------------------------------------------------------

def read_varint(data: bytes, offset: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if offset >= len(data):
            return result, offset
        b = data[offset]
        offset += 1
        result |= (b & 0x7f) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, offset

def extract_workspace_uri(blob: bytes) -> str:
    m = re.search(b'file:///([^\x00-\x1F]+)', blob)
    if m:
        return m.group(1).decode('utf-8', errors='replace')
    return ""

def extract_prompt_from_step_blob(blob: bytes) -> str:
    try:
        offset = 0
        while offset < len(blob):
            tag, offset = read_varint(blob, offset)
            wire_type = tag & 0x07
            field_num = tag >> 3
            
            if field_num == 19 and wire_type == 2:
                msg_len, offset = read_varint(blob, offset)
                end_offset = offset + msg_len
                
                while offset < end_offset:
                    sub_tag, offset = read_varint(blob, offset)
                    sub_wire_type = sub_tag & 0x07
                    sub_field_num = sub_tag >> 3
                    
                    if sub_field_num == 2 and sub_wire_type == 2:
                        str_len, offset = read_varint(blob, offset)
                        prompt_bytes = blob[offset:offset+str_len]
                        return prompt_bytes.decode('utf-8', errors='replace')
                    else:
                        if sub_wire_type == 0:
                            _, offset = read_varint(blob, offset)
                        elif sub_wire_type == 1:
                            offset += 8
                        elif sub_wire_type == 2:
                            f_len, offset = read_varint(blob, offset)
                            offset += f_len
                        elif sub_wire_type == 5:
                            offset += 4
                        else:
                            break
                break
            else:
                if wire_type == 0:
                    _, offset = read_varint(blob, offset)
                elif wire_type == 1:
                    offset += 8
                elif wire_type == 2:
                    f_len, offset = read_varint(blob, offset)
                    offset += f_len
                elif wire_type == 5:
                    offset += 4
                else:
                    break
    except Exception:
        pass
    return ""

def iter_user_inputs(brain_dirs: list[Path], cutoff: datetime | None,
                     only_conv: str | None, repo_root_n: str):
    """Yield user-input dicts from every matching conversation transcript or db."""
    import sqlite3
    seen_convs = set()

    for brain in brain_dirs:
        # 1. Check Antigravity 2.0 SQLite databases
        conv_dir_sqlite = brain.parent / "conversations"
        if conv_dir_sqlite.exists() and conv_dir_sqlite.is_dir():
            for db_file in conv_dir_sqlite.glob("*.db"):
                conv_id = db_file.stem
                if only_conv and conv_id != only_conv:
                    continue
                
                try:
                    # Use read-only mode if possible, but standard connect works
                    conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
                    
                    ws_uri = ""
                    for row in conn.execute("SELECT data FROM trajectory_metadata_blob LIMIT 1;"):
                        if row[0]:
                            ws_uri = extract_workspace_uri(row[0])
                    
                    ws_n = _normalize(ws_uri.replace("file:///", "").replace("file://", ""))
                    if repo_root_n and not _conv_matches_repo({ws_n}, repo_root_n):
                        conn.close()
                        continue
                        
                    db_mtime = db_file.stat().st_mtime
                    if cutoff:
                        db_dt = datetime.fromtimestamp(db_mtime, tz=timezone.utc)
                        if db_dt < cutoff:
                            conn.close()
                            continue
                            
                    for row in conn.execute("SELECT idx, step_payload FROM steps WHERE step_type=14;"):
                        idx = row[0]
                        blob = row[1]
                        if not blob:
                            continue
                        
                        prompt = extract_prompt_from_step_blob(blob)
                        # Remove wrappers if any
                        prompt = extract_user_prompt(prompt)
                        if len(prompt) < 2:
                            continue
                        
                        ts = datetime.fromtimestamp(db_mtime, tz=timezone.utc).isoformat()
                        
                        yield {
                            "conv_id": conv_id,
                            "step_index": idx,
                            "timestamp": ts,
                            "text": prompt,
                        }
                    conn.close()
                    seen_convs.add(conv_id)
                except Exception:
                    pass

        # 2. Check Antigravity 1.x legacy JSONL
        if not brain.exists():
            continue
            
        for conv_dir in sorted(brain.iterdir()):
            if not conv_dir.is_dir():
                continue
            if only_conv and conv_dir.name != only_conv:
                continue
            if conv_dir.name in seen_convs:
                continue
                
            transcript = (
                conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
            )
            if not transcript.exists() or transcript.stat().st_size == 0:
                continue

            cwds = _conv_cwds(transcript)
            # If we have a repo root, skip convs that never touched it.
            if repo_root_n and not _conv_matches_repo(cwds, repo_root_n):
                continue

            with open(transcript, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if (entry.get("type") != "USER_INPUT"
                            or entry.get("source") != "USER_EXPLICIT"):
                        continue

                    ts = entry.get("created_at") or ""
                    if cutoff and ts:
                        try:
                            ts_dt = datetime.fromisoformat(
                                ts.replace("Z", "+00:00")
                            )
                            if ts_dt < cutoff:
                                continue
                        except ValueError:
                            pass

                    text = extract_user_prompt(entry.get("content", ""))
                    if len(text) < 2:
                        continue

                    yield {
                        "conv_id": conv_dir.name,
                        "step_index": int(entry.get("step_index", 0)),
                        "timestamp": ts,
                        "text": text,
                    }


# ---------------------------------------------------------------------------
# Emitting entries
# ---------------------------------------------------------------------------

def build_entry(msg: dict, repo: str, branch: str, commit: str,
                student: str) -> dict:
    ts = msg["timestamp"]
    if ts.endswith("Z"):
        try:
            ts = (
                datetime.fromisoformat(ts.replace("Z", "+00:00"))
                .astimezone(VN_TZ)
                .isoformat()
            )
        except ValueError:
            pass

    return {
        "ts": ts or datetime.now(VN_TZ).isoformat(),
        "tool": "antigravity",
        "event": "UserPrompt",
        "entry_id": f"antigravity-{msg['conv_id']}-{msg['step_index']:05d}",
        "session_id": msg["conv_id"],
        "model": "gemini",
        "repo": repo,
        "branch": branch,
        "commit": commit,
        "student": student,
        "prompt": msg["text"],
        "response_summary": "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract user prompts from Antigravity IDE transcripts"
                    " into .ai-log/session.jsonl."
    )
    parser.add_argument("--auto", action="store_true",
                        help="Default mode: scan recent conversations.")
    parser.add_argument("--hours", type=int, default=24,
                        help="Window in hours when scanning (default: 24).")
    parser.add_argument("--all", action="store_true",
                        help="Ignore the time window; scan everything.")
    parser.add_argument("--conv-id",
                        help="Limit to a single conversation id.")
    parser.add_argument("--no-repo-filter", action="store_true",
                        help="Don't filter conversations by current repo.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be logged, don't write.")
    # Legacy positional args from old log_manual.py callers.
    parser.add_argument("summary", nargs="?", help=argparse.SUPPRESS)
    parser.add_argument("model", nargs="?", help=argparse.SUPPRESS)
    args = parser.parse_args()

    # Legacy manual mode: `log_antigravity.py "my summary" gemini`
    if args.summary and not (args.auto or args.conv_id or args.all):
        _legacy_log(args.summary, args.model or "gemini")
        return

    brain_dirs = get_brain_dirs()
    if not brain_dirs:
        print("[antigravity-log] No Antigravity brain/ directory found "
              f"(checked {', '.join(str(p) for p in BRAIN_CANDIDATES)}).",
              file=sys.stderr)
        sys.exit(0)

    log_dir = Path(os.environ.get("AI_LOG_DIR", ".ai-log"))
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "session.jsonl"
    logged_ids = get_logged_entry_ids(log_file)

    cutoff = None
    if not args.all:
        cutoff = datetime.now(tz=VN_TZ) - timedelta(hours=args.hours)

    repo_root_n = "" if args.no_repo_filter else _normalize(str(Path.cwd()))

    repo = git("git remote get-url origin").split("/")[-1].replace(".git", "")
    branch = git("git rev-parse --abbrev-ref HEAD")
    commit = git("git rev-parse --short HEAD")
    student = git("git config user.email") or os.environ.get(
        "USERNAME", os.environ.get("USER", "unknown"))

    new_entries: list[dict] = []
    for msg in iter_user_inputs(brain_dirs, cutoff, args.conv_id, repo_root_n):
        entry = build_entry(msg, repo or Path.cwd().name, branch, commit,
                            student)
        if entry["entry_id"] in logged_ids:
            continue
        new_entries.append(entry)
        logged_ids.add(entry["entry_id"])

    if not new_entries:
        scope = "all" if args.all else f"{args.hours}h"
        repo_note = "any repo" if args.no_repo_filter else f"repo={repo_root_n or '(unknown)'}"
        print(f"[antigravity-log] No new prompts ({repo_note}, window={scope}).",
              file=sys.stderr)
        sys.exit(0)

    if args.dry_run:
        print(f"\n[antigravity-log] DRY RUN — would log "
              f"{len(new_entries)} entries:\n")
        for e in new_entries:
            preview = e["prompt"].replace("\n", " ")[:120]
            print(f"  [{e['ts'][:19]}] {preview}")
        sys.exit(0)

    with open(log_file, "a", encoding="utf-8") as f:
        for e in new_entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"[antigravity-log] Logged {len(new_entries)} prompt(s) from "
          f"Antigravity IDE.", file=sys.stderr)


# ---------------------------------------------------------------------------
# Legacy manual mode (kept for back-compat with log_manual.py callers and the
# old .agents/rules instructions). New rules tell the AI not to call this.
# ---------------------------------------------------------------------------

def _legacy_log(summary: str, model: str) -> None:
    ts = datetime.now(VN_TZ).isoformat()
    entry = {
        "ts": ts,
        "tool": "antigravity",
        "event": "TaskComplete",
        "entry_id": f"antigravity-{datetime.now(VN_TZ).strftime('%Y%m%d-%H%M%S')}",
        "model": model,
        "repo": git("git remote get-url origin").split("/")[-1].replace(".git", ""),
        "branch": git("git rev-parse --abbrev-ref HEAD"),
        "commit": git("git rev-parse --short HEAD"),
        "student": git("git config user.email") or os.environ.get(
            "USERNAME", os.environ.get("USER", "unknown")),
        "prompt": summary[:1000],
        "response_summary": f"[Antigravity] {summary[:500]}",
    }
    log_dir = Path(os.environ.get("AI_LOG_DIR", ".ai-log"))
    log_dir.mkdir(exist_ok=True)
    with open(log_dir / "session.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[antigravity-log] Logged manual: {summary[:80]}...", file=sys.stderr)


if __name__ == "__main__":
    main()
