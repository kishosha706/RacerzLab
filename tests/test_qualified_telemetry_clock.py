from __future__ import annotations

import polars as pl
import pytest

from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
from racelab_engine.analysis.lap_detection import detect_laps
from racelab_engine.analysis.lap_eligibility import (
    lap_ineligibility_reasons,
    lap_is_eligible,
)
from racelab_engine.analysis.qualified_clock import build_qualified_telemetry_clock
from racelab_engine.analysis.sim_integrity import build_sim_integrity_certificate
from racelab_engine.analysis.vectorized_channels import normalize_telemetry_frame
from racelab_engine.io.ibt_types import IBTHeader, IBTVariableDefinition
from racelab_engine.io.telemetry_manifest import (
    build_telemetry_manifest,
    compact_capability_summary,
)


def _full_lap(*, seconds: int = 40) -> list[dict[str, object]]:
    sample_count = seconds * 60 + 1
    return [
        {
            "lap": 4,
            "lap_dist_pct": index / (sample_count - 1),
            "session_tick": 10_000 + index,
            "session_time": 200.0 + index / 60.0,
            "speed_mph": 160.0,
            "rpm": 8_000.0,
            "throttle_pct": 95.0,
            "brake_pct": 0.0,
            "lap_current_time_s": index / 60.0,
            "lap_delta_to_best_valid": True,
        }
        for index in range(sample_count)
    ]


def test_contiguous_ticks_own_canonical_time_despite_duplicate_session_time() -> None:
    rows = _full_lap()
    rows[600]["session_time"] = rows[599]["session_time"]
    rows[1_800]["session_time"] = rows[1_799]["session_time"]

    clock = build_qualified_telemetry_clock(rows, expected_sample_rate_hz=60.0)

    assert clock.primary_clock == "session_tick"
    assert clock.clock_state == "qualified"
    assert clock.canonical_duration_s == pytest.approx(40.0)
    assert clock.session_time_duplicate_count == 2
    assert clock.session_time_residual_s[600] == pytest.approx(-1 / 60)
    assert clock.session_time_residual_p95_s == pytest.approx(0.0)
    assert clock.blockers == []
    assert "Count-as-time" in clock.sub_tick_semantics


def test_duplicate_observed_time_does_not_reject_lap_in_row_or_frame_engine() -> None:
    rows = _full_lap()
    rows[1_200]["session_time"] = rows[1_199]["session_time"]

    for table in (rows, pl.DataFrame(rows, strict=False)):
        lap = detect_laps(table, expected_sample_rate_hz=60.0)[0]
        assert lap.is_useful is True
        assert lap.lap_time == pytest.approx(40.0)
        assert lap.timing_primary_clock == "session_tick"
        assert lap.timing_clock_state == "qualified"
        assert lap.session_time_duplicate_count == 1
        assert lap.lap_time_channel_corroboration == "agrees"
        assert "TIMING_INTEGRITY_BLOCKED" not in lap.classification_tags


def test_session_time_only_lap_is_archived_but_never_timing_eligible() -> None:
    rows = _full_lap()
    for row in rows:
        row.pop("session_tick")

    for table in (rows, pl.DataFrame(rows, strict=False)):
        lap = detect_laps(table, expected_sample_rate_hz=60.0)[0]
        assert lap.timing_primary_clock == "session_time"
        assert lap.timing_clock_state == "degraded"
        assert lap.is_useful is False
        assert "ELIGIBLE_FLYING_LAP" not in lap.classification_tags
        assert {"TIMING_INTEGRITY_BLOCKED", "NO_SETUP_CONCLUSION"}.issubset(
            lap.classification_tags
        )
        assert lap_is_eligible(lap) is False
        assert "Qualified SessionTick timing unavailable" in lap_ineligibility_reasons(lap)


def test_genuine_tick_gap_blocks_lap_and_integrity_certificate() -> None:
    rows = _full_lap()
    for index in range(1_200, len(rows)):
        rows[index]["session_tick"] = int(rows[index]["session_tick"]) + 2

    clock = build_qualified_telemetry_clock(rows, expected_sample_rate_hz=60.0)
    lap = detect_laps(rows, expected_sample_rate_hz=60.0)[0]
    certificate = build_sim_integrity_certificate(rows, expected_sample_rate_hz=60.0)

    assert clock.clock_state == "blocked"
    assert clock.dropped_tick_count == 2
    assert "tick_discontinuity" in clock.blockers
    assert lap.is_useful is False
    assert {"SAMPLE_DISCONTINUITY", "TIMING_INTEGRITY_BLOCKED"}.issubset(
        lap.classification_tags
    )
    assert certificate.is_clear_for_analysis is False


def test_material_session_clock_disagreement_blocks_even_with_contiguous_ticks() -> None:
    rows = _full_lap()
    for index, row in enumerate(rows):
        row["session_time"] = 200.0 + index / 59.0

    clock = build_qualified_telemetry_clock(rows, expected_sample_rate_hz=60.0)
    lap = detect_laps(rows, expected_sample_rate_hz=60.0)[0]

    assert clock.primary_clock == "session_tick"
    assert clock.clock_state == "blocked"
    assert clock.session_time_residual_p95_s is not None
    assert clock.session_time_residual_p95_s > 0.010
    assert "material_session_clock_disagreement" in clock.blockers
    assert lap.is_useful is False
    assert "TIMING_INTEGRITY_BLOCKED" in lap.classification_tags


def test_matching_tick_and_session_time_resets_create_explicit_epochs() -> None:
    rows = [
        {"session_tick": tick, "session_time": time}
        for tick, time in ((100, 10.0), (101, 10 + 1 / 60), (0, 0.0), (1, 1 / 60))
    ]

    clock = build_qualified_telemetry_clock(rows, expected_sample_rate_hz=60.0)

    assert clock.primary_clock == "session_tick"
    assert clock.clock_state == "qualified"
    assert clock.epoch_count == 2
    assert clock.reset_epoch_count == 1
    assert clock.tick_discontinuity_count == 0
    assert clock.epoch_index_by_sample == (0, 0, 1, 1)
    assert clock.canonical_elapsed_time_s == pytest.approx((0.0, 1 / 60, 2 / 60, 3 / 60))


def test_lap_crossing_clock_reset_epoch_is_not_setup_evidence() -> None:
    rows = _full_lap()
    for index in range(1_200, len(rows)):
        rows[index]["session_tick"] = index - 1_200
        rows[index]["session_time"] = (index - 1_200) / 60.0

    lap = detect_laps(rows, expected_sample_rate_hz=60.0)[0]

    assert lap.timing_epoch_count == 2
    assert lap.is_useful is False
    assert "CLOCK_RESET_BOUNDARY" in lap.classification_tags


def test_simulator_lap_time_and_validity_are_corroboration_not_authority() -> None:
    agreeing = _full_lap()
    for row in agreeing:
        row["lap_delta_to_best_valid"] = False
    agreed_clock = build_qualified_telemetry_clock(
        agreeing,
        expected_sample_rate_hz=60.0,
    )
    assert agreed_clock.clock_state == "qualified"
    assert agreed_clock.lap_time_channel_corroboration == "agrees"
    assert agreed_clock.lap_delta_validity_corroboration is False

    disagreeing = _full_lap()
    disagreeing[-1]["lap_current_time_s"] = 41.0
    blocked_clock = build_qualified_telemetry_clock(
        disagreeing,
        expected_sample_rate_hz=60.0,
    )
    assert blocked_clock.clock_state == "blocked"
    assert blocked_clock.lap_time_channel_corroboration == "disagrees"
    assert "simulator_lap_time_disagreement" in blocked_clock.blockers


def test_reviewed_lap_timing_aliases_have_row_frame_parity() -> None:
    raw = [{
        "LapCurrentLapTime": 12.5,
        "LapLastLapTime": 40.1,
        "LapBestLapTime": 39.9,
        "LapDeltaToBestLap": 0.2,
        "LapDeltaToBestLap_OK": True,
        "LapDeltaToSessionOptimalLap_OK": False,
    }]

    row = normalize_telemetry_rows(raw)[0]
    frame = normalize_telemetry_frame(pl.DataFrame(raw, strict=False)).row(0, named=True)

    for key in (
        "lap_current_time_s", "lap_last_time_s", "lap_best_time_s",
        "lap_delta_to_best_s", "lap_delta_to_best_valid",
        "lap_delta_to_session_optimal_valid",
    ):
        assert row[key] == frame[key]


def test_manifest_reports_qualified_tick_clock_and_preserves_timestamp_anomaly() -> None:
    times = [0.0, 1 / 60, 1 / 60, 3 / 60, 4 / 60]
    frame = pl.DataFrame({
        "SessionTick": [20, 21, 22, 23, 24],
        "SessionTime": times,
    })
    definitions = [
        IBTVariableDefinition(name="SessionTick", data_type_id=2, offset=0),
        IBTVariableDefinition(name="SessionTime", unit="s", data_type_id=5, offset=4),
    ]

    manifest = build_telemetry_manifest(
        IBTHeader(version=2, telemetry_rate_hz=60, record_length=12, record_count=5),
        definitions,
        frame,
    )
    continuity = manifest["sample_continuity"]

    assert continuity["status"] == "qualified_tick_clock"
    assert continuity["duplicate_timestamp_transition_count"] == 1
    assert continuity["tick_discontinuity_count"] == 0
    assert continuity["qualified_clock"]["primary_clock"] == "session_tick"
    assert continuity["qualified_clock"]["clock_state"] == "qualified"
    assert manifest["health_summary"]["qualified_clock_state"] == "qualified"
    assert manifest["capability_summary"]["qualified_clock_primary"] == "session_tick"
    assert manifest["capability_summary"]["qualified_clock_decision_ready"] is True


def test_manifest_keeps_session_time_only_diagnostics_but_blocks_decision_readiness() -> None:
    manifest = build_telemetry_manifest(
        IBTHeader(version=2, telemetry_rate_hz=60, record_length=8, record_count=4),
        [IBTVariableDefinition(name="SessionTime", unit="s", data_type_id=5, offset=0)],
        pl.DataFrame({"SessionTime": [0.0, 1 / 60, 2 / 60, 3 / 60]}),
    )

    clock = manifest["sample_continuity"]["qualified_clock"]
    summary = manifest["capability_summary"]
    assert manifest["lossless_archive_complete"] is True
    assert clock["clock_state"] == "degraded"
    assert clock["primary_clock"] == "session_time"
    assert clock["observed_session_time_start_s"] == 0.0
    assert summary["qualified_clock_state"] == "degraded"
    assert summary["qualified_clock_primary"] == "session_time"
    assert summary["qualified_clock_decision_ready"] is False

    manifest["health_summary"]["qualified_clock_state"] = "qualified"
    hostile_summary = compact_capability_summary(manifest)
    assert hostile_summary["qualified_clock_state"] == "degraded"
    assert hostile_summary["qualified_clock_decision_ready"] is False


def test_manifest_admits_lap_channels_only_for_clock_corroboration() -> None:
    definitions = [
        IBTVariableDefinition(
            name="LapCurrentLapTime",
            description="Player current lap time",
            unit="s",
            data_type_id=4,
            offset=0,
        ),
        IBTVariableDefinition(
            name="LapDeltaToBestLap_OK",
            description="Player best-lap delta is valid",
            unit="bool",
            data_type_id=1,
            offset=4,
        ),
    ]
    manifest = build_telemetry_manifest(
        IBTHeader(version=2, telemetry_rate_hz=60, record_length=8, record_count=2),
        definitions,
        pl.DataFrame({
            "LapCurrentLapTime": [1.0, 2.0],
            "LapDeltaToBestLap_OK": [True, True],
        }),
    )
    candidates = {
        item["raw_name"]: item
        for item in manifest["measurement_candidate_contracts"]
    }

    for raw_name in ("LapCurrentLapTime", "LapDeltaToBestLap_OK"):
        candidate = candidates[raw_name]
        assert candidate["state"] == "clock_corroboration_admitted"
        assert candidate["runtime_mapping_admitted"] is True
        assert candidate["engineering_role"] == "simulator_clock_corroboration_only"
        assert "Cannot replace the qualified clock" in candidate["authority_limit"]
