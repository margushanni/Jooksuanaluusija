$ErrorActionPreference = "Stop"

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$Requirements = Join-Path $PSScriptRoot "requirements.txt"
$VendorDir = Join-Path $PSScriptRoot ".vendor"
$MtpSource = Join-Path $VendorDir "mtp-main"
$MtpArchive = Join-Path $VendorDir "mtp-main.zip"

if (-not (Test-Path $Python)) {
    py -3 -m venv (Join-Path $PSScriptRoot ".venv")
}

& $Python -m pip install -r $Requirements

if (-not (Test-Path (Join-Path $MtpSource "mtp\win_access.py"))) {
    New-Item -ItemType Directory -Force -Path $VendorDir | Out-Null
    Invoke-WebRequest -Uri "https://github.com/Heribert17/mtp/archive/refs/heads/main.zip" -OutFile $MtpArchive
    Expand-Archive -LiteralPath $MtpArchive -DestinationPath $VendorDir -Force
    Remove-Item -LiteralPath $MtpArchive
}

& $Python (Join-Path $PSScriptRoot "garmin_run_analyzer.py")
