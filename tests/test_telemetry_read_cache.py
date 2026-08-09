from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

import racelab_engine.services.import_service as import_service
from racelab_engine.io.ibt_types import IBTVariableDefinition
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.services.import_service import (
    TRACE_AUTO_POINT_BUDGET,
    TelemetryArtifactIdentityError,
    bucket_downsample,
    build_channel_catalog,
    build_channel_summary,
    build_trace_payload,
    read_telemetry_rows,
    write_channel_metadata,
    write_telemetry_cache,
)


pytest.importorskip("polars")


@pytest.fixture(autouse=True)
def clear_telemetry_caches() -> None:
    with import_service._TELEMETRY_ROWS_CACHE_LOCK:
        import_service._TELEMETRY_ROWS_CACHE.clear()
        import_service._PROJECTED_TELEMETRY_CACHE.clear()
        import_service._CHANNEL_CATALOG_CACHE.clear()
        import_service._CHANNEL_SUMMARY_CACHE.clear()
        import_service._cached_parquet_schema.cache_clear()
        import_service._cached_file_sha256.cache_clear()
    yield
    with import_service._TELEMETRY_ROWS_CACHE_LOCK:
        import_service._TELEMETRY_ROWS_CACHE.clear()
        import_service._PROJECTED_TELEMETRY_CACHE.clear()
        import_service._CHANNEL_CATALOG_CACHE.clear()
        import_service._CHANNEL_SUMMARY_CACHE.clear()
        import_service._cached_parquet_schema.cache_clear()
        import_service._cached_file_sha256.cache_clear()


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


def _replace_preserving_size_and_mtime(path: Path, replacement: Path) -> None:
    original_stat = path.stat()
    replacement_bytes = replacement.read_bytes()
    assert len(replacement_bytes) == original_stat.st_size
    path.write_bytes(replacement_bytes)
    os.utime(
        path,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )
    replaced_stat = path.stat()
    assert replaced_stat.st_size == original_stat.st_size
    assert replaced_stat.st_mtime_ns == original_stat.st_mtime_ns


def test_full_telemetry_cache_returns_deep_mutation_safe_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    rows = [
        {**row, "cfs_risk_score": 0.1, "subtick_samples": [1.0, 2.0]}
        for row in _rows(100.0)
    ]
    write_telemetry_cache("full-mutation", rows, data_dir=tmp_path)
    first = read_telemetry_rows("full-mutation", data_dir=tmp_path)
    first[0]["speed_mph"] = -1.0
    first[0]["subtick_samples"][0] = -1.0
    first.pop()

    polars = pytest.importorskip("polars")

    def unexpected_read(*args, **kwargs):
        raise AssertionError("warm full read loaded Parquet again")

    monkeypatch.setattr(polars, "read_parquet", unexpected_read)
    second = read_telemetry_rows("full-mutation", data_dir=tmp_path)

    assert len(second) == 3
    assert second[0]["speed_mph"] == 100.0
    assert second[0]["subtick_samples"] == [1.0, 2.0]


def test_full_telemetry_cache_enforces_entry_byte_budget(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(import_service, "_TELEMETRY_ROWS_CACHE_MAX_ENTRY_BYTES", 1)
    write_telemetry_cache("full-entry-budget", _rows(100.0), data_dir=tmp_path)

    rows = read_telemetry_rows("full-entry-budget", data_dir=tmp_path)

    assert rows[0]["speed_mph"] == 100.0
    assert import_service._TELEMETRY_ROWS_CACHE == {}


def test_full_telemetry_cache_enforces_total_byte_budget(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(import_service, "_TELEMETRY_ROWS_CACHE_MAX_BYTES", 1)
    write_telemetry_cache("full-total-budget", _rows(100.0), data_dir=tmp_path)

    rows = read_telemetry_rows("full-total-budget", data_dir=tmp_path)

    assert rows[0]["speed_mph"] == 100.0
    assert import_service._TELEMETRY_ROWS_CACHE == {}


def test_full_telemetry_cache_accounts_for_large_nested_values_after_legacy_sample_window(
    tmp_path: Path,
    monkeypatch,
) -> None:
    rows = [
        {
            "lap": 2,
            "lap_dist_pct": index / 100.0,
            "session_time": float(index),
            "speed_mph": 100.0,
            "cfs_risk_score": 0.1,
            "subtick_samples": [1.0],
        }
        for index in range(65)
    ]
    rows[-1]["subtick_samples"] = [float(index) for index in range(20_000)]
    monkeypatch.setattr(import_service, "_TELEMETRY_ROWS_CACHE_MAX_ENTRY_BYTES", 100_000)
    write_telemetry_cache("late-wide-row", rows, data_dir=tmp_path)

    loaded = read_telemetry_rows("late-wide-row", data_dir=tmp_path)

    assert len(loaded[-1]["subtick_samples"]) == 20_000
    assert import_service._TELEMETRY_ROWS_CACHE == {}


@pytest.mark.parametrize("projected", [False, True], ids=["full", "projected"])
def test_equal_size_equal_mtime_telemetry_replacement_is_rejected(
    tmp_path: Path,
    projected: bool,
) -> None:
    run_id = f"signature-{projected}"
    write_telemetry_cache(run_id, _rows(100.0), data_dir=tmp_path)
    write_telemetry_cache("replacement", _rows(200.0), data_dir=tmp_path)
    path = import_service.parquet_path(tmp_path, run_id)
    replacement = import_service.parquet_path(tmp_path, "replacement")
    kwargs = {"lap": 2, "columns": ["speed_mph"]} if projected else {}

    before_signature = import_service._source_signature(
        path,
        import_service.csv_path(tmp_path, run_id),
    )
    first = read_telemetry_rows(run_id, data_dir=tmp_path, **kwargs)
    assert first[0]["speed_mph"] == 100.0

    _replace_preserving_size_and_mtime(path, replacement)
    after_signature = import_service._source_signature(
        path,
        import_service.csv_path(tmp_path, run_id),
    )
    assert before_signature is not None and after_signature is not None
    assert before_signature[1:3] == after_signature[1:3]
    assert before_signature != after_signature

    with pytest.raises(TelemetryArtifactIdentityError, match="does not match"):
        read_telemetry_rows(run_id, data_dir=tmp_path, **kwargs)


def test_channel_catalog_and_summary_cache_are_deep_mutation_safe(tmp_path: Path) -> None:
    run_id = "channel-mutation"
    write_telemetry_cache(run_id, _rows(100.0), data_dir=tmp_path)
    write_channel_metadata(
        run_id,
        [IBTVariableDefinition(name="speed_mph", description="old description", unit="mph")],
        data_dir=tmp_path,
    )

    first_catalog = build_channel_catalog(run_id, tmp_path)
    first_summary = build_channel_summary(run_id, tmp_path)
    catalog_speed = next(item for item in first_catalog if item["name"] == "speed_mph")
    summary_speed = next(item for item in first_summary if item["name"] == "speed_mph")
    catalog_speed["description"] = "caller poisoned"
    catalog_speed["dependencies"].append("caller poisoned")
    summary_speed["description"] = "caller poisoned"

    second_catalog = build_channel_catalog(run_id, tmp_path)
    second_summary = build_channel_summary(run_id, tmp_path)
    catalog_speed = next(item for item in second_catalog if item["name"] == "speed_mph")
    summary_speed = next(item for item in second_summary if item["name"] == "speed_mph")

    assert catalog_speed["description"] == "old description"
    assert "caller poisoned" not in catalog_speed["dependencies"]
    assert summary_speed["description"] == "old description"


def test_channel_catalog_and_summary_caches_enforce_entry_byte_budgets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_id = "channel-entry-budgets"
    write_telemetry_cache(run_id, _rows(100.0), data_dir=tmp_path)
    monkeypatch.setattr(import_service, "_CHANNEL_CATALOG_CACHE_MAX_ENTRY_BYTES", 1)
    monkeypatch.setattr(import_service, "_CHANNEL_SUMMARY_CACHE_MAX_ENTRY_BYTES", 1)

    assert build_channel_catalog(run_id, tmp_path)
    assert build_channel_summary(run_id, tmp_path)
    assert import_service._CHANNEL_CATALOG_CACHE == {}
    assert import_service._CHANNEL_SUMMARY_CACHE == {}


def test_equal_size_equal_mtime_metadata_replacement_invalidates_channel_caches(
    tmp_path: Path,
) -> None:
    run_id = "metadata-signature"
    write_telemetry_cache(run_id, _rows(100.0), data_dir=tmp_path)
    write_channel_metadata(
        run_id,
        [IBTVariableDefinition(name="speed_mph", description="old description", unit="mph")],
        data_dir=tmp_path,
    )
    metadata_path = import_service.channel_metadata_path(tmp_path, run_id)
    replacement_path = tmp_path / "replacement.channels.json"
    replacement_bytes = metadata_path.read_bytes().replace(b"old description", b"new description")
    assert replacement_bytes != metadata_path.read_bytes()
    replacement_path.write_bytes(replacement_bytes)

    first_catalog = build_channel_catalog(run_id, tmp_path)
    first_summary = build_channel_summary(run_id, tmp_path)
    assert next(item for item in first_catalog if item["name"] == "speed_mph")["description"] == "old description"
    assert next(item for item in first_summary if item["name"] == "speed_mph")["description"] == "old description"
    before_signature = import_service._file_signature(metadata_path)

    _replace_preserving_size_and_mtime(metadata_path, replacement_path)
    after_signature = import_service._file_signature(metadata_path)
    assert before_signature is not None and after_signature is not None
    assert before_signature[1:3] == after_signature[1:3]
    assert before_signature != after_signature

    second_catalog = build_channel_catalog(run_id, tmp_path)
    second_summary = build_channel_summary(run_id, tmp_path)
    assert next(item for item in second_catalog if item["name"] == "speed_mph")["description"] == "new description"
    assert next(item for item in second_summary if item["name"] == "speed_mph")["description"] == "new description"


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
