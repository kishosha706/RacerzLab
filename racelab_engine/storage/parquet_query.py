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
import re
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


_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_. -]+$")
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


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
            assert duckdb is not None
            self._connection = duckdb.connect()
        return self._connection

    def _parquet_file(self, run_id: str) -> Path | None:
        if not _SAFE_RUN_ID_RE.fullmatch(run_id):
            self.warnings.append(f"Unsafe run id rejected: {run_id!r}.")
            return None
        path = parquet_path(self.data_dir, run_id)
        cache_root = (self.data_dir / "cache" / "parquet").resolve()
        try:
            if path.resolve().parent != cache_root:
                self.warnings.append(f"Unsafe parquet path rejected for run {run_id}.")
                return None
        except OSError as exc:
            self.warnings.append(f"Could not resolve parquet path for run {run_id}: {exc}")
            return None
        return path

    def _parquet_exists(self, run_id: str) -> bool:
        path = self._parquet_file(run_id)
        return path.exists() if path is not None else False

    def _parquet_sql_literal(self, run_id: str) -> str | None:
        path = self._parquet_file(run_id)
        return _quote_literal(str(path)) if path is not None else None

    def _available_columns(self, run_id: str) -> set[str] | None:
        path = self._parquet_file(run_id)
        if path is None or not path.exists():
            return None
        try:
            import polars as pl  # type: ignore
            return set(pl.read_parquet_schema(path).keys())
        except Exception:
            return None

    def _safe_channels(self, run_id: str, channels: list[str]) -> list[str] | None:
        known_columns = self._available_columns(run_id)
        safe: list[str] = []
        for channel in channels:
            if not _SAFE_IDENTIFIER_RE.fullmatch(channel):
                self.warnings.append(f"Unsafe channel name rejected: {channel!r}.")
                return None
            if known_columns is not None and channel not in known_columns:
                self.warnings.append(f"Unknown channel rejected: {channel}.")
                return None
            safe.append(channel)
        return safe

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
        parquet_literal = self._parquet_sql_literal(run_id)
        if parquet_literal is None or not self._parquet_exists(run_id):
            self.warnings.append(f"Parquet cache not found for run {run_id}.")
            return None

        conn = self._connect()
        if conn is None:
            return None

        bin_size_pct = max(1, int(bin_size_pct))
        lap_filter = f"AND lap = {int(lap)}" if lap is not None else ""
        query = f"""
        SELECT
            CAST(CAST(lap_dist_pct * 100 AS INTEGER) / {bin_size_pct} * {bin_size_pct} AS INTEGER) AS bin_start,
            AVG(speed_mph) AS avg_speed_mph,
            MIN(speed_mph) AS min_speed_mph,
            MAX(speed_mph) AS max_speed_mph,
            COUNT(*) AS sample_count
        FROM read_parquet({parquet_literal})
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
        parquet_literal = self._parquet_sql_literal(run_id)
        if parquet_literal is None or not self._parquet_exists(run_id):
            self.warnings.append(f"Parquet cache not found for run {run_id}.")
            return None

        conn = self._connect()
        if conn is None:
            return None

        bin_size_pct = max(1, int(bin_size_pct))
        lap_filter = f"AND lap = {int(lap)}" if lap is not None else ""
        query = f"""
        SELECT
            CAST(CAST(lap_dist_pct * 100 AS INTEGER) / {bin_size_pct} * {bin_size_pct} AS INTEGER) AS bin_start,
            MIN(cfsr_height_mm) AS min_splitter_mm,
            AVG(cfsr_height_mm) AS avg_splitter_mm,
            COUNT(*) AS sample_count
        FROM read_parquet({parquet_literal})
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
        parquet_literal = self._parquet_sql_literal(run_id)
        if parquet_literal is None or not self._parquet_exists(run_id):
            self.warnings.append(f"Parquet cache not found for run {run_id}.")
            return None

        conn = self._connect()
        if conn is None:
            return None

        safe_channels = self._safe_channels(run_id, channels)
        if safe_channels is None:
            return None
        if not safe_channels:
            self.warnings.append("No channels requested.")
            return None
        channel_cols = ", ".join(
            f"AVG({_quote_identifier(ch)}) AS {_quote_identifier(f'avg_{ch}')}, "
            f"MIN({_quote_identifier(ch)}) AS {_quote_identifier(f'min_{ch}')}, "
            f"MAX({_quote_identifier(ch)}) AS {_quote_identifier(f'max_{ch}')}"
            for ch in safe_channels
        )
        lap_filter = f"WHERE lap = {int(lap)}" if lap is not None else "WHERE 1=1"
        query = f"""
        SELECT
            lap,
            {channel_cols},
            COUNT(*) AS sample_count
        FROM read_parquet({parquet_literal})
        {lap_filter}
        GROUP BY lap
        ORDER BY lap
        """
        try:
            result = conn.execute(query).fetchall()
            columns = ["lap"] + [f"{agg}_{ch}" for ch in safe_channels for agg in ("avg", "min", "max")] + ["sample_count"]
            return [dict(zip(columns, row)) for row in result]
        except Exception as exc:
            self.warnings.append(f"DuckDB query failed: {exc}")
            return None

    def close(self) -> None:
        if self._connection is not None and HAS_DUCKDB:
            self._connection.close()
            self._connection = None
