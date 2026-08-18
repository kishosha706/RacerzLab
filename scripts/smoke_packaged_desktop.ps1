param(
  [string]$Executable = "ui\src-tauri\target\release\racelab-garage.exe",
  [int]$Port = 8010
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ExecutablePath = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $Executable))
$FirstProcess = $null
$SecondProcess = $null
$OwnedBackendProcessId = $null

function Read-Health {
  try {
    return Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
  } catch {
    return $null
  }
}

function Wait-ForHealth([int]$TimeoutSeconds) {
  $Deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
  while ([DateTimeOffset]::UtcNow -lt $Deadline) {
    $Health = Read-Health
    if ($null -ne $Health) { return $Health }
    Start-Sleep -Milliseconds 250
  }
  return $null
}

function Wait-ForNoHealth([int]$TimeoutSeconds) {
  $Deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
  while ([DateTimeOffset]::UtcNow -lt $Deadline) {
    if ($null -eq (Read-Health)) { return $true }
    Start-Sleep -Milliseconds 250
  }
  return $false
}

if (-not (Test-Path -LiteralPath $ExecutablePath -PathType Leaf)) {
  throw "Packaged desktop executable is missing: $ExecutablePath"
}
if ($null -ne (Read-Health)) {
  throw "Port $Port already serves a health endpoint; packaged ownership cannot be tested safely."
}

try {
  $FirstProcess = Start-Process -FilePath $ExecutablePath -PassThru -WindowStyle Hidden
  $FirstHealth = Wait-ForHealth 45
  if ($null -eq $FirstHealth) {
    throw "The packaged desktop did not start its backend within 45 seconds."
  }
  if (
    $FirstHealth.status -ne "ok" -or
    $FirstHealth.app -ne "RacerZLab" -or
    [string]::IsNullOrWhiteSpace([string]$FirstHealth.instance_id)
  ) {
    throw "The packaged desktop health response lacks exact RacerZLab instance identity."
  }
  $Connection = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $Port -State Listen -ErrorAction Stop |
    Select-Object -First 1
  $OwnedBackendProcessId = $Connection.OwningProcess

  $SecondProcess = Start-Process -FilePath $ExecutablePath -PassThru -WindowStyle Hidden
  if (-not $SecondProcess.WaitForExit(10000)) {
    throw "A second desktop launch remained active instead of handing off to the first instance."
  }
  if ($FirstProcess.HasExited) {
    throw "The first desktop instance exited during the single-instance handoff."
  }
  $SecondHealth = Read-Health
  if ($null -eq $SecondHealth -or $SecondHealth.instance_id -ne $FirstHealth.instance_id) {
    throw "The second launch changed or lost the first instance's backend identity."
  }

  if (-not $FirstProcess.CloseMainWindow()) {
    throw "The packaged desktop window could not receive a normal close request."
  }
  if (-not $FirstProcess.WaitForExit(15000)) {
    throw "The packaged desktop did not exit after a normal close request."
  }
  if (-not (Wait-ForNoHealth 15)) {
    throw "The owned backend remained reachable after the desktop closed."
  }
  Write-Output "Packaged desktop single-instance, backend identity, and shutdown smoke passed."
} finally {
  if ($null -ne $SecondProcess -and -not $SecondProcess.HasExited) {
    Stop-Process -Id $SecondProcess.Id -Force -ErrorAction SilentlyContinue
  }
  if ($null -ne $FirstProcess -and -not $FirstProcess.HasExited) {
    Stop-Process -Id $FirstProcess.Id -Force -ErrorAction SilentlyContinue
  }
  if ($null -ne $OwnedBackendProcessId) {
    $OwnedBackend = Get-Process -Id $OwnedBackendProcessId -ErrorAction SilentlyContinue
    if ($null -ne $OwnedBackend) {
      Stop-Process -Id $OwnedBackendProcessId -Force -ErrorAction SilentlyContinue
    }
  }
}
