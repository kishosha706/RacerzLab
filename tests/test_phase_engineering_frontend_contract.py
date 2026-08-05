from __future__ import annotations

from pathlib import Path

from api.main import app


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_engineering_systems_endpoint_has_declared_response_contract() -> None:
    operation = app.openapi()["paths"]["/api/compare/engineering-systems"]["post"]

    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/EngineeringSystemsResponse")


def test_staged_laps_comparison_exposes_engineering_decision_layer() -> None:
    laps = _read("ui/src/tabs/LapsTab.tsx")
    surface = _read("ui/src/components/EngineeringSystemsComparison.tsx")
    client = _read("ui/src/api/client.ts")

    assert "<EngineeringSystemsComparison" in laps
    assert '"/api/compare/engineering-systems"' in client
    assert 'aria-label="Engineering decision layer"' in surface
    assert "Can this comparison support a setup decision?" in surface
    assert 'selection.selectedMode === "learning"' in surface


def test_engineering_surface_keeps_proxy_and_integrity_caveats_visible() -> None:
    surface = _read("ui/src/components/EngineeringSystemsComparison.tsx")

    assert "sim_integrity_clear" in surface
    assert "sim_integrity_confidence_cap" in surface
    assert "Proxy conclusions stay explicitly separate" in surface
    assert "setup attribution" in surface.lower()
    assert "source_channels" in surface
    assert "blocker_reasons" in surface
    assert 'driver.driver_execution_changed === false' in surface
    assert '"Driver match unavailable"' in surface
    assert 'data.sim_integrity_confidence_cap >= 0.75' in surface
    assert 'data.baseline_sim_integrity_status === "pass"' in surface
    assert '+{data.warnings.length - 2} more warnings' in surface
