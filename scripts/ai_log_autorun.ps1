#!/usr/bin/env pwsh
# Background sync: scans Codex/Antigravity transcripts and submits .ai-log/session.jsonl
# to the AI20K grading server, independent of `git push`. Registered as a Windows
# Scheduled Task (see scripts/setup_autorun.ps1) so logging doesn't wait for a push.

$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$LogDir = Join-Path $RepoRoot '.ai-log'
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$RunLog = Join-Path $LogDir 'autorun.log'
$PyRun = Join-Path $RepoRoot 'scripts\_pyrun.cmd'

function Invoke-Step {
    param([string]$Name, [string]$ScriptRelPath, [string[]]$ScriptArgs)
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    try {
        # Route through cmd.exe so stdout+stderr merge natively — piping a native
        # exe's 2>&1 straight through PowerShell wraps each line as an ErrorRecord.
        $cmdLine = "`"$PyRun`" `"$(Join-Path $RepoRoot $ScriptRelPath)`" $($ScriptArgs -join ' ') 2>&1"
        $out = cmd.exe /c $cmdLine
        Add-Content -Encoding utf8 $RunLog "$ts [$Name] $($out -join ' ')"
    } catch {
        Add-Content -Encoding utf8 $RunLog "$ts [$Name] ERROR: $_"
    }
}

Invoke-Step -Name 'codex'       -ScriptRelPath 'scripts\log_codex.py'       -ScriptArgs @('--auto')
Invoke-Step -Name 'antigravity' -ScriptRelPath 'scripts\log_antigravity.py' -ScriptArgs @('--auto')
Invoke-Step -Name 'submit'      -ScriptRelPath 'scripts\submit_log.py'      -ScriptArgs @()
