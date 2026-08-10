from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_vehicle_systems_projects_into_existing_engineer_and_setup_workspaces() -> None:
    engineer = _read("ui/src/tabs/EngineerTab.tsx")
    setup = _read("ui/src/tabs/SetupTab.tsx")
    panel = _read("ui/src/components/VehicleSystemsPanel.tsx")

    assert '<VehicleSystemsPanel runId={runId}' in engineer
    assert '<VehicleSystemsPanel runId={overview.run_id}' in setup
    assert "P19 authority only" in panel
    assert "Previous exact-context Undo preserved" in panel
    assert 'data-mode={learning ? "learning" : "race"}' in panel
    assert "No setup-change" not in panel


def test_vehicle_systems_client_uses_read_only_run_scope() -> None:
    client = _read("ui/src/api/client.ts")

    assert "export function fetchVehicleSystems" in client
    assert "/vehicle-systems${suffix}" in client
    assert "method: \"POST\"" not in client[client.index("export function fetchVehicleSystems"):client.index("export function fetchEngineeringAwareness")]
