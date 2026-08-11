from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from racelab_engine.analysis.observation_intelligence import (
    adapt_controlled_producer_observations,
    adapt_event_mechanism_observations,
)
from racelab_engine.models.engineering import EngineGate, EngineeringConclusion
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.observation_intelligence import (
    MechanismKind,
    ObservationStatus,
    ProducerArtifactScope,
)
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services import p3_observation_bridge as bridge
from racelab_engine.services import observation_intelligence_service as observation_service
from racelab_engine.services.run_intelligence_service import _observation_hypotheses
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
    platform = _report(
        "aero_platform_window",
        "platform_phase_metrics",
        "lf_shock_vel_in_s",
    )
    stint = _report(
        "stint_tire_strategy",
        "stint_pace_drift",
        "rpm",
        historical_segment_laps=[1, 2, 3],
        active_segment_laps=[1, 2, 3],
        pace_drift=SimpleNamespace(authority_blocker_reasons=[]),
    )
    producer_mocks = {
        "analyze_braking_efficiency": Mock(return_value=brake),
        "analyze_tire_state": Mock(return_value=tire),
        "analyze_damper_response": Mock(return_value=damper),
        "analyze_powertrain_gearing": Mock(return_value=powertrain),
        "analyze_stint_strategy": Mock(return_value=stint),
    }
    for name, producer in producer_mocks.items():
        monkeypatch.setattr(bridge, name, producer)
    certificates = {
        number: SimpleNamespace(
            is_clear_for_analysis=True,
            confidence_cap=1.0,
            status="pass",
            conclusion=EngineeringConclusion(
                key="sim_integrity_certificate",
                summary="Simulator/data integrity certificate: pass.",
                evidence_state=EvidenceState.CALCULATED,
                confidence_score=0.9,
                source_channels=["session_tick", "session_time"],
                supporting_evidence=["Clock continuity passed."],
            ),
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
        aero_platform=platform,
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
        MechanismKind.PLATFORM_RESPONSE,
        MechanismKind.STINT_TREND,
        MechanismKind.SIM_INTEGRITY,
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
            MechanismKind.PLATFORM_RESPONSE,
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
    stint_observation = next(
        item for item in single if item.mechanism is MechanismKind.STINT_TREND
    )
    assert {citation.lap_number for citation in stint_observation.citations} == {1, 2, 3}
    selected_lap_observations = [item for item in single if item is not stint_observation]
    assert all(
        {citation.lap_number for citation in item.citations} == {2}
        for item in selected_lap_observations
    )
    assert all(item.sample_coverage == 1.0 for item in qualified)
    assert all(item.authority == "observation_only" for item in qualified)
    resistance = next(
        item
        for item in report.observations
        if item.mechanism is MechanismKind.RESISTANCE_SCRUB_LIKE
    )
    assert resistance.qualified is False
    assert "A/B/A2" in " ".join(resistance.blocker_reasons)


def test_traffic_blocked_stint_cannot_become_a_p19_cause(monkeypatch) -> None:
    blocker_reason = (
        "Nearby traffic entered the operational time-gap window; retain the pace "
        "drift as observed correlation only and do not feed it to setup authority."
    )
    stint = _report(
        "stint_tire_strategy",
        "stint_pace_drift",
        "rpm",
        historical_segment_laps=[1, 2, 3],
        active_segment_laps=[1, 2, 3],
        pace_drift=SimpleNamespace(authority_blocker_reasons=[blocker_reason]),
    )
    monkeypatch.setattr(bridge, "analyze_stint_strategy", Mock(return_value=stint))
    monkeypatch.setattr(
        bridge,
        "_cohort_integrity",
        lambda *_args, **_kwargs: (True, 1.0, {}),
    )
    existing = tuple(
        mechanism
        for mechanism in MechanismKind
        if mechanism is not MechanismKind.STINT_TREND
    )

    report = bridge.build_p3_mechanism_observations(
        _rows(),
        [_lap(1, 50.0), _lap(2, 49.0), _lap(3, 53.0)],
        run_id="run-a",
        setup_id="setup-a",
        telemetry_rate_hz=1.0,
        preferred_lap_number=2,
        existing_mechanisms=existing,
    )

    assert report.status is ObservationStatus.BLOCKED
    assert len(report.observations) == 1
    observation = report.observations[0]
    assert observation.mechanism is MechanismKind.STINT_TREND
    assert observation.qualified is False
    assert blocker_reason in observation.blocker_reasons
    assert {
        "car_distance_ahead_m",
        "car_distance_behind_m",
        "speed_mps",
    }.issubset(observation.required_channels)
    assert _observation_hypotheses(report) == ()


def test_each_missing_producer_retains_its_own_blocked_state() -> None:
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
    assert {item.mechanism for item in qualified} == {MechanismKind.SIM_INTEGRITY}
    blocked = [item for item in report.observations if not item.qualified]
    assert not any(item.citations for item in blocked)
    assert {item.mechanism for item in blocked} == {
        MechanismKind.BRAKING_RESPONSE,
        MechanismKind.TIRE_STATE,
        MechanismKind.DAMPER_RESPONSE,
        MechanismKind.POWERTRAIN_RESPONSE,
        MechanismKind.DRIVER_EXECUTION,
        MechanismKind.CORNER_ROTATION,
        MechanismKind.PLATFORM_RESPONSE,
        MechanismKind.STINT_TREND,
        MechanismKind.RESISTANCE_SCRUB_LIKE,
    }
    assert all(item.blocker_reasons for item in blocked)


def test_controlled_resistance_artifact_reaches_p19_without_setup_authority() -> None:
    report = _report(
        "relative_high_speed_resistance",
        "relative_resistance_direction",
        "speed_rate_mph_s",
        aba_confirmed=True,
    )
    scopes = tuple(
        ProducerArtifactScope(
            stage=stage,
            run_id=run_id,
            setup_id=setup_id,
            lap_number=4,
            phase="high_speed_coastdown",
            lap_pct_start=72.0,
            lap_pct_end=78.0,
            lap_pct_peak=75.0,
            telemetry_sample_count=24,
            sample_coverage=0.96,
        )
        for stage, run_id, setup_id in (
            ("A1", "run-a1", "setup-a"),
            ("B", "run-b", "setup-b"),
            ("A2", "run-a2", "setup-a"),
        )
    )

    observations = adapt_controlled_producer_observations(
        report,
        scopes,
        anchor_run_id="run-b",
        anchor_setup_id="setup-b",
        mechanism=MechanismKind.RESISTANCE_SCRUB_LIKE,
    )
    hypotheses = _observation_hypotheses(observations)

    assert observations.status is ObservationStatus.READY
    observation = observations.observations[0]
    assert observation.source_run_ids == ("run-a1", "run-b", "run-a2")
    assert {citation.run_id for citation in observation.citations} == {
        "run-a1",
        "run-b",
        "run-a2",
    }
    assert observation.sample_coverage == 0.96
    assert observation.authority == "observation_only"
    assert "52%" not in str(observation.model_dump())
    assert hypotheses[0].mechanism_key == "resistance_scrub_like"

    wrong_order = adapt_controlled_producer_observations(
        report,
        (scopes[1], scopes[0], scopes[2]),
        anchor_run_id="run-b",
        anchor_setup_id="setup-b",
        mechanism=MechanismKind.RESISTANCE_SCRUB_LIKE,
    )
    assert wrong_order.status is ObservationStatus.BLOCKED
    assert not any(item.qualified for item in wrong_order.observations)
    assert "ordered A1/B/A2" in " ".join(wrong_order.blocker_reasons)


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
    assert qualified.observations[0].sample_coverage == 0.5
    assert qualified.observations[0].citations[0].telemetry_sample_count == 1
    assert blocked.status is ObservationStatus.BLOCKED
    assert not blocked.observations[0].citations
    assert "long_accel" in " ".join(blocked.observations[0].blocker_reasons)


def test_distinct_same_kind_windows_survive_and_true_artifact_duplicates_dedupe() -> None:
    laps = [_lap(1, 50.0), _lap(2, 49.0), _lap(3, 53.0)]
    events = [
        TelemetryEvent(
            event_id=event_id,
            run_id="run-a",
            lap_number=2,
            event_type="corner_rotation",
            event_subtype="center",
            lap_pct_start=start,
            lap_pct_end=end,
            lap_pct_peak=(start + end) / 2.0,
            confidence_score=0.8,
            valid_for_tuning=True,
            evidence_state=EvidenceState.CALCULATED,
            source_channels=["yaw_rate", "steering_deg"],
            blocker_reasons=[],
        )
        for event_id, start, end in (
            ("rotation-one", 35.0, 42.0),
            ("rotation-two", 68.0, 74.0),
        )
    ]
    adapted = adapt_event_mechanism_observations(
        events,
        laps,
        run_id="run-a",
        setup_id="setup-a",
    )
    merged = bridge.merge_mechanism_observation_reports(
        "run-a",
        "setup-a",
        (adapted, adapted),
    )

    assert len(adapted.observations) == 2
    assert len(merged.observations) == 2
    assert {item.artifact_id for item in merged.observations} == {
        "event:rotation-one",
        "event:rotation-two",
    }
    assert {
        (item.lap_pct_start, item.lap_pct_end) for item in merged.observations
    } == {(35.0, 42.0), (68.0, 74.0)}

    conflicting_payload = adapted.observations[1].model_dump()
    conflicting_payload["artifact_id"] = adapted.observations[0].artifact_id
    conflicting = adapted.model_copy(
        update={
            "observations": (
                adapted.observations[0],
                type(adapted.observations[1]).model_validate(conflicting_payload),
            )
        }
    )
    conflict = bridge.merge_mechanism_observation_reports(
        "run-a",
        "setup-a",
        (adapted, conflicting),
    )
    assert conflict.status is ObservationStatus.BLOCKED
    assert not conflict.observations
    assert "conflicting observation payloads" in " ".join(conflict.blocker_reasons)


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
