$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

function Assert-Command($Name, $InstallHint) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    Write-Error "$Name was not found on PATH. $InstallHint"
  }
}

Assert-Command "npm" "Install Node.js 20+ and open a new PowerShell window."
Assert-Command "cargo" "Install Rust from https://rustup.rs and open a new PowerShell window."

Write-Host "Building RaceLab Garage desktop app"
Push-Location (Join-Path $ProjectRoot "ui")
try {
  if (-not (Test-Path "node_modules")) {
    npm install
  }
  npm run build
  npm run tauri:build
} finally {
  Pop-Location
}

Write-Host "Build complete."
Write-Host "Expected executable/bundles under:"
Write-Host "  ui\src-tauri\target\release\"
Write-Host "  ui\src-tauri\target\release\bundle\"
