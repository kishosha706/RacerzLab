from __future__ import annotations

import math
from pathlib import Path

import pytest

import racelab_engine.services.import_service as import_service
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.services.import_service import (
    TRACE_AUTO_POINT_BUDGET,
    bucket_downsample,
    build_trace_payload,
    read_telemetry_rows,
    write_telemetry_cache,
)


pytest.importorskip("polars")


@pytest.fixture(autouse=True)
def clear_projected_cache() -> None:
    with import_service._TELEMETRY_ROWS_CACHE_LOCK:
        import_service._PROJECTED_TELEMETRY_CACHE.clear()
    yield
    with import_service._TELEMETRY_ROWS_CACHE_LOCK:
        import_service._PROJECTED_TELEMETRY_CACHE.clear()


def _rows(speed: float) -> list[dict[str, float | int]]:
    return [
        {
            "lap": 2,
            "lap_dist_pct": index / 2,
            "session_time": float(index),
            "speed_mph": speed + index,
        }
        for index in range(3)
    ]


def test_projected_parquet_cache_returns_mutation_safe_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    write_telemetry_cache("projection", _rows(100.0), data_dir=tmp_path)
    first = read_telemetry_rows(
        "projection",
        data_dir=tmp_path,
        lap=2,
        columns=["lap", "speed_mph"],
    )
    first[0]["speed_mph"] = -1.0

    polars = pytest.importorskip("polars")

    def unexpected_scan(*args, **kwargs):
        raise AssertionError("warm projected read scanned Parquet again")

    monkeypatch.setattr(polars, "scan_parquet", unexpected_scan)
    second = read_telemetry_rows(
        "projection",
        data_dir=tmp_path,
        lap=2,
        columns=["lap", "speed_mph"],
    )

    assert second[0]["speed_mph"] == 100.0


def test_rewriting_run_invalidates_projected_parquet_cache(tmp_path: Path) -> None:
    write_telemetry_cache("rewritten", _rows(100.0), data_dir=tmp_path)
    first = read_telemetry_rows(
        "rewritten",
        data_dir=tmp_path,
        lap=2,
        columns=["speed_mph"],
    )
    assert first[0]["speed_mph"] == 100.0

    write_telemetry_cache("rewritten", _rows(200.0), data_dir=tmp_path)
    second = read_telemetry_rows(
        "rewritten",
        data_dir=tmp_path,
        lap=2,
        columns=["speed_mph"],
    )

    assert second[0]["speed_mph"] == 200.0


def test_rewriting_run_invalidates_cached_parquet_schema(tmp_path: Path) -> None:
    write_telemetry_cache("schema-rewrite", [{"lap": 2, "old_channel": 1.0}], data_dir=tmp_path)
    path = import_service.parquet_path(tmp_path, "schema-rewrite")
    assert "old_channel" in import_service._read_parquet_schema(path)
    assert import_service._cached_parquet_schema.cache_info().currsize > 0

    write_telemetry_cache("schema-rewrite", [{"lap": 2, "new_channel": 1.0}], data_dir=tmp_path)

    assert import_service._cached_parquet_schema.cache_info().currsize == 0
    rewritten = import_service._read_parquet_schema(path)
    assert "new_channel" in rewritten
    assert "old_channel" not in rewritten


def test_projected_parquet_cache_evicts_oldest_entry_by_count(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(import_service, "_PROJECTED_TELEMETRY_CACHE_MAX", 1)
    write_telemetry_cache("first", _rows(100.0), data_dir=tmp_path)
    write_telemetry_cache("second", _rows(200.0), data_dir=tmp_path)

    read_telemetry_rows("first", data_dir=tmp_path, lap=2, columns=["speed_mph"])
    read_telemetry_rows("second", data_dir=tmp_path, lap=2, columns=["speed_mph"])

    assert len(import_service._PROJECTED_TELEMETRY_CACHE) == 1
    remaining_path = next(iter(import_service._PROJECTED_TELEMETRY_CACHE))[0]
    assert remaining_path.endswith("second.parquet")


def test_projected_parquet_cache_enforces_total_byte_budget(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(import_service, "_PROJECTED_TELEMETRY_CACHE_MAX_BYTES", 1)
    write_telemetry_cache("byte-budget", _rows(100.0), data_dir=tmp_path)

    read_telemetry_rows(
        "byte-budget",
        data_dir=tmp_path,
        lap=2,
        columns=["speed_mph"],
    )

    assert import_service._PROJECTED_TELEMETRY_CACHE == {}


def test_extrema_downsampling_keeps_nearest_event_anchor() -> None:
    rows = [
        {"lap_dist_pct_100": float(index * 5), "speed_mph": 100.0}
        for index in range(20)
    ]
    event = TelemetryEvent(
        event_id="event-anchor",
        run_id="projection",
        event_type="TEST_EVENT",
        lap_pct_peak=37.0,
    )

    downsampled = bucket_downsample(
        rows,
        bucket_size=5,
        channels=["speed_mph"],
        events=[event],
    )

    assert any(row["lap_dist_pct_100"] == 35.0 for row in downsampled)


def test_auto_trace_honors_point_budget_and_keeps_global_extreme(tmp_path: Path) -> None:
    rows = [
        {
            "lap": 2,
            "lap_dist_pct": index / 5_999,
            "lap_dist_pct_100": index * 100.0 / 5_999,
            "session_time": index / 60.0,
            "sample_index": index,
            "speed_mph": 180.0 + (index % 17),
            "rpm": 8_000.0 + (index % 31),
            "throttle_pct": float(index % 101),
            "brake_pct": float((index * 3) % 101),
            "cfs_ride_height_mm": 20.0 + (index % 13),
        }
        for index in range(6_000)
    ]
    rows[3_217]["cfs_ride_height_mm"] = 1.25
    write_telemetry_cache("auto-trace", rows, data_dir=tmp_path)

    payload = build_trace_payload(
        "auto-trace",
        lap=2,
        channels=[
            "speed_mph",
            "rpm",
            "throttle_pct",
            "brake_pct",
            "cfs_ride_height_mm",
        ],
        downsample="auto",
        preserve_extrema=True,
        data_dir=tmp_path,
    )

    assert payload["sample_count"] <= TRACE_AUTO_POINT_BUDGET
    assert min(payload["channels"]["cfs_ride_height_mm"]) == 1.25


def test_auto_bucket_math_bounds_many_channel_extrema() -> None:
    channels = [f"channel_{index}" for index in range(19)]
    rows = [
        {channel: float(row_index + channel_index) for channel_index, channel in enumerate(channels)}
        for row_index in range(1_201)
    ]

    bucket_size = import_service._extrema_aware_auto_bucket_size(rows, channels, events=None)
    worst_case_points = math.ceil(len(rows) / bucket_size) * (2 + 2 * len(channels))

    assert worst_case_points <= TRACE_AUTO_POINT_BUDGET
