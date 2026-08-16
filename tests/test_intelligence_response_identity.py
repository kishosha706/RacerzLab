from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.intelligence_identity import intelligence_snapshot_identity
from api.intelligence_schemas import (
    IntelligenceCitationResponse,
    IntelligenceQueryResponse,
    RunIntelligenceResponse,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services.session_intelligence_service import setup_snapshot_fingerprint

REASONING_SHA256 = "a" * 64
SETUP_SHA256 = "b" * 64


def _report_payload() -> dict[str, object]:
    return {
        "schema_version": "p19.run-intelligence.v1",
        "run_id": "run-1",
        "session_id": "session-1",
        "reasoning_snapshot_sha256": REASONING_SHA256,
        "setup_id": None,
        "setup_snapshot_sha256": None,
        "status": "ready",
        "decision_status": "measure",
        "briefing": {
            "issue": "More evidence is required.",
            "action": {
                "kind": "no_call",
                "title": "Hold setup",
                "instruction": "Collect another qualified lap.",
                "setup_authorized": False,
                "evidence_state": "needs_confirmation",
            },
        },
        "calibration": {
            "status": "insufficient_history",
            "summary": "No graded history.",
            "caveat": "Direction is not calibrated.",
        },
    }


def _citation() -> IntelligenceCitationResponse:
    return IntelligenceCitationResponse(
        citation_id="event-1",
        label="Turn 1 center evidence",
        run_id="run-1",
        lap_number=4,
        lap_pct=17.5,
        event_id="event-1",
        workspace="platform_trace",
        source_channels=["Speed"],
        evidence_state=EvidenceState.MEASURED,
        valid_for_tuning=True,
        phase="center",
        track_region_id="turn_1",
        track_region_label="Turn 1 center",
        track_region_phase="center",
        track_region_confidence="section_geometry",
    )


def _query_payload() -> dict[str, object]:
    return {
        "schema_version": "p19.intelligence-query.v1",
        "run_id": "run-1",
        "session_id": "session-1",
        "reasoning_snapshot_sha256": REASONING_SHA256,
        "setup_id": "setup-1",
        "setup_snapshot_sha256": SETUP_SHA256,
        "scope_run_ids": ["run-1"],
        "status": "ready",
        "question": "Where is the center loss in Turn 1?",
        "headline": "Where the loss appears",
        "answer": "The qualified event is in Turn 1 center.",
        "interpreted_phase": "center",
        "interpreted_track_region_id": "turn_1",
        "interpreted_track_region_label": "Turn 1",
        "evidence_state": EvidenceState.MEASURED,
        "citations": [_citation()],
    }


def test_snapshot_identity_is_deterministic_and_run_bound() -> None:
    reasoning = SimpleNamespace(model_dump=lambda **_: {"z": 1, "a": [2, 3]})
    setup = SetupSnapshot(setup_id="setup-1", run_id="run-1", tape_percent=30)

    first = intelligence_snapshot_identity(
        reasoning,
        run_id="run-1",
        setup_snapshot=setup,
    )
    second = intelligence_snapshot_identity(
        reasoning,
        run_id="run-1",
        setup_snapshot=setup,
    )

    assert first == second
    assert len(first.reasoning_snapshot_sha256) == 64
    assert first.setup_id == "setup-1"
    assert len(first.setup_snapshot_sha256 or "") == 64
    assert first.setup_snapshot_sha256 == setup_snapshot_fingerprint(setup)
    with pytest.raises(ValueError, match="does not match the reasoning run"):
        intelligence_snapshot_identity(
            reasoning,
            run_id="run-foreign",
            setup_snapshot=setup,
        )


def test_snapshot_identity_rejects_non_finite_setup_values() -> None:
    reasoning = SimpleNamespace(model_dump=lambda **_: {"state": "ready"})
    setup = SetupSnapshot(
        setup_id="setup-corrupt",
        run_id="run-1",
        cross_weight_percent=float("nan"),
    )

    with pytest.raises(ValueError, match="Out of range float values"):
        intelligence_snapshot_identity(
            reasoning,
            run_id="run-1",
            setup_snapshot=setup,
        )


def test_public_snapshot_identity_matches_the_embedded_p26_projection() -> None:
    from tests.test_vehicle_systems_intelligence import _project, _report

    report = _report()
    setup = SetupSnapshot(
        setup_id="setup-p26",
        run_id=report.run_id,
        cross_weight_percent=50.0,
    )
    projection = _project(report, setup_snapshot=setup)
    identity = intelligence_snapshot_identity(
        report.reasoning_snapshot,
        run_id=report.run_id,
        setup_snapshot=setup,
    )

    assert identity.reasoning_snapshot_sha256 == projection.reasoning_snapshot_sha256
    assert identity.setup_id == projection.setup_id
    assert identity.setup_snapshot_sha256 == projection.setup_snapshot_sha256
    payload = _report_payload() | {
        "run_id": report.run_id,
        "session_id": None,
        "reasoning_snapshot_sha256": identity.reasoning_snapshot_sha256,
        "setup_id": identity.setup_id,
        "setup_snapshot_sha256": identity.setup_snapshot_sha256,
        "vehicle_systems": projection,
    }
    RunIntelligenceResponse.model_validate(payload)
    with pytest.raises(ValueError, match="scope, snapshots, and authority"):
        RunIntelligenceResponse.model_validate(
            payload | {"reasoning_snapshot_sha256": "c" * 64}
        )


def test_report_authority_requires_exact_setup_identity() -> None:
    payload = _report_payload()
    RunIntelligenceResponse.model_validate(payload)

    hostile = payload | {
        "decision_status": "ready",
        "briefing": {
            "action": {
                "kind": "controlled_test",
                "title": "Forged exact target",
                "instruction": "50.0% -> 50.1% (adjacent observed tech-passing option)",
                "setup_authorized": True,
                "control_key": "cross_weight_percent",
                "setup_effect_id": "add_crossweight_small",
                "experiment_factor_id": "factor:crossweight",
                "direction_sign": 1,
                "current_value": "50.0%",
                "proposed_value": "50.1%",
                "evidence_state": "measured",
                "source_event_ids": ["event-1"],
            }
        },
    }
    with pytest.raises(ValueError, match="exact setup snapshot identity"):
        RunIntelligenceResponse.model_validate(hostile)


def test_query_rejects_forged_phase_and_region_provenance() -> None:
    payload = _query_payload()
    response = IntelligenceQueryResponse.model_validate(payload)
    assert response.citations[0].phase == "center"

    with pytest.raises(ValueError, match="interpreted phase"):
        IntelligenceQueryResponse.model_validate(payload | {"interpreted_phase": "exit"})
    with pytest.raises(ValueError, match="interpreted track region"):
        IntelligenceQueryResponse.model_validate(
            payload
            | {
                "interpreted_track_region_id": "turn_2",
                "interpreted_track_region_label": "Turn 2",
            }
        )


def test_citation_rejects_incomplete_track_region_provenance() -> None:
    payload = _citation().model_dump(mode="json")
    payload["track_region_confidence"] = None
    with pytest.raises(ValueError, match="must be supplied together"):
        IntelligenceCitationResponse.model_validate(payload)
