$ErrorActionPreference = "Continue"

function Test-RacerLabName {
  param([string]$Value)
  if ([string]::IsNullOrWhiteSpace($Value)) { return $false }
  return $Value -match "(?i)racer.*lab|racerzlab|racerzlab|racelab"
}

function Resolve-ExecutablePath {
  param([string]$Raw)
  if ([string]::IsNullOrWhiteSpace($Raw)) { return $null }
  $value = [Environment]::ExpandEnvironmentVariables($Raw.Trim())
  if ($value.StartsWith('"')) {
    $end = $value.IndexOf('"', 1)
    if ($end -gt 1) { return $value.Substring(1, $end - 1) }
  }
  $match = [regex]::Match($value, "(?i)([A-Z]:\\[^`"']+?\.exe)")
  if ($match.Success) { return $match.Groups[1].Value.Trim() }
  return $value
}

function Normalize-PathText {
  param([string]$Raw)
  if ([string]::IsNullOrWhiteSpace($Raw)) { return $null }
  return [Environment]::ExpandEnvironmentVariables($Raw.Trim().Trim('"'))
}

function Test-AppExecutable {
  param([string]$Path)
  if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
  if ([IO.Path]::GetExtension($Path) -ne ".exe") { return $false }
  $name = [IO.Path]::GetFileName($Path)
  if ($name -match "(?i)uninstall|update|setup|backend") { return $false }
  return Test-RacerLabName $name
}

function Candidate-Score {
  param([string]$Path, [object]$Detail)
  $score = 100
  if ($Path -match "(?i)\\RacerZLab\\") { $score -= 50 }
  if ([IO.Path]::GetFileName($Path) -eq "racelab-garage.exe") { $score -= 30 }
  if ($Detail -and $Detail.DisplayName -eq "RacerZLab") { $score -= 20 }
  return $score
}

function Add-Candidate {
  param(
    [System.Collections.Generic.List[object]]$Candidates,
    [string]$Source,
    [string]$Path,
    [object]$Detail = $null,
    [bool]$Installed = $true
  )
  if ([string]::IsNullOrWhiteSpace($Path)) { return }
  $expanded = Normalize-PathText $Path
  if (-not (Test-AppExecutable $expanded)) { return }
  if (-not (Test-Path -LiteralPath $expanded -PathType Leaf)) { return }
  if ($Candidates | Where-Object { $_.Path -eq $expanded }) { return }
  $Candidates.Add([pscustomobject]@{
    Source = $Source
    Path = $expanded
    Installed = $Installed
    Score = Candidate-Score -Path $expanded -Detail $Detail
    Detail = $Detail
  }) | Out-Null
}

$candidates = [System.Collections.Generic.List[object]]::new()
$registryMatches = [System.Collections.Generic.List[object]]::new()
$shortcutMatches = [System.Collections.Generic.List[object]]::new()
$diagnostics = [System.Collections.Generic.List[object]]::new()

$registryRoots = @(
  "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
  "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
  "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
)

foreach ($root in $registryRoots) {
  Get-ItemProperty -Path $root -ErrorAction SilentlyContinue | ForEach-Object {
    $displayName = [string]$_.DisplayName
    if (-not (Test-RacerLabName $displayName)) { return }
    $entry = [pscustomobject]@{
      DisplayName = $_.DisplayName
      DisplayVersion = $_.DisplayVersion
      InstallLocation = $_.InstallLocation
      DisplayIcon = $_.DisplayIcon
      UninstallString = $_.UninstallString
      RegistryPath = $_.PSPath
    }
    $registryMatches.Add($entry) | Out-Null
    foreach ($raw in @($_.DisplayIcon, $_.UninstallString)) {
      $resolved = Resolve-ExecutablePath $raw
      Add-Candidate -Candidates $candidates -Source "registry" -Path $resolved -Detail $entry -Installed $true
    }
    $installLocation = Normalize-PathText $_.InstallLocation
    if ($installLocation) {
      Get-ChildItem -Path $installLocation -Filter "*.exe" -ErrorAction SilentlyContinue |
        Where-Object { -not $_.PSIsContainer -and (Test-AppExecutable $_.FullName) } |
        ForEach-Object { Add-Candidate -Candidates $candidates -Source "registry-install-location" -Path $_.FullName -Detail $entry -Installed $true }
    }
  }
}

$shortcutRoots = @(
  (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"),
  (Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs")
)

$wsh = $null
try { $wsh = New-Object -ComObject WScript.Shell } catch { $wsh = $null }

foreach ($root in $shortcutRoots) {
  if (-not (Test-Path -LiteralPath $root)) { continue }
  Get-ChildItem -Path $root -Recurse -Filter "*.lnk" -File -ErrorAction SilentlyContinue |
    Where-Object { Test-RacerLabName $_.Name } |
    ForEach-Object {
      $target = $null
      if ($wsh) {
        try { $target = $wsh.CreateShortcut($_.FullName).TargetPath } catch { $target = $null }
      }
      $shortcut = [pscustomobject]@{
        Shortcut = $_.FullName
        TargetPath = $target
      }
      $shortcutMatches.Add($shortcut) | Out-Null
      Add-Candidate -Candidates $candidates -Source "start-menu-shortcut" -Path $target -Detail $shortcut -Installed $true
    }
}

$searchRoots = @(
  (Join-Path $env:LOCALAPPDATA "Programs"),
  $env:LOCALAPPDATA,
  $env:ProgramFiles,
  ${env:ProgramFiles(x86)},
  $env:APPDATA,
  $env:ProgramData
) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique

$patterns = @("*Racer*Lab*.exe", "*RacerZLab*.exe", "*RacerzLab*.exe", "*racelab*.exe")
foreach ($root in $searchRoots) {
  if (-not (Test-Path -LiteralPath $root)) { continue }
  foreach ($pattern in $patterns) {
    Get-ChildItem -Path $root -Recurse -Filter $pattern -ErrorAction SilentlyContinue |
      Where-Object { -not $_.PSIsContainer -and (Test-AppExecutable $_.FullName) } |
      ForEach-Object { Add-Candidate -Candidates $candidates -Source "file-search" -Path $_.FullName -Installed $true }
  }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $repoRoot "ui\src-tauri\target\release"
if (Test-Path -LiteralPath $releaseRoot) {
  Get-ChildItem -Path $releaseRoot -Filter "*.exe" -ErrorAction SilentlyContinue |
    Where-Object { -not $_.PSIsContainer } |
    Where-Object { Test-RacerLabName $_.Name } |
    ForEach-Object {
      $diagnostics.Add([pscustomobject]@{
        Source = "release-diagnostic"
        Path = $_.FullName
        Installed = $false
      }) | Out-Null
    }
}

Write-Host "Registry matches:"
if ($registryMatches.Count -eq 0) { Write-Host "  none" } else { $registryMatches | Format-List | Out-String | Write-Host }

Write-Host "Start Menu matches:"
if ($shortcutMatches.Count -eq 0) { Write-Host "  none" } else { $shortcutMatches | Format-List | Out-String | Write-Host }

Write-Host "Installed executable candidates:"
if ($candidates.Count -eq 0) {
  Write-Host "  none"
} else {
  $candidates | Format-List | Out-String | Write-Host
}

Write-Host "Release diagnostics, not valid for installed-app smoke:"
if ($diagnostics.Count -eq 0) { Write-Host "  none" } else { $diagnostics | Format-List | Out-String | Write-Host }

if ($candidates.Count -eq 0) {
  exit 1
}

$primary = $candidates | Sort-Object Score, Source, Path | Select-Object -First 1
Write-Host "PRIMARY_INSTALLED_EXE=$($primary.Path)"
exit 0
