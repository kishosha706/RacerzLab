from __future__ import annotations

from pathlib import Path

import pytest

from racelab_engine.services.import_service import (
    build_trace_payload,
    write_telemetry_cache,
)
from racelab_engine.storage import parquet_query
from racelab_engine.storage.parquet_query import ParquetQueryEngine

requires_duckdb = pytest.mark.skipif(
    not parquet_query.HAS_DUCKDB,
    reason="DuckDB optional dependency not installed",
)


@requires_duckdb
def test_parquet_query_rejects_unsafe_channel_name(tmp_path: Path) -> None:
    write_telemetry_cache(
        "safe-run",
        [{"lap": 1, "speed_mph": 100.0, "session_time": 0.0}],
        data_dir=tmp_path,
    )
    engine = ParquetQueryEngine(tmp_path)

    result = engine.query_channels_by_lap("safe-run", ["speed_mph); DROP TABLE runs; --"])

    assert result is None
    assert any("Unsafe channel name rejected" in warning for warning in engine.warnings)


@requires_duckdb
def test_parquet_query_rejects_unknown_channel_without_fake_zero(tmp_path: Path) -> None:
    write_telemetry_cache(
        "safe-run",
        [{"lap": 1, "speed_mph": 100.0, "session_time": 0.0}],
        data_dir=tmp_path,
    )
    engine = ParquetQueryEngine(tmp_path)

    result = engine.query_channels_by_lap("safe-run", ["not_a_channel"])

    assert result is None
    assert any("Unknown channel rejected" in warning for warning in engine.warnings)


@requires_duckdb
def test_parquet_query_valid_channel_still_queries(tmp_path: Path) -> None:
    write_telemetry_cache(
        "safe-run",
        [{"lap": 1, "speed_mph": 100.0, "session_time": 0.0}],
        data_dir=tmp_path,
    )
    engine = ParquetQueryEngine(tmp_path)

    result = engine.query_channels_by_lap("safe-run", ["speed_mph"])

    assert result == [
        {
            "lap": 1,
            "avg_speed_mph": 100.0,
            "min_speed_mph": 100.0,
            "max_speed_mph": 100.0,
            "sample_count": 1,
        },
    ]


def test_trace_payload_window_returns_raw_samples_without_bucket_stepping(tmp_path: Path) -> None:
    rows = [
        {
            "lap": 1,
            "lap_dist_ft": float(index),
            "lap_dist_pct": index / 19,
            "lap_dist_pct_100": (index / 19) * 100,
            "session_time": index * 0.01,
            "cfs_ride_height_in": 2.0 + index * 0.01,
            "speed_mph": 150.0 + index,
        }
        for index in range(20)
    ]
    write_telemetry_cache("raw-window-run", rows, data_dir=tmp_path)

    payload = build_trace_payload(
        "raw-window-run",
        lap=1,
        channels=["cfs_ride_height_in", "speed_mph"],
        x_axis="lap_dist_ft",
        downsample=1,
        data_dir=tmp_path,
        start_ft=5.5,
        end_ft=8.5,
    )

    assert payload["downsample"] == 1
    assert payload["sample_count"] == 3
    assert payload["x"] == [6.0, 7.0, 8.0]
    assert payload["x_by_name"]["lap_dist_ft"] == [6.0, 7.0, 8.0]
    assert payload["channels"]["cfs_ride_height_in"]["values"] == [2.06, 2.07, 2.08]
    assert payload["channels"]["speed_mph"]["values"] == [156.0, 157.0, 158.0]
