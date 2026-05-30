$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$Failures = New-Object System.Collections.Generic.List[string]

function Add-Failure($Message) {
  $Failures.Add($Message) | Out-Null
}

$TauriConfigPath = "ui\src-tauri\tauri.conf.json"
$TauriConfig = Get-Content -Raw $TauriConfigPath | ConvertFrom-Json

if ($TauriConfig.build.devUrl -ne "http://127.0.0.1:5173") {
  Add-Failure "Tauri devUrl must be http://127.0.0.1:5173"
}

if ($TauriConfig.build.frontendDist -ne "../dist") {
  Add-Failure "Tauri frontendDist must point to ../dist"
}

$TauriText = Get-Content -Raw $TauriConfigPath
if ($TauriText -match "https?://(?!127\.0\.0\.1|localhost|schema\.tauri\.app)") {
  Add-Failure "Tauri config contains a non-local runtime URL"
}

if ($TauriText -match '"all"\s*:\s*true' -or $TauriText -match 'allowlist' -or $TauriText -match 'capabilities') {
  Add-Failure "Tauri config appears to contain broad allowlist/capability settings"
}

if ($TauriText -match "updater") {
  Add-Failure "Tauri updater must not be enabled"
}

$BackendScripts = @("scripts\start_api.ps1", "scripts\start_desktop.ps1", "package.json")
foreach ($script in $BackendScripts) {
  $text = Get-Content -Raw $script
  if ($text -match "0\.0\.0\.0") {
    Add-Failure "$script binds or references 0.0.0.0"
  }
}

$RuntimeFiles = @(
  "ui\index.html",
  "ui\src",
  "api",
  "racelab_engine",
  "scripts"
)

foreach ($path in $RuntimeFiles) {
  if (-not (Test-Path $path)) {
    continue
  }
  $files = Get-ChildItem -LiteralPath $path -Recurse -File |
    Where-Object {
      $_.FullName -notmatch "\\node_modules\\" -and
      $_.FullName -notmatch "\\dist\\" -and
      $_.FullName -notmatch "\\target\\" -and
      $_.FullName -notmatch "\\__pycache__\\" -and
      $_.Extension -ne ".pyc" -and
      $_.Name -ne "audit_local_only.ps1"
    }
  foreach ($file in $files) {
    $text = Get-Content -Raw -LiteralPath $file.FullName
    if ($text -match "https?://(?!127\.0\.0\.1|localhost|tauri\.localhost|nodejs\.org|rustup\.rs)") {
      Add-Failure "Potential non-local URL in $($file.FullName)"
    }
    if ($text -match "analytics|sentry|crash reporting|cloud sync|telemetry upload") {
      Add-Failure "Potential remote telemetry/analytics wording in $($file.FullName)"
    }
    if ($text -match "<script[^>]+https?://" -or $text -match "<link[^>]+https?://") {
      Add-Failure "Potential CDN runtime asset in $($file.FullName)"
    }
  }
}

if ($Failures.Count -gt 0) {
  Write-Host "Local-only audit failed:"
  foreach ($failure in $Failures) {
    Write-Host " - $failure"
  }
  exit 1
}

Write-Host "Local-only audit passed."
