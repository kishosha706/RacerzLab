$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "RaceLab Garage environment check"
Write-Host ""

Write-Host "Python:"
python --version

Write-Host ""
Write-Host "RaceLab CLI:"
python -m racelab_engine.cli --help | Select-Object -First 2

Write-Host ""
Write-Host "Node:"
if (Get-Command node -ErrorAction SilentlyContinue) {
  node --version
} else {
  Write-Host "node not found"
}

Write-Host ""
Write-Host "npm:"
if (Get-Command npm -ErrorAction SilentlyContinue) {
  npm --version
} else {
  Write-Host "npm not found"
}

Write-Host ""
Write-Host "Tests:"
python -B -m pytest -p no:cacheprovider
