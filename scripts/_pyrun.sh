#!/usr/bin/env bash
# Cross-platform Python launcher for AI log hooks.
# Tries python3 → python → py -3 on PATH; on Windows, falls back to common
# Python install locations because Git Bash launched by some hooks gets a
# stripped PATH that omits the Windows Python directory.
# Designed to be sourced or called as: bash scripts/_pyrun.sh <script> [args...]
#
# Exits 0 silently if no Python is found — hooks must never block the AI tool.
set -u

# On Windows, `python`/`python3` on PATH can resolve to the Microsoft Store
# app-execution-alias stub (WindowsApps\python3.exe) even when no real
# Python is installed via the Store. That stub "exists" for `command -v`
# but fails at runtime, so we verify each candidate actually runs.
works() { "$@" --version >/dev/null 2>&1; }

PY=""
for cand in python3 python "py -3"; do
  if command -v "${cand%% *}" >/dev/null 2>&1 && works $cand; then
    PY="$cand"
    break
  fi
done

if [ -z "$PY" ]; then
  # PATH lookup failed — probe standard Windows install locations.
  shopt -s nullglob 2>/dev/null || true
  for cand in \
    /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/c/Program Files/Python"*/python.exe \
    "/c/Program Files (x86)/Python"*/python.exe \
    /c/Python*/python.exe; do
    if [ -x "$cand" ] && works "$cand"; then PY="$cand"; break; fi
  done
  shopt -u nullglob 2>/dev/null || true
  [ -n "$PY" ] || exit 0
fi

# shellcheck disable=SC2086
exec $PY "$@"
