import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_vehicle_systems_projects_into_existing_engineer_and_setup_workspaces() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    setup = _read("ui/src/tabs/SetupTab.tsx")
    panel = _read("ui/src/components/VehicleSystemsPanel.tsx")

    assert "initialProjection={report.vehicle_systems}" in engineer
    assert "expectedSetupId={setup.setup_id}" in setup
    assert 'refreshKey={`${workflowId ?? "no-workflow"}:${workflowUpdatedAt ?? "no-revision"}`}' in engineer
    assert 'refreshKey={`${workflowId ?? "no-workflow"}:${workflowUpdatedAt ?? "no-revision"}`}' in setup
    assert "Read-only · P19 decides setup" in panel
    assert "Previous exact-context Undo preserved" in panel
    assert 'data-mode={learning ? "learning" : "race"}' in panel
    assert "No setup-change" not in panel


def test_vehicle_systems_client_uses_read_only_run_scope() -> None:
    client = _read("ui/src/api/client.ts")

    assert "export function fetchVehicleSystems" in client
    assert "export function fetchVehicleSystemComponent" in client
    assert "export function fetchVehicleSystemControlTrace" in client
    assert "const INTELLIGENCE_TIMEOUT_MS = 60_000" in client
    assert "/vehicle-systems${suffix}" in client
    assert "method: \"POST\"" not in client[client.index("export function fetchVehicleSystems"):client.index("export function fetchEngineeringAwareness")]


def test_vehicle_systems_runtime_guards_reject_foreign_and_malformed_payloads() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the UI runtime contract test")
    result = subprocess.run(
        [
            node,
            "--no-warnings",
            "--experimental-strip-types",
            str(ROOT / "ui/tests/vehicleSystems.runtime.test.mjs"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
