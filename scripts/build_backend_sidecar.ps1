param(
  [string]$OutputDir = "ui\src-tauri\bin"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$OutputPath = Join-Path $Root $OutputDir
$WorkPath = Join-Path $Root "build\pyinstaller"
$SpecPath = Join-Path $Root "build\racerzlab-backend.spec"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$Python = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { "python" }

New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null
New-Item -ItemType Directory -Force -Path $WorkPath | Out-Null

Push-Location $Root
try {
  & $Python -m PyInstaller --version | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed for $Python. Install it with: $Python -m pip install pyinstaller"
  }

  & $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --noconsole `
    --name racerzlab-backend `
    --distpath $OutputPath `
    --workpath $WorkPath `
    --specpath (Split-Path -Parent $SpecPath) `
    --collect-data racelab_engine `
    --collect-data api `
    --hidden-import uvicorn.logging `
    --hidden-import uvicorn.loops.auto `
    --hidden-import uvicorn.protocols.http.auto `
    --hidden-import uvicorn.protocols.websockets.auto `
    --hidden-import uvicorn.lifespan.on `
    api\server.py
  if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller backend sidecar build failed."
  }

  $ExePath = Join-Path $OutputPath "racerzlab-backend.exe"
  if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "Backend sidecar build did not produce $ExePath"
  }

  Write-Host "Backend sidecar ready: $ExePath"
} finally {
  Pop-Location
}
