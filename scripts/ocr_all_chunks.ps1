param(
    [int]$Jobs = 2,
    [string]$SourceDir = 'data\pdf_chunks_60',
    [string]$OutputDir = 'data\ocr_chunks_60'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$sourceDir = Join-Path $repo $SourceDir
$outputDir = Join-Path $repo $OutputDir
$logFile = Join-Path $outputDir 'batch.log'
$statusFile = Join-Path $outputDir 'status.txt'
$python = Join-Path $repo '.venv\Scripts\python.exe'
$ocrScript = Join-Path $repo 'scripts\ocr_pdf.py'

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$files = Get-ChildItem -LiteralPath $sourceDir -Filter 'part-*.pdf' | Sort-Object Name

foreach ($index in 0..($files.Count - 1)) {
    $file = $files[$index]
    $number = $index + 1
    $outPdf = Join-Path $outputDir $file.Name
    $outTxt = [System.IO.Path]::ChangeExtension($outPdf, '.txt')

    if ((Test-Path -LiteralPath $outPdf) -and (Test-Path -LiteralPath $outTxt)) {
        "[$number/$($files.Count)] SKIP $($file.Name)" | Tee-Object -FilePath $logFile -Append
        continue
    }

    "running=$number/$($files.Count) file=$($file.Name)" | Set-Content $statusFile
    "[$number/$($files.Count)] OCR $($file.Name)" | Tee-Object -FilePath $logFile -Append
    # Windows PowerShell 5 wraps native stderr (including OCRmyPDF progress)
    # as NativeCommandError when ErrorActionPreference is Stop. OCRmyPDF uses
    # stderr for normal progress, so judge success by its process exit code.
    $ErrorActionPreference = 'Continue'
    & $python -u $ocrScript $file.FullName $outPdf --jobs $Jobs --overwrite *>> $logFile
    $ocrExitCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($ocrExitCode -ne 0) {
        "failed=$number/$($files.Count) file=$($file.Name) exit=$ocrExitCode" | Set-Content $statusFile
        exit $ocrExitCode
    }
}

"complete=$($files.Count)/$($files.Count)" | Set-Content $statusFile
"ALL_COMPLETE" | Tee-Object -FilePath $logFile -Append
