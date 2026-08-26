[CmdletBinding()]
param(
  [string]$Executable = "",
  [ValidateSet("Fail", "Skip")]
  [string]$MissingArtifactAction = "Fail",
  [int]$Port = 8010,
  [int]$StartupTimeoutSeconds = 45
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseExecutable = Join-Path $ProjectRoot "ui\src-tauri\target\release\racelab-garage.exe"
$TauriConfigPath = Join-Path $ProjectRoot "ui\src-tauri\tauri.conf.json"
$StateProbePath = Join-Path $PSScriptRoot "packaged_desktop_state_probe.py"
$FirstProcess = $null
$SecondProcess = $null
$RestartProcess = $null
$MarkerSessionId = $null
$MarkerName = "RacerZLab packaged restart smoke $([guid]::NewGuid().ToString('N'))"
$OwnedBackendProcessIds = [System.Collections.Generic.HashSet[int]]::new()
$SmokeWorkingRoot = Join-Path ([System.IO.Path]::GetTempPath()) "racerzlab-packaged-smoke-$([guid]::NewGuid().ToString('N'))"
$LaunchDirectories = @(
  (Join-Path $SmokeWorkingRoot "first-launch"),
  (Join-Path $SmokeWorkingRoot "single-instance-launch"),
  (Join-Path $SmokeWorkingRoot "restart-launch")
)

function Complete-ArtifactUnavailable {
  param([string]$Reason)

  $Message = "code=artifact_unavailable reason=$Reason"
  if ($MissingArtifactAction -eq "Skip") {
    Write-Output "PACKAGED_DESKTOP_SMOKE_SKIPPED $Message"
    exit 0
  }
  throw "Packaged desktop smoke cannot run: $Message"
}

function Resolve-CandidatePath {
  param([string]$Candidate)

  if ([string]::IsNullOrWhiteSpace($Candidate)) { return $null }
  $Expanded = [Environment]::ExpandEnvironmentVariables($Candidate.Trim().Trim('"'))
  if (-not [System.IO.Path]::IsPathRooted($Expanded)) {
    $Expanded = Join-Path $ProjectRoot $Expanded
  }
  return [System.IO.Path]::GetFullPath($Expanded)
}

function Resolve-DisplayIconExecutable {
  param([string]$RawValue)

  if ([string]::IsNullOrWhiteSpace($RawValue)) { return $null }
  $Expanded = [Environment]::ExpandEnvironmentVariables($RawValue.Trim())
  $Match = [regex]::Match($Expanded, '^\s*"(?<path>[^"]+\.exe)"|^\s*(?<path>[^,]+\.exe)', 'IgnoreCase')
  if (-not $Match.Success) { return $null }
  return Resolve-CandidatePath $Match.Groups['path'].Value
}

function Find-InstalledExecutable {
  $Candidates = [System.Collections.Generic.List[string]]::new()
  foreach ($CandidateSpec in @(
      [pscustomobject]@{ Root = $env:LOCALAPPDATA; Child = "RacerZLab\racelab-garage.exe" },
      [pscustomobject]@{ Root = $env:LOCALAPPDATA; Child = "Programs\RacerZLab\racelab-garage.exe" },
      [pscustomobject]@{ Root = $env:ProgramFiles; Child = "RacerZLab\racelab-garage.exe" },
      [pscustomobject]@{ Root = ${env:ProgramFiles(x86)}; Child = "RacerZLab\racelab-garage.exe" }
    )) {
    if (-not [string]::IsNullOrWhiteSpace([string]$CandidateSpec.Root)) {
      $Candidate = Join-Path ([string]$CandidateSpec.Root) ([string]$CandidateSpec.Child)
      $Candidates.Add((Resolve-CandidatePath $Candidate)) | Out-Null
    }
  }

  foreach ($RegistryRoot in @(
      "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
      "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
      "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )) {
    Get-ItemProperty -Path $RegistryRoot -ErrorAction SilentlyContinue |
      Where-Object { [string]$_.DisplayName -eq "RacerZLab" } |
      ForEach-Object {
        $DisplayExecutable = Resolve-DisplayIconExecutable ([string]$_.DisplayIcon)
        if ($null -ne $DisplayExecutable) {
          $Candidates.Add($DisplayExecutable) | Out-Null
        }
        if (-not [string]::IsNullOrWhiteSpace([string]$_.InstallLocation)) {
          foreach ($Name in @("racelab-garage.exe", "RacerZLab.exe")) {
            $Candidates.Add((Resolve-CandidatePath (Join-Path ([string]$_.InstallLocation) $Name))) | Out-Null
          }
        }
      }
  }

  return $Candidates |
    Where-Object {
      (Test-Path -LiteralPath $_ -PathType Leaf) -and
      (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $_) "bin\racerzlab-backend.exe") -PathType Leaf)
    } |
    Sort-Object { (Get-Item -LiteralPath $_).LastWriteTimeUtc } -Descending |
    Select-Object -First 1
}

function Get-NewestInput {
  param([string[]]$Paths)

  $Items = foreach ($Path in $Paths) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
      Get-Item -LiteralPath $Path
    } elseif (Test-Path -LiteralPath $Path -PathType Container) {
      Get-ChildItem -LiteralPath $Path -Recurse -File |
        Where-Object {
          $_.Extension -ne ".pyc" -and
          $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and
          $_.Name -notmatch '\.(?:test|spec)\.[^.]+$'
        }
    }
  }
  return $Items | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
}

function Assert-CurrentReleaseArtifact {
  param(
    [string]$ExecutablePath,
    [string]$SidecarPath
  )

  $NewestShellInput = Get-NewestInput @(
    (Join-Path $ProjectRoot "ui\src-tauri\src"),
    (Join-Path $ProjectRoot "ui\src-tauri\Cargo.toml"),
    (Join-Path $ProjectRoot "ui\src-tauri\Cargo.lock"),
    $TauriConfigPath,
    (Join-Path $ProjectRoot "ui\src"),
    (Join-Path $ProjectRoot "ui\package.json"),
    (Join-Path $ProjectRoot "ui\package-lock.json"),
    (Join-Path $ProjectRoot "ui\vite.config.ts"),
    (Join-Path $ProjectRoot "ui\dist")
  )
  if ($null -ne $NewestShellInput -and (Get-Item -LiteralPath $ExecutablePath).LastWriteTimeUtc -lt $NewestShellInput.LastWriteTimeUtc) {
    Complete-ArtifactUnavailable "release_shell_is_stale"
  }

  $NewestBackendInput = Get-NewestInput @(
    (Join-Path $ProjectRoot "api"),
    (Join-Path $ProjectRoot "racelab_engine"),
    (Join-Path $ProjectRoot "scripts\build_backend_sidecar.ps1"),
    (Join-Path $ProjectRoot "requirements.lock")
  )
  if ($null -ne $NewestBackendInput -and (Get-Item -LiteralPath $SidecarPath).LastWriteTimeUtc -lt $NewestBackendInput.LastWriteTimeUtc) {
    Complete-ArtifactUnavailable "release_sidecar_is_stale"
  }
}

function Test-PathUnderRoot {
  param(
    [string]$Path,
    [string]$Root,
    [bool]$AllowRoot = $false
  )

  $FullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
  $FullRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
  if ($AllowRoot -and $FullPath.Equals($FullRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    return $true
  }
  $RootPrefix = $FullRoot + [System.IO.Path]::DirectorySeparatorChar
  return $FullPath.StartsWith($RootPrefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Assert-NoWorkingDirectoryStorage {
  param([string]$WorkingDirectory)

  foreach ($RelativePath in @("racelab.sqlite", "data", "logs", "backend.log")) {
    if (Test-Path -LiteralPath (Join-Path $WorkingDirectory $RelativePath)) {
      throw "The packaged backend leaked storage into its arbitrary launch working directory."
    }
  }
}

function Assert-AppLocalStorageContract {
  param(
    [string]$Root,
    [string]$Database,
    [string]$DataDirectory,
    [string]$LogPath
  )

  foreach ($Path in @($Database, $DataDirectory, $LogPath)) {
    if (-not (Test-PathUnderRoot -Path $Path -Root $Root)) {
      throw "A packaged backend storage path escaped the intended app-local root."
    }
  }
  if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
    throw "The packaged desktop did not create its app-local storage root."
  }
  if (-not (Test-Path -LiteralPath $Database -PathType Leaf)) {
    throw "The packaged desktop did not create its app-local database."
  }
  if (-not (Test-Path -LiteralPath $DataDirectory -PathType Container)) {
    throw "The packaged desktop did not create its app-local data directory."
  }
  if (-not (Test-Path -LiteralPath $LogPath -PathType Leaf)) {
    throw "The packaged desktop did not create its app-local backend log."
  }
}

function Read-Health {
  try {
    return Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
  } catch {
    return $null
  }
}

function Wait-ForHealth {
  param([int]$TimeoutSeconds)

  $Deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
  while ([DateTimeOffset]::UtcNow -lt $Deadline) {
    $Health = Read-Health
    if ($null -ne $Health) { return $Health }
    Start-Sleep -Milliseconds 250
  }
  return $null
}

function Wait-ForNoHealth {
  param([int]$TimeoutSeconds)

  $Deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
  while ([DateTimeOffset]::UtcNow -lt $Deadline) {
    if ($null -eq (Read-Health)) { return $true }
    Start-Sleep -Milliseconds 250
  }
  return $false
}

function Assert-ReadyHealth {
  param([object]$Health)

  if (
    $null -eq $Health -or
    $Health.status -ne "ok" -or
    $Health.app -ne "RacerZLab" -or
    [string]::IsNullOrWhiteSpace([string]$Health.instance_id)
  ) {
    throw "The packaged desktop health response was not storage-ready RacerZLab health."
  }
}

function Start-PackagedProcess {
  param([string]$WorkingDirectory)

  if (-not [System.IO.Path]::IsPathRooted($WorkingDirectory)) {
    throw "The packaged smoke launch directory must be absolute."
  }
  return Start-Process -FilePath $ExecutablePath -WorkingDirectory $WorkingDirectory -PassThru -WindowStyle Hidden
}

function Capture-OwnedBackendProcess {
  $Connection = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $Port -State Listen -ErrorAction Stop |
    Select-Object -First 1
  if ($null -eq $Connection) {
    throw "The packaged desktop health endpoint has no local listening process."
  }
  $BackendProcess = Get-Process -Id $Connection.OwningProcess -ErrorAction Stop
  $ActualPath = [System.IO.Path]::GetFullPath($BackendProcess.Path)
  if (-not $ActualPath.Equals($SidecarPath, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "The health endpoint is not owned by the packaged RacerZLab sidecar."
  }
  $OwnedBackendProcessIds.Add([int]$Connection.OwningProcess) | Out-Null
  return [int]$Connection.OwningProcess
}

function Invoke-StateProbe {
  param([string[]]$ProbeArguments)

  $Output = & $PythonPath -B $StateProbePath @ProbeArguments 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "The packaged persistence probe failed: $($Output -join [Environment]::NewLine)"
  }
  return ($Output -join [Environment]::NewLine).Trim()
}

function Close-PackagedProcess {
  param([System.Diagnostics.Process]$Process)

  $Process.Refresh()
  if ($Process.HasExited) {
    throw "The packaged desktop exited before its normal shutdown check."
  }
  if (-not $Process.CloseMainWindow()) {
    throw "The packaged desktop window could not receive a normal close request."
  }
  if (-not $Process.WaitForExit(15000)) {
    throw "The packaged desktop did not exit after a normal close request."
  }
  if ($Process.ExitCode -ne 0) {
    throw "The packaged desktop returned a failure exit code during normal shutdown."
  }
  if (-not (Wait-ForNoHealth 15)) {
    throw "The owned backend remained reachable after the desktop closed."
  }
}

function Remove-SmokeWorkingRoot {
  if (-not (Test-Path -LiteralPath $SmokeWorkingRoot)) { return }
  $ResolvedRoot = [System.IO.Path]::GetFullPath($SmokeWorkingRoot)
  $ResolvedTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
  if (-not (Test-PathUnderRoot -Path $ResolvedRoot -Root $ResolvedTemp)) {
    throw "Refusing to remove a smoke working directory outside the system temporary root."
  }
  Remove-Item -LiteralPath $ResolvedRoot -Recurse -Force
}

if ($env:OS -ne "Windows_NT") {
  Complete-ArtifactUnavailable "windows_desktop_required"
}
if (-not (Test-Path -LiteralPath $TauriConfigPath -PathType Leaf)) {
  Complete-ArtifactUnavailable "tauri_config_missing"
}
if (-not (Test-Path -LiteralPath $StateProbePath -PathType Leaf)) {
  Complete-ArtifactUnavailable "persistence_probe_missing"
}

$ArtifactSource = "explicit"
if (-not [string]::IsNullOrWhiteSpace($Executable)) {
  $ExecutablePath = Resolve-CandidatePath $Executable
  if (-not (Test-Path -LiteralPath $ExecutablePath -PathType Leaf)) {
    Complete-ArtifactUnavailable "explicit_executable_missing"
  }
} elseif (Test-Path -LiteralPath $ReleaseExecutable -PathType Leaf) {
  $ExecutablePath = [System.IO.Path]::GetFullPath($ReleaseExecutable)
  $ArtifactSource = "release"
} else {
  $InstalledExecutable = Find-InstalledExecutable
  if ($null -eq $InstalledExecutable) {
    Complete-ArtifactUnavailable "installed_and_release_executables_missing"
  }
  $ExecutablePath = [System.IO.Path]::GetFullPath($InstalledExecutable)
  $ArtifactSource = "installed"
}

$SidecarPath = [System.IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $ExecutablePath) "bin\racerzlab-backend.exe"))
if (-not (Test-Path -LiteralPath $SidecarPath -PathType Leaf)) {
  Complete-ArtifactUnavailable "packaged_sidecar_missing"
}
if ($ExecutablePath.Equals([System.IO.Path]::GetFullPath($ReleaseExecutable), [System.StringComparison]::OrdinalIgnoreCase)) {
  $ArtifactSource = "release"
  Assert-CurrentReleaseArtifact -ExecutablePath $ExecutablePath -SidecarPath $SidecarPath
}

$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
  $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if ($null -eq $PythonCommand) {
    Complete-ArtifactUnavailable "python_runtime_missing"
  }
  $PythonPath = $PythonCommand.Source
}

$TauriConfig = Get-Content -LiteralPath $TauriConfigPath -Raw | ConvertFrom-Json
$AppIdentifier = [string]$TauriConfig.identifier
if ($AppIdentifier -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]+$') {
  throw "The packaged desktop identifier is invalid."
}
$LocalAppData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
if ([string]::IsNullOrWhiteSpace($LocalAppData)) {
  Complete-ArtifactUnavailable "local_app_data_unavailable"
}
$AppLocalRoot = [System.IO.Path]::GetFullPath((Join-Path $LocalAppData $AppIdentifier))
$DatabasePath = [System.IO.Path]::GetFullPath((Join-Path $AppLocalRoot "racelab.sqlite"))
$DataDirectory = [System.IO.Path]::GetFullPath((Join-Path $AppLocalRoot "data"))
$LogPath = [System.IO.Path]::GetFullPath((Join-Path $AppLocalRoot "logs\backend.log"))
foreach ($Path in @($DatabasePath, $DataDirectory, $LogPath)) {
  if (-not (Test-PathUnderRoot -Path $Path -Root $AppLocalRoot)) {
    throw "The expected packaged storage contract escapes the app-local root."
  }
}

if ($null -ne (Read-Health)) {
  throw "Port $Port already serves a health endpoint; packaged ownership cannot be tested safely."
}

New-Item -ItemType Directory -Path $SmokeWorkingRoot | Out-Null
foreach ($Directory in $LaunchDirectories) {
  New-Item -ItemType Directory -Path $Directory | Out-Null
  if (-not (Test-PathUnderRoot -Path $Directory -Root $SmokeWorkingRoot)) {
    throw "A smoke launch directory escaped the isolated temporary root."
  }
}

$Completed = $false
try {
  $FirstProcess = Start-PackagedProcess -WorkingDirectory $LaunchDirectories[0]
  $FirstHealth = Wait-ForHealth $StartupTimeoutSeconds
  Assert-ReadyHealth $FirstHealth
  Capture-OwnedBackendProcess | Out-Null
  Assert-AppLocalStorageContract -Root $AppLocalRoot -Database $DatabasePath -DataDirectory $DataDirectory -LogPath $LogPath
  Assert-NoWorkingDirectoryStorage $LaunchDirectories[0]

  # The desktop capability remains private to its owned webview. This probe
  # writes the same durable session record served by the sessions API.
  $SeedJson = Invoke-StateProbe @(
    "seed",
    "--database", $DatabasePath,
    "--name", $MarkerName
  )
  $Seed = $SeedJson | ConvertFrom-Json
  $MarkerSessionId = [string]$Seed.session_id
  if ([string]::IsNullOrWhiteSpace($MarkerSessionId) -or [string]$Seed.name -ne $MarkerName) {
    throw "The packaged persistence probe did not return the exact seeded session identity."
  }

  $SecondProcess = Start-PackagedProcess -WorkingDirectory $LaunchDirectories[1]
  if (-not $SecondProcess.WaitForExit(10000)) {
    throw "A second desktop launch remained active instead of handing off to the first instance."
  }
  if ($SecondProcess.ExitCode -ne 0) {
    throw "The single-instance handoff returned a failure exit code."
  }
  $FirstProcess.Refresh()
  if ($FirstProcess.HasExited) {
    throw "The first desktop instance exited during the single-instance handoff."
  }
  $SecondHealth = Read-Health
  Assert-ReadyHealth $SecondHealth
  if ($SecondHealth.instance_id -ne $FirstHealth.instance_id) {
    throw "The second launch changed the first instance's backend identity."
  }
  Assert-NoWorkingDirectoryStorage $LaunchDirectories[1]

  Close-PackagedProcess $FirstProcess

  $RestartProcess = Start-PackagedProcess -WorkingDirectory $LaunchDirectories[2]
  $RestartHealth = Wait-ForHealth $StartupTimeoutSeconds
  Assert-ReadyHealth $RestartHealth
  if ($RestartHealth.instance_id -eq $FirstHealth.instance_id) {
    throw "A full desktop restart reused the prior shell/backend instance identity."
  }
  Capture-OwnedBackendProcess | Out-Null
  Assert-AppLocalStorageContract -Root $AppLocalRoot -Database $DatabasePath -DataDirectory $DataDirectory -LogPath $LogPath
  Assert-NoWorkingDirectoryStorage $LaunchDirectories[2]

  $VerifyJson = Invoke-StateProbe @(
    "verify",
    "--database", $DatabasePath,
    "--session-id", $MarkerSessionId,
    "--name", $MarkerName
  )
  $Verified = $VerifyJson | ConvertFrom-Json
  if (-not [bool]$Verified.present -or [string]$Verified.session_id -ne $MarkerSessionId) {
    throw "The API-visible session marker did not survive the packaged desktop restart."
  }

  Close-PackagedProcess $RestartProcess
  Invoke-StateProbe @(
    "delete",
    "--database", $DatabasePath,
    "--session-id", $MarkerSessionId,
    "--name", $MarkerName
  ) | Out-Null
  $MarkerSessionId = $null

  $Completed = $true
  Write-Output "PACKAGED_DESKTOP_SMOKE_PASSED artifact=$ArtifactSource storage=ready persistence=restart single_instance=passed shutdown=passed"
} finally {
  foreach ($Process in @($SecondProcess, $RestartProcess, $FirstProcess)) {
    if ($null -ne $Process) {
      try {
        $Process.Refresh()
        if (-not $Process.HasExited) {
          Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        }
      } catch {
        # Best-effort cleanup continues to the exact owned backend PIDs below.
      }
    }
  }
  foreach ($BackendProcessId in $OwnedBackendProcessIds) {
    $OwnedBackend = Get-Process -Id $BackendProcessId -ErrorAction SilentlyContinue
    if ($null -ne $OwnedBackend) {
      try {
        $OwnedBackendPath = [string]$OwnedBackend.Path
        if (
          -not [string]::IsNullOrWhiteSpace($OwnedBackendPath) -and
          ([System.IO.Path]::GetFullPath($OwnedBackendPath)).Equals(
            $SidecarPath,
            [System.StringComparison]::OrdinalIgnoreCase
          )
        ) {
          Stop-Process -Id $BackendProcessId -Force -ErrorAction SilentlyContinue
        }
      } catch {
        # PID reuse or an already-exited process must not broaden cleanup scope.
      }
    }
  }
  Wait-ForNoHealth 10 | Out-Null

  if (-not [string]::IsNullOrWhiteSpace([string]$MarkerSessionId) -and (Test-Path -LiteralPath $DatabasePath -PathType Leaf)) {
    try {
      Invoke-StateProbe @(
        "delete",
        "--database", $DatabasePath,
        "--session-id", $MarkerSessionId,
        "--name", $MarkerName
      ) | Out-Null
      $MarkerSessionId = $null
    } catch {
      if ($Completed) { throw }
      Write-Warning "The failed packaged smoke could not remove its uniquely named session marker."
    }
  }
  Remove-SmokeWorkingRoot
}
