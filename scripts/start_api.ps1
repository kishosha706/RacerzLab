$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "Backend-only debugging. Normal RaceLab Garage launch is: .\scripts\start_desktop.ps1"
Write-Host "Starting RaceLab Engine on http://127.0.0.1:8000"

if (Test-Path ".venv\Scripts\python.exe") {
  .\.venv\Scripts\python.exe -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
} else {
  python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
}
