param([switch]$SyncDatabase)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ensureArgs = @()
if ($SyncDatabase) { $ensureArgs = @("-Sync") }
& (Join-Path $Root "database\ensure_current.ps1") @ensureArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== Starting Missubibi ==="
function Test-PortListening([int]$Port) {
  return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

if (Test-PortListening 8100) {
  Write-Host "Backend already running on http://127.0.0.1:8100; reusing it."
} else {
  Start-Process powershell -WorkingDirectory (Join-Path $Root "backend") -ArgumentList "-NoExit", "-Command", "uv run uvicorn app.main:app --reload --port 8100"
}

if (Test-PortListening 5174) {
  Write-Host "Frontend already running on http://localhost:5174; reusing it."
} else {
  Start-Process powershell -WorkingDirectory (Join-Path $Root "frontend") -ArgumentList "-NoExit", "-Command", "npm run dev"
}
Write-Host "Frontend: http://localhost:5174"
Write-Host "Backend:  http://127.0.0.1:8100"
