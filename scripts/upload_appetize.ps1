# Registers an already-hosted RemindRx APK with Appetize.io so it can be
# embedded in web/public/emulator/index.html.
#
# Appetize's REST API (v1) only accepts a *publicly reachable URL* to the
# APK, not a direct file upload from disk — see docs/android-web-emulator-testing.md.
# So this script does NOT build or host the APK; it just registers a URL you
# already have (e.g. a GitHub Release asset link) and prints the publicKey.
#
# Usage:
#   $env:APPETIZE_API_TOKEN = "tok_..."
#   ./scripts/upload_appetize.ps1 -ApkUrl "https://github.com/.../app-debug.apk"
#
# To upload a *local* file instead, use the Appetize dashboard's drag-and-drop
# uploader — that path does not go through this script.

param(
    [Parameter(Mandatory = $true)]
    [string]$ApkUrl
)

if (-not $env:APPETIZE_API_TOKEN) {
    Write-Error "Set APPETIZE_API_TOKEN first: `$env:APPETIZE_API_TOKEN = 'tok_...'"
    exit 1
}

$body = @{ platform = "android"; url = $ApkUrl } | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Method Post -Uri "https://api.appetize.io/v1/apps" `
        -Headers @{ "X-API-KEY" = $env:APPETIZE_API_TOKEN; "Content-Type" = "application/json" } `
        -Body $body
} catch {
    Write-Error "Appetize API call failed: $($_.Exception.Message)"
    if ($_.ErrorDetails) { Write-Error $_.ErrorDetails.Message }
    exit 1
}

Write-Output "publicKey: $($response.publicKey)"
Write-Output "embed URL: https://appetize.io/embed/$($response.publicKey)?device=pixel7&osVersion=13.0&scale=75"
Write-Output ""
Write-Output "Next: put publicKey into web/public/emulator/config.js (copy from config.example.js)."
