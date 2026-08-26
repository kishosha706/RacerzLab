from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from racelab_engine.services.session_service import get_session
from racelab_engine.storage.db import initialize_database


ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = ROOT / "scripts" / "smoke_packaged_desktop.ps1"
STATE_PROBE = ROOT / "scripts" / "packaged_desktop_state_probe.py"
SMOKE_NAME = "RacerZLab packaged restart smoke executable-contract"


def _run_probe(*arguments: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-B", str(STATE_PROBE), *arguments],
        cwd=STATE_PROBE.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_packaged_state_probe_survives_separate_processes_and_cleans_exact_marker(
    tmp_path: Path,
) -> None:
    database = tmp_path / "racelab.sqlite"
    initialize_database(database).close()

    seeded = _run_probe(
        "seed",
        "--database",
        str(database),
        "--name",
        SMOKE_NAME,
    )
    session_id = str(seeded["session_id"])

    verified = _run_probe(
        "verify",
        "--database",
        str(database),
        "--session-id",
        session_id,
        "--name",
        SMOKE_NAME,
    )
    assert verified == {
        "name": SMOKE_NAME,
        "present": True,
        "session_id": session_id,
        "status": "active",
    }

    deleted = _run_probe(
        "delete",
        "--database",
        str(database),
        "--session-id",
        session_id,
        "--name",
        SMOKE_NAME,
    )
    assert deleted["deleted"] is True
    assert get_session(session_id, db_path=database) is None


def test_packaged_state_probe_refuses_to_delete_a_different_session(
    tmp_path: Path,
) -> None:
    database = tmp_path / "racelab.sqlite"
    initialize_database(database).close()
    seeded = _run_probe(
        "seed",
        "--database",
        str(database),
        "--name",
        SMOKE_NAME,
    )
    session_id = str(seeded["session_id"])

    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(STATE_PROBE),
            "delete",
            "--database",
            str(database),
            "--session-id",
            session_id,
            "--name",
            f"{SMOKE_NAME}-different",
        ],
        cwd=STATE_PROBE.parent,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert get_session(session_id, db_path=database) is not None


@pytest.mark.skipif(os.name != "nt", reason="the packaged desktop smoke is Windows-only")
def test_missing_packaged_artifact_has_an_explicit_executable_skip(tmp_path: Path) -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is unavailable")

    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SMOKE_SCRIPT),
            "-Executable",
            str(tmp_path / "missing-racelab-garage.exe"),
            "-MissingArtifactAction",
            "Skip",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "PACKAGED_DESKTOP_SMOKE_SKIPPED code=artifact_unavailable" in completed.stdout
    assert "reason=explicit_executable_missing" in completed.stdout


@pytest.mark.skipif(os.name != "nt", reason="the packaged desktop smoke is Windows-only")
def test_missing_packaged_artifact_fails_the_release_gate(tmp_path: Path) -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is unavailable")

    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SMOKE_SCRIPT),
            "-Executable",
            str(tmp_path / "missing-racelab-garage.exe"),
            "-MissingArtifactAction",
            "Fail",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    combined_output = completed.stdout + completed.stderr
    assert "code=artifact_unavailable" in combined_output
    assert "reason=explicit_executable_missing" in combined_output


def test_release_workflow_runs_the_real_packaged_restart_contract() -> None:
    smoke = SMOKE_SCRIPT.read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "release-trust.yml").read_text(
        encoding="utf-8"
    )

    assert "scripts/smoke_packaged_desktop.ps1 -MissingArtifactAction Fail" in workflow
    assert "Invoke-RestMethod" in smoke
    assert "Assert-ReadyHealth $FirstHealth" in smoke
    assert "Assert-ReadyHealth $RestartHealth" in smoke
    assert "Capture-OwnedBackendProcess" in smoke
    assert "-WorkingDirectory $WorkingDirectory" in smoke
    assert "Assert-NoWorkingDirectoryStorage" in smoke
    assert "Assert-AppLocalStorageContract" in smoke
    assert 'Join-Path $AppLocalRoot "racelab.sqlite"' in smoke
    assert 'Join-Path $AppLocalRoot "data"' in smoke
    assert 'Join-Path $AppLocalRoot "logs\\backend.log"' in smoke
    assert 'Complete-ArtifactUnavailable "release_shell_is_stale"' in smoke
    assert 'Complete-ArtifactUnavailable "release_sidecar_is_stale"' in smoke
    assert '"seed"' in smoke
    assert '"verify"' in smoke
    assert "$RestartHealth.instance_id -eq $FirstHealth.instance_id" in smoke
    assert "Wait-ForNoHealth" in smoke
    assert "single-instance handoff" in smoke
    assert "mock" not in smoke.lower()
