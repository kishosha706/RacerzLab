from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from racelab_engine.analysis.observation_intelligence import adapt_event_mechanism_observations
from racelab_engine.models.engineering import EngineGate, EngineeringConclusion
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.observation_intelligence import MechanismKind, ObservationStatus
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services import p3_observation_bridge as bridge
from racelab_engine.services import observation_intelligence_service as observation_service
from racelab_engine.services.import_service import TelemetryArtifactIdentityError


def _lap(number: int, lap_time: float) -> LapSummary:
    return LapSummary(
        lap_id=f"run-a:{number}",
        run_id="run-a",
        lap_number=number,
        lap_type="flying",
        is_complete=True,
        is_useful=True,
        lap_time=lap_time,
    )


def _rows() -> list[dict[str, float | int | str]]:
    rows: list[dict[str, float | int | str]] = []
    tick = 0
    for number in (1, 2, 3):
        for index in range(41):
            position = index * 2.5
            rows.append({
                "run_id": "run-a",
                "lap": number,
                "lap_dist_pct_100": position,
                "lap_dist_pct": position / 100.0,
                "engineering_phase": "straight",
                "session_tick": tick,
                "session_time": float(tick),
                "brake_pct": 60.0,
                "lf_pressure": 28.0,
                "lf_shock_vel_in_s": 1.0,
                "rpm": 7_000.0,
                "steering_deg": 1.0,
                "yaw_rate": 0.1,
            })
            tick += 1
    return rows


def _report(
    contract_key: str,
    conclusion_key: str,
    source_channel: str,
    **extra,
):
    return SimpleNamespace(
        gate=EngineGate(
            contract_key=contract_key,
            eligible=True,
            confidence_cap=0.8,
        ),
        conclusions=[
            EngineeringConclusion(
                key=conclusion_key,
                summary=f"Qualified {conclusion_key} observation.",
                evidence_state=EvidenceState.CALCULATED,
                confidence_score=0.8,
                source_channels=["lap_dist_pct_100", source_channel],
                supporting_evidence=["The deterministic producer qualified this evidence."],
                recommendation="Move a setup control to 52%.",
            )
        ],
        phases=["straight"],
        **extra,
    )


def test_bridge_calls_each_missing_producer_once_and_preserves_paired_laps(
    monkeypatch,
) -> None:
    brake = _report(
        "braking_efficiency_dynamic_balance",
        "braking_phase_metrics",
        "brake_pct",
        metrics=SimpleNamespace(incipient_lock_lap_pct=50.0),
    )
    tire = _report(
        "tire_state_energy",
        "lf_tire_state",
        "lf_pressure",
        working_history_laps=3,
    )
    damper = _report(
        "damper_suspension_response",
        "lf_damper_response",
        "lf_shock_vel_in_s",
    )
    powertrain = _report(
        "powertrain_gearing",
        "powertrain_phase_metrics",
        "rpm",
        context_diagnostics=SimpleNamespace(comparable_laps=[1, 2, 3]),
    )
    driver = _report(
        "driver_input_racing_line_efficiency",
        "driver_phase_metrics",
        "steering_deg",
    )
    rotation = _report(
        "corner_balance_rotation",
        "rotation_phase_metrics",
        "yaw_rate",
    )
    producer_mocks = {
        "analyze_braking_efficiency": Mock(return_value=brake),
        "analyze_tire_state": Mock(return_value=tire),
        "analyze_damper_response": Mock(return_value=damper),
        "analyze_powertrain_gearing": Mock(return_value=powertrain),
    }
    for name, producer in producer_mocks.items():
        monkeypatch.setattr(bridge, name, producer)
    certificates = {
        number: SimpleNamespace(
            is_clear_for_analysis=True,
            confidence_cap=1.0,
            status="pass",
        )
        for number in (1, 2, 3)
    }
    monkeypatch.setattr(
        bridge,
        "_cohort_integrity",
        lambda *_args, **_kwargs: (True, 1.0, certificates),
    )
    alignment = SimpleNamespace(
        grid_pct=[0.0, 50.0, 100.0],
        alignment=[
            SimpleNamespace(is_gap=False, aligned_test_pct=position)
            for position in (0.0, 50.0, 100.0)
        ],
    )
    monkeypatch.setattr(bridge, "analyze_time_alignment", Mock(return_value=alignment))
    monkeypatch.setattr(
        bridge,
        "comparison_integrity_gate",
        lambda *_args: (True, 1.0, []),
    )
    phase_producer = Mock(return_value=SimpleNamespace(
        driver_line=driver,
        corner_rotation=rotation,
    ))
    monkeypatch.setattr(bridge, "analyze_phase_engineering_systems", phase_producer)

    report = bridge.build_p3_mechanism_observations(
        _rows(),
        [_lap(1, 50.0), _lap(2, 49.0), _lap(3, 53.0)],
        run_id="run-a",
        setup_id="setup-a",
        telemetry_rate_hz=1.0,
        preferred_lap_number=2,
    )

    assert report.status is ObservationStatus.READY
    qualified = [item for item in report.observations if item.qualified]
    assert {item.mechanism for item in qualified} == {
        MechanismKind.BRAKING_RESPONSE,
        MechanismKind.TIRE_STATE,
        MechanismKind.DAMPER_RESPONSE,
        MechanismKind.POWERTRAIN_RESPONSE,
        MechanismKind.DRIVER_EXECUTION,
        MechanismKind.CORNER_ROTATION,
    }
    for producer in producer_mocks.values():
        assert producer.call_count == 1
    assert phase_producer.call_count == 1
    assert "52%" not in str(report.model_dump())
    paired = [
        item
        for item in qualified
        if item.mechanism in {
            MechanismKind.DRIVER_EXECUTION,
            MechanismKind.CORNER_ROTATION,
        }
    ]
    assert all({citation.lap_number for citation in item.citations} == {1, 2} for item in paired)
    assert all(item.repetition_count == 2 for item in paired)
    assert all(item.telemetry_sample_count == 82 for item in paired)
    assert all(
        citation.telemetry_sample_count == 41
        for item in paired
        for citation in item.citations
    )
    single = [item for item in qualified if item not in paired]
    assert all({citation.lap_number for citation in item.citations} == {2} for item in single)
    assert all(item.telemetry_sample_count == 41 for item in single)
    assert all(item.citations[0].telemetry_sample_count == 41 for item in single)
    assert all(item.authority == "observation_only" for item in qualified)


def test_missing_p3_channels_fail_closed_without_citations() -> None:
    report = bridge.build_p3_mechanism_observations(
        _rows(),
        [_lap(1, 50.0), _lap(2, 49.0), _lap(3, 53.0)],
        run_id="run-a",
        setup_id="setup-a",
        telemetry_rate_hz=1.0,
        preferred_lap_number=2,
    )

    assert report.status is ObservationStatus.BLOCKED
    assert not any(item.qualified for item in report.observations)
    assert not any(item.citations for item in report.observations)
    assert {
        item.mechanism for item in report.observations
    } == {
        MechanismKind.BRAKING_RESPONSE,
        MechanismKind.TIRE_STATE,
        MechanismKind.DAMPER_RESPONSE,
        MechanismKind.POWERTRAIN_RESPONSE,
        MechanismKind.DRIVER_EXECUTION,
        MechanismKind.CORNER_ROTATION,
    }
    assert all(item.blocker_reasons for item in report.observations)


def test_cross_run_rows_block_before_any_producer_is_called(monkeypatch) -> None:
    producer = Mock(side_effect=AssertionError("producer must not run"))
    monkeypatch.setattr(bridge, "analyze_braking_efficiency", producer)
    rows = _rows()
    rows[0]["run_id"] = "run-b"

    report = bridge.build_p3_mechanism_observations(
        rows,
        [_lap(1, 50.0), _lap(2, 49.0), _lap(3, 53.0)],
        run_id="run-a",
        setup_id="setup-a",
        telemetry_rate_hz=1.0,
    )

    assert report.status is ObservationStatus.BLOCKED
    assert "different run" in " ".join(report.blocker_reasons)
    producer.assert_not_called()


def test_artifact_identity_failure_invalidates_persisted_event_observations(
    monkeypatch,
) -> None:
    laps = [_lap(1, 50.0), _lap(2, 49.0), _lap(3, 53.0)]
    overview = RunOverview(
        run_id="run-a",
        session=SessionSummary(run_id="run-a", telemetry_rate_hz=60),
        best_useful_lap=laps[1],
        laps=laps,
        events=[
            TelemetryEvent(
                event_id="brake-event",
                run_id="run-a",
                lap_number=2,
                event_type="braking_efficiency",
                event_subtype="threshold_braking",
                lap_pct_start=20.0,
                lap_pct_end=22.0,
                lap_pct_peak=21.0,
                confidence_score=0.8,
                valid_for_tuning=True,
                evidence_state=EvidenceState.CALCULATED,
                source_channels=["brake_pct", "long_accel"],
                blocker_reasons=[],
            )
        ],
        setup_snapshot=SetupSnapshot(
            setup_id="setup-a",
            run_id="run-a",
        ),
    )

    class Repository:
        def get_overview(self, run_id: str):
            assert run_id == "run-a"
            return overview

    def fail_read(*_args, **_kwargs):
        raise TelemetryArtifactIdentityError("cache owner mismatch")

    monkeypatch.setattr(observation_service, "read_telemetry_rows", fail_read)

    report = observation_service.build_observation_intelligence(
        "run-a",
        repository=Repository(),
    )

    assert report.mechanism_observations.status is ObservationStatus.BLOCKED
    assert not report.mechanism_observations.observations
    assert "cache owner mismatch" in " ".join(report.mechanism_observations.blocker_reasons)


def test_persisted_event_requires_coobserved_source_channels_in_exact_window() -> None:
    laps = [_lap(1, 50.0), _lap(2, 49.0), _lap(3, 53.0)]
    event = TelemetryEvent(
        event_id="brake-event",
        run_id="run-a",
        lap_number=2,
        event_type="braking_efficiency",
        event_subtype="threshold_braking",
        lap_pct_start=20.0,
        lap_pct_end=22.0,
        lap_pct_peak=21.0,
        confidence_score=0.8,
        valid_for_tuning=True,
        evidence_state=EvidenceState.CALCULATED,
        source_channels=["brake_pct", "long_accel"],
        blocker_reasons=[],
    )
    persisted = adapt_event_mechanism_observations(
        [event],
        laps,
        run_id="run-a",
        setup_id="setup-a",
    )
    rows = [
        {
            "run_id": "run-a",
            "lap": 2,
            "lap_dist_pct_100": 21.0,
            "brake_pct": 60.0,
            "long_accel": -8.0,
        },
        {
            "run_id": "run-a",
            "lap": 2,
            "lap_dist_pct_100": 21.5,
            "brake_pct": 55.0,
            "long_accel": None,
        },
    ]

    qualified = bridge.revalidate_event_mechanism_observations(persisted, rows)
    blocked = bridge.revalidate_event_mechanism_observations(
        persisted,
        [{**row, "long_accel": None} for row in rows],
    )

    assert qualified.status is ObservationStatus.READY
    assert qualified.observations[0].telemetry_sample_count == 1
    assert qualified.observations[0].citations[0].telemetry_sample_count == 1
    assert blocked.status is ObservationStatus.BLOCKED
    assert not blocked.observations[0].citations
    assert "long_accel" in " ".join(blocked.observations[0].blocker_reasons)


def test_p3_citation_fails_closed_when_claimed_channels_only_coexist_once(
    monkeypatch,
) -> None:
    brake = _report(
        "braking_efficiency_dynamic_balance",
        "braking_phase_metrics",
        "brake_pct",
        metrics=SimpleNamespace(incipient_lock_lap_pct=50.0),
    )
    producer = Mock(return_value=brake)
    monkeypatch.setattr(bridge, "analyze_braking_efficiency", producer)
    certificates = {
        number: SimpleNamespace(
            is_clear_for_analysis=True,
            confidence_cap=1.0,
            status="pass",
        )
        for number in (1, 2, 3)
    }
    monkeypatch.setattr(
        bridge,
        "_cohort_integrity",
        lambda *_args, **_kwargs: (True, 1.0, certificates),
    )
    rows = _rows()
    for row in rows:
        if row["lap"] == 2 and row["lap_dist_pct_100"] != 50.0:
            row["brake_pct"] = None  # type: ignore[assignment]

    report = bridge.build_p3_mechanism_observations(
        rows,
        [_lap(1, 50.0), _lap(2, 49.0), _lap(3, 53.0)],
        run_id="run-a",
        setup_id="setup-a",
        telemetry_rate_hz=1.0,
        preferred_lap_number=2,
        existing_mechanisms=tuple(
            mechanism
            for mechanism in MechanismKind
            if mechanism is not MechanismKind.BRAKING_RESPONSE
        ),
    )

    assert report.status is ObservationStatus.BLOCKED
    observation = report.observations[0]
    assert observation.qualified is False
    assert observation.telemetry_sample_count == 0
    assert observation.citations == ()
    assert "1/41" in " ".join(observation.blocker_reasons)
    assert "90%" in " ".join(observation.blocker_reasons)
