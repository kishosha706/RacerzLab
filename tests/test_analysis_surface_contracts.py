from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from racelab_engine.analysis.analysis_surface_contracts import analysis_surface_contracts


def test_professional_surface_registry_covers_required_analysis_language() -> None:
    contracts = analysis_surface_contracts()
    assert len({item.surface_id for item in contracts}) == len(contracts)
    visible = " ".join(item.professional_term.casefold() for item in contracts)
    for term in (
        "time variance", "synchronized comparison", "overlays", "math channels",
        "map", "histogram", "power spectral density", "cursor statistics",
        "metrics", "report",
    ):
        assert term in visible


def test_every_surface_answers_a_decision_and_preserves_evidence_gaps() -> None:
    for item in analysis_surface_contracts():
        assert item.decision_question.endswith("?")
        assert item.consumer
        assert item.driver_follow_up
        assert item.provenance
        assert item.units
        assert any(term in item.gap_behavior.casefold() for term in ("gap", "missing", "unavailable", "unmapped"))
        assert all(term not in item.gap_behavior.casefold() for term in ("missing becomes zero", "fill with zero"))
        assert item.proxy_policy


def test_surface_contracts_are_available_to_reports_and_ui_consumers() -> None:
    response = TestClient(app).get("/api/analysis/surface-contracts")
    assert response.status_code == 200
    payload = response.json()
    assert {item["surface_id"] for item in payload} == {
        item.surface_id for item in analysis_surface_contracts()
    }
    assert all(item["decision_question"] and item["provenance"] for item in payload)
