from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from racelab_engine.analysis.observation_intelligence import (
    adapt_event_mechanism_observations,
    adapt_p3_report_observations,
    build_driver_repeatability_signature,
    build_opportunity_signatures,
    build_same_setup_anomaly_envelopes,
)
from racelab_engine.models.engineering import EngineGate, EngineeringConclusion
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.observation_intelligence import (
    MechanismKind,
    ObservationStatus,
    OpportunitySignature,
)
from racelab_engine.services.observation_intelligence_service import (
    build_observation_intelligence,
)
from racelab_engine.services.import_service import TelemetryArtifactIdentityError


def _lap(
    number: int,
    *,
    run_id: str = "run-a",
    useful: bool = True,
    tags: list[str] | None = None,
) -> LapSummary:
    return LapSummary(
        lap_id=f"{run_id}:{number}",
        run_id=run_id,
        lap_number=number,
        lap_type="flying" if useful else "cooldown",
        is_complete=True,
        is_useful=useful,
        lap_time=50.0,
        classification_tags=tags or [],
    )


def _rows(
    *,
    step_pct: float = 0.25,
    opportunity: bool = False,
    anomaly_window: tuple[float, float] | None = None,
    anomaly_point: float | None = None,
    driver_variation: bool = False,
    include_session_time: bool = True,
    include_throttle: bool = True,
) -> list[dict[str, float | int | str]]:
    output: list[dict[str, float | int | str]] = []
    steps = round(100.0 / step_pct)
    for lap_number in (1, 2, 3):
        for index in range(steps + 1):
            pct = round(index * step_pct, 6)
            extra = 0.0
            if opportunity and lap_number in {2, 3}:
                extra = max(0.0, min(10.0, pct - 40.0)) * 0.04
            anomaly = 0.0
            if lap_number == 3 and anomaly_window is not None:
                anomaly = 10.0 if anomaly_window[0] <= pct <= anomaly_window[1] else 0.0
            if lap_number == 3 and anomaly_point is not None and abs(pct - anomaly_point) < 1e-9:
                anomaly = 10.0
            throttle = (
                45.0
                if driver_variation and lap_number == 3 and 60.0 <= pct <= 70.0
                else 20.0
            )
            row: dict[str, float | int | str] = {
                "run_id": "run-a",
                "lap": lap_number,
                "lap_dist_pct_100": pct,
                "speed_mph": 150.0,
                "brake_pct": 0.0,
                "steering_deg": 0.0,
                "test_signal": anomaly,
                "engineering_phase": (
                    "center" if 30.0 <= pct <= 70.0 else "straight"
                ),
            }
            if include_session_time:
                row["session_time"] = lap_number * 1_000.0 + pct * 0.5 + extra
            if include_throttle:
                row["throttle_pct"] = throttle
            output.append(row)
    return output


def _laps() -> list[LapSummary]:
    return [_lap(1), _lap(2), _lap(3)]


def test_repeatable_opportunity_uses_physical_position_and_distinct_laps() -> None:
    report = build_opportunity_signatures(
        _rows(opportunity=True),
        _laps(),
        run_id="run-a",
        setup_id="setup-a",
    )

    assert report.status is ObservationStatus.READY
    signature = report.signatures[0]
    assert signature.authority == "observation_only"
    assert signature.observational_label == "repeatable_same_setup_opportunity"
    assert signature.phase == "center"
    assert signature.lap_pct_start <= 41.0
    assert signature.lap_pct_end >= 49.0
    assert signature.repetition_count == 2
    assert {citation.lap_number for citation in signature.citations} == {2, 3}
    assert all(citation.run_id == "run-a" for citation in signature.citations)
    assert signature.median_opportunity_s > signature.empirical_noise_s


def test_repeatable_opportunity_below_empirical_noise_is_withheld() -> None:
    rows: list[dict[str, float | int | str]] = []
    segment_durations = (0.125, 0.126, 0.126, 0.145, 0.145)
    for lap_number, duration in enumerate(segment_durations, start=1):
        for index in range(401):
            pct = index * 0.25
            rows.append(
                {
                    "run_id": "run-a",
                    "lap": lap_number,
                    "lap_dist_pct_100": pct,
                    "session_time": lap_number * 1_000.0 + index * duration,
                    "speed_mph": 150.0,
                    "engineering_phase": "center",
                }
            )

    report = build_opportunity_signatures(
        rows,
        [_lap(number) for number in range(1, 6)],
        run_id="run-a",
        setup_id="setup-a",
    )

    assert report.status is ObservationStatus.NO_FINDING
    assert report.signatures == ()


def test_junk_lap_cannot_create_or_cite_an_opportunity() -> None:
    rows = _rows(opportunity=False)
    for row in list(rows):
        if row["lap"] == 3:
            junk = dict(row)
            junk["lap"] = 4
            pct = float(junk["lap_dist_pct_100"])
            junk["session_time"] = 4_000.0 + pct * 0.5 + max(0.0, min(10.0, pct - 40.0))
            rows.append(junk)
    laps = [*_laps(), _lap(4, useful=False, tags=["COOLDOWN"])]

    report = build_opportunity_signatures(
        rows, laps, run_id="run-a", setup_id="setup-a"
    )

    assert report.status is ObservationStatus.NO_FINDING
    assert report.eligible_lap_numbers == (1, 2, 3)
    assert not report.signatures


@pytest.mark.parametrize(
    ("builder", "kwargs", "expected_fragment"),
    [
        (
            build_opportunity_signatures,
            {"rows": _rows(include_session_time=False), "laps": _laps()},
            "session_time",
        ),
        (
            build_same_setup_anomaly_envelopes,
            {"rows": _rows(), "laps": _laps(), "channels": ("missing_signal",)},
            "missing_signal",
        ),
        (
            build_driver_repeatability_signature,
            {"rows": _rows(include_throttle=False), "laps": _laps()},
            "throttle_pct",
        ),
    ],
)
def test_missing_required_channels_fail_closed(builder, kwargs, expected_fragment: str) -> None:
    report = builder(**kwargs, run_id="run-a", setup_id="setup-a")

    assert report.status is ObservationStatus.BLOCKED
    assert expected_fragment in " ".join(report.blocker_reasons)


@pytest.mark.parametrize(
    "builder,extra",
    [
        (build_opportunity_signatures, {}),
        (build_same_setup_anomaly_envelopes, {"channels": ("test_signal",)}),
        (build_driver_repeatability_signature, {}),
    ],
)
def test_fewer_than_three_eligible_laps_are_blocked(builder, extra) -> None:
    report = builder(
        _rows(),
        [_lap(1), _lap(2)],
        run_id="run-a",
        setup_id="setup-a",
        **extra,
    )

    assert report.status is ObservationStatus.BLOCKED
    assert "At least three eligible same-setup laps" in " ".join(report.blocker_reasons)


@pytest.mark.parametrize(
    "builder,extra",
    [
        (build_opportunity_signatures, {}),
        (build_same_setup_anomaly_envelopes, {"channels": ("test_signal",)}),
        (build_driver_repeatability_signature, {}),
    ],
)
def test_cross_run_lap_or_row_identity_blocks_the_whole_scope(builder, extra) -> None:
    laps = [_lap(1), _lap(2), _lap(3, run_id="run-b")]
    report = builder(
        _rows(),
        laps,
        run_id="run-a",
        setup_id="setup-a",
        **extra,
    )

    assert report.status is ObservationStatus.BLOCKED
    assert "different run" in " ".join(report.blocker_reasons)


def test_sustained_anomaly_is_reported_but_one_point_spike_is_not() -> None:
    sustained = build_same_setup_anomaly_envelopes(
        _rows(anomaly_window=(30.0, 40.0)),
        _laps(),
        run_id="run-a",
        setup_id="setup-a",
        channels=("test_signal",),
        minimum_absolute_deviation={"test_signal": 1.0},
    )
    spike = build_same_setup_anomaly_envelopes(
        _rows(anomaly_point=35.0),
        _laps(),
        run_id="run-a",
        setup_id="setup-a",
        channels=("test_signal",),
        minimum_absolute_deviation={"test_signal": 1.0},
    )

    assert sustained.status is ObservationStatus.READY
    assert len(sustained.anomalies) == 1
    anomaly = sustained.anomalies[0]
    assert anomaly.lap_number == 3
    assert anomaly.reference_lap_numbers == (1, 2)
    assert anomaly.direction == "above_envelope"
    assert anomaly.lap_pct_end - anomaly.lap_pct_start >= 0.75
    assert spike.status is ObservationStatus.NO_FINDING
    assert not spike.anomalies


def test_anomaly_window_is_sample_rate_invariant() -> None:
    common = {
        "laps": _laps(),
        "run_id": "run-a",
        "setup_id": "setup-a",
        "channels": ("test_signal",),
        "minimum_absolute_deviation": {"test_signal": 1.0},
    }
    dense = build_same_setup_anomaly_envelopes(
        _rows(step_pct=0.1, anomaly_window=(30.0, 40.0)), **common
    )
    sparse = build_same_setup_anomaly_envelopes(
        _rows(step_pct=0.5, anomaly_window=(30.0, 40.0)), **common
    )

    dense_finding = dense.anomalies[0]
    sparse_finding = sparse.anomalies[0]
    assert (
        dense_finding.lap_pct_start,
        dense_finding.lap_pct_end,
        dense_finding.phase,
        dense_finding.direction,
    ) == (
        sparse_finding.lap_pct_start,
        sparse_finding.lap_pct_end,
        sparse_finding.phase,
        sparse_finding.direction,
    )
    assert dense_finding.aligned_bin_count == sparse_finding.aligned_bin_count
    assert dense_finding.telemetry_sample_count != sparse_finding.telemetry_sample_count


def test_balanced_bimodal_cohort_is_withheld_as_an_unresolved_context_split() -> None:
    rows: list[dict[str, float | int | str]] = []
    for lap_number in (1, 2, 3, 4):
        for index in range(401):
            pct = index * 0.25
            rows.append({
                "run_id": "run-a",
                "lap": lap_number,
                "lap_dist_pct_100": pct,
                "session_time": lap_number * 1_000.0 + pct * 0.5,
                "test_signal": (
                    10.0
                    if lap_number in {3, 4} and 30.0 <= pct <= 40.0
                    else 0.0
                ),
                "engineering_phase": "center",
            })

    report = build_same_setup_anomaly_envelopes(
        rows,
        [_lap(1), _lap(2), _lap(3), _lap(4)],
        run_id="run-a",
        setup_id="setup-a",
        channels=("test_signal",),
        minimum_absolute_deviation={"test_signal": 1.0},
    )

    assert report.status is ObservationStatus.BLOCKED
    assert report.anomalies == ()
    blocker_text = " ".join(report.blocker_reasons)
    assert "Reciprocal high-frequency" in blocker_text
    assert "unresolved context split" in blocker_text


def test_driver_repeatability_emits_coaching_only_and_no_setup_authority() -> None:
    report = build_driver_repeatability_signature(
        _rows(driver_variation=True),
        _laps(),
        run_id="run-a",
        setup_id="setup-a",
    )

    assert report.status is ObservationStatus.READY
    assert report.authority == "driver_coaching_only"
    assert report.focus is not None
    assert report.focus.channel == "throttle_pct"
    assert report.focus.setup_authorized is False
    assert len(report.focus.citations) == 3
    assert "without changing setup" in report.focus.instruction
    payload = report.model_dump()
    assert "proposed_value" not in str(payload)
    assert "probability" not in str(payload)


def test_driver_focus_is_sample_rate_invariant() -> None:
    dense = build_driver_repeatability_signature(
        _rows(step_pct=0.1, driver_variation=True),
        _laps(),
        run_id="run-a",
        setup_id="setup-a",
    )
    sparse = build_driver_repeatability_signature(
        _rows(step_pct=0.5, driver_variation=True),
        _laps(),
        run_id="run-a",
        setup_id="setup-a",
    )

    assert dense.focus is not None and sparse.focus is not None
    assert (
        dense.focus.phase,
        dense.focus.channel,
        dense.focus.lap_pct_start,
        dense.focus.lap_pct_end,
    ) == (
        sparse.focus.phase,
        sparse.focus.channel,
        sparse.focus.lap_pct_start,
        sparse.focus.lap_pct_end,
    )


def test_driver_repeatability_fails_closed_on_95_percent_aligned_coverage() -> None:
    rows = _rows()
    for row in rows:
        if row["lap"] == 3 and float(row["lap_dist_pct_100"]) > 95.0:
            row.pop("throttle_pct", None)

    report = build_driver_repeatability_signature(
        rows,
        _laps(),
        run_id="run-a",
        setup_id="setup-a",
    )

    assert report.status is ObservationStatus.BLOCKED
    assert report.focus is None
    blocker_text = " ".join(report.blocker_reasons)
    assert "complete common physical-position grid" in blocker_text
    assert "lap 3 throttle_pct 95%" in blocker_text


def test_qualified_event_becomes_typed_observation_without_action_text() -> None:
    event = TelemetryEvent(
        event_id="brake-1",
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
        evidence_json={
            "sample_count": 40,
            "summary": "Brake response repeated; move the control to 52%.",
            "evidence": ["Set the brake control to 52% now."],
        },
        related_setup_keys=["front_brake_bias_percent"],
        recommended_actions=["Move brake bias to 52%."],
    )

    report = adapt_event_mechanism_observations(
        [event], _laps(), run_id="run-a", setup_id="setup-a"
    )

    assert report.status is ObservationStatus.READY
    observation = report.observations[0]
    assert observation.mechanism is MechanismKind.BRAKING_RESPONSE
    assert observation.qualified is True
    assert observation.citations[0].event_id == "brake-1"
    payload = observation.model_dump()
    assert "52%" not in str(payload)
    assert "Brake response repeated" not in str(payload)
    assert "related_setup_keys" not in payload


def test_valid_for_tuning_event_with_zero_confidence_is_incoherent_and_blocked() -> None:
    event = TelemetryEvent(
        event_id="brake-zero-confidence",
        run_id="run-a",
        lap_number=2,
        event_type="braking_efficiency",
        event_subtype="threshold_braking",
        lap_pct_start=20.0,
        lap_pct_end=22.0,
        lap_pct_peak=21.0,
        confidence_score=0.0,
        valid_for_tuning=True,
        evidence_state=EvidenceState.CALCULATED,
        source_channels=["brake_pct", "long_accel"],
        blocker_reasons=[],
    )

    report = adapt_event_mechanism_observations(
        [event], _laps(), run_id="run-a", setup_id="setup-a"
    )

    assert report.status is ObservationStatus.BLOCKED
    observation = report.observations[0]
    assert observation.qualified is False
    assert observation.citations == ()
    assert "no positive confidence" in " ".join(observation.blocker_reasons)


def test_unqualified_or_cross_run_events_never_leak_citations() -> None:
    event = TelemetryEvent(
        event_id="wrong-run",
        run_id="run-b",
        lap_number=2,
        event_type="platform_balance",
        lap_pct_peak=50.0,
        valid_for_tuning=True,
        evidence_state=EvidenceState.CALCULATED,
        source_channels=["speed_mph"],
        blocker_reasons=[],
    )

    report = adapt_event_mechanism_observations(
        [event], _laps(), run_id="run-a", setup_id="setup-a"
    )

    assert report.status is ObservationStatus.BLOCKED
    assert not report.observations
    assert "different run" in " ".join(report.blocker_reasons)


def test_p3_adapter_discards_the_producers_setup_recommendation() -> None:
    report = SimpleNamespace(
        gate=EngineGate(contract_key="braking_efficiency", eligible=True, confidence_cap=0.8),
        conclusions=[
            EngineeringConclusion(
                key="braking_phase_metrics",
                summary="Position-aligned braking response was calculated.",
                evidence_state=EvidenceState.CALCULATED,
                confidence_score=0.8,
                source_channels=["brake_pct", "long_accel"],
                supporting_evidence=["Three eligible laps repeated the response."],
                recommendation="Move front brake bias to 52%.",
            )
        ],
    )

    adapted = adapt_p3_report_observations(
        report,
        _laps(),
        run_id="run-a",
        setup_id="setup-a",
        lap_number=2,
        phase="threshold_braking",
        lap_pct_start=20.0,
        lap_pct_end=22.0,
        lap_pct_peak=21.0,
        telemetry_sample_count=40,
    )

    assert adapted.status is ObservationStatus.READY
    assert "52%" not in str(adapted.model_dump())
    assert adapted.observations[0].repetition_count == 1
    assert len({item.lap_number for item in adapted.observations[0].citations}) == 1


def test_models_forbid_setup_targets_and_probabilities() -> None:
    source = build_opportunity_signatures(
        _rows(opportunity=True), _laps(), run_id="run-a", setup_id="setup-a"
    ).signatures[0]
    payload = source.model_dump()
    payload["proposed_setup_value"] = 52.0
    payload["probability"] = 0.9

    with pytest.raises(ValidationError):
        OpportunitySignature.model_validate(payload)

    below_noise = source.model_dump()
    below_noise["empirical_noise_s"] = below_noise["median_opportunity_s"]
    with pytest.raises(ValidationError, match="noise floor"):
        OpportunitySignature.model_validate(below_noise)


def test_wrapper_rejects_a_run_outside_supplied_session_before_repository_read() -> None:
    class FailIfRead:
        def get_overview(self, _run_id: str):
            raise AssertionError("repository must not be read for an invalid session scope")

    report = build_observation_intelligence(
        "run-a", session_run_ids=("run-b",), repository=FailIfRead()
    )

    assert report.run_id == "run-a"
    assert report.opportunity_signatures.status is ObservationStatus.BLOCKED
    assert "not part of the supplied session" in " ".join(report.blocker_reasons)


def test_wrapper_fails_closed_when_telemetry_artifact_identity_is_unverifiable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overview = SimpleNamespace(
        run_id="run-a",
        session=SimpleNamespace(run_id="run-a"),
        warnings=[],
        setup_snapshot=SimpleNamespace(run_id="run-a", setup_id="setup-a"),
        laps=_laps(),
        events=[],
    )

    class Repository:
        def get_overview(self, _run_id: str):
            return overview

    def fail_identity(*_args, **_kwargs):
        raise TelemetryArtifactIdentityError(
            "Telemetry samples are unavailable until the original file is re-imported."
        )

    monkeypatch.setattr(
        "racelab_engine.services.observation_intelligence_service.read_telemetry_rows",
        fail_identity,
    )

    report = build_observation_intelligence("run-a", repository=Repository())

    assert report.opportunity_signatures.status is ObservationStatus.BLOCKED
    assert report.anomaly_envelopes.status is ObservationStatus.BLOCKED
    assert report.driver_repeatability.status is ObservationStatus.BLOCKED
    assert "Telemetry artifacts could not be verified" in " ".join(
        report.blocker_reasons
    )
