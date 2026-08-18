from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.observation_intelligence import (
    DriverRepeatabilitySignature,
    MechanismObservationReport,
    ObservationCitation,
    ObservationStatus,
    OpportunitySignature,
    OpportunitySignatureReport,
    RunObservationIntelligence,
    SameSetupAnomalyReport,
)
from racelab_engine.services import session_position_bridge as bridge
from racelab_engine.services.import_service import write_telemetry_cache
from racelab_engine.services.session_intelligence_service import (
    position_evidence_sha256,
)


def _lap(run_id: str, number: int, *, eligible: bool = True) -> LapSummary:
    return LapSummary(
        lap_id=f"{run_id}:{number}",
        run_id=run_id,
        lap_number=number,
        lap_type="flying" if eligible else "cooldown",
        is_complete=True,
        is_useful=eligible,
        lap_time=50.0 + number / 100.0,
        classification_tags=[] if eligible else ["COOLDOWN"],
    )


def _overview(
    run_id: str,
    lap_numbers: tuple[int, ...],
    *,
    setup_id: str | None = None,
    extra_laps: tuple[LapSummary, ...] = (),
    warnings: tuple[str, ...] = (),
):
    setup = (
        SimpleNamespace(run_id=run_id, setup_id=setup_id)
        if setup_id is not None
        else None
    )
    return SimpleNamespace(
        run_id=run_id,
        session=SimpleNamespace(run_id=run_id),
        laps=[*(_lap(run_id, number) for number in lap_numbers), *extra_laps],
        setup_snapshot=setup,
        warnings=list(warnings),
        engineering_blockers=[],
    )


def _observations(
    *,
    run_id: str = "run-current",
    setup_id: str = "setup-current",
    eligible_lap_numbers: tuple[int, ...] = (1, 2, 3),
    status: ObservationStatus = ObservationStatus.READY,
) -> RunObservationIntelligence:
    citations = tuple(
        ObservationCitation(
            run_id=run_id,
            lap_number=number,
            setup_id=setup_id,
            lap_pct_start=20.0,
            lap_pct_end=30.0,
            lap_pct_peak=25.0,
            phase="entry",
            evidence_state=EvidenceState.OBSERVED_CORRELATION,
            source_channels=("lap_dist_pct_100", "session_time"),
            telemetry_sample_count=100,
        )
        for number in eligible_lap_numbers[:2]
    )
    signatures = (
        OpportunitySignature(
            signature_id="opportunity-current-entry",
            run_id=run_id,
            setup_id=setup_id,
            phase="entry",
            lap_pct_start=20.0,
            lap_pct_end=30.0,
            lap_pct_peak=25.0,
            eligible_lap_count=len(eligible_lap_numbers),
            repetition_count=len(citations),
            telemetry_sample_count=200,
            aligned_bin_count=40,
            median_opportunity_s=0.12,
            empirical_noise_s=0.02,
            source_channels=("lap_dist_pct_100", "session_time"),
            citations=citations,
        ),
    ) if status is ObservationStatus.READY else ()
    opportunity = OpportunitySignatureReport(
        status=status,
        run_id=run_id,
        setup_id=setup_id,
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        source_channels=("lap_dist_pct_100", "session_time"),
        eligible_lap_numbers=eligible_lap_numbers,
        eligible_lap_count=len(eligible_lap_numbers),
        telemetry_sample_count=300,
        signatures=signatures,
    )
    blockers = ("Not requested by this bridge test.",)
    return RunObservationIntelligence(
        run_id=run_id,
        setup_id=setup_id,
        opportunity_signatures=opportunity,
        mechanism_observations=MechanismObservationReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=setup_id,
            blocker_reasons=blockers,
        ),
        anomaly_envelopes=SameSetupAnomalyReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=setup_id,
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            required_channels=("lap_dist_pct_100", "speed_mph"),
            eligible_lap_count=0,
            reference_lap_count=0,
            telemetry_sample_count=0,
            blocker_reasons=blockers,
        ),
        driver_repeatability=DriverRepeatabilitySignature(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=setup_id,
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            eligible_lap_count=0,
            telemetry_sample_count=0,
            blocker_reasons=blockers,
        ),
    )


def _rows(run_id: str, lap_number: int) -> list[dict[str, float | int | str]]:
    del run_id
    return [
        {
            "lap": lap_number,
            "lap_number": lap_number,
            "lap_dist_pct_100": pct,
            "session_time": lap_number * 100.0 + pct / 2.0,
            "lap_dist_ft": pct * 50.0,
            "speed_mps": 40.0,
            "fuel_level": 20.0 - pct / 1_000.0,
            "lf_tire_distance_m": 1_000.0 + pct,
            "rf_tire_distance_m": 1_000.0 + pct,
            "lr_tire_distance_m": 1_000.0 + pct,
            "rr_tire_distance_m": 1_000.0 + pct,
            "player_tire_compound": "primary",
            "air_temp": 25.0,
            "track_temp": 35.0,
            "wind_vel": 2.0,
            "wind_dir": 1.0,
            "car_distance_ahead_m": 500.0,
            "car_distance_behind_m": 500.0,
            "lat": 35.0 + pct / 10_000.0,
            "lon": -80.0 + pct / 10_000.0,
        }
        for pct in (20.0, 25.0, 30.0)
    ]


def _alignment_result(delta: float, *, coverage: float = 1.0, confidence: float = 0.9):
    grid = [20.0, 25.0, 30.0]
    return SimpleNamespace(
        grid_pct=grid,
        coverage_fraction=coverage,
        local_alignment_confidence=confidence,
        incremental_delta_s=[0.0, delta / 2.0, delta / 2.0],
        incremental_basis=[
            None,
            "aligned_timing_boundaries",
            "aligned_timing_boundaries",
        ],
        alignment=[
            SimpleNamespace(
                methods=["lap_percentage", "track_distance_geometry", "gps_geometry"],
                is_gap=False,
                aligned_test_pct=pct,
            )
            for pct in grid
        ],
        phase_effects=[
            SimpleNamespace(
                delta_s=delta,
                source_channels=["session_time", "lap_dist_ft"],
            )
        ],
    )


def _install_repository(monkeypatch, overviews: dict[str, object]) -> None:
    repository = SimpleNamespace(get_overview=lambda run_id: overviews.get(run_id))
    monkeypatch.setattr(bridge, "RaceLabRepository", lambda _db_path: repository)


def test_builds_robust_position_evidence_from_each_recent_lap_pair(monkeypatch) -> None:
    _install_repository(
        monkeypatch,
        {
            "run-baseline": _overview("run-baseline", (1, 2, 3, 4), setup_id="setup-a"),
            "run-current": _overview(
                "run-current",
                (1, 2, 3),
                setup_id="setup-current",
                extra_laps=(_lap("run-current", 9, eligible=False),),
            ),
        },
    )
    reads: list[tuple[str, int, tuple[str, ...]]] = []

    def read_rows(run_id, _data_dir, *, lap, columns):
        reads.append((run_id, lap, tuple(columns)))
        return _rows(run_id, lap)

    monkeypatch.setattr(bridge, "read_telemetry_rows", read_rows)
    deltas = iter((-0.12, -0.10, -0.08))
    calls: list[tuple[float, float]] = []

    def analyze(_baseline_rows, _test_rows, *, start_pct, end_pct):
        calls.append((start_pct, end_pct))
        return _alignment_result(next(deltas))

    monkeypatch.setattr(bridge, "analyze_time_alignment", analyze)

    result = bridge.build_session_position_evidence(
        "run-current",
        ("unrelated-earlier", "run-baseline", "run-current", "unrelated-later"),
        _observations(),
        db_path="ignored.sqlite",
        data_dir="ignored-data",
    )

    assert len(result) == 1
    evidence = result[0]
    assert evidence.baseline_run_id == "run-baseline"
    assert evidence.test_run_id == "run-current"
    assert evidence.baseline_lap_ids == (
        "run-baseline:2",
        "run-baseline:3",
        "run-baseline:4",
    )
    assert evidence.test_lap_ids == (
        "run-current:1",
        "run-current:2",
        "run-current:3",
    )
    assert evidence.delta_s == pytest.approx(-0.1)
    assert evidence.empirical_noise_s == pytest.approx(0.02)
    assert evidence.alignment_confidence == pytest.approx(0.9)
    assert evidence.start_pct == 20.0
    assert evidence.end_pct == 30.0
    assert evidence.phase == "entry"
    assert {
        "lap_dist_pct_100",
        "session_time",
        "lap_dist_ft",
        "speed_mps",
        "fuel_level",
        "lf_tire_distance_m",
        "rf_tire_distance_m",
        "lr_tire_distance_m",
        "rr_tire_distance_m",
        "player_tire_compound",
        "air_temp",
        "track_temp",
        "wind_vel",
        "wind_dir",
        "car_distance_ahead_m",
        "car_distance_behind_m",
        "lat",
        "lon",
    } <= set(evidence.source_channels)
    assert evidence.context_match.status == "matched"
    assert evidence.context_match.comparison_scope == "paired_lap_physical_window"
    assert len(evidence.context_match.pairs) == 3
    assert all(pair.proximity.matched for pair in evidence.context_match.pairs)
    assert all(len(pair.tire_distances) == 4 for pair in evidence.context_match.pairs)
    assert evidence.provenance_sha256 == position_evidence_sha256(evidence)
    assert calls == [(20.0, 30.0)] * 3
    assert [(run_id, lap) for run_id, lap, _columns in reads] == [
        ("run-baseline", 2),
        ("run-current", 1),
        ("run-baseline", 3),
        ("run-current", 2),
        ("run-baseline", 4),
        ("run-current", 3),
    ]
    assert all("lap" in columns and "lap_dist_pct_100" in columns for _, _, columns in reads)
    assert not hasattr(evidence, "cause")
    assert not hasattr(evidence, "setup_change")


def test_real_cache_reads_and_position_alignment_produce_verified_evidence(
    tmp_path, monkeypatch
) -> None:
    _install_repository(
        monkeypatch,
        {
            "run-baseline": _overview("run-baseline", (1, 2, 3), setup_id="setup-a"),
            "run-current": _overview(
                "run-current", (1, 2, 3), setup_id="setup-current"
            ),
        },
    )

    def telemetry(run_id: str, speed_gain: float):
        rows: list[dict[str, float | int | str]] = []
        for lap_number in (1, 2, 3):
            for index in range(401):
                pct = index * 0.25
                angle = pct / 100.0 * 2.0 * math.pi
                road = math.sin(angle * 8.0)
                rows.append(
                    {
                        "run_id": run_id,
                        "lap": lap_number,
                        "lap_number": lap_number,
                        "lap_dist_pct_100": pct,
                        "session_time": lap_number * 100.0 + pct * 0.5,
                        "lap_dist_ft": pct * 50.0,
                        "speed_mps": 40.0 + speed_gain + 2.0 * math.sin(angle),
                        "speed_mph": None,
                        "fuel_level": 20.0 - pct / 1_000.0,
                        "fuel_level_pct": 50.0 - pct / 2_000.0,
                        "lf_tire_distance_m": 1_000.0 + lap_number * 500.0 + pct,
                        "rf_tire_distance_m": 1_000.0 + lap_number * 500.0 + pct,
                        "lr_tire_distance_m": 1_000.0 + lap_number * 500.0 + pct,
                        "rr_tire_distance_m": 1_000.0 + lap_number * 500.0 + pct,
                        "player_tire_compound": "primary",
                        "air_temp": 25.0,
                        "track_temp": 35.0,
                        "wind_vel": 2.0,
                        "wind_dir": 1.0,
                        "car_distance_ahead_m": 500.0,
                        "car_distance_behind_m": 500.0,
                        "throttle_pct": 50.0 + 20.0 * math.sin(angle),
                        "brake_pct": max(0.0, 30.0 * math.sin(angle)),
                        "steering_deg": 10.0 * math.sin(angle),
                        "yaw_rate": 0.2 * math.sin(angle),
                        "lat_accel": 2.0 * math.sin(angle),
                        "long_accel": 0.5 * math.cos(angle),
                        "vert_accel": 9.80665 + road,
                        "lat": 35.0 + pct / 100_000.0,
                        "lon": -80.0 + pct / 80_000.0,
                        "alt": 100.0 + math.sin(angle),
                        "on_pit_road": 0,
                        "enter_exit_reset_state": 0,
                        "lf_shock_defl_in": 0.2 + 0.05 * road,
                        "rf_shock_defl_in": 0.2 + 0.04 * road,
                        "lr_shock_defl_in": 0.3 + 0.03 * road,
                        "rr_shock_defl_in": 0.3 + 0.03 * road,
                        "lf_shock_vel_in_s": road,
                        "rf_shock_vel_in_s": road,
                        "lr_shock_vel_in_s": road,
                        "rr_shock_vel_in_s": road,
                        "lf_ride_height_in": 2.0 + 0.05 * road,
                        "rf_ride_height_in": 2.0 + 0.04 * road,
                        "lr_ride_height_in": 3.0 + 0.03 * road,
                        "rr_ride_height_in": 3.0 + 0.03 * road,
                        "cfs_ride_height_in": 2.0 + 0.05 * road,
                    }
                )
        return rows

    data_dir = tmp_path / "telemetry"
    write_telemetry_cache(
        "run-baseline", telemetry("run-baseline", 0.0), data_dir=data_dir
    )
    write_telemetry_cache(
        "run-current", telemetry("run-current", 1.0), data_dir=data_dir
    )

    evidence = bridge.build_session_position_evidence(
        "run-current",
        ("run-baseline", "run-current"),
        _observations(),
        data_dir=data_dir,
    )

    assert len(evidence) == 1
    assert evidence[0].delta_s < -evidence[0].empirical_noise_s
    assert evidence[0].alignment_confidence >= 0.8
    assert evidence[0].context_match.status == "matched"
    assert evidence[0].provenance_sha256 == position_evidence_sha256(evidence[0])


@pytest.mark.parametrize(
    "ordered",
    [
        (),
        ("run-current",),
        ("run-current", "run-baseline"),
        ("run-baseline", "run-current", "run-current"),
        ("run-baseline", "different"),
        (" run-baseline", "run-current"),
    ],
)
def test_session_scope_errors_fail_closed_without_reading_telemetry(monkeypatch, ordered) -> None:
    monkeypatch.setattr(
        bridge,
        "RaceLabRepository",
        lambda _path: pytest.fail("invalid session scope must not touch storage"),
    )

    assert bridge.build_session_position_evidence(
        "run-current", ordered, _observations()
    ) == ()


@pytest.mark.parametrize(
    ("current_laps", "observed_laps", "stored_setup", "observation_setup"),
    [
        ((1, 2), (1, 2, 3), "setup-current", "setup-current"),
        ((1, 2, 3), (1, 2, 4), "setup-current", "setup-current"),
        ((1, 2, 3), (1, 2, 3), "setup-new", "setup-current"),
        ((1, 2, 3), (1, 2, 3), None, "setup-current"),
    ],
)
def test_stale_or_insufficient_current_observation_scope_fails_closed(
    monkeypatch,
    current_laps,
    observed_laps,
    stored_setup,
    observation_setup,
) -> None:
    _install_repository(
        monkeypatch,
        {
            "run-baseline": _overview("run-baseline", (1, 2, 3), setup_id="setup-a"),
            "run-current": _overview(
                "run-current", current_laps, setup_id=stored_setup
            ),
        },
    )
    monkeypatch.setattr(
        bridge,
        "read_telemetry_rows",
        lambda *_args, **_kwargs: pytest.fail("stale scope must not read telemetry"),
    )

    assert bridge.build_session_position_evidence(
        "run-current",
        ("run-baseline", "run-current"),
        _observations(
            setup_id=observation_setup,
            eligible_lap_numbers=observed_laps,
        ),
    ) == ()


@pytest.mark.parametrize(
    ("coverage", "confidence"),
    [
        (0.949, 0.9),
        (1.0, 0.799),
    ],
)
def test_any_pair_below_alignment_gate_suppresses_the_whole_signature(
    monkeypatch, coverage, confidence
) -> None:
    _install_repository(
        monkeypatch,
        {
            "run-baseline": _overview("run-baseline", (1, 2, 3), setup_id="setup-a"),
            "run-current": _overview(
                "run-current", (1, 2, 3), setup_id="setup-current"
            ),
        },
    )
    monkeypatch.setattr(
        bridge,
        "read_telemetry_rows",
        lambda run_id, _data_dir, *, lap, columns: _rows(run_id, lap),
    )
    results = iter(
        (
            _alignment_result(-0.1),
            _alignment_result(-0.1, coverage=coverage, confidence=confidence),
            _alignment_result(-0.1),
        )
    )
    monkeypatch.setattr(
        bridge, "analyze_time_alignment", lambda *_args, **_kwargs: next(results)
    )

    assert bridge.build_session_position_evidence(
        "run-current",
        ("run-baseline", "run-current"),
        _observations(),
    ) == ()


def test_cache_identity_or_analysis_failure_is_withheld(monkeypatch) -> None:
    _install_repository(
        monkeypatch,
        {
            "run-baseline": _overview("run-baseline", (1, 2, 3), setup_id="setup-a"),
            "run-current": _overview(
                "run-current", (1, 2, 3), setup_id="setup-current"
            ),
        },
    )
    monkeypatch.setattr(
        bridge,
        "read_telemetry_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("telemetry cache hash mismatch")
        ),
    )

    assert bridge.build_session_position_evidence(
        "run-current",
        ("run-baseline", "run-current"),
        _observations(),
    ) == ()


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("missing_air_temperature", None),
        ("unmatched_fuel", 50.0),
        ("different_tire_compound", "alternate"),
        ("nearby_car", 20.0),
        ("different_racing_line", 0.001),
        ("racing_line_tail_split", 0.001),
        ("missing_tire_context", None),
        ("missing_tire_compound", None),
        ("partial_tire_distance", None),
    ],
)
def test_required_operating_context_is_fail_closed(monkeypatch, mutation, value) -> None:
    _install_repository(
        monkeypatch,
        {
            "run-baseline": _overview("run-baseline", (1, 2, 3), setup_id="setup-a"),
            "run-current": _overview(
                "run-current", (1, 2, 3), setup_id="setup-current"
            ),
        },
    )

    def read_rows(run_id, _data_dir, *, lap, columns):
        rows = _rows(run_id, lap)
        if run_id != "run-current":
            return rows
        for row in rows:
            if mutation == "missing_air_temperature":
                row.pop("air_temp")
            elif mutation == "unmatched_fuel":
                row["fuel_level"] = value
            elif mutation == "different_tire_compound":
                row["player_tire_compound"] = value
            elif mutation == "nearby_car":
                row["car_distance_ahead_m"] = value
            elif mutation == "different_racing_line":
                row["lat"] = float(row["lat"]) + float(value)
            elif (
                mutation == "racing_line_tail_split"
                and row["lap_dist_pct_100"] == 30.0
            ):
                row["lat"] = float(row["lat"]) + float(value)
            elif mutation == "missing_tire_context":
                for channel in (
                    "lf_tire_distance_m",
                    "rf_tire_distance_m",
                    "lr_tire_distance_m",
                    "rr_tire_distance_m",
                ):
                    row.pop(channel)
            elif mutation == "missing_tire_compound":
                row.pop("player_tire_compound")
            elif mutation == "partial_tire_distance":
                row.pop("rr_tire_distance_m")
        return rows

    monkeypatch.setattr(bridge, "read_telemetry_rows", read_rows)
    monkeypatch.setattr(
        bridge,
        "analyze_time_alignment",
        lambda *_args, **_kwargs: _alignment_result(-0.1),
    )

    assert bridge.build_session_position_evidence(
        "run-current",
        ("run-baseline", "run-current"),
        _observations(),
    ) == ()


def test_median_effect_must_exceed_paired_lap_mad(monkeypatch) -> None:
    _install_repository(
        monkeypatch,
        {
            "run-baseline": _overview("run-baseline", (1, 2, 3), setup_id="setup-a"),
            "run-current": _overview(
                "run-current", (1, 2, 3), setup_id="setup-current"
            ),
        },
    )
    monkeypatch.setattr(
        bridge,
        "read_telemetry_rows",
        lambda run_id, _data_dir, *, lap, columns: _rows(run_id, lap),
    )
    results = iter(
        (
            _alignment_result(-0.10),
            _alignment_result(0.02),
            _alignment_result(0.10),
        )
    )
    monkeypatch.setattr(
        bridge, "analyze_time_alignment", lambda *_args, **_kwargs: next(results)
    )

    assert bridge.build_session_position_evidence(
        "run-current",
        ("run-baseline", "run-current"),
        _observations(),
    ) == ()
