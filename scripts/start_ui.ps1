$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "Developer-only browser UI debugging. Normal RaceLab Garage launch is: .\scripts\start_desktop.ps1"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  Write-Error "npm was not found on PATH. Install Node.js 20+ from https://nodejs.org, then rerun this script."
}

if (-not (Test-Path "ui\node_modules")) {
  npm --prefix ui install
}

npm --prefix ui run dev
