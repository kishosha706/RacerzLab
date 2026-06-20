from __future__ import annotations

import math
from pathlib import Path

import pytest

from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
from racelab_engine.analysis.platform_metrics import classify_splitter_height_mm
from racelab_engine.services.import_service import build_trace_payload, write_telemetry_cache


NEXT_GEN_PATHS = [
    "stockcars chevycamarozl12022",
    "stockcars fordmustang2022",
    "stockcars toyotacamry2022",
]


def _platform_row(lr: float | None = 4.0) -> dict[str, float | None]:
    return {
        "lap": 1,
        "lap_dist_ft": 10.0,
        "session_time": 0.0,
        "cfs_ride_height_in": 2.0,
        "cfs_ride_height_mm": 50.8,
        "cfs_risk_score": 0.08,
        "platform_risk_score": 0.08,
        "lf_ride_height_in": 2.0,
        "rf_ride_height_in": 3.0,
        "lr_ride_height_in": lr,
        "rr_ride_height_in": 5.0,
        "lf_ride_height_mm": 50.8,
        "rf_ride_height_mm": 76.2,
        "lr_ride_height_mm": None if lr is None else lr * 25.4,
        "rr_ride_height_mm": 127.0,
    }


def test_splitter_height_classification_boundaries() -> None:
    assert classify_splitter_height_mm(0.0) == "scrape"
    assert classify_splitter_height_mm(3.0) == "critical"
    assert classify_splitter_height_mm(6.0) == "high"
    assert classify_splitter_height_mm(10.0) == "watch"
    assert classify_splitter_height_mm(10.1) == "safe"


def test_splitter_height_missing_and_nan_stay_unavailable() -> None:
    assert classify_splitter_height_mm(None) == "unavailable"
    assert classify_splitter_height_mm(math.nan) == "unavailable"
    assert classify_splitter_height_mm(math.inf) == "unavailable"


@pytest.mark.parametrize("car_path", NEXT_GEN_PATHS)
def test_next_gen_car_paths_apply_lr_ride_height_offset(car_path: str) -> None:
    row = normalize_telemetry_rows([_platform_row()], car_path=car_path)[0]

    assert row["lr_ride_height_in"] == pytest.approx(3.5)
    assert row["lr_ride_height_mm"] == pytest.approx(88.9)
    assert row["lr_ride_height_raw_in"] == pytest.approx(4.0)
    assert row["lr_ride_height_raw_mm"] == pytest.approx(101.6)
    assert row["lr_ride_height_offset_applied"] is True
    assert row["lr_ride_height_offset_in"] == pytest.approx(-0.5)
    assert row["lr_ride_height_offset_reason"] == "Next Gen LR ride-height calibration"
    assert row["lr_ride_height_offset_car_path"] == car_path


def test_next_gen_detection_normalizes_case_and_outer_whitespace_only() -> None:
    row = normalize_telemetry_rows([_platform_row()], car_path="  STOCKCARS FORDMUSTANG2022  ")[0]
    non_match = normalize_telemetry_rows([_platform_row()], car_path="stockcars  fordmustang2022")[0]

    assert row["lr_ride_height_in"] == pytest.approx(3.5)
    assert non_match["lr_ride_height_in"] == pytest.approx(4.0)


def test_non_next_gen_and_unknown_car_paths_do_not_apply_lr_offset() -> None:
    non_next = normalize_telemetry_rows([_platform_row()], car_path="stockcars camarozl12018")[0]
    unknown = normalize_telemetry_rows([_platform_row()], car_path=None)[0]

    assert non_next["lr_ride_height_in"] == pytest.approx(4.0)
    assert non_next["lr_ride_height_offset_applied"] is False
    assert unknown["lr_ride_height_in"] == pytest.approx(4.0)
    assert unknown["lr_ride_height_offset_applied"] is False


def test_missing_lr_value_remains_unavailable_not_zero_or_offset() -> None:
    row = normalize_telemetry_rows([_platform_row(lr=None)], car_path="stockcars chevycamarozl12022")[0]

    assert row["lr_ride_height_in"] is None
    assert row["lr_ride_height_mm"] is None
    assert row.get("lr_ride_height_raw_in") is None
    assert row.get("rear_avg_rh_in") is None


@pytest.mark.parametrize("lr", [math.nan, math.inf, -math.inf])
def test_non_finite_lr_value_remains_unavailable(lr: float) -> None:
    row = normalize_telemetry_rows([_platform_row(lr=lr)], car_path="stockcars toyotacamry2022")[0]

    assert row["lr_ride_height_in"] is None
    assert row["lr_ride_height_mm"] is None
    assert row.get("rear_avg_rh_in") is None


def test_rear_average_and_side_rake_use_corrected_next_gen_lr() -> None:
    row = normalize_telemetry_rows([_platform_row()], car_path="stockcars fordmustang2022")[0]

    assert row["rear_avg_rh_in"] == pytest.approx(4.25)
    assert row["left_avg_rh_in"] == pytest.approx(2.75)
    assert row["right_avg_rh_in"] == pytest.approx(4.0)
    assert row["side_rake_in"] == pytest.approx(1.25)
    assert row["rear_split_in"] == pytest.approx(1.5)


def test_lr_offset_is_applied_exactly_once() -> None:
    first = normalize_telemetry_rows([_platform_row()], car_path="stockcars chevycamarozl12022")
    second = normalize_telemetry_rows(first, car_path="stockcars chevycamarozl12022")

    assert first[0]["lr_ride_height_in"] == pytest.approx(3.5)
    assert second[0]["lr_ride_height_in"] == pytest.approx(3.5)
    assert second[0]["rear_avg_rh_in"] == pytest.approx(4.25)


def test_raw_zoom_trace_uses_corrected_lr_and_metadata_for_next_gen(tmp_path: Path) -> None:
    rows = [
        {
            **_platform_row(lr=4.0 + index),
            "sample_index": index,
            "lap_dist_ft": float(index),
            "session_time": index / 60,
        }
        for index in range(3)
    ]
    write_telemetry_cache("next-gen-zoom", rows, data_dir=tmp_path)

    payload = build_trace_payload(
        "next-gen-zoom",
        lap=1,
        channels=["lr_ride_height_in", "rr_ride_height_in", "rear_avg_rh_in", "side_rake_in"],
        x_axis="lap_dist_ft",
        downsample=1,
        data_dir=tmp_path,
        raw_resolution=True,
        car_path="stockcars toyotacamry2022",
    )

    assert payload["channels"]["lr_ride_height_in"]["values"] == pytest.approx([3.5, 4.5, 5.5])
    assert payload["channels"]["rear_avg_rh_in"]["values"] == pytest.approx([4.25, 4.75, 5.25])
    assert payload["channels"]["side_rake_in"]["values"] == pytest.approx([1.25, 0.75, 0.25])
    assert payload["trace_meta"]["lr_ride_height_offset_applied"] is True
    assert payload["trace_meta"]["lr_ride_height_offset_in"] == pytest.approx(-0.5)
    assert payload["trace_meta"]["lr_ride_height_offset_car_path"] == "stockcars toyotacamry2022"


def test_raw_zoom_trace_does_not_correct_non_next_gen(tmp_path: Path) -> None:
    write_telemetry_cache("non-next-gen-zoom", [_platform_row()], data_dir=tmp_path)

    payload = build_trace_payload(
        "non-next-gen-zoom",
        lap=1,
        channels=["lr_ride_height_in", "rear_avg_rh_in"],
        x_axis="lap_dist_ft",
        downsample=1,
        data_dir=tmp_path,
        raw_resolution=True,
        car_path="stockcars camarozl12018",
    )

    assert payload["channels"]["lr_ride_height_in"]["values"] == pytest.approx([4.0])
    assert payload["channels"]["rear_avg_rh_in"]["values"] == pytest.approx([4.5])
    assert payload["trace_meta"]["lr_ride_height_offset_applied"] is False
