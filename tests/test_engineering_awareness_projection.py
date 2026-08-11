from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import app
from racelab_engine.models.engineering_awareness import TrustAxis, TrustBudget, TrustState
from racelab_engine.models.engineering_projection import (
    AwarenessArtifactVersion,
    AwarenessRequestIdentity,
    EngineeringAwarenessProjection,
    ExpectedVsObservedState,
    SubsystemAwarenessState,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.observation_intelligence import MechanismKind
from racelab_engine.services import engineering_projection_service as service


def _axis() -> TrustAxis:
    return TrustAxis(
        state=TrustState.UNAVAILABLE,
        basis="Synthetic hostile projection test.",
        blockers=("Evidence is intentionally unavailable in this fixture.",),
    )


def _projection(run_id: str = "run-a") -> EngineeringAwarenessProjection:
    digest = "a" * 64
    revision = "b" * 64
    trust = TrustBudget(
        data_health=_axis(),
        alignment_quality=_axis(),
        context_comparability=_axis(),
        driver_repeatability=_axis(),
        mechanism_separation=_axis(),
        controlled_response_validity=_axis(),
        policy_countereffect_risk=_axis(),
        history_completeness=_axis(),
    )
    systems = tuple(
        SubsystemAwarenessState(
            mechanism=kind,
            status="unavailable",
            summary=f"{kind.value} unavailable",
            evidence_state=EvidenceState.UNAVAILABLE,
            blocker_reasons=("No producer artifact.",),
        )
        for kind in MechanismKind
        if kind is not MechanismKind.UNCLASSIFIED
    )
    return EngineeringAwarenessProjection(
        run_id=run_id,
        reasoning_snapshot_id=digest,
        state_revision=revision,
        request_identity=AwarenessRequestIdentity(
            run_id=run_id,
            reasoning_snapshot_id=digest,
            state_revision=revision,
        ),
        generated_at=datetime.now(timezone.utc),
        cache_state="cold",
        build_duration_ms=1.0,
        trust_budget=trust,
        subsystem_states=systems,
        state_drift_status="unavailable",
        state_drift_blocker_reasons=("No canonical drift ledger.",),
        artifact_versions=(
            AwarenessArtifactVersion(artifact_key="projection_schema", version="p20.awareness.v2"),
        ),
    )


def test_projection_requires_all_ten_mechanisms_and_exact_identity() -> None:
    projection = _projection()
    assert len(projection.subsystem_states) == 10
    assert {item.mechanism for item in projection.subsystem_states} == {
        item for item in MechanismKind if item is not MechanismKind.UNCLASSIFIED
    }
    with pytest.raises(ValueError, match="exact session scope"):
        EngineeringAwarenessProjection.model_validate(
            {
                **projection.model_dump(mode="json"),
                "session_id": "session-b",
            }
        )
    with pytest.raises(ValueError, match="every mechanism family exactly once"):
        duplicated = projection.model_dump(mode="json")["subsystem_states"]
        duplicated[-1] = duplicated[0]
        EngineeringAwarenessProjection.model_validate(
            {
                **projection.model_dump(mode="json"),
                "subsystem_states": duplicated,
            }
        )


@pytest.mark.parametrize(
    ("removed_field", "hostile_value"),
    (
        ("authority_state", "controlled_setup"),
        ("setup_authorized", True),
        ("current_mission", {"instruction": "Increase front spring rate."}),
        ("setup_leverage_states", [{"control_key": "front_spring", "states": ["authorized"]}]),
    ),
)
def test_projection_rejects_removed_p19_policy_and_action_mirrors(
    removed_field: str,
    hostile_value: object,
) -> None:
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        EngineeringAwarenessProjection.model_validate(
            {**_projection().model_dump(mode="json"), removed_field: hostile_value}
        )


def test_expected_vs_observed_rejects_policy_fields() -> None:
    safe = {
        "workflow_id": "workflow-1",
        "control_key": "front_arb",
        "metric": "center phase time",
        "phase": "center",
        "mechanism_state": "supported",
        "control_response": "missed",
        "mechanism_reason": "Mechanism persisted.",
        "control_response_reason": "The measured response missed the expectation.",
    }
    for field, value in (
        ("policy_verdict", "undo"),
        ("policy_reason", "Undo this control."),
        ("countereffects", ["exit loss"]),
    ):
        with pytest.raises(ValueError, match="Extra inputs are not permitted"):
            ExpectedVsObservedState.model_validate({**safe, field: value})


def test_expected_vs_observed_redacts_p19_policy_and_keeps_axes_separate() -> None:
    outcome = SimpleNamespace(
        workflow_id="workflow-1",
        mechanism=SimpleNamespace(state="supported", reason="Mechanism persisted."),
        control_response=SimpleNamespace(
            control_key="front_arb",
            result="missed",
            metric="center phase time",
            phase="center",
            reason="The exact control missed its expected response.",
        ),
        policy=SimpleNamespace(
            verdict="undo",
            reason="The countereffect made the policy unacceptable.",
            countereffects=("exit loss",),
        ),
    )
    snapshot = SimpleNamespace(controlled_outcomes=(outcome,))
    bundle = SimpleNamespace(report=SimpleNamespace(reasoning_snapshot=snapshot))
    expected = service._expected_vs_observed(bundle)
    assert expected[0].mechanism_state == "supported"
    assert expected[0].control_response == "missed"
    assert {
        "policy_verdict",
        "policy_reason",
        "countereffects",
    }.isdisjoint(expected[0].model_dump())
    service_source = Path(service.__file__).read_text(encoding="utf-8")
    assert ".policy.verdict" not in service_source
    assert ".policy.reason" not in service_source


def test_failed_producer_stays_visible_when_same_family_has_qualified_evidence() -> None:
    ready = SimpleNamespace(
        mechanism=MechanismKind.PLATFORM_RESPONSE,
        qualified=True,
        artifact_id="platform:ready",
        summary="Platform response qualified.",
        phase="center",
        lap_number=4,
        lap_pct_start=40.0,
        lap_pct_end=45.0,
        evidence_state=EvidenceState.CALCULATED,
        source_channels=("cfs_ride_height_mm",),
        blocker_reasons=(),
    )
    blocked = SimpleNamespace(
        mechanism=MechanismKind.PLATFORM_RESPONSE,
        qualified=False,
        artifact_id="platform:blocked",
        source_channels=(),
        blocker_reasons=("RF ride-height coverage is incomplete.",),
    )
    bundle = SimpleNamespace(
        report=SimpleNamespace(
            mechanism_observations=SimpleNamespace(observations=(ready, blocked))
        )
    )
    state = next(
        item
        for item in service._subsystem_states(bundle)
        if item.mechanism is MechanismKind.PLATFORM_RESPONSE
    )
    assert state.status == "blocked"
    assert state.source_artifact_ids == ("platform:blocked", "platform:ready")
    assert state.blocker_reasons == ("RF ride-height coverage is incomplete.",)


def test_projection_cache_is_bounded_and_marks_warm_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    service.clear_engineering_awareness_cache()
    built: list[str] = []
    monkeypatch.setattr(service, "_cache_key", lambda run_id, session_id, db_path: ("v", run_id, session_id))
    monkeypatch.setattr(
        service,
        "build_run_intelligence",
        lambda run_id, session_id=None, db_path=None: built.append(run_id) or object(),
    )
    monkeypatch.setattr(service, "_build_projection", lambda bundle, started: _projection("run-a"))
    cold = service.build_engineering_awareness_projection("run-a")
    warm = service.build_engineering_awareness_projection("run-a")
    assert cold.cache_state == "cold"
    assert warm.cache_state == "warm"
    assert built == ["run-a"]
    assert warm.request_identity == cold.request_identity


def test_engineering_awareness_route_is_registered_and_stays_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.routes_engineering_awareness as route

    monkeypatch.setattr(
        route,
        "build_engineering_awareness_projection",
        lambda run_id, session_id=None, refresh=False: _projection(run_id),
    )
    response = TestClient(app).get("/api/runs/run-a/engineering-awareness")
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run-a"
    assert payload["raw_trace_included"] is False
    assert "trace" not in payload
    assert payload["authority"] == "observation_only"
    assert {
        "authority_state",
        "setup_authorized",
        "current_mission",
        "setup_leverage_states",
    }.isdisjoint(payload)


def test_engineering_awareness_route_fails_closed_on_mirrored_policy_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import api.routes_engineering_awareness as route

    hostile = _projection().model_dump(mode="json")
    hostile["setup_authorized"] = True
    hostile["current_mission"] = {
        "instruction": "Increase front spring rate.",
        "setup_authorized": True,
    }
    hostile["expected_vs_observed"] = [
        {
            "workflow_id": "workflow-hostile",
            "control_key": "front_spring",
            "metric": "center phase time",
            "phase": "center",
            "mechanism_state": "supported",
            "control_response": "matched",
            "mechanism_reason": "Observed mechanism response.",
            "control_response_reason": "Observed control response.",
            "policy_verdict": "keep",
            "policy_reason": "Keep this setup change.",
        }
    ]
    monkeypatch.setattr(
        route,
        "build_engineering_awareness_projection",
        lambda run_id, session_id=None, refresh=False: hostile,
    )

    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/runs/run-a/engineering-awareness"
    )
    assert response.status_code == 500


def test_frontend_awareness_is_stale_safe_and_uses_existing_surfaces() -> None:
    root = Path(__file__).resolve().parents[1]
    panel = (root / "ui/src/components/EngineeringAwarenessPanel.tsx").read_text(encoding="utf-8")
    types = (root / "ui/src/types/engineeringAwareness.ts").read_text(encoding="utf-8")
    assert "sequence !== requestSequence.current" in panel
    assert "response.run_id !== requestedRunId" in panel
    assert "response.request_identity.run_id !== requestedRunId" in panel
    assert "response.session_id !== requestedSessionId" in panel
    assert "response.request_identity.session_id !== requestedSessionId" in panel
    assert "focusEvidence({" in panel
    assert 'learning ? <>' in panel
    assert 'className="engineering-awareness__systems"' in panel
    assert '<span>Current blocker</span>' in panel
    assert '<span>Evidence boundary</span>' in panel
    for authority_read in (
        "projection.setup_authorized",
        "projection.authority_state",
        "projection.current_mission",
        "projection.setup_leverage_states",
        "item.policy_verdict",
        "item.policy_reason",
    ):
        assert authority_read not in panel
    for removed_contract in (
        "setup_authorized",
        "authority_state",
        "current_mission",
        "setup_leverage_states",
        "policy_verdict",
        "policy_reason",
    ):
        assert removed_contract not in types
    expected = {
        "OverviewTab.tsx": 'surface="overview"',
        "LapsTab.tsx": 'surface="laps"',
        "PlatformTab.tsx": 'surface="platform"',
        "SetupTab.tsx": 'surface="setup"',
        "CompareTab.tsx": 'surface="compare"',
        "EngineerTab.tsx": 'surface="engineer"',
    }
    for filename, marker in expected.items():
        source = (root / "ui/src/tabs" / filename).read_text(encoding="utf-8")
        assert marker in source
    app_source = (root / "ui/src/App.tsx").read_text(encoding="utf-8")
    assert "engineering-awareness" not in app_source
