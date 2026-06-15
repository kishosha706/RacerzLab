from __future__ import annotations

import csv
import importlib.util
import json
import logging
import math
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from racelab_engine.analysis.calculated_channels import (
    CALCULATED_CHANNEL_UNITS,
    HIGH_VALUE_RAW_CHANNELS,
    channel_metadata,
    normalize_telemetry_rows,
)
from racelab_engine.analysis.constants import FORCE_PROXY_WARNING, FORCE_PROXY_CHANNELS
from racelab_engine.io import ibt_reader as ibt_mod
from racelab_engine.io.ibt_reader import import_ibt
from racelab_engine.io.ibt_types import IBTImportResult, IBTVariableDefinition
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.storage.repository import RaceLabRepository


TRACE_DEFAULT_CHANNELS = [
    "speed_mph",
    "rpm",
    "throttle_pct",
    "brake_pct",
    "cfs_ride_height_mm",
]

TRACE_CHANNEL_UNITS = {
    **CALCULATED_CHANNEL_UNITS,
    "rpm": "rpm",
    "throttle_pct": "%",
    "brake_pct": "%",
    "lap_dist_pct": "ratio",
    "session_time": "s",
    "steering_deg": "deg",
    "abs_steering_deg": "deg",
    "gear": "gear",
    "lap": "lap",
    "session_tick": "tick",
    "air_density": "kg/m^3",
    "air_temp": "C",
    "track_temp": "C",
    "water_temp": "C",
    "oil_temp": "C",
    "fuel_level": "L",
    "voltage": "V",
    "shift_power_pct": "%",
    "lf_shock_velocity_rms": "in/s",
    "rf_shock_velocity_rms": "in/s",
    "lr_shock_velocity_rms": "in/s",
    "rr_shock_velocity_rms": "in/s",
    "lf_shock_activity_index": "index",
    "rf_shock_activity_index": "index",
    "lr_shock_activity_index": "index",
    "rr_shock_activity_index": "index",
    "lf_damper_energy_proxy": "index",
    "rf_damper_energy_proxy": "index",
    "lr_damper_energy_proxy": "index",
    "rr_damper_energy_proxy": "index",
}

PRESERVE_EXTREMA_CHANNELS = [
    "cfs_ride_height_in",
    "cfs_ride_height_mm",
    "cfsr_height_mm",
    "center_rake_fs_in",
    "side_rake_in",
    "lf_ride_height_in",
    "rf_ride_height_in",
    "lr_ride_height_in",
    "rr_ride_height_in",
    "lf_shock_vel_in_s",
    "rf_shock_vel_in_s",
    "lr_shock_vel_in_s",
    "rr_shock_vel_in_s",
    "drag_scrub_suspicion",
    "speed_rate_mph_s",
    "dynamic_pressure_psf",
    "platform_compression_index",
    "full_throttle_resistance_index",
    "shock_velocity_rms",
    "shock_activity_index",
    "damper_energy_proxy",
]

@dataclass(frozen=True)
class TelemetryCacheResult:
    path: Path
    format: str
    used_fallback: bool


@dataclass
class _StagedImportCache:
    temp_run_id: str
    cache_result: TelemetryCacheResult
    metadata_path: Path
    final_cache_path: Path
    final_metadata_path: Path
    data_root: Path
    run_id: str

    def cleanup(self) -> None:
        _safe_unlink(self.cache_result.path)
        _safe_unlink(self.metadata_path)

    def promote(self) -> TelemetryCacheResult:
        _atomic_replace(self.cache_result.path, self.final_cache_path)
        _atomic_replace(self.metadata_path, self.final_metadata_path)
        _invalidate_run_cache(self.data_root, self.run_id)
        return TelemetryCacheResult(
            path=self.final_cache_path,
            format=self.cache_result.format,
            used_fallback=self.cache_result.used_fallback,
        )


@dataclass
class _TelemetryRowsCacheEntry:
    signature: tuple[str, int, int]
    rows: list[dict[str, Any]]
    last_access: float


_NORMALIZED_BASE_COLUMNS = ("speed_mph", "lap_dist_pct", "session_time")
_NORMALIZED_CALCULATED_COLUMNS = ("cfs_risk_score", "drag_scrub_suspicion", "platform_compression_index")
_TELEMETRY_ROWS_CACHE: dict[tuple[str, str], _TelemetryRowsCacheEntry] = {}
_TELEMETRY_ROWS_CACHE_LOCK = RLock()
_TELEMETRY_ROWS_CACHE_MAX = 24


@dataclass
class _ChannelCatalogCacheEntry:
    signature: tuple[Any, ...] | None
    catalog: list[dict[str, Any]]
    last_access: float


_CHANNEL_CATALOG_CACHE: dict[tuple[str, str], _ChannelCatalogCacheEntry] = {}
_CHANNEL_CATALOG_CACHE_MAX = 16


@dataclass
class _ChannelSummaryCacheEntry:
    signature: tuple[Any, ...] | None
    summary: list[dict[str, Any]]
    last_access: float


_CHANNEL_SUMMARY_CACHE: dict[tuple[str, str], _ChannelSummaryCacheEntry] = {}
_CHANNEL_SUMMARY_CACHE_MAX = 24
_CHANNEL_SCHEMA_VERSION = "v2"

def default_data_dir() -> Path:
    return Path(os.environ.get("RACELAB_DATA_DIR", "data"))


def parquet_path(data_dir: Path, run_id: str) -> Path:
    return data_dir / "cache" / "parquet" / f"{run_id}.parquet"


def csv_path(data_dir: Path, run_id: str) -> Path:
    return data_dir / "cache" / "normalized" / f"{run_id}.csv"


def channel_metadata_path(data_dir: Path, run_id: str) -> Path:
    return data_dir / "cache" / "normalized" / f"{run_id}.channels.json"


def _temp_cache_path(final_path: Path, run_id: str) -> Path:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    return final_path.with_name(f".{run_id}.{uuid.uuid4().hex}.tmp{final_path.suffix}")


def _safe_unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        if path.exists():
            path.unlink()
    except OSError:
        logging.getLogger(__name__).warning("Could not remove temp cache artifact: %s", path)


def _atomic_replace(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _numeric_value(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _scalar_columns(rows: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "sample_index",
        "session_time",
        "session_tick",
        "lap",
        "lap_completed",
        "lap_dist_m",
        "lap_dist_pct",
        "speed_mps",
        "speed_mph",
        "rpm",
        "gear",
        "throttle_01",
        "throttle_pct",
        "brake_01",
        "brake_pct",
        "clutch_01",
        "steering_rad",
        "steering_deg",
        "abs_steering_deg",
        "yaw_rate",
        "lat_accel",
        "abs_lat_accel",
        "long_accel",
        "cfsr_height_m",
        "cfsr_height_mm",
        "cfs_ride_height_m",
        "cfs_ride_height_mm",
        "cfs_ride_height_in",
        "lf_ride_height_mm",
        "rf_ride_height_mm",
        "lr_ride_height_mm",
        "rr_ride_height_mm",
        "lf_ride_height_in",
        "rf_ride_height_in",
        "lr_ride_height_in",
        "rr_ride_height_in",
        "front_avg_rh_in",
        "rear_avg_rh_in",
        "left_avg_rh_in",
        "right_avg_rh_in",
        "center_rake_fs_in",
        "side_rake_in",
        "front_split_in",
        "rear_split_in",
        "dynamic_pressure_pa",
        "dynamic_pressure_psf",
        "speed_rate_mph_s",
        "speed_rate_mph_1000ft",
        "cfs_risk_score",
        "platform_risk_score",
        "platform_stability_score",
        "rake_stability_score",
        "full_throttle_resistance_index",
        "drag_scrub_suspicion",
        "lf_shock_defl",
        "rf_shock_defl",
        "lr_shock_defl",
        "rr_shock_defl",
        "lf_shock_defl_in",
        "rf_shock_defl_in",
        "lr_shock_defl_in",
        "rr_shock_defl_in",
        "lf_shock_vel",
        "rf_shock_vel",
        "lr_shock_vel",
        "rr_shock_vel",
        "lf_shock_vel_in_s",
        "rf_shock_vel_in_s",
        "lr_shock_vel_in_s",
        "rr_shock_vel_in_s",
        "lf_slip_ratio",
        "rf_slip_ratio",
        "lr_slip_ratio",
        "rr_slip_ratio",
        "front_wheel_speed_mismatch",
        "rear_wheel_speed_mismatch",
        "front_scrub_proxy",
        "rear_scrub_proxy",
        "track_x_m",
        "track_y_m",
        "track_x_ft",
        "track_y_ft",
        "water_temp",
        "oil_temp",
        "fuel_level",
        "fuel_use_per_hour",
        "dynamic_pressure_index",
        "platform_compression_index",
        "driven_wheel_slip_proxy",
        "shock_velocity_rms",
        "shock_activity_index",
        "damper_energy_proxy",
        "lf_shock_velocity_rms",
        "rf_shock_velocity_rms",
        "lr_shock_velocity_rms",
        "rr_shock_velocity_rms",
        "lf_shock_activity_index",
        "rf_shock_activity_index",
        "lr_shock_activity_index",
        "rr_shock_activity_index",
        "lf_damper_energy_proxy",
        "rf_damper_energy_proxy",
        "lr_damper_energy_proxy",
        "rr_damper_energy_proxy",
    ]
    available = {str(column) for row in rows for column in row.keys()}
    scalar_available = {
        column
        for column in available
        if all(_is_scalar(row.get(column)) for row in rows if row.get(column) is not None)
    }
    ordered = [column for column in preferred if column in scalar_available]
    extras = sorted(column for column in scalar_available if column not in ordered)
    return ordered + extras


def _write_csv(rows: list[dict[str, Any]], path: Path) -> TelemetryCacheResult:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = _scalar_columns(rows)
    with path.open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) for column in columns})
    return TelemetryCacheResult(path=path, format="csv", used_fallback=True)


def write_channel_metadata(
    run_id: str,
    definitions: list[IBTVariableDefinition],
    data_dir: str | Path | None = None,
    staged: bool = False,
) -> Path:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    final_path = channel_metadata_path(data_root, run_id)
    path = _temp_cache_path(final_path, run_id)
    try:
        path.write_text(
            json.dumps([definition.model_dump() for definition in definitions], indent=2),
            encoding="utf-8",
        )
        if staged:
            return path
        _atomic_replace(path, final_path)
        return final_path
    except Exception:
        _safe_unlink(path)
        raise


def read_channel_metadata(run_id: str, data_dir: str | Path | None = None) -> list[dict[str, Any]]:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    path = channel_metadata_path(data_root, run_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def write_telemetry_cache(
    run_id: str,
    rows: list[dict[str, Any]],
    normalized_frame: Any | None = None,
    data_dir: str | Path | None = None,
    profile_out: dict[str, float] | None = None,
) -> TelemetryCacheResult:
    """Write telemetry cache — uses Polars direct write for speed."""
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    data_root.mkdir(parents=True, exist_ok=True)

    if importlib.util.find_spec("polars") is not None:
        pl = importlib.import_module("polars")
        path = parquet_path(data_root, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        if normalized_frame is not None and hasattr(normalized_frame, "write_parquet"):
            t0 = time.perf_counter()
            normalized_frame.write_parquet(path, compression="snappy")
            if profile_out is not None:
                profile_out["cache_write_from_frame"] = 1.0
                profile_out["cache_dataframe_and_parquet_write_s"] = time.perf_counter() - t0
                profile_out["cache_schema_inference_mode"] = -2.0
            _invalidate_run_cache(data_root, run_id)
            return TelemetryCacheResult(path=path, format="parquet", used_fallback=False)

        if not rows:
            pl.DataFrame().write_parquet(path)
            return TelemetryCacheResult(path=path, format="parquet", used_fallback=False)

        # Fast path: use first row keys (all vec output columns are scalar)
        # Skip _scalar_columns() full scan — saves ~5s on 54K rows
        t0 = time.perf_counter()
        columns = list(rows[0].keys())
        if profile_out is not None:
            profile_out["cache_scalar_column_selection_s"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        try:
            pl.from_dicts(rows, infer_schema_length=5000).write_parquet(
                path, compression="snappy",
            )
            if profile_out is not None:
                profile_out["cache_dataframe_and_parquet_write_s"] = time.perf_counter() - t0
                profile_out["cache_schema_inference_mode"] = 5000.0
        except Exception:
            t0 = time.perf_counter()
            pl.from_dicts(rows, infer_schema_length=None).write_parquet(
                path, compression="snappy",
            )
            if profile_out is not None:
                profile_out["cache_dataframe_and_parquet_write_s"] = time.perf_counter() - t0
                profile_out["cache_schema_inference_mode"] = -1.0
        _invalidate_run_cache(data_root, run_id)
        return TelemetryCacheResult(path=path, format="parquet", used_fallback=False)

    if importlib.util.find_spec("pandas") is not None and importlib.util.find_spec("pyarrow") is not None:
        pd = importlib.import_module("pandas")
        path = parquet_path(data_root, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        columns = list(rows[0].keys()) if rows else []
        data = [{column: row.get(column) for column in columns} for row in rows]
        if profile_out is not None:
            profile_out["cache_scalar_column_selection_s"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        pd.DataFrame(data).to_parquet(path)
        if profile_out is not None:
            profile_out["cache_dataframe_and_parquet_write_s"] = time.perf_counter() - t0
        _invalidate_run_cache(data_root, run_id)
        return TelemetryCacheResult(path=path, format="parquet", used_fallback=False)
    cache_result = _write_csv(rows, csv_path(data_root, run_id))
    _invalidate_run_cache(data_root, run_id)
    return cache_result


def _stage_import_cache(
    run_id: str,
    rows: list[dict[str, Any]],
    definitions: list[IBTVariableDefinition],
    *,
    normalized_frame: Any | None,
    data_dir: str | Path,
    profile_out: dict[str, float] | None = None,
) -> _StagedImportCache:
    data_root = Path(data_dir)
    temp_run_id = f".{run_id}.{uuid.uuid4().hex}.tmp"
    cache_result = write_telemetry_cache(
        temp_run_id,
        rows,
        normalized_frame=normalized_frame,
        data_dir=data_root,
        profile_out=profile_out,
    )
    try:
        metadata_path = write_channel_metadata(temp_run_id, definitions, data_root)
    except Exception:
        _safe_unlink(cache_result.path)
        raise

    final_cache_path = parquet_path(data_root, run_id) if cache_result.format == "parquet" else csv_path(data_root, run_id)
    return _StagedImportCache(
        temp_run_id=temp_run_id,
        cache_result=cache_result,
        metadata_path=metadata_path,
        final_cache_path=final_cache_path,
        final_metadata_path=channel_metadata_path(data_root, run_id),
        data_root=data_root,
        run_id=run_id,
    )


def _coerce_number(value: str) -> Any:
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return value
    return int(number) if number.is_integer() else number


def _cache_key(data_root: Path, run_id: str) -> tuple[str, str]:
    return str(data_root.resolve()), run_id


def _source_signature(parquet: Path, csv_file: Path) -> tuple[str, int, int] | None:
    source = parquet if parquet.exists() else csv_file if csv_file.exists() else None
    if source is None:
        return None
    stat = source.stat()
    return str(source.resolve()), stat.st_mtime_ns, stat.st_size


def _rows_look_normalized(rows: list[dict[str, Any]]) -> bool:
    if not rows:
        return True
    first = rows[0]
    if not isinstance(first, dict):
        return False
    has_base = all(column in first for column in _NORMALIZED_BASE_COLUMNS)
    has_calculated = any(column in first for column in _NORMALIZED_CALCULATED_COLUMNS)
    return has_base and has_calculated


def _normalize_if_needed(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return rows if _rows_look_normalized(rows) else normalize_telemetry_rows(rows)


def _evict_if_needed() -> None:
    if len(_TELEMETRY_ROWS_CACHE) <= _TELEMETRY_ROWS_CACHE_MAX:
        return
    oldest_key = min(_TELEMETRY_ROWS_CACHE.items(), key=lambda item: item[1].last_access)[0]
    _TELEMETRY_ROWS_CACHE.pop(oldest_key, None)


def _evict_channel_catalog_if_needed() -> None:
    if len(_CHANNEL_CATALOG_CACHE) <= _CHANNEL_CATALOG_CACHE_MAX:
        return
    oldest_key = min(_CHANNEL_CATALOG_CACHE.items(), key=lambda item: item[1].last_access)[0]
    _CHANNEL_CATALOG_CACHE.pop(oldest_key, None)


def _evict_channel_summary_if_needed() -> None:
    if len(_CHANNEL_SUMMARY_CACHE) <= _CHANNEL_SUMMARY_CACHE_MAX:
        return
    oldest_key = min(_CHANNEL_SUMMARY_CACHE.items(), key=lambda item: item[1].last_access)[0]
    _CHANNEL_SUMMARY_CACHE.pop(oldest_key, None)


def _invalidate_run_cache(data_root: Path, run_id: str) -> None:
    with _TELEMETRY_ROWS_CACHE_LOCK:
        _TELEMETRY_ROWS_CACHE.pop(_cache_key(data_root, run_id), None)
        _CHANNEL_CATALOG_CACHE.pop(_cache_key(data_root, run_id), None)
        _CHANNEL_SUMMARY_CACHE.pop(_cache_key(data_root, run_id), None)


def read_telemetry_rows(
    run_id: str,
    data_dir: str | Path | None = None,
    lap: int | None = None,
    columns: list[str] | None = None,
) -> list[dict[str, Any]]:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    parquet = parquet_path(data_root, run_id)
    csv_file = csv_path(data_root, run_id)
    signature = _source_signature(parquet, csv_file)
    key = _cache_key(data_root, run_id)
    requested_columns = list(dict.fromkeys(columns or []))

    def _filter_rows(source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        scoped_rows = source_rows if lap is None else [row for row in source_rows if row.get("lap") == lap]
        if not requested_columns:
            return scoped_rows
        return [{column: row.get(column) for column in requested_columns} for row in scoped_rows]

    with _TELEMETRY_ROWS_CACHE_LOCK:
        entry = _TELEMETRY_ROWS_CACHE.get(key)
        if entry is not None and entry.signature == signature:
            entry.last_access = time.time()
            return _filter_rows(entry.rows)
        if entry is not None and entry.signature != signature:
            _TELEMETRY_ROWS_CACHE.pop(key, None)

    # Fast miss path for lap/column-scoped calls: avoid reading full parquet into memory.
    if (lap is not None or requested_columns) and parquet.exists() and importlib.util.find_spec("polars") is not None:
        pl = importlib.import_module("polars")
        schema = pl.read_parquet_schema(parquet)
        available_columns = set(schema.keys())
        read_columns = requested_columns or list(schema.keys())
        if lap is not None and "lap" in available_columns and "lap" not in read_columns:
            read_columns = [*read_columns, "lap"]
        safe_columns = [column for column in read_columns if column in available_columns]
        if not safe_columns:
            return []
        frame = pl.scan_parquet(parquet).select(safe_columns)
        if lap is not None and "lap" in safe_columns:
            frame = frame.filter(pl.col("lap") == lap)
        rows = frame.collect().to_dicts()
        if requested_columns:
            return [{column: row.get(column) for column in requested_columns} for row in rows]
        return _normalize_if_needed([dict(row) for row in rows])

    if parquet.exists() and importlib.util.find_spec("polars") is not None:
        pl = importlib.import_module("polars")
        rows = _normalize_if_needed([dict(row) for row in pl.read_parquet(parquet).to_dicts()])
    elif parquet.exists() and importlib.util.find_spec("pandas") is not None:
        pd = importlib.import_module("pandas")
        rows = _normalize_if_needed(pd.read_parquet(parquet).to_dict("records"))
    else:
        if not csv_file.exists():
            rows = []
        else:
            with csv_file.open("r", newline="", encoding="utf-8") as file_obj:
                rows = [
                    {key: _coerce_number(value) for key, value in row.items()}
                    for row in csv.DictReader(file_obj)
                ]
            rows = _normalize_if_needed(rows)

    if signature is not None and not requested_columns:
        with _TELEMETRY_ROWS_CACHE_LOCK:
            _TELEMETRY_ROWS_CACHE[key] = _TelemetryRowsCacheEntry(
                signature=signature,
                rows=rows,
                last_access=time.time(),
            )
            _evict_if_needed()

    return _filter_rows(rows)


def _channel_stats(rows: list[dict[str, Any]], channel: str) -> dict[str, Any]:
    values = [row.get(channel) for row in rows if row.get(channel) is not None]
    numeric_values: list[float] = [value for value in (_numeric_value(value) for value in values) if value is not None]
    sample_value = values[0] if values else None
    if not numeric_values:
        return {"min": None, "max": None, "mean": None, "sample_value": sample_value}
    return {
        "min": min(numeric_values),
        "max": max(numeric_values),
        "mean": sum(numeric_values) / len(numeric_values),
        "sample_value": sample_value,
    }


def _precompute_channel_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for row in rows:
        for name, value in row.items():
            if value is None:
                continue
            if name not in stats:
                stats[name] = {
                    "min": None,
                    "max": None,
                    "sum": 0.0,
                    "count": 0,
                    "sample_value": value,
                }
            entry = stats[name]
            if entry["sample_value"] is None:
                entry["sample_value"] = value
            numeric_value = _numeric_value(value)
            if numeric_value is None:
                continue
            entry["min"] = numeric_value if entry["min"] is None else min(entry["min"], numeric_value)
            entry["max"] = numeric_value if entry["max"] is None else max(entry["max"], numeric_value)
            entry["sum"] += numeric_value
            entry["count"] += 1

    result: dict[str, dict[str, Any]] = {}
    for name, entry in stats.items():
        count = int(entry["count"])
        if count == 0:
            result[name] = {
                "min": None,
                "max": None,
                "mean": None,
                "sample_value": entry["sample_value"],
            }
            continue
        result[name] = {
            "min": entry["min"],
            "max": entry["max"],
            "mean": entry["sum"] / count,
            "sample_value": entry["sample_value"],
        }
    return result


def _is_numeric_dtype(dtype: Any) -> bool:
    kind = str(dtype).lower()
    return any(
        marker in kind
        for marker in ("int", "uint", "float", "decimal")
    ) and "list" not in kind and "struct" not in kind


def _precompute_channel_stats_from_parquet(
    path: Path,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if importlib.util.find_spec("polars") is None:
        return {}, []
    pl = importlib.import_module("polars")
    schema = pl.read_parquet_schema(path)
    columns = list(schema.keys())
    if not columns:
        return {}, []

    head_df = pl.read_parquet(path, n_rows=1)
    sample_values = head_df.to_dicts()[0] if head_df.height > 0 else {}

    numeric_cols = [name for name, dtype in schema.items() if _is_numeric_dtype(dtype)]
    stats: dict[str, dict[str, Any]] = {
        name: {"min": None, "max": None, "mean": None, "sample_value": sample_values.get(name)}
        for name in columns
    }
    if not numeric_cols:
        return stats, columns

    exprs: list[Any] = []
    for name in numeric_cols:
        exprs.extend([
            pl.col(name).min().alias(f"{name}__min"),
            pl.col(name).max().alias(f"{name}__max"),
            pl.col(name).mean().alias(f"{name}__mean"),
        ])
    row = pl.scan_parquet(path).select(exprs).collect(streaming=True).to_dicts()[0]
    for name in numeric_cols:
        stats[name] = {
            "min": row.get(f"{name}__min"),
            "max": row.get(f"{name}__max"),
            "mean": row.get(f"{name}__mean"),
            "sample_value": sample_values.get(name),
        }
    return stats, columns


def _definition_type(definition: dict[str, Any]) -> str | None:
    data_type = definition.get("data_type")
    return str(data_type) if data_type else None


def _missing_status(name: str, definition: dict[str, Any] | None, is_calculated: bool, in_column_set: bool) -> str | None:
    if in_column_set:
        return None
    if definition is not None:
        return "Raw channel metadata is available, but samples are not cached for this workbench yet."
    if name in HIGH_VALUE_RAW_CHANNELS:
        return "Raw channel is not present in this .ibt file."
    if is_calculated:
        return "Calculated channel unavailable because required source channels are missing."
    return None


def _definition_type_for(definition: dict[str, Any] | None, is_calculated: bool) -> str | None:
    if definition:
        return _definition_type(definition)
    return "float" if is_calculated else None


def _build_catalog_item(
    name: str,
    definition: dict[str, Any] | None,
    is_raw: bool,
    is_calculated: bool,
    in_column_set: bool,
    channel_stats: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    stats = channel_stats.get(name, {"min": None, "max": None, "mean": None, "sample_value": None})
    missing_status = _missing_status(name, definition, is_calculated, in_column_set)
    definition_type = _definition_type_for(definition, is_calculated)
    meta = channel_metadata(name)
    item: dict[str, Any] = {
        "name": name,
        "label": meta.get("label", name),
        "description": definition.get("description") if definition else meta.get("description"),
        "unit": definition.get("unit") if definition and definition.get("unit") else TRACE_CHANNEL_UNITS.get(name),
        "type": definition_type,
        "count": definition.get("count", 1) if definition else 1,
        "is_raw": is_raw,
        "is_calculated": is_calculated,
        "is_proxy": name in FORCE_PROXY_CHANNELS,
        "formula": meta.get("formula"),
        "dependencies": meta.get("dependencies", []),
        "used_by_charts": meta.get("used_by_charts", []),
        "used_by_events": meta.get("used_by_events", []),
        "used_by_recommendations": meta.get("used_by_recommendations", []),
        "missing_status": missing_status,
        **stats,
    }
    if name in FORCE_PROXY_CHANNELS:
        item["is_proxy"] = True
        if not item.get("description") or "ESTIMATE" not in str(item.get("description", "")):
            item["description"] = f"ESTIMATE — {FORCE_PROXY_WARNING}"
    return item


def _build_summary_item(
    name: str,
    definition: dict[str, Any] | None,
    is_raw: bool,
    is_calculated: bool,
    in_column_set: bool,
) -> dict[str, Any]:
    meta = channel_metadata(name)
    missing_status = _missing_status(name, definition, is_calculated, in_column_set)
    definition_type = _definition_type_for(definition, is_calculated)
    return {
        "name": name,
        "label": meta.get("label", name),
        "description": definition.get("description") if definition else meta.get("description"),
        "unit": definition.get("unit") if definition and definition.get("unit") else TRACE_CHANNEL_UNITS.get(name),
        "type": definition_type,
        "count": definition.get("count", 1) if definition else 1,
        "is_raw": is_raw,
        "is_calculated": is_calculated,
        "is_proxy": name in FORCE_PROXY_CHANNELS,
        "formula": None,
        "dependencies": [],
        "used_by_charts": [],
        "used_by_events": [],
        "used_by_recommendations": [],
        "min": None,
        "max": None,
        "mean": None,
        "sample_value": None,
        "missing_status": missing_status,
        "group": "raw" if is_raw and not is_calculated else "calculated" if is_calculated else "derived",
        "source": "raw" if definition is not None else "calculated" if is_calculated else "derived",
    }


def build_channel_catalog(run_id: str, data_dir: str | Path | None = None) -> list[dict[str, Any]]:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    key = _cache_key(data_root, run_id)
    source_signature = _source_signature(parquet_path(data_root, run_id), csv_path(data_root, run_id))
    signature = None if source_signature is None else (*source_signature, _CHANNEL_SCHEMA_VERSION)
    with _TELEMETRY_ROWS_CACHE_LOCK:
        entry = _CHANNEL_CATALOG_CACHE.get(key)
        if entry is not None and entry.signature == signature:
            entry.last_access = time.time()
            return entry.catalog

    path = parquet_path(data_root, run_id)
    if path.exists() and importlib.util.find_spec("polars") is not None:
        stats_map, columns = _precompute_channel_stats_from_parquet(path)
    else:
        rows = read_telemetry_rows(run_id, data_dir)
        stats_map = _precompute_channel_stats(rows)
        columns = list(stats_map.keys())
    column_set = set(columns)
    definitions = {definition["name"]: definition for definition in read_channel_metadata(run_id, data_dir)}
    catalog_names = list(definitions)
    catalog_names.extend(name for name in HIGH_VALUE_RAW_CHANNELS if name not in catalog_names)
    catalog_names.extend(name for name in columns if name not in catalog_names)
    catalog_names.extend(name for name in CALCULATED_CHANNEL_UNITS if name not in catalog_names)

    catalog: list[dict[str, Any]] = []
    for name in catalog_names:
        definition = definitions.get(name)
        is_raw = definition is not None or name in HIGH_VALUE_RAW_CHANNELS
        is_calculated = name in CALCULATED_CHANNEL_UNITS or (not is_raw and name in column_set)
        catalog.append(_build_catalog_item(name, definition, is_raw, is_calculated, name in column_set, stats_map))

    with _TELEMETRY_ROWS_CACHE_LOCK:
        _CHANNEL_CATALOG_CACHE[key] = _ChannelCatalogCacheEntry(
            signature=signature,
            catalog=catalog,
            last_access=time.time(),
        )
        _evict_channel_catalog_if_needed()
    return catalog


def build_channel_summary(run_id: str, data_dir: str | Path | None = None) -> list[dict[str, Any]]:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    key = _cache_key(data_root, run_id)
    source_signature = _source_signature(parquet_path(data_root, run_id), csv_path(data_root, run_id))
    signature = None if source_signature is None else (*source_signature, _CHANNEL_SCHEMA_VERSION)
    with _TELEMETRY_ROWS_CACHE_LOCK:
        entry = _CHANNEL_SUMMARY_CACHE.get(key)
        if entry is not None and entry.signature == signature:
            entry.last_access = time.time()
            return entry.summary

    path = parquet_path(data_root, run_id)
    columns: list[str]
    if path.exists() and importlib.util.find_spec("polars") is not None:
        pl = importlib.import_module("polars")
        columns = list(pl.read_parquet_schema(path).keys())
    else:
        rows = read_telemetry_rows(run_id, data_dir)
        columns = list(rows[0].keys()) if rows else []

    column_set = set(columns)
    definitions = {definition["name"]: definition for definition in read_channel_metadata(run_id, data_dir)}
    catalog_names = list(definitions)
    catalog_names.extend(name for name in HIGH_VALUE_RAW_CHANNELS if name not in catalog_names)
    catalog_names.extend(name for name in columns if name not in catalog_names)
    catalog_names.extend(name for name in CALCULATED_CHANNEL_UNITS if name not in catalog_names)

    summary: list[dict[str, Any]] = []
    for name in catalog_names:
        definition = definitions.get(name)
        is_raw = definition is not None or name in HIGH_VALUE_RAW_CHANNELS
        is_calculated = name in CALCULATED_CHANNEL_UNITS or (not is_raw and name in column_set)
        summary.append(_build_summary_item(name, definition, is_raw, is_calculated, name in column_set))

    with _TELEMETRY_ROWS_CACHE_LOCK:
        _CHANNEL_SUMMARY_CACHE[key] = _ChannelSummaryCacheEntry(
            signature=signature,
            summary=summary,
            last_access=time.time(),
        )
        _evict_channel_summary_if_needed()
    return summary


def _row_delta(row: dict[str, Any], event: TelemetryEvent) -> float | None:
    event_pct = event.lap_pct_peak
    event_distance_m = event.distance_m_peak
    if event_pct is not None:
        row_pct = row.get("lap_dist_pct_100")
        if row_pct is None and row.get("lap_dist_pct") is not None:
            raw_pct = _numeric_value(row.get("lap_dist_pct"))
            row_pct = raw_pct * 100.0 if raw_pct is not None and raw_pct <= 1.5 else raw_pct
        if row_pct is not None:
            return abs(float(row_pct) - event_pct)
    if event_distance_m is not None and row.get("lap_dist_m") is not None:
        return abs(float(row["lap_dist_m"]) - event_distance_m)
    return None


def _nearest_event_indices(rows: list[dict[str, Any]], events: list[TelemetryEvent] | None) -> set[int]:
    indices: set[int] = set()
    if not events:
        return indices
    for event in events:
        best_index: int | None = None
        best_delta: float | None = None
        for index, row in enumerate(rows):
            delta = _row_delta(row, event)
            if delta is not None and (best_delta is None or delta < best_delta):
                best_delta = delta
                best_index = index
        if best_index is not None:
            indices.add(best_index)
    return indices


def _bucket_downsample(
    rows: list[dict[str, Any]],
    bucket_size: int,
    channels: list[str],
    events: list[TelemetryEvent] | None = None,
) -> list[dict[str, Any]]:
    if bucket_size <= 1 or len(rows) <= bucket_size:
        return rows

    preserve_channels = list(dict.fromkeys([*channels, *PRESERVE_EXTREMA_CHANNELS]))
    indices: set[int] = {0, len(rows) - 1}
    indices.update(_nearest_event_indices(rows, events))

    for start in range(0, len(rows), bucket_size):
        end = min(len(rows), start + bucket_size)
        bucket = rows[start:end]
        if not bucket:
            continue
        indices.add(start)
        indices.add(end - 1)
        for channel in preserve_channels:
            numeric = [(index + start, _numeric_value(row.get(channel))) for index, row in enumerate(bucket)]
            numeric_clean = [(index, value) for index, value in numeric if value is not None]
            if not numeric_clean:
                continue
            indices.add(min(numeric_clean, key=lambda item: item[1])[0])
            indices.add(max(numeric_clean, key=lambda item: item[1])[0])

    return [rows[index] for index in sorted(indices)]


def bucket_downsample(
    rows: list[dict[str, Any]],
    bucket_size: int,
    channels: list[str],
    events: list[TelemetryEvent] | None = None,
) -> list[dict[str, Any]]:
    """Public wrapper for extrema-preserving bucket downsampling."""
    return _bucket_downsample(rows, bucket_size, channels, events=events)


def _resolve_bucket_size(row_count: int, downsample: int | str | None) -> tuple[int, int | str]:
    if downsample is None:
        return 1, 1
    if isinstance(downsample, str) and downsample.lower() == "auto":
        bucket_size = max(1, math.ceil(row_count / 1200))
        return bucket_size, "auto"
    try:
        bucket_size = max(1, int(downsample))
    except (TypeError, ValueError):
        bucket_size = 1
    return bucket_size, bucket_size


def _trace_channel_payload(rows: list[dict[str, Any]], channel: str) -> dict[str, Any]:
    stats = _channel_stats(rows, channel)
    return {
        "unit": TRACE_CHANNEL_UNITS.get(channel),
        "values": [row.get(channel) for row in rows],
        "missing_status": None if any(row.get(channel) is not None for row in rows) else "Channel unavailable for this run or lap.",
        **{key: stats[key] for key in ("min", "max", "mean")},
    }


def build_trace_payload(
    run_id: str,
    lap: int | None = None,
    channels: list[str] | None = None,
    downsample: int | str | None = 1,
    x_axis: str | None = None,
    preserve_extrema: bool = False,
    events: list[TelemetryEvent] | None = None,
    data_dir: str | Path | None = None,
) -> dict[str, Any]:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    selected_channels = channels or TRACE_DEFAULT_CHANNELS

    # Fast path: use column pruning to read only needed channels from parquet
    if importlib.util.find_spec("polars") is not None:
        pl = importlib.import_module("polars")
        path = parquet_path(data_root, run_id)
        if path.exists():
            needed_cols = list(dict.fromkeys(
                [c for c in selected_channels + (["lap", "lap_dist_ft", "lap_dist_pct", "session_time", "lap_dist_pct_100"] if x_axis else ["lap"])]
            ))
            # Only request columns that actually exist in the parquet file
            existing = set(pl.read_parquet_schema(path).keys())
            safe_cols = [c for c in needed_cols if c in existing]
            df = pl.read_parquet(path, columns=safe_cols) if safe_cols else pl.read_parquet(path)
            if lap is not None:
                df = df.filter(pl.col("lap") == lap)
            rows = df.to_dicts()
        else:
            rows = read_telemetry_rows(run_id, data_dir)
            if lap is not None:
                rows = [row for row in rows if row.get("lap") == lap]
    else:
        rows = read_telemetry_rows(run_id, data_dir)
        if lap is not None:
            rows = [row for row in rows if row.get("lap") == lap]

    selected_channels = channels or TRACE_DEFAULT_CHANNELS
    bucket_size, downsample_label = _resolve_bucket_size(len(rows), downsample)
    if bucket_size > 1:
        rows = (
            _bucket_downsample(rows, bucket_size, selected_channels, events=events)
            if preserve_extrema
            else rows[::bucket_size]
        )

    if x_axis:
        x_unit = TRACE_CHANNEL_UNITS.get(x_axis)
        return {
            "run_id": run_id,
            "lap": lap,
            "x_name": x_axis,
            "x_unit": x_unit,
            "x": [row.get(x_axis) for row in rows],
            "x_by_name": {
                "lap_dist_pct": [row.get("lap_dist_pct") for row in rows],
                "lap_dist_ft": [row.get("lap_dist_ft") for row in rows],
                "session_time": [row.get("session_time") for row in rows],
                "lap_dist_pct_100": [row.get("lap_dist_pct_100") for row in rows],
            },
            "channels": {channel: _trace_channel_payload(rows, channel) for channel in selected_channels},
            "events": [event.model_dump(mode="json") for event in events or []],
            "sample_count": len(rows),
            "downsample": downsample_label,
            "preserve_extrema": preserve_extrema,
        }

    return {
        "run_id": run_id,
        "lap": lap,
        "x": {"lap_dist_pct": [row.get("lap_dist_pct") for row in rows]},
        "channels": {
            channel: [row.get(channel) for row in rows]
            for channel in selected_channels
        },
        "sample_count": len(rows),
        "downsample": downsample_label,
    }


class ImportService:
    def __init__(self, db_path: str | Path | None = None, data_dir: str | Path | None = None):
        self.repository = RaceLabRepository(db_path)
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.last_import_timings: dict[str, float] = {}

    def import_ibt_file(
        self,
        path: str | Path,
    ) -> tuple[IBTImportResult, TelemetryCacheResult | None]:
        _log = logging.getLogger(__name__)
        t0 = time.perf_counter()
        result = import_ibt(path)
        _timings: dict[str, Any] = {"decode_ibt": time.perf_counter() - t0}
        for k, v in (getattr(ibt_mod, "LAST_IMPORT_PROFILE", {}) or {}).items():
            if isinstance(v, (int, float)):
                _timings[f"decode_sub_{k}"] = float(v)
            elif isinstance(v, str) and k == "frame_to_rows_reason":
                _timings[f"decode_sub_{k}"] = v  # type: ignore[assignment]
            elif isinstance(v, str) and k == "overview_legacy_consumers_remaining":
                _timings[f"decode_sub_{k}"] = v  # type: ignore[assignment]

        if result.overview is None:
            self.last_import_timings = dict(_timings)
            return result, None

        run_id = result.overview.run_id
        existing_run_updated = self.repository.get_overview(run_id) is not None

        t0 = time.perf_counter()
        cache_profile: dict[str, float] = {}
        normalized_frame = getattr(result, "get_normalized_frame", lambda: None)()
        staged_cache = _stage_import_cache(
            run_id,
            result.records,
            result.variable_definitions,
            normalized_frame=normalized_frame,
            data_dir=self.data_dir,
            profile_out=cache_profile,
        )
        _timings["write_parquet_cache"] = time.perf_counter() - t0
        for k, v in cache_profile.items():
            _timings[k] = float(v)

        try:
            t0 = time.perf_counter()
            self.repository.save_import(result.overview, result.fingerprint)
            _timings["save_run_metadata"] = time.perf_counter() - t0

            t0 = time.perf_counter()
            cache_result = staged_cache.promote()
            _timings["promote_cache_artifacts"] = time.perf_counter() - t0
        except Exception:
            staged_cache.cleanup()
            raise

        # ── Post-import analysis ──────────────────────────────────
        rows_or_frame: Any = normalized_frame if normalized_frame is not None else result.records
        # 1. Build and persist segments
        t0 = time.perf_counter()
        try:
            from racelab_engine.analysis.segments import build_fixed_pct_segments
            from racelab_engine.models.segment import SegmentSummary as ModelSegment
            segment_profile: dict[str, float] = {}
            if raw_segments := build_fixed_pct_segments(rows_or_frame, run_id=run_id, profile_out=segment_profile):
                model_segments = [
                    ModelSegment(**seg.model_dump()) for seg in raw_segments
                ]
                self.repository.save_segments(run_id, model_segments)
                _log.info("Saved %d segments for run %s", len(model_segments), run_id)
            for k, v in segment_profile.items():
                _timings[f"segment_sub_{k}"] = float(v)
        except Exception as exc:
            _log.warning("Segment persistence failed for run %s: %s", run_id, exc)
        _timings["segment_building"] = time.perf_counter() - t0

        numeric_timings = [(k, v) for k, v in _timings.items() if isinstance(v, (int, float))]
        _log.info(
            "Import stage timings for %s: %s",
            run_id,
            " | ".join(f"{k}={float(v):.2f}s" for k, v in sorted(numeric_timings, key=lambda x: -float(x[1]))),
        )
        self.last_import_timings = dict(_timings)

        implemented = list(result.status.implemented)
        for item in ["SQLite persistence", f"telemetry cache persistence ({cache_result.format})",
                      "segment persistence"]:
            if item not in implemented:
                implemented.append(item)
        status_message = "Existing run updated." if existing_run_updated else (
            "Imported and persisted iRacing .ibt header, variable definitions, "
            "session YAML, MVP telemetry channels, analysis summaries, "
            "telemetry cache, and segments."
        )
        warnings = list(result.status.warnings)
        if existing_run_updated:
            warnings.append("Duplicate telemetry detected - updated the existing run record.")
        result.status = result.status.model_copy(
            update={
                "message": status_message,
                "implemented": implemented,
                "warnings": warnings,
                "remaining": [
                    item for item in result.status.remaining if item != "persist normalized telemetry cache"
                ],
            }
        )
        return result, cache_result
