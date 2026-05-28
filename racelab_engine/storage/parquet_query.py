"""
Optional DuckDB/Parquet query prototype.

This module provides optional Parquet-backed telemetry queries using DuckDB.
SQLite remains the metadata source. DuckDB queries the Parquet telemetry cache only.

Usage:
    from racelab_engine.storage.parquet_query import ParquetQueryEngine
    engine = ParquetQueryEngine(data_dir="data")
    results = engine.query_avg_speed_by_bin("run_abc123", lap=2)

Dependencies:
    duckdb (optional) — install via `pip install duckdb`

If DuckDB is not installed, all methods return None and set a warning.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

try:
    import duckdb  # type: ignore
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False
    duckdb = None  # type: ignore


def default_data_dir() -> Path:
    import os
    return Path(os.environ.get("RACELAB_DATA_DIR", "data"))


def parquet_path(data_dir: Path, run_id: str) -> Path:
    return data_dir / "cache" / "parquet" / f"{run_id}.parquet"


class ParquetQueryEngine:
    """Optional DuckDB-backed query engine for Parquet telemetry cache."""

    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self._connection: Any = None
        self.warnings: list[str] = []

        if not HAS_DUCKDB:
            self.warnings.append("DuckDB not installed. Install via `pip install duckdb`.")

    def _connect(self) -> Any:
        """Lazy-init DuckDB connection."""
        if self._connection is None and HAS_DUCKDB:
            self._connection = duckdb.connect()
        return self._connection

    def _parquet_exists(self, run_id: str) -> bool:
        return parquet_path(self.data_dir, run_id).exists()

    def _parquet_str(self, run_id: str) -> str:
        return str(parquet_path(self.data_dir, run_id))

    def query_avg_speed_by_bin(
        self, run_id: str, lap: int | None = None, bin_size_pct: int = 5,
    ) -> list[dict[str, Any]] | None:
        """
        Query average speed by lap-percentage bin.

        Returns list of {bin_label, avg_speed_mph, min_speed_mph, max_speed_mph, sample_count}.
        """
        if not HAS_DUCKDB:
            self.warnings.append("DuckDB not available.")
            return None
        if not self._parquet_exists(run_id):
            self.warnings.append(f"Parquet cache not found for run {run_id}.")
            return None

        conn = self._connect()
        if conn is None:
            return None

        lap_filter = f"AND lap = {int(lap)}" if lap is not None else ""
        query = f"""
        SELECT
            CAST(CAST(lap_dist_pct * 100 AS INTEGER) / {bin_size_pct} * {bin_size_pct} AS INTEGER) AS bin_start,
            AVG(speed_mph) AS avg_speed_mph,
            MIN(speed_mph) AS min_speed_mph,
            MAX(speed_mph) AS max_speed_mph,
            COUNT(*) AS sample_count
        FROM read_parquet('{self._parquet_str(run_id)}')
        WHERE speed_mph IS NOT NULL
          AND lap_dist_pct IS NOT NULL
          {lap_filter}
        GROUP BY bin_start
        ORDER BY bin_start
        """
        try:
            result = conn.execute(query).fetchall()
            columns = ["bin_start", "avg_speed_mph", "min_speed_mph", "max_speed_mph", "sample_count"]
            return [dict(zip(columns, row)) for row in result]
        except Exception as exc:
            self.warnings.append(f"DuckDB query failed: {exc}")
            return None

    def query_min_splitter_by_bin(
        self, run_id: str, lap: int | None = None, bin_size_pct: int = 5,
    ) -> list[dict[str, Any]] | None:
        """Query minimum splitter height by lap-percentage bin."""
        if not HAS_DUCKDB:
            self.warnings.append("DuckDB not available.")
            return None
        if not self._parquet_exists(run_id):
            self.warnings.append(f"Parquet cache not found for run {run_id}.")
            return None

        conn = self._connect()
        if conn is None:
            return None

        lap_filter = f"AND lap = {int(lap)}" if lap is not None else ""
        query = f"""
        SELECT
            CAST(CAST(lap_dist_pct * 100 AS INTEGER) / {bin_size_pct} * {bin_size_pct} AS INTEGER) AS bin_start,
            MIN(cfsr_height_mm) AS min_splitter_mm,
            AVG(cfsr_height_mm) AS avg_splitter_mm,
            COUNT(*) AS sample_count
        FROM read_parquet('{self._parquet_str(run_id)}')
        WHERE cfsr_height_mm IS NOT NULL
          AND lap_dist_pct IS NOT NULL
          {lap_filter}
        GROUP BY bin_start
        ORDER BY bin_start
        """
        try:
            result = conn.execute(query).fetchall()
            columns = ["bin_start", "min_splitter_mm", "avg_splitter_mm", "sample_count"]
            return [dict(zip(columns, row)) for row in result]
        except Exception as exc:
            self.warnings.append(f"DuckDB query failed: {exc}")
            return None

    def query_channels_by_lap(
        self, run_id: str, channels: list[str], lap: int | None = None,
    ) -> list[dict[str, Any]] | None:
        """Query selected channels grouped by lap."""
        if not HAS_DUCKDB:
            self.warnings.append("DuckDB not available.")
            return None
        if not self._parquet_exists(run_id):
            self.warnings.append(f"Parquet cache not found for run {run_id}.")
            return None

        conn = self._connect()
        if conn is None:
            return None

        channel_cols = ", ".join(
            f"AVG({ch}) AS avg_{ch}, MIN({ch}) AS min_{ch}, MAX({ch}) AS max_{ch}"
            for ch in channels
        )
        lap_filter = f"WHERE lap = {int(lap)}" if lap is not None else "WHERE 1=1"
        query = f"""
        SELECT
            lap,
            {channel_cols},
            COUNT(*) AS sample_count
        FROM read_parquet('{self._parquet_str(run_id)}')
        {lap_filter}
        GROUP BY lap
        ORDER BY lap
        """
        try:
            result = conn.execute(query).fetchall()
            columns = ["lap"] + [f"{agg}_{ch}" for ch in channels for agg in ("avg", "min", "max")] + ["sample_count"]
            return [dict(zip(columns, row)) for row in result]
        except Exception as exc:
            self.warnings.append(f"DuckDB query failed: {exc}")
            return None

    def close(self) -> None:
        if self._connection is not None and HAS_DUCKDB:
            self._connection.close()
            self._connection = None
