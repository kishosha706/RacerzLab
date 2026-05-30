$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

function Assert-Command($Name, $InstallHint) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    Write-Error "$Name was not found on PATH. $InstallHint"
  }
}

function Test-BackendHealth {
  try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8010/api/health" -UseBasicParsing -TimeoutSec 2
    return ($response.StatusCode -eq 200)
  } catch {
    return $false
  }
}

Assert-Command "npm" "Install Node.js 20+ and open a new PowerShell window."
Assert-Command "cargo" "Install Rust from https://rustup.rs and open a new PowerShell window."

$BackendProcess = $null

try {
  if (Test-BackendHealth) {
    Write-Host "RaceLab Engine already running on http://127.0.0.1:8010"
  } else {
    Write-Host "Starting RaceLab Engine on http://127.0.0.1:8010"
    $PythonExe = "python"
    if (Test-Path ".venv\Scripts\python.exe") {
      $PythonExe = (Resolve-Path ".venv\Scripts\python.exe").Path
    }
    $BackendProcess = Start-Process `
      -FilePath $PythonExe `
      -ArgumentList @("-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8010") `
      -WorkingDirectory $ProjectRoot `
      -PassThru `
      -WindowStyle Hidden

    $Ready = $false
    for ($i = 0; $i -lt 30; $i++) {
      Start-Sleep -Milliseconds 500
      if (Test-BackendHealth) {
        $Ready = $true
        break
      }
      if ($BackendProcess.HasExited) {
        throw "RaceLab Engine exited before becoming ready."
      }
    }
    if (-not $Ready) {
      throw "RaceLab Engine did not become ready on http://127.0.0.1:8010"
    }
  }

  Write-Host "Starting RaceLab Garage desktop app"
  Push-Location (Join-Path $ProjectRoot "ui")
  try {
    if (-not (Test-Path "node_modules")) {
      npm install
    }
    npm run tauri:dev
  } finally {
    Pop-Location
  }
} finally {
  if ($BackendProcess -and -not $BackendProcess.HasExited) {
    Write-Host "Stopping RaceLab Engine"
    Stop-Process -Id $BackendProcess.Id -Force
  }
}
