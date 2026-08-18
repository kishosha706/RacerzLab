from __future__ import annotations

from copy import deepcopy
import hashlib

import pytest
from pydantic import ValidationError

from racelab_engine.analysis.qualified_clock import build_qualified_telemetry_clock
from racelab_engine.analysis.surface_disturbance_response import (
    analyze_surface_disturbance_episode,
    ordered_telemetry_content_sha256,
)
from racelab_engine.models.surface_disturbance_response import PhysicalLapScope
from racelab_engine.services.surface_disturbance_response_service import (
    SurfaceDisturbanceTelemetryInput,
    build_surface_disturbance_settling_report,
)


_CORNERS = ("lf", "rf", "lr", "rr")


def _pulse(
    rows: list[dict[str, object]],
    channel: str,
    *,
    onset: int,
    values: tuple[float, ...],
    baseline: float = 0.0,
) -> None:
    for row in rows:
        row[channel] = baseline
    for offset, value in enumerate(values):
        rows[onset + offset][channel] = baseline + value


def _episode_rows(
    lap: int,
    *,
    event_index: int = 25,
    duplicate_observed_time: bool = False,
    right_censored: bool = False,
) -> list[dict[str, object]]:
    count = 90
    rows: list[dict[str, object]] = [
        {
            "run_id": f"run-{lap}",
            "lap": lap,
            "lap_dist_pct_100": 10.0 + index * 0.02,
            "session_tick": 10_000 + lap * 1_000 + index,
            "session_time": 200.0 + lap * 10.0 + index / 60.0,
            "speed_mps": 70.0 + (index % 3 - 1) * 0.05,
            "engineering_phase": "transition",
        }
        for index in range(count)
    ]
    _pulse(
        rows,
        "vert_accel",
        onset=event_index,
        values=(0.8, 0.65, -0.38, -0.22, 0.12, 0.06, -0.025, -0.01),
    )
    _pulse(
        rows,
        "yaw_rate",
        onset=event_index + 3,
        values=(0.025, 0.055, 0.035, -0.018, -0.01, 0.004, 0.002),
        baseline=0.22,
    )
    for offset, corner in enumerate(_CORNERS):
        _pulse(
            rows,
            f"{corner}_shock_vel_in_s",
            onset=event_index + offset,
            values=(
                2.4 - offset * 0.1,
                1.8 - offset * 0.1,
                -1.1,
                -0.6,
                0.35,
                0.18,
                -0.08,
                -0.03,
            ),
        )
        _pulse(
            rows,
            f"{corner}_shock_defl_in",
            onset=event_index + offset + 1,
            values=(0.045, 0.085, 0.06, 0.025, -0.014, -0.007, 0.003, 0.001),
            baseline=1.0 + offset * 0.1,
        )
    if right_censored:
        for index in range(event_index + 3, count):
            rows[index]["yaw_rate"] = 0.25
        for index in range(event_index + 4, count):
            rows[index]["rr_shock_defl_in"] = 1.34
    if duplicate_observed_time:
        rows[event_index + 2]["session_time"] = rows[event_index + 1]["session_time"]
    return rows


def _scope(
    lap: int,
    *,
    run_id: str | None = None,
    source_file_sha256: str | None = None,
    eligible: bool = True,
) -> PhysicalLapScope:
    return PhysicalLapScope(
        run_id=run_id or f"run-{lap}",
        source_file_sha256=source_file_sha256
        or hashlib.sha256(f"recording-{lap // 10}".encode()).hexdigest(),
        source_artifact_id=f"artifact-{run_id or lap}",
        setup_id="setup-stock",
        context_id="atlanta-transition-stock",
        track_identity="atlanta-2022-oval",
        build_identity="2026.06.24.02",
        lap_number=lap,
        phase="transition",
        lap_pct_start=10.0,
        lap_pct_end=11.78,
        lap_is_complete=True,
        lap_is_eligible=eligible,
    )


def _input(
    lap: int,
    *,
    rows: list[dict[str, object]] | None = None,
    run_id: str | None = None,
    source_file_sha256: str | None = None,
    eligible: bool = True,
) -> SurfaceDisturbanceTelemetryInput:
    selected = rows or _episode_rows(lap)
    return SurfaceDisturbanceTelemetryInput(
        data=selected,
        scope=_scope(
            lap,
            run_id=run_id,
            source_file_sha256=source_file_sha256,
            eligible=eligible,
        ),
        expected_sample_rate_hz=60.0,
    )


def _codes(report: object) -> set[str]:
    return {item.code for item in report.blockers}  # type: ignore[attr-defined]


def test_repeated_physical_laps_publish_complete_measurement_only_signature() -> None:
    first_rows = _episode_rows(14)
    second_rows = _episode_rows(15, duplicate_observed_time=True)

    report = build_surface_disturbance_settling_report(
        [
            _input(14, rows=first_rows),
            _input(15, rows=second_rows),
        ]
    )

    assert report.status == "ready"
    assert report.blockers == ()
    assert report.signature is not None
    signature = report.signature
    assert signature.repetition_count == 2
    assert signature.independence_unit_ids == tuple(
        f"{episode.scope.source_file_sha256}:lap:{episode.scope.lap_number}"
        for episode in signature.episodes
    )
    assert signature.source_file_sha256s == tuple(
        dict.fromkeys(
            episode.scope.source_file_sha256 for episode in signature.episodes
        )
    )
    assert signature.telemetry_content_sha256s == tuple(
        dict.fromkeys(
            episode.telemetry_content_sha256 for episode in signature.episodes
        )
    )
    assert signature.disturbance_onset_median_lap_pct == pytest.approx(10.5)
    assert signature.disturbance_onset_span_pct == pytest.approx(0.0)
    assert signature.physical_repetition_tolerance_pct == pytest.approx(0.06)
    assert signature.median_speed_mps == pytest.approx(70.0)
    assert len(signature.aggregate_noise_floor_by_channel) == 10
    assert signature.track_input_directly_measured is False
    assert signature.nominal_vehicle_constants_used is False
    assert signature.cause_attribution_available is False
    assert signature.setup_direction_available is False

    episode = signature.episodes[1]
    assert episode.clock_primary == "session_tick"
    assert episode.clock_state == "qualified"
    assert episode.scope.phase == "transition"
    assert len(episode.corner_responses) == 4
    assert all(item.peak_abs_shock_velocity_in_s > 0 for item in episode.corner_responses)
    assert all(item.peak_abs_shock_travel_delta_in > 0 for item in episode.corner_responses)
    assert all(item.velocity_settling_duration_s is not None for item in episode.corner_responses)
    assert all(item.travel_settling_duration_s is not None for item in episode.corner_responses)
    assert episode.platform_yaw_response.observed_yaw_lag_s == pytest.approx(3 / 60)
    assert episode.platform_yaw_response.peak_platform_motion_proxy_in > 0
    assert episode.platform_yaw_response.peak_abs_yaw_rate_delta_rad_s > 0
    assert episode.platform_yaw_response.yaw_correction_count >= 1
    assert episode.platform_yaw_response.settling_right_censored is False
    assert "session_tick" in episode.clock_source_channels
    assert second_rows[27]["session_time"] == second_rows[26]["session_time"]


@pytest.mark.parametrize("missing", ["rate", "yaw", "shock_velocity", "shock_travel"])
def test_missing_clock_yaw_or_any_shock_response_is_unavailable(missing: str) -> None:
    rows = _episode_rows(20)
    expected_rate: float | None = 60.0
    if missing == "rate":
        expected_rate = None
    elif missing == "yaw":
        for row in rows:
            row.pop("yaw_rate")
    elif missing == "shock_velocity":
        for row in rows:
            row.pop("rf_shock_vel_in_s")
    else:
        for row in rows:
            row.pop("rr_shock_defl_in")

    result = analyze_surface_disturbance_episode(
        rows,
        scope=_scope(20),
        expected_sample_rate_hz=expected_rate,
    )

    assert result.status == "unavailable"
    assert result.episode is None
    assert _codes(result) & {
        "QUALIFIED_CLOCK_UNAVAILABLE",
        "REQUIRED_RESPONSE_CHANNEL_UNAVAILABLE",
    }


def test_foreign_same_length_clock_cannot_be_injected_into_the_analyzer() -> None:
    rows = _episode_rows(20)
    foreign_clock = build_qualified_telemetry_clock(
        rows,
        expected_sample_rate_hz=600.0,
    )
    assert foreign_clock.sample_count == len(rows)

    with pytest.raises(TypeError, match="unexpected keyword argument 'clock'"):
        analyze_surface_disturbance_episode(
            rows,
            scope=_scope(20),
            expected_sample_rate_hz=60.0,
            clock=foreign_clock,  # type: ignore[call-arg]
        )

    wrong_rate = analyze_surface_disturbance_episode(
        rows,
        scope=_scope(20),
        expected_sample_rate_hz=600.0,
    )
    correct_rate = analyze_surface_disturbance_episode(
        rows,
        scope=_scope(20),
        expected_sample_rate_hz=60.0,
    )
    assert wrong_rate.status == "unavailable"
    assert "QUALIFIED_CLOCK_UNAVAILABLE" in _codes(wrong_rate)
    assert correct_rate.status == "qualified"


def test_tick_discontinuity_and_junk_lap_each_fail_closed() -> None:
    rows = _episode_rows(21)
    for index in range(40, len(rows)):
        rows[index]["session_tick"] = int(rows[index]["session_tick"]) + 1
    blocked_clock = build_qualified_telemetry_clock(
        rows,
        expected_sample_rate_hz=60.0,
    )

    clock_result = analyze_surface_disturbance_episode(
        rows,
        scope=_scope(21),
        expected_sample_rate_hz=blocked_clock.tick_rate_hz,
    )
    junk_result = analyze_surface_disturbance_episode(
        _episode_rows(22),
        scope=_scope(22, eligible=False),
        expected_sample_rate_hz=60.0,
    )

    assert clock_result.status == "unavailable"
    assert "QUALIFIED_CLOCK_UNAVAILABLE" in _codes(clock_result)
    assert junk_result.status == "unavailable"
    assert "INELIGIBLE_PHYSICAL_LAP" in _codes(junk_result)


def test_one_episode_and_same_recording_lap_aliases_cannot_claim_repetition() -> None:
    one = build_surface_disturbance_settling_report([_input(30)])
    rows = _episode_rows(31)
    alias_a = deepcopy(rows)
    alias_b = deepcopy(rows)
    for row in alias_a:
        row["run_id"] = "alias-a"
    for row in alias_b:
        row["run_id"] = "alias-b"
    assert ordered_telemetry_content_sha256(alias_a) == (
        ordered_telemetry_content_sha256(alias_b)
    )
    assert len(ordered_telemetry_content_sha256(alias_a)) == 64
    aliases = build_surface_disturbance_settling_report(
        [
            _input(
                31,
                rows=alias_a,
                run_id="alias-a",
                source_file_sha256="a" * 64,
            ),
            _input(
                31,
                rows=alias_b,
                run_id="alias-b",
                source_file_sha256="b" * 64,
            ),
        ]
    )

    assert one.status == "unavailable"
    assert "INSUFFICIENT_INDEPENDENT_EPISODES" in _codes(one)
    assert aliases.status == "unavailable"
    assert {
        "DUPLICATE_TELEMETRY_CONTENT_EPISODE",
        "INSUFFICIENT_INDEPENDENT_EPISODES",
    }.issubset(_codes(aliases))


def test_verified_source_file_sha_is_primary_when_projections_differ() -> None:
    first_rows = _episode_rows(32)
    second_rows = deepcopy(first_rows)
    for row in first_rows:
        row["run_id"] = "source-alias-a"
    for row in second_rows:
        row["run_id"] = "source-alias-b"
    second_rows[10]["speed_mps"] = 70.2
    assert ordered_telemetry_content_sha256(first_rows) != (
        ordered_telemetry_content_sha256(second_rows)
    )

    report = build_surface_disturbance_settling_report(
        [
            _input(
                32,
                rows=first_rows,
                run_id="source-alias-a",
                source_file_sha256="c" * 64,
            ),
            _input(
                32,
                rows=second_rows,
                run_id="source-alias-b",
                source_file_sha256="c" * 64,
            ),
        ]
    )

    assert report.status == "unavailable"
    assert {
        "DUPLICATE_SOURCE_FILE_EPISODE",
        "INSUFFICIENT_INDEPENDENT_EPISODES",
    }.issubset(_codes(report))


def test_disturbances_must_repeat_by_physical_position_not_sample_identity() -> None:
    report = build_surface_disturbance_settling_report(
        [
            _input(40, rows=_episode_rows(40, event_index=25)),
            _input(41, rows=_episode_rows(41, event_index=42)),
        ]
    )

    assert report.status == "unavailable"
    assert report.signature is None
    assert "DISTURBANCE_POSITION_NOT_REPEATED" in _codes(report)


def test_unfinished_settling_is_right_censored_instead_of_fabricated() -> None:
    report = build_surface_disturbance_settling_report(
        [
            _input(
                50,
                rows=_episode_rows(50, right_censored=True),
            ),
            _input(
                51,
                rows=_episode_rows(51, right_censored=True),
            ),
        ]
    )

    assert report.status == "limited"
    assert report.signature is not None
    assert "SETTLING_RIGHT_CENSORED" in _codes(report)
    for episode in report.signature.episodes:
        response = episode.platform_yaw_response
        assert response.settling_right_censored is True
        assert response.yaw_settling_duration_s is None
        rr = next(item for item in episode.corner_responses if item.corner == "rr")
        assert rr.settling_right_censored is True
        assert rr.travel_settling_duration_s is None


def test_contract_rejects_setup_authority_smuggling() -> None:
    report = build_surface_disturbance_settling_report(
        [
            _input(60),
            _input(61),
        ]
    )
    assert report.signature is not None
    payload = report.signature.model_dump(mode="json")
    payload["setup_direction"] = "more rebound"

    with pytest.raises(ValidationError):
        type(report.signature).model_validate(payload)

    invalid_scope = _scope(60).model_dump(mode="json")
    invalid_scope["source_file_sha256"] = "caller-label"
    with pytest.raises(ValidationError):
        PhysicalLapScope.model_validate(invalid_scope)

    assert "setup_direction" in report.contract.forbidden_claims
    assert "setup_target" in report.contract.forbidden_claims
    assert report.setup_direction_available is False
