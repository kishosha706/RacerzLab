from __future__ import annotations

from pathlib import Path

import pytest

from racelab_engine.services.import_service import write_telemetry_cache
from racelab_engine.storage import parquet_query
from racelab_engine.storage.parquet_query import ParquetQueryEngine


pytestmark = pytest.mark.skipif(not parquet_query.HAS_DUCKDB, reason="DuckDB optional dependency not installed")


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
