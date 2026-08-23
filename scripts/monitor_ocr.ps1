param(
    [string]$OutputDir = 'data\ocr_chunks_60',
    [int]$Expected = 60
)

$repo = Split-Path -Parent $PSScriptRoot
$outputDir = Join-Path $repo $OutputDir

while ($true) {
    $pdfs = @(Get-ChildItem -LiteralPath $outputDir -Filter 'part-*.pdf' -ErrorAction SilentlyContinue)
    $txts = @(Get-ChildItem -LiteralPath $outputDir -Filter 'part-*.txt' -ErrorAction SilentlyContinue)
    $latest = $pdfs | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $workers = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ProcessName -match 'tesseract|gswin64c|python'
    })

    Clear-Host
    Write-Host 'OCR LIVE STATUS' -ForegroundColor Cyan
    Write-Host ('Updated:   {0:yyyy-MM-dd HH:mm:ss}' -f (Get-Date))
    Write-Host ("Completed: {0}/{2} PDF | {1}/{2} TXT" -f $pdfs.Count, $txts.Count, $Expected) -ForegroundColor Green
    if ($latest) {
        Write-Host ("Latest:    {0}" -f $latest.Name)
        Write-Host ("Finished:  {0:yyyy-MM-dd HH:mm:ss}" -f $latest.LastWriteTime)
    }
    Write-Host ("Workers:   {0}" -f $workers.Count)
    foreach ($worker in $workers) {
        Write-Host ("  {0,-12} PID={1,-6} CPU={2:N1}s RAM={3:N0} MB" -f `
            $worker.ProcessName, $worker.Id, $worker.CPU, ($worker.WorkingSet64 / 1MB))
    }
    Write-Host ''
    Write-Host 'Auto refresh every 5 seconds. Ctrl+C to close monitor.' -ForegroundColor DarkGray
    Start-Sleep -Seconds 5
}
