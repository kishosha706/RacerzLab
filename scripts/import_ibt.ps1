param(
  [Parameter(Mandatory=$true)]
  [string]$Path
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (Test-Path ".venv\Scripts\python.exe") {
  .\.venv\Scripts\python.exe -m racelab_engine.cli import-ibt $Path
} else {
  python -m racelab_engine.cli import-ibt $Path
}
