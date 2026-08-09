from __future__ import annotations

import pytest

from racelab_engine.analysis.vectorized_channels import normalize_telemetry_frame
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.lap_engineering_context import ChannelUpdateSemantic
from racelab_engine.services.lap_engineering_context_service import (
    build_lap_engineering_context_report,
)


def _lap(number: int, *, useful: bool = True) -> LapSummary:
    return LapSummary(
        lap_id=f"run-1:{number}",
        run_id="run-1",
        lap_number=number,
        lap_type="flying" if useful else "out_lap",
        is_complete=True,
        is_useful=useful,
        lap_time=30.0,
        sample_count=3,
        classification_tags=[] if useful else ["OUT_LAP"],
    )


def _rows() -> list[dict[str, float | int]]:
    result: list[dict[str, float | int]] = []
    for index in range(3):
        row: dict[str, float | int] = {
            "lap": 1,
            "session_time": float(index),
            "fuel_level": 60.0 - index * 0.1,
            "air_temp": 24.0,
            "track_temp": 38.0 + index * 0.1,
            "wind_vel": 2.0 + index * 0.05,
            "wind_dir": 180.0,
            "player_tire_compound": 0,
            "car_distance_ahead_m": 500.0,
            "car_distance_behind_m": 500.0,
            "speed_mps": 70.0,
            "rear_wheel_speed_mismatch_raw": 0.1 + index * 0.01,
        }
        for corner in ("lf", "rf", "lr", "rr"):
            row.update({
                f"{corner}_temp_inner": 80.0 + index,
                f"{corner}_temp_middle": 81.0 + index,
                f"{corner}_temp_outer": 82.0 + index,
                f"{corner}_carcass_temp_l": 75.0,
                f"{corner}_carcass_temp_m": 76.0,
                f"{corner}_carcass_temp_r": 77.0,
                f"{corner}_wear_inner": 0.98,
                f"{corner}_wear_middle": 0.98,
                f"{corner}_wear_outer": 0.98,
                f"{corner}_pressure": 180.0 + index,
                f"{corner}_tire_distance_m": 1000.0 + index * 70.0,
            })
        result.append(row)
    return result


def test_lap_context_distinguishes_live_channels_from_pit_snapshots() -> None:
    report = build_lap_engineering_context_report(
        run_id="run-1",
        laps=[_lap(0, useful=False), _lap(1)],
        rows=_rows(),
    )
    assert report.status == "ready"
    assert report.excluded_lap_numbers == (0,)
    assert len(report.contexts) == 1
    context = report.contexts[0]
    rf = next(item for item in context.tire_corners if item.corner == "rf")
    rr = next(item for item in context.tire_corners if item.corner == "rr")
    assert {item.semantic for item in rf.surface_temperatures} == {
        ChannelUpdateSemantic.CONTINUOUS
    }
    assert {item.semantic for item in rf.carcass_temperatures} == {
        ChannelUpdateSemantic.PIT_SNAPSHOT
    }
    assert {item.semantic for item in rr.wear} == {
        ChannelUpdateSemantic.PIT_SNAPSHOT
    }
    assert rf.pressure.semantic is ChannelUpdateSemantic.CONTINUOUS
    assert rf.odometer.semantic is ChannelUpdateSemantic.CONTINUOUS
    assert context.rear_wheel_speed_mismatch.authority == "geometry_contaminated_proxy"
    assert context.nearby_traffic_exposure_fraction == 0.0


def test_vectorized_next_gen_carcass_aliases_match_row_engine_contract() -> None:
    pl = pytest.importorskip("polars")
    frame = normalize_telemetry_frame(pl.DataFrame({
        "RFtempCL": [70.0],
        "RFtempCM": [71.0],
        "RFtempCR": [72.0],
        "RRtempCL": [73.0],
        "RRtempCM": [74.0],
        "RRtempCR": [75.0],
    }))
    assert frame["rf_carcass_temp_l"][0] == 70.0
    assert frame["rf_carcass_temp_m"][0] == 71.0
    assert frame["rf_carcass_temp_r"][0] == 72.0
    assert frame["rr_carcass_temp_l"][0] == 73.0
    assert frame["rr_carcass_temp_m"][0] == 74.0
    assert frame["rr_carcass_temp_r"][0] == 75.0
