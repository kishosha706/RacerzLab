from __future__ import annotations

import csv
import ctypes
import hashlib
import importlib.util
import json
import logging
import math
import os
import sys
import time
import uuid
from bisect import bisect_left
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any

from racelab_engine.analysis.calculated_channels import (
    CALCULATED_CHANNEL_UNITS,
    HIGH_VALUE_RAW_CHANNELS,
    channel_metadata,
    normalize_telemetry_rows,
)
from racelab_engine.analysis.channel_registry import canonical_name
from racelab_engine.analysis.constants import (
    CALCULATED_PROXY_CHANNELS,
    DIFFUSER_GEOMETRY_PROXY_CHANNELS,
    FORCE_PROXY_CHANNELS,
    FORCE_PROXY_WARNING,
)
from racelab_engine.analysis.ride_height_calibration import (
    apply_next_gen_lr_ride_height_offset_to_rows,
    trace_offset_metadata,
)
from racelab_engine.io import ibt_reader as ibt_mod
from racelab_engine.io.ibt_reader import import_ibt
from racelab_engine.io.ibt_types import (
    IBTHeader,
    IBTImportResult,
    IBTVariableDefinition,
)
from racelab_engine.io.telemetry_manifest import (
    assess_cache_compatibility,
    build_telemetry_manifest,
    compact_capability_summary,
)
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.recording_identity import (
    canonical_recording_run_id,
    normalize_source_sha256,
)
from racelab_engine.storage.repository import RaceLabRepository

TRACE_DEFAULT_CHANNELS = [
    "speed_mph",
    "rpm",
    "throttle_pct",
    "brake_pct",
    "cfs_ride_height_mm",
]

TRACE_AUTO_POINT_BUDGET = 1200

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
    "car_distance_ahead_m": "m",
    "car_distance_behind_m": "m",
    "lf_brake_line_pressure_bar": "bar",
    "rf_brake_line_pressure_bar": "bar",
    "lr_brake_line_pressure_bar": "bar",
    "rr_brake_line_pressure_bar": "bar",
    "lf_tire_distance_m": "m",
    "rf_tire_distance_m": "m",
    "lr_tire_distance_m": "m",
    "rr_tire_distance_m": "m",
    "brake_abs_cut_01": "ratio",
    "steering_wheel_torque_nm": "N*m",
    "steering_wheel_torque_subtick_nm": "N*m",
    "steering_wheel_torque_unsigned_01": "ratio",
    "steering_wheel_torque_signed_01": "ratio",
    "steering_wheel_torque_stops_01": "ratio",
    "channel_latency_s": "s",
    "channel_average_latency_s": "s",
    "memory_page_faults_per_s": "faults/s",
    "memory_soft_page_faults_per_s": "faults/s",
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

LR_RIDE_HEIGHT_OFFSET_DEPENDENCIES = {
    "lf_ride_height_in",
    "rf_ride_height_in",
    "lr_ride_height_in",
    "rr_ride_height_in",
    "lr_ride_height_mm",
    "rr_ride_height_mm",
    "cfs_ride_height_in",
    "cfs_risk_score",
    "platform_risk_score",
}

LR_RIDE_HEIGHT_OFFSET_DERIVED_CHANNELS = {
    "lr_ride_height_in",
    "lr_ride_height_mm",
    "rear_avg_rh_in",
    "left_avg_rh_in",
    "right_avg_rh_in",
    "center_rake_fs_in",
    "side_rake_in",
    "rear_split_in",
    "rear_min_ride_height_mm",
    "rear_min_ride_height_in",
    "rear_scrape_margin_mm",
    "rear_scrape_risk_score",
    "rear_platform_contact_risk",
    "rear_scrape_side",
    "rear_scrape_side_label",
    "rear_platform_risk_score",
    "whole_car_bottoming_risk",
    "platform_balance_label",
    "platform_balance_explanation",
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


class TelemetryArtifactIdentityError(RuntimeError):
    """Raised when persisted telemetry artifacts no longer share one owner."""


@dataclass
class _StagedImportCache:
    temp_run_id: str
    cache_result: TelemetryCacheResult
    metadata_path: Path
    manifest_path: Path
    final_cache_path: Path
    alternate_cache_path: Path
    final_metadata_path: Path
    final_manifest_path: Path
    data_root: Path
    run_id: str
    raw_archive_columns: dict[str, str]
    expected_record_count: int | None
    array_element_counts: dict[str, int]
    backups: dict[Path, Path] | None = None
    promoted_destinations: list[Path] | None = None

    def cleanup(self) -> None:
        _safe_unlink(self.cache_result.path)
        _safe_unlink(self.metadata_path)
        _safe_unlink(self.manifest_path)

    def _artifacts(self) -> tuple[tuple[Path, Path], ...]:
        return (
            (self.cache_result.path, self.final_cache_path),
            (self.metadata_path, self.final_metadata_path),
            (self.manifest_path, self.final_manifest_path),
        )

    def rollback(self) -> None:
        for destination in reversed(self.promoted_destinations or []):
            _safe_unlink(destination)
        for destination, backup in (self.backups or {}).items():
            if backup.exists():
                try:
                    os.replace(backup, destination)
                except OSError:
                    logging.getLogger(__name__).exception(
                        "Could not restore cache artifact %s from %s", destination, backup
                    )
        self.promoted_destinations = []
        self.backups = {}
        _invalidate_run_cache(self.data_root, self.run_id)

    def commit(self) -> None:
        for backup in (self.backups or {}).values():
            _safe_unlink(backup)
        self.backups = {}
        self.promoted_destinations = []

    def promote(self) -> TelemetryCacheResult:
        _assert_declared_channels_archived(
            self.cache_result,
            self.raw_archive_columns,
            expected_record_count=self.expected_record_count,
            array_element_counts=self.array_element_counts,
        )
        self.backups = {}
        self.promoted_destinations = []
        try:
            backup_destinations = [destination for _source, destination in self._artifacts()]
            if self.alternate_cache_path not in backup_destinations:
                backup_destinations.append(self.alternate_cache_path)
            for destination in backup_destinations:
                if destination.exists():
                    backup = _temp_cache_path(destination, f"{self.run_id}.backup")
                    _atomic_replace(destination, backup)
                    self.backups[destination] = backup
            for source, destination in self._artifacts():
                _atomic_replace(source, destination)
                self.promoted_destinations.append(destination)
        except Exception:
            self.rollback()
            raise
        _invalidate_run_cache(self.data_root, self.run_id)
        return TelemetryCacheResult(
            path=self.final_cache_path,
            format=self.cache_result.format,
            used_fallback=self.cache_result.used_fallback,
        )


@dataclass
class _TelemetryRowsCacheEntry:
    signature: tuple[Any, ...]
    rows: list[dict[str, Any]]
    size_bytes: int
    last_access: float


_NORMALIZED_BASE_COLUMNS = ("speed_mph", "lap_dist_pct", "session_time")
_NORMALIZED_CALCULATED_COLUMNS = ("cfs_risk_score", "drag_scrub_suspicion", "platform_compression_index")
_TELEMETRY_ROWS_CACHE: dict[tuple[str, str], _TelemetryRowsCacheEntry] = {}
_TELEMETRY_ROWS_CACHE_LOCK = RLock()
_TELEMETRY_ROWS_CACHE_MAX = 24
_TELEMETRY_ROWS_CACHE_MAX_BYTES = 128 * 1024 * 1024
_TELEMETRY_ROWS_CACHE_MAX_ENTRY_BYTES = 32 * 1024 * 1024


@dataclass
class _ProjectedTelemetryCacheEntry:
    frame: Any
    size_bytes: int
    last_access: float


# Unlike the legacy whole-row cache, this cache retains compact Polars frames
# and converts them to fresh dictionaries for every caller.  The byte budget is
# intentionally small enough to prevent wide, long telemetry runs from turning
# endpoint acceleration into unbounded resident memory.
_PROJECTED_TELEMETRY_CACHE: dict[
    tuple[Any, ...],
    _ProjectedTelemetryCacheEntry,
] = {}
_PROJECTED_TELEMETRY_CACHE_MAX = 24
_PROJECTED_TELEMETRY_CACHE_MAX_BYTES = 128 * 1024 * 1024
_PROJECTED_TELEMETRY_CACHE_MAX_ENTRY_BYTES = 32 * 1024 * 1024


@dataclass
class _ChannelCatalogCacheEntry:
    signature: tuple[Any, ...] | None
    catalog: list[dict[str, Any]]
    size_bytes: int
    last_access: float


_CHANNEL_CATALOG_CACHE: dict[tuple[str, str], _ChannelCatalogCacheEntry] = {}
_CHANNEL_CATALOG_CACHE_MAX = 16
_CHANNEL_CATALOG_CACHE_MAX_BYTES = 16 * 1024 * 1024
_CHANNEL_CATALOG_CACHE_MAX_ENTRY_BYTES = 4 * 1024 * 1024


@dataclass
class _ChannelSummaryCacheEntry:
    signature: tuple[Any, ...] | None
    summary: list[dict[str, Any]]
    size_bytes: int
    last_access: float


_CHANNEL_SUMMARY_CACHE: dict[tuple[str, str], _ChannelSummaryCacheEntry] = {}
_CHANNEL_SUMMARY_CACHE_MAX = 24
_CHANNEL_SUMMARY_CACHE_MAX_BYTES = 12 * 1024 * 1024
_CHANNEL_SUMMARY_CACHE_MAX_ENTRY_BYTES = 2 * 1024 * 1024
_CHANNEL_SCHEMA_VERSION = "v5-p3541-truth-provenance"

def default_data_dir() -> Path:
    return Path(os.environ.get("RACELAB_DATA_DIR", "data"))


def parquet_path(data_dir: Path, run_id: str) -> Path:
    return data_dir / "cache" / "parquet" / f"{run_id}.parquet"


def csv_path(data_dir: Path, run_id: str) -> Path:
    return data_dir / "cache" / "normalized" / f"{run_id}.csv"


def channel_metadata_path(data_dir: Path, run_id: str) -> Path:
    return data_dir / "cache" / "normalized" / f"{run_id}.channels.json"


def telemetry_manifest_path(data_dir: Path, run_id: str) -> Path:
    return data_dir / "cache" / "normalized" / f"{run_id}.telemetry-manifest.json"


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


def _archived_columns(cache_result: TelemetryCacheResult) -> set[str]:
    if cache_result.format == "parquet":
        if importlib.util.find_spec("polars") is None:
            raise RuntimeError("Cannot verify Parquet archive completeness without Polars.")
        pl = __import__("polars")
        return set(pl.read_parquet_schema(cache_result.path))
    with cache_result.path.open("r", newline="", encoding="utf-8") as file_obj:
        return set(next(csv.reader(file_obj), []))


def _assert_declared_channels_archived(
    cache_result: TelemetryCacheResult,
    raw_archive_columns: dict[str, str] | tuple[str, ...] | list[str],
    *,
    expected_record_count: int | None = None,
    array_element_counts: dict[str, int] | None = None,
) -> None:
    """Block promotion unless every file-declared raw channel exists physically."""

    archived = _archived_columns(cache_result)
    mapping = (
        raw_archive_columns
        if isinstance(raw_archive_columns, dict)
        else {name: name for name in raw_archive_columns}
    )
    if len(set(mapping.values())) != len(mapping):
        raise RuntimeError("Telemetry archive invariant failed: raw archive columns are not unique.")
    missing = sorted(raw_name for raw_name, column in mapping.items() if column not in archived)
    if missing:
        preview = ", ".join(missing[:8])
        suffix = "..." if len(missing) > 8 else ""
        raise RuntimeError(
            "Telemetry archive invariant failed: "
            f"{len(missing)} declared raw channel(s) are missing from the staged cache: {preview}{suffix}"
        )
    if cache_result.format == "parquet":
        pl = __import__("polars")
        actual_record_count = int(
            pl.scan_parquet(cache_result.path).select(pl.len()).collect().item()
        )
        if expected_record_count is not None and actual_record_count != expected_record_count:
            raise RuntimeError(
                "Telemetry archive invariant failed: "
                f"expected {expected_record_count} records but staged cache contains {actual_record_count}."
            )
        null_aliases = {
            raw_name: f"__null_{index}"
            for index, raw_name in enumerate(mapping)
        }
        null_row = (
            pl.scan_parquet(cache_result.path)
            .select(
                pl.col(archive_column).null_count().alias(null_aliases[raw_name])
                for raw_name, archive_column in mapping.items()
            )
            .collect()
            .to_dicts()[0]
            if mapping
            else {}
        )
        null_channels = {
            raw_name: int(null_row[alias])
            for raw_name, alias in null_aliases.items()
            if int(null_row[alias]) > 0
        }
        if null_channels:
            details = ", ".join(
                f"{name} ({count})" for name, count in sorted(null_channels.items())
            )
            raise RuntimeError(
                "Telemetry archive invariant failed: declared raw channels contain null records: "
                + details
            )
        for raw_name, expected_count in (array_element_counts or {}).items():
            archive_column = mapping[raw_name]
            malformed_count = int(
                pl.scan_parquet(cache_result.path)
                .select(
                    (
                        pl.col(archive_column).is_null()
                        | (pl.col(archive_column).list.len() != expected_count)
                        | pl.col(archive_column)
                        .list.eval(pl.element().is_null())
                        .list.any()
                        .fill_null(True)
                    )
                    .sum()
                )
                .collect()
                .item()
            )
            if malformed_count:
                raise RuntimeError(
                    "Telemetry archive invariant failed: "
                    f"{raw_name} has {malformed_count} malformed array record(s); "
                    f"expected {expected_count} elements per record."
                )
    elif expected_record_count is not None:
        with cache_result.path.open("r", newline="", encoding="utf-8") as file_obj:
            actual_record_count = max(0, sum(1 for _line in file_obj) - 1)
        if actual_record_count != expected_record_count:
            raise RuntimeError(
                "Telemetry archive invariant failed: "
                f"expected {expected_record_count} records but staged cache contains {actual_record_count}."
            )


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
        _invalidate_channel_context_cache(data_root, run_id)
        return final_path
    except Exception:
        _safe_unlink(path)
        raise


def read_channel_metadata(run_id: str, data_dir: str | Path | None = None) -> list[dict[str, Any]]:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    path = channel_metadata_path(data_root, run_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def write_telemetry_manifest(
    run_id: str,
    header: IBTHeader,
    definitions: list[IBTVariableDefinition],
    frame: Any,
    session_yaml: str | None = None,
    raw_archive_columns: dict[str, str] | None = None,
    data_dir: str | Path | None = None,
    staged: bool = False,
    *,
    manifest_run_id: str | None = None,
    source_file_sha256: str | None = None,
    source_file_size_bytes: int | None = None,
    telemetry_cache_sha256: str | None = None,
    analysis_engine: str | None = None,
    decoder_path: str | None = None,
    decoder_fallback_reason: str | None = None,
) -> Path:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    final_path = telemetry_manifest_path(data_root, run_id)
    path = _temp_cache_path(final_path, run_id)
    try:
        path.write_text(
            json.dumps(
                build_telemetry_manifest(
                    header,
                    definitions,
                    frame,
                    session_yaml,
                    raw_archive_columns,
                    run_id=manifest_run_id or run_id,
                    source_file_sha256=source_file_sha256,
                    source_file_size_bytes=source_file_size_bytes,
                    telemetry_cache_sha256=telemetry_cache_sha256,
                    analysis_engine=analysis_engine,
                    decoder_path=decoder_path,
                    decoder_fallback_reason=decoder_fallback_reason,
                ),
                indent=2,
            ),
            encoding="utf-8",
        )
        if staged:
            return path
        _atomic_replace(path, final_path)
        _invalidate_channel_context_cache(data_root, run_id)
        return final_path
    except Exception:
        _safe_unlink(path)
        raise


def read_telemetry_manifest(run_id: str, data_dir: str | Path | None = None) -> dict[str, Any]:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    path = telemetry_manifest_path(data_root, run_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def build_telemetry_capability_payload(
    run_id: str,
    data_dir: str | Path | None = None,
    *,
    expected_source_file_sha256: str | None = None,
) -> dict[str, Any]:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    manifest = dict(read_telemetry_manifest(run_id, data_root))
    cache_source = _telemetry_cache_source(data_root, run_id)
    cache_present = cache_source is not None
    if not manifest and not cache_present:
        return {}
    identity = _telemetry_artifact_identity(
        manifest,
        requested_run_id=run_id,
        expected_source_file_sha256=expected_source_file_sha256,
        cache_source=cache_source,
    )
    if identity["status"] != "verified":
        unavailable: dict[str, Any] = {
            # This is response-envelope identity only. No manifest content is
            # relabelled when artifact identity cannot be verified.
            "run_id": run_id,
            "manifest_identity": identity,
            "cache_compatibility": assess_cache_compatibility(
                {},
                cache_present=cache_present,
            ),
            "capabilities": [],
            "channels": [],
        }
        unavailable["capability_summary"] = compact_capability_summary(unavailable)
        return unavailable
    manifest["manifest_identity"] = identity
    manifest["cache_compatibility"] = assess_cache_compatibility(
        manifest,
        cache_present=cache_present,
    )
    manifest["capability_summary"] = compact_capability_summary(manifest)
    manifest.setdefault("capabilities", [])
    manifest.setdefault("channels", [])
    return manifest


def _persist_minimal_cache_identity(
    data_root: Path,
    run_id: str,
    cache_result: TelemetryCacheResult,
) -> TelemetryCacheResult:
    """Make every newly written cache self-identifying before it can be read."""
    _invalidate_run_cache(data_root, run_id)
    final_path = telemetry_manifest_path(data_root, run_id)
    temp_path = _temp_cache_path(final_path, run_id)
    try:
        temp_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "telemetry_cache_sha256": _sha256_file(cache_result.path),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        _atomic_replace(temp_path, final_path)
        _invalidate_channel_context_cache(data_root, run_id)
        return cache_result
    except Exception:
        _safe_unlink(temp_path)
        _safe_unlink(cache_result.path)
        raise


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
            return _persist_minimal_cache_identity(
                data_root,
                run_id,
                TelemetryCacheResult(path=path, format="parquet", used_fallback=False),
            )

        if not rows:
            pl.DataFrame().write_parquet(path)
            return _persist_minimal_cache_identity(
                data_root,
                run_id,
                TelemetryCacheResult(path=path, format="parquet", used_fallback=False),
            )

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
        return _persist_minimal_cache_identity(
            data_root,
            run_id,
            TelemetryCacheResult(path=path, format="parquet", used_fallback=False),
        )

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
        return _persist_minimal_cache_identity(
            data_root,
            run_id,
            TelemetryCacheResult(path=path, format="parquet", used_fallback=False),
        )
    cache_result = _write_csv(rows, csv_path(data_root, run_id))
    return _persist_minimal_cache_identity(data_root, run_id, cache_result)


def _stage_import_cache(
    run_id: str,
    rows: list[dict[str, Any]],
    definitions: list[IBTVariableDefinition],
    *,
    header: IBTHeader,
    session_yaml: str | None,
    raw_archive_columns: dict[str, str],
    normalized_frame: Any | None,
    data_dir: str | Path,
    source_file_sha256: str | None,
    source_file_size_bytes: int | None,
    analysis_engine: str,
    decoder_path: str,
    decoder_fallback_reason: str | None,
    profile_out: dict[str, float] | None = None,
) -> _StagedImportCache:
    data_root = Path(data_dir)
    temp_run_id = f".{run_id}.{uuid.uuid4().hex}.tmp"
    cache_result: TelemetryCacheResult | None = None
    try:
        cache_result = write_telemetry_cache(
            temp_run_id,
            rows,
            normalized_frame=normalized_frame,
            data_dir=data_root,
            profile_out=profile_out,
        )
        declared_raw_names = tuple(definition.name for definition in definitions)
        archive_mapping = {
            name: raw_archive_columns.get(name, name)
            for name in declared_raw_names
        }
        canonical_targets = {
            canonical
            for definition in definitions
            if (canonical := canonical_name(definition.name)) is not None
        }
        unsafe_collisions = sorted(
            raw_name
            for raw_name, archive_column in archive_mapping.items()
            if raw_name in canonical_targets and archive_column == raw_name
        )
        if unsafe_collisions:
            raise RuntimeError(
                "Telemetry archive invariant failed: raw/canonical namespace collision for "
                + ", ".join(unsafe_collisions)
            )
        array_element_counts = {
            definition.name: definition.count
            for definition in definitions
            if definition.count > 1 and definition.data_type_id != 0
        }
        _assert_declared_channels_archived(
            cache_result,
            archive_mapping,
            expected_record_count=header.record_count,
            array_element_counts=array_element_counts,
        )
        metadata_path = write_channel_metadata(temp_run_id, definitions, data_root)
        manifest_frame = normalized_frame
        if manifest_frame is None and importlib.util.find_spec("polars") is not None:
            pl = importlib.import_module("polars")
            manifest_frame = pl.from_dicts(rows, infer_schema_length=None) if rows else pl.DataFrame()
        manifest_path = write_telemetry_manifest(
            temp_run_id,
            header,
            definitions,
            manifest_frame,
            session_yaml,
            archive_mapping,
            data_root,
            manifest_run_id=run_id,
            source_file_sha256=source_file_sha256,
            source_file_size_bytes=source_file_size_bytes,
            telemetry_cache_sha256=_sha256_file(cache_result.path),
            analysis_engine=analysis_engine,
            decoder_path=decoder_path,
            decoder_fallback_reason=decoder_fallback_reason,
        )
    except Exception:
        _safe_unlink(cache_result.path if cache_result is not None else None)
        _safe_unlink(parquet_path(data_root, temp_run_id))
        _safe_unlink(csv_path(data_root, temp_run_id))
        _safe_unlink(locals().get("metadata_path"))
        _safe_unlink(locals().get("manifest_path"))
        _safe_unlink(telemetry_manifest_path(data_root, temp_run_id))
        raise

    assert cache_result is not None

    final_cache_path = parquet_path(data_root, run_id) if cache_result.format == "parquet" else csv_path(data_root, run_id)
    return _StagedImportCache(
        temp_run_id=temp_run_id,
        cache_result=cache_result,
        metadata_path=metadata_path,
        manifest_path=manifest_path,
        final_cache_path=final_cache_path,
        alternate_cache_path=(
            csv_path(data_root, run_id)
            if cache_result.format == "parquet"
            else parquet_path(data_root, run_id)
        ),
        final_metadata_path=channel_metadata_path(data_root, run_id),
        final_manifest_path=telemetry_manifest_path(data_root, run_id),
        data_root=data_root,
        run_id=run_id,
        raw_archive_columns=archive_mapping,
        expected_record_count=header.record_count,
        array_element_counts=array_element_counts,
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


_FILE_IDENTITY_SAMPLE_BYTES = 16 * 1024
_FILE_IDENTITY_SAMPLE_COUNT = 8


def _sampled_file_identity(path: Path, file_size: int) -> str:
    """Bounded content fallback for platforms without a change-time identity."""
    digest = hashlib.blake2b(digest_size=16)
    digest.update(str(file_size).encode("ascii"))
    with path.open("rb") as file_obj:
        if file_size <= _FILE_IDENTITY_SAMPLE_BYTES * _FILE_IDENTITY_SAMPLE_COUNT:
            for block in iter(lambda: file_obj.read(64 * 1024), b""):
                digest.update(block)
        else:
            last_offset = file_size - _FILE_IDENTITY_SAMPLE_BYTES
            offsets = {
                round(last_offset * index / (_FILE_IDENTITY_SAMPLE_COUNT - 1))
                for index in range(_FILE_IDENTITY_SAMPLE_COUNT)
            }
            for offset in sorted(offsets):
                file_obj.seek(offset)
                digest.update(offset.to_bytes(8, "little", signed=False))
                digest.update(file_obj.read(_FILE_IDENTITY_SAMPLE_BYTES))
    return digest.hexdigest()


@lru_cache(maxsize=1)
def _windows_change_time_api() -> tuple[Any, Any, Any, type[ctypes.Structure]]:
    class _FileBasicInfo(ctypes.Structure):
        _fields_ = [
            ("creation_time", ctypes.c_longlong),
            ("last_access_time", ctypes.c_longlong),
            ("last_write_time", ctypes.c_longlong),
            ("change_time", ctypes.c_longlong),
            ("file_attributes", ctypes.c_ulong),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    get_file_information = kernel32.GetFileInformationByHandleEx
    get_file_information.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
    ]
    get_file_information.restype = ctypes.c_int
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int
    return create_file, get_file_information, close_handle, _FileBasicInfo


def _windows_file_change_time(path: Path) -> int:
    create_file, get_file_information, close_handle, info_type = _windows_change_time_api()
    handle = create_file(
        str(path),
        0,
        0x1 | 0x2 | 0x4,  # Share read, write, and delete access.
        None,
        3,  # OPEN_EXISTING
        0x80,  # FILE_ATTRIBUTE_NORMAL
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        info = info_type()
        if not get_file_information(handle, 0, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(info.change_time)
    finally:
        close_handle(handle)


def _file_signature(path: Path) -> tuple[Any, ...] | None:
    try:
        stat = path.stat()
        if os.name == "nt":
            try:
                generation: int | str = _windows_file_change_time(path)
            except (AttributeError, OSError):
                generation = _sampled_file_identity(path, stat.st_size)
        else:
            generation = stat.st_ctime_ns
        return (
            str(path.resolve()),
            stat.st_mtime_ns,
            stat.st_size,
            stat.st_dev,
            stat.st_ino,
            generation,
        )
    except OSError:
        return None


@lru_cache(maxsize=64)
def _cached_file_sha256(
    resolved_path: str,
    modified_time_ns: int,
    file_size: int,
    device: int,
    inode: int,
    generation: int | str,
) -> str:
    del modified_time_ns, file_size, device, inode, generation
    digest = hashlib.sha256()
    with Path(resolved_path).open("rb") as file_obj:
        for block in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    signature = _file_signature(path)
    if signature is None:
        raise FileNotFoundError(path)
    return _cached_file_sha256(*signature)


def _telemetry_cache_source(data_root: Path, run_id: str) -> Path | None:
    candidates = [
        path
        for path in (parquet_path(data_root, run_id), csv_path(data_root, run_id))
        if path.exists()
    ]
    return candidates[0] if len(candidates) == 1 else None


def _valid_sha256(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text if len(text) == 64 and all(char in "0123456789abcdef" for char in text) else None


def _telemetry_cache_artifact_identity(
    manifest: dict[str, Any],
    *,
    requested_run_id: str,
    cache_source: Path | None,
) -> dict[str, Any]:
    stored_run_id = manifest.get("run_id")
    if not isinstance(stored_run_id, str) or not stored_run_id:
        return {
            "status": "blocked",
            "reason_code": "missing_manifest_run_id",
            "reason": "Telemetry samples are unavailable until the original file is re-imported with immutable run ownership.",
        }
    if stored_run_id != requested_run_id:
        return {
            "status": "blocked",
            "reason_code": "manifest_run_mismatch",
            "reason": "Telemetry samples are unavailable because the cache manifest belongs to a different run.",
        }
    stored_cache_sha256 = _valid_sha256(manifest.get("telemetry_cache_sha256"))
    if stored_cache_sha256 is None:
        return {
            "status": "blocked",
            "reason_code": "missing_manifest_cache_hash",
            "reason": "Telemetry samples are unavailable until the original file is re-imported with immutable cache ownership.",
        }
    if cache_source is None:
        return {
            "status": "blocked",
            "reason_code": "cache_missing_or_ambiguous",
            "reason": "Telemetry samples are unavailable because exactly one cache artifact is required.",
        }
    if stored_cache_sha256 != _sha256_file(cache_source):
        return {
            "status": "blocked",
            "reason_code": "telemetry_cache_mismatch",
            "reason": "Telemetry samples are unavailable because the cache does not match its imported manifest.",
        }
    return {
        "status": "verified",
        "run_id": requested_run_id,
        "telemetry_cache_sha256": stored_cache_sha256,
    }


def _telemetry_artifact_identity(
    manifest: dict[str, Any],
    *,
    requested_run_id: str,
    expected_source_file_sha256: str | None,
    cache_source: Path | None,
) -> dict[str, Any]:
    stored_run_id = manifest.get("run_id")
    if not isinstance(stored_run_id, str) or not stored_run_id:
        return {
            "status": "blocked",
            "reason_code": "missing_manifest_run_id",
            "reason": "The telemetry manifest predates immutable run ownership.",
            "required_action": "reimport_original_ibt",
        }
    if stored_run_id != requested_run_id:
        return {
            "status": "blocked",
            "reason_code": "manifest_run_mismatch",
            "reason": "The telemetry manifest belongs to a different run.",
            "required_action": "reimport_original_ibt",
        }
    stored_source_sha256 = _valid_sha256(manifest.get("source_file_sha256"))
    if stored_source_sha256 is None:
        return {
            "status": "blocked",
            "reason_code": "missing_manifest_source_hash",
            "reason": "The telemetry manifest predates immutable source-file ownership.",
            "required_action": "reimport_original_ibt",
        }
    expected_source_sha256 = _valid_sha256(expected_source_file_sha256)
    if expected_source_sha256 is None:
        return {
            "status": "blocked",
            "reason_code": "source_reference_unavailable",
            "reason": "The run record cannot verify the manifest's source file.",
            "required_action": "reimport_original_ibt",
        }
    if stored_source_sha256 != expected_source_sha256:
        return {
            "status": "blocked",
            "reason_code": "manifest_source_mismatch",
            "reason": "The telemetry manifest belongs to a different source file.",
            "required_action": "reimport_original_ibt",
        }
    stored_cache_sha256 = _valid_sha256(manifest.get("telemetry_cache_sha256"))
    if stored_cache_sha256 is None:
        return {
            "status": "blocked",
            "reason_code": "missing_manifest_cache_hash",
            "reason": "The telemetry manifest predates immutable cache ownership.",
            "required_action": "reimport_original_ibt",
        }
    if cache_source is None:
        return {
            "status": "blocked",
            "reason_code": "cache_missing_or_ambiguous",
            "reason": "Exactly one telemetry cache artifact is required for this run.",
            "required_action": "reimport_original_ibt",
        }
    actual_cache_sha256 = _sha256_file(cache_source)
    if stored_cache_sha256 != actual_cache_sha256:
        return {
            "status": "blocked",
            "reason_code": "telemetry_cache_mismatch",
            "reason": "The telemetry cache does not match its imported manifest.",
            "required_action": "reimport_original_ibt",
        }
    return {
        "status": "verified",
        "run_id": requested_run_id,
        "source_file_sha256": stored_source_sha256,
        "telemetry_cache_sha256": stored_cache_sha256,
    }


def _assert_telemetry_cache_identity(
    data_root: Path,
    run_id: str,
    cache_source: Path | None,
) -> None:
    manifest = read_telemetry_manifest(run_id, data_root)
    identity = _telemetry_cache_artifact_identity(
        manifest,
        requested_run_id=run_id,
        cache_source=cache_source,
    )
    if identity["status"] != "verified":
        raise TelemetryArtifactIdentityError(str(identity["reason"]))


def assert_telemetry_cache_identity(
    run_id: str,
    data_dir: str | Path | None = None,
) -> None:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    _assert_telemetry_cache_identity(
        data_root,
        run_id,
        _telemetry_cache_source(data_root, run_id),
    )


def _source_signature(parquet: Path, csv_file: Path) -> tuple[Any, ...] | None:
    source = parquet if parquet.exists() else csv_file if csv_file.exists() else None
    return _file_signature(source) if source is not None else None


def _channel_context_signature(
    data_root: Path,
    run_id: str,
    source_signature: tuple[Any, ...] | None,
) -> tuple[Any, ...]:
    return (
        source_signature,
        _file_signature(channel_metadata_path(data_root, run_id)),
        _file_signature(telemetry_manifest_path(data_root, run_id)),
        _CHANNEL_SCHEMA_VERSION,
    )


@lru_cache(maxsize=64)
def _cached_parquet_schema(
    resolved_path: str,
    modified_time_ns: int,
    file_size: int,
    device: int,
    inode: int,
    generation: int | str,
) -> tuple[tuple[str, Any], ...]:
    del modified_time_ns, file_size, device, inode, generation
    pl = importlib.import_module("polars")
    return tuple(pl.read_parquet_schema(resolved_path).items())


def _read_parquet_schema(
    path: Path,
    signature: tuple[Any, ...] | None = None,
) -> dict[str, Any]:
    resolved_signature = signature or _file_signature(path)
    return dict(_cached_parquet_schema(*resolved_signature)) if resolved_signature is not None else {}


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


def _copy_telemetry_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_copy_telemetry_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_copy_telemetry_value(item) for item in value)
    if isinstance(value, dict):
        return {key: _copy_telemetry_value(item) for key, item in value.items()}
    return deepcopy(value)


def _copy_telemetry_rows(
    rows: list[dict[str, Any]],
    columns: list[str] | None = None,
) -> list[dict[str, Any]]:
    if columns is None:
        return [
            {key: _copy_telemetry_value(value) for key, value in row.items()}
            for row in rows
        ]
    return [
        {column: _copy_telemetry_value(row.get(column)) for column in columns}
        for row in rows
    ]


def _estimate_telemetry_value_size(value: Any, seen: set[int]) -> int:
    value_id = id(value)
    if value_id in seen:
        return 0
    seen.add(value_id)
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(
            _estimate_telemetry_value_size(item, seen)
            for pair in value.items()
            for item in pair
        )
    elif isinstance(value, (list, tuple, set, frozenset)):
        size += sum(_estimate_telemetry_value_size(item, seen) for item in value)
    return size


def _estimate_telemetry_rows_size(
    rows: list[dict[str, Any]],
    *,
    maximum_bytes: int | None = None,
) -> int:
    """Measure the retained Python object graph without sampling blind spots."""
    seen = {id(rows)}
    size = sys.getsizeof(rows)
    for row in rows:
        size += _estimate_telemetry_value_size(row, seen)
        if maximum_bytes is not None and size > maximum_bytes:
            return size
    return size


def _evict_if_needed() -> None:
    total_bytes = sum(entry.size_bytes for entry in _TELEMETRY_ROWS_CACHE.values())
    while (
        len(_TELEMETRY_ROWS_CACHE) > _TELEMETRY_ROWS_CACHE_MAX
        or total_bytes > _TELEMETRY_ROWS_CACHE_MAX_BYTES
    ):
        oldest_key, oldest = min(
            _TELEMETRY_ROWS_CACHE.items(),
            key=lambda item: item[1].last_access,
        )
        total_bytes -= oldest.size_bytes
        _TELEMETRY_ROWS_CACHE.pop(oldest_key, None)


def _evict_projected_telemetry_if_needed() -> None:
    total_bytes = sum(entry.size_bytes for entry in _PROJECTED_TELEMETRY_CACHE.values())
    while (
        len(_PROJECTED_TELEMETRY_CACHE) > _PROJECTED_TELEMETRY_CACHE_MAX
        or total_bytes > _PROJECTED_TELEMETRY_CACHE_MAX_BYTES
    ):
        oldest_key, oldest = min(
            _PROJECTED_TELEMETRY_CACHE.items(),
            key=lambda item: item[1].last_access,
        )
        total_bytes -= oldest.size_bytes
        _PROJECTED_TELEMETRY_CACHE.pop(oldest_key, None)


def _evict_channel_catalog_if_needed() -> None:
    total_bytes = sum(entry.size_bytes for entry in _CHANNEL_CATALOG_CACHE.values())
    while _CHANNEL_CATALOG_CACHE and (
        len(_CHANNEL_CATALOG_CACHE) > _CHANNEL_CATALOG_CACHE_MAX
        or total_bytes > _CHANNEL_CATALOG_CACHE_MAX_BYTES
    ):
        oldest_key, oldest = min(
            _CHANNEL_CATALOG_CACHE.items(), key=lambda item: item[1].last_access,
        )
        total_bytes -= oldest.size_bytes
        _CHANNEL_CATALOG_CACHE.pop(oldest_key, None)


def _evict_channel_summary_if_needed() -> None:
    total_bytes = sum(entry.size_bytes for entry in _CHANNEL_SUMMARY_CACHE.values())
    while _CHANNEL_SUMMARY_CACHE and (
        len(_CHANNEL_SUMMARY_CACHE) > _CHANNEL_SUMMARY_CACHE_MAX
        or total_bytes > _CHANNEL_SUMMARY_CACHE_MAX_BYTES
    ):
        oldest_key, oldest = min(
            _CHANNEL_SUMMARY_CACHE.items(), key=lambda item: item[1].last_access,
        )
        total_bytes -= oldest.size_bytes
        _CHANNEL_SUMMARY_CACHE.pop(oldest_key, None)


def _invalidate_run_cache(data_root: Path, run_id: str) -> None:
    with _TELEMETRY_ROWS_CACHE_LOCK:
        # Writes are rare, so clear the small global schema cache atomically.
        # This closes the equal-size/equal-mtime replacement edge case that a
        # filesystem signature alone cannot distinguish.
        _cached_parquet_schema.cache_clear()
        _cached_file_sha256.cache_clear()
        _TELEMETRY_ROWS_CACHE.pop(_cache_key(data_root, run_id), None)
        _CHANNEL_CATALOG_CACHE.pop(_cache_key(data_root, run_id), None)
        _CHANNEL_SUMMARY_CACHE.pop(_cache_key(data_root, run_id), None)
        source_paths = {
            str(parquet_path(data_root, run_id).resolve()),
            str(csv_path(data_root, run_id).resolve()),
        }
        for projected_key in list(_PROJECTED_TELEMETRY_CACHE):
            if projected_key[0] in source_paths:
                _PROJECTED_TELEMETRY_CACHE.pop(projected_key, None)


def _invalidate_channel_context_cache(data_root: Path, run_id: str) -> None:
    with _TELEMETRY_ROWS_CACHE_LOCK:
        key = _cache_key(data_root, run_id)
        _CHANNEL_CATALOG_CACHE.pop(key, None)
        _CHANNEL_SUMMARY_CACHE.pop(key, None)


def read_telemetry_rows(
    run_id: str,
    data_dir: str | Path | None = None,
    lap: int | None = None,
    columns: list[str] | None = None,
) -> list[dict[str, Any]]:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    parquet = parquet_path(data_root, run_id)
    csv_file = csv_path(data_root, run_id)
    _assert_telemetry_cache_identity(
        data_root,
        run_id,
        _telemetry_cache_source(data_root, run_id),
    )
    signature = _source_signature(parquet, csv_file)
    key = _cache_key(data_root, run_id)
    requested_columns = list(dict.fromkeys(columns or []))
    projection_key = (
        (*signature, lap, tuple(requested_columns))
        if signature is not None and parquet.exists() and (lap is not None or requested_columns)
        else None
    )

    def _filter_rows(
        source_rows: list[dict[str, Any]],
        *,
        isolate_from_cache: bool,
    ) -> list[dict[str, Any]]:
        scoped_rows = source_rows if lap is None else [row for row in source_rows if row.get("lap") == lap]
        if isolate_from_cache:
            return _copy_telemetry_rows(
                scoped_rows,
                requested_columns or None,
            )
        if not requested_columns:
            return scoped_rows
        return [{column: row.get(column) for column in requested_columns} for row in scoped_rows]

    cached_rows: list[dict[str, Any]] | None = None
    cached_frame: Any | None = None
    with _TELEMETRY_ROWS_CACHE_LOCK:
        entry = _TELEMETRY_ROWS_CACHE.get(key)
        if entry is not None and entry.signature == signature:
            entry.last_access = time.time()
            cached_rows = entry.rows
        if entry is not None and entry.signature != signature:
            _TELEMETRY_ROWS_CACHE.pop(key, None)
        if cached_rows is None and projection_key is not None:
            projected_entry = _PROJECTED_TELEMETRY_CACHE.get(projection_key)
            if projected_entry is not None:
                projected_entry.last_access = time.time()
                cached_frame = projected_entry.frame

    # Filtering and Polars-to-dict conversion can be significant.  Perform both
    # outside the shared cache lock so independent API requests remain parallel.
    if cached_rows is not None:
        return _filter_rows(cached_rows, isolate_from_cache=True)
    if cached_frame is not None:
        projected_rows = cached_frame.to_dicts()
        if requested_columns:
            return [
                {column: row.get(column) for column in requested_columns}
                for row in projected_rows
            ]
        return _normalize_if_needed([dict(row) for row in projected_rows])

    # Fast miss path for lap/column-scoped calls: avoid reading full parquet into memory.
    if (lap is not None or requested_columns) and parquet.exists() and importlib.util.find_spec("polars") is not None:
        pl = importlib.import_module("polars")
        schema = _read_parquet_schema(parquet, signature)
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
        collected = frame.collect()
        if projection_key is not None:
            estimated_size = int(collected.estimated_size())
            if estimated_size <= _PROJECTED_TELEMETRY_CACHE_MAX_ENTRY_BYTES:
                with _TELEMETRY_ROWS_CACHE_LOCK:
                    _PROJECTED_TELEMETRY_CACHE[projection_key] = _ProjectedTelemetryCacheEntry(
                        frame=collected,
                        size_bytes=estimated_size,
                        last_access=time.time(),
                    )
                    _evict_projected_telemetry_if_needed()
        rows = collected.to_dicts()
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

    cache_admitted = False
    if signature is not None and not requested_columns:
        estimated_size = _estimate_telemetry_rows_size(
            rows,
            maximum_bytes=_TELEMETRY_ROWS_CACHE_MAX_ENTRY_BYTES,
        )
        if estimated_size <= _TELEMETRY_ROWS_CACHE_MAX_ENTRY_BYTES:
            with _TELEMETRY_ROWS_CACHE_LOCK:
                entry = _TelemetryRowsCacheEntry(
                    signature=signature,
                    rows=rows,
                    size_bytes=estimated_size,
                    last_access=time.time(),
                )
                _TELEMETRY_ROWS_CACHE[key] = entry
                _evict_if_needed()
                cache_admitted = _TELEMETRY_ROWS_CACHE.get(key) is entry

    return _filter_rows(rows, isolate_from_cache=cache_admitted)


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
    signature: tuple[Any, ...] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if importlib.util.find_spec("polars") is None:
        return {}, []
    pl = importlib.import_module("polars")
    schema = _read_parquet_schema(path, signature)
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
    row = pl.scan_parquet(path).select(exprs).collect(engine="streaming").to_dicts()[0]
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


def _manifest_channel_fields(manifest_channel: dict[str, Any] | None) -> dict[str, Any]:
    if not manifest_channel:
        return {}
    return {
        key: manifest_channel.get(key)
        for key in (
            "raw_name",
            "archive_column",
            "canonical_name",
            "canonical_mapping_kind",
            "registry_status",
            "engineering_role",
            "engineering_admission_state",
            "engineering_authority_limit",
            "provenance",
            "archive_status",
            "variation",
            "health_status",
            "health_warnings",
            "non_finite_sample_count",
            "impossible_sample_count",
            "impossible_range_rule",
            "malformed_array_record_count",
            "null_element_count",
            "numeric_limit_hit_count",
            "clipping_status",
            "saturation_status",
            "lower_bound_occupancy_fraction",
            "upper_bound_occupancy_fraction",
            "count_as_time",
            "base_sample_rate_hz",
            "effective_sample_rate_hz",
            "missing_fraction",
        )
    }


def _build_catalog_item(
    name: str,
    definition: dict[str, Any] | None,
    is_raw: bool,
    is_calculated: bool,
    in_column_set: bool,
    channel_stats: dict[str, dict[str, Any]],
    manifest_channel: dict[str, Any] | None = None,
    is_canonical_alias: bool = False,
) -> dict[str, Any]:
    stats_name = (
        str(manifest_channel.get("archive_column"))
        if manifest_channel and is_raw and manifest_channel.get("archive_column")
        else name
    )
    stats = channel_stats.get(stats_name, {"min": None, "max": None, "mean": None, "sample_value": None})
    missing_status = _missing_status(name, definition, is_calculated, in_column_set)
    definition_type = _definition_type_for(definition, is_calculated)
    meta = channel_metadata(name)
    item: dict[str, Any] = {
        "name": name,
        "label": meta.get("label", name),
        "description": definition.get("description") if definition else meta.get("description"),
        "unit": (
            TRACE_CHANNEL_UNITS.get(name)
            or CALCULATED_CHANNEL_UNITS.get(name)
            or (definition.get("unit") if definition else None)
            if is_canonical_alias
            else definition.get("unit") if definition and definition.get("unit") else TRACE_CHANNEL_UNITS.get(name)
        ),
        "type": definition_type,
        "count": definition.get("count", 1) if definition else 1,
        "is_raw": is_raw,
        "is_calculated": is_calculated,
        "is_canonical_alias": is_canonical_alias,
        "is_proxy": name in CALCULATED_PROXY_CHANNELS,
        "formula": meta.get("formula"),
        "dependencies": meta.get("dependencies", []),
        "used_by_charts": meta.get("used_by_charts", []),
        "used_by_events": meta.get("used_by_events", []),
        "used_by_analyses": meta.get("used_by_analyses", []),
        "missing_status": missing_status,
        **stats,
        **_manifest_channel_fields(manifest_channel),
    }
    if is_canonical_alias:
        item["source"] = "canonical_alias"
        item["group"] = "canonical_alias"
    if name in FORCE_PROXY_CHANNELS:
        item["is_proxy"] = True
        if not item.get("description") or "ESTIMATE" not in str(item.get("description", "")):
            item["description"] = f"ESTIMATE — {FORCE_PROXY_WARNING}"
    elif name in DIFFUSER_GEOMETRY_PROXY_CHANNELS:
        item["is_proxy"] = True
        if not item.get("description") or "PROXY" not in str(item.get("description", "")).upper():
            item["description"] = (
                "CALCULATED PROXY — requires complete reviewed vehicle-profile "
                "geometry; unavailable when that provenance is missing."
            )
    return item


def _build_summary_item(
    name: str,
    definition: dict[str, Any] | None,
    is_raw: bool,
    is_calculated: bool,
    in_column_set: bool,
    manifest_channel: dict[str, Any] | None = None,
    is_canonical_alias: bool = False,
) -> dict[str, Any]:
    meta = channel_metadata(name)
    missing_status = _missing_status(name, definition, is_calculated, in_column_set)
    definition_type = _definition_type_for(definition, is_calculated)
    return {
        "name": name,
        "label": meta.get("label", name),
        "description": definition.get("description") if definition else meta.get("description"),
        "unit": (
            TRACE_CHANNEL_UNITS.get(name)
            or CALCULATED_CHANNEL_UNITS.get(name)
            or (definition.get("unit") if definition else None)
            if is_canonical_alias
            else definition.get("unit") if definition and definition.get("unit") else TRACE_CHANNEL_UNITS.get(name)
        ),
        "type": definition_type,
        "count": definition.get("count", 1) if definition else 1,
        "is_raw": is_raw,
        "is_calculated": is_calculated,
        "is_canonical_alias": is_canonical_alias,
        "is_proxy": name in CALCULATED_PROXY_CHANNELS,
        "formula": None,
        "dependencies": [],
        "used_by_charts": [],
        "used_by_events": [],
        "used_by_analyses": [],
        "min": None,
        "max": None,
        "mean": None,
        "sample_value": None,
        "missing_status": missing_status,
        "group": "raw" if is_raw else "canonical_alias" if is_canonical_alias else "calculated" if is_calculated else "derived",
        "source": "raw" if is_raw else "canonical_alias" if is_canonical_alias else "calculated" if is_calculated else "derived",
        **_manifest_channel_fields(manifest_channel),
    }
def build_channel_catalog(run_id: str, data_dir: str | Path | None = None) -> list[dict[str, Any]]:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    _assert_telemetry_cache_identity(
        data_root,
        run_id,
        _telemetry_cache_source(data_root, run_id),
    )
    key = _cache_key(data_root, run_id)
    source_signature = _source_signature(parquet_path(data_root, run_id), csv_path(data_root, run_id))
    signature = _channel_context_signature(data_root, run_id, source_signature)
    cached_catalog: list[dict[str, Any]] | None = None
    with _TELEMETRY_ROWS_CACHE_LOCK:
        entry = _CHANNEL_CATALOG_CACHE.get(key)
        if entry is not None and entry.signature == signature:
            entry.last_access = time.time()
            cached_catalog = entry.catalog
    if cached_catalog is not None:
        return deepcopy(cached_catalog)

    path = parquet_path(data_root, run_id)
    if path.exists() and importlib.util.find_spec("polars") is not None:
        stats_map, columns = _precompute_channel_stats_from_parquet(path, source_signature)
    else:
        rows = read_telemetry_rows(run_id, data_dir)
        stats_map = _precompute_channel_stats(rows)
        columns = list(stats_map.keys())
    column_set = set(columns)
    definitions = {definition["name"]: definition for definition in read_channel_metadata(run_id, data_dir)}
    manifest_channels = {
        channel["raw_name"]: channel
        for channel in read_telemetry_manifest(run_id, data_dir).get("channels", [])
        if channel.get("raw_name")
    }
    manifest_by_canonical = {
        channel["canonical_name"]: channel
        for channel in manifest_channels.values()
        if channel.get("canonical_name")
    }
    namespaced_raw_columns = {
        str(channel["archive_column"])
        for channel in manifest_channels.values()
        if channel.get("archive_column") and channel.get("archive_column") != channel.get("raw_name")
    }
    physical_raw_names = {
        str(channel.get("archive_column", raw_name)): raw_name
        for raw_name, channel in manifest_channels.items()
    }
    catalog_names = [
        str(manifest_channels.get(name, {}).get("archive_column", name))
        for name in definitions
    ]
    catalog_names.extend(name for name in HIGH_VALUE_RAW_CHANNELS if name not in catalog_names)
    catalog_names.extend(
        name for name in columns
        if name not in catalog_names and name not in namespaced_raw_columns
    )
    catalog_names.extend(name for name in CALCULATED_CHANNEL_UNITS if name not in catalog_names)

    catalog: list[dict[str, Any]] = []
    for name in catalog_names:
        is_physical_raw = name in physical_raw_names
        logical_raw_name = physical_raw_names.get(name, name)
        # Boot metadata remains authoritative even when a synthetic/test cache
        # has no telemetry manifest yet.
        definition = (
            definitions.get(logical_raw_name)
            if is_physical_raw or not manifest_channels
            else None
        )
        manifest_channel = (
            manifest_channels.get(logical_raw_name)
            if is_physical_raw
            else manifest_by_canonical.get(name)
        )
        is_canonical_alias = definition is None and name in manifest_by_canonical
        source_definition = (
            definitions.get(str(manifest_channel.get("raw_name")))
            if is_canonical_alias and manifest_channel
            else definition
        )
        is_raw = definition is not None or name in HIGH_VALUE_RAW_CHANNELS
        is_calculated = not is_raw and not is_canonical_alias and (
            name in CALCULATED_CHANNEL_UNITS or (not is_raw and name in column_set)
        )
        in_column_set = (
            str(manifest_channel.get("archive_column")) in column_set
            if is_raw and manifest_channel and manifest_channel.get("archive_column")
            else name in column_set
        )
        catalog.append(
            _build_catalog_item(
                name,
                source_definition,
                is_raw,
                is_calculated,
                in_column_set,
                stats_map,
                manifest_channel,
                is_canonical_alias,
            )
        )

    estimated_size = _estimate_telemetry_value_size(catalog, set())
    with _TELEMETRY_ROWS_CACHE_LOCK:
        _CHANNEL_CATALOG_CACHE.pop(key, None)
        if estimated_size <= _CHANNEL_CATALOG_CACHE_MAX_ENTRY_BYTES:
            _CHANNEL_CATALOG_CACHE[key] = _ChannelCatalogCacheEntry(
                signature=signature,
                catalog=catalog,
                size_bytes=estimated_size,
                last_access=time.time(),
            )
            _evict_channel_catalog_if_needed()
    return deepcopy(catalog)


def build_channel_summary(run_id: str, data_dir: str | Path | None = None) -> list[dict[str, Any]]:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    _assert_telemetry_cache_identity(
        data_root,
        run_id,
        _telemetry_cache_source(data_root, run_id),
    )
    key = _cache_key(data_root, run_id)
    source_signature = _source_signature(parquet_path(data_root, run_id), csv_path(data_root, run_id))
    signature = _channel_context_signature(data_root, run_id, source_signature)
    cached_summary: list[dict[str, Any]] | None = None
    with _TELEMETRY_ROWS_CACHE_LOCK:
        entry = _CHANNEL_SUMMARY_CACHE.get(key)
        if entry is not None and entry.signature == signature:
            entry.last_access = time.time()
            cached_summary = entry.summary
    if cached_summary is not None:
        return deepcopy(cached_summary)

    path = parquet_path(data_root, run_id)
    columns: list[str]
    if path.exists() and importlib.util.find_spec("polars") is not None:
        columns = list(_read_parquet_schema(path, source_signature).keys())
    else:
        rows = read_telemetry_rows(run_id, data_dir)
        columns = list(rows[0].keys()) if rows else []

    column_set = set(columns)
    definitions = {definition["name"]: definition for definition in read_channel_metadata(run_id, data_dir)}
    manifest_channels = {
        channel["raw_name"]: channel
        for channel in read_telemetry_manifest(run_id, data_dir).get("channels", [])
        if channel.get("raw_name")
    }
    manifest_by_canonical = {
        channel["canonical_name"]: channel
        for channel in manifest_channels.values()
        if channel.get("canonical_name")
    }
    namespaced_raw_columns = {
        str(channel["archive_column"])
        for channel in manifest_channels.values()
        if channel.get("archive_column") and channel.get("archive_column") != channel.get("raw_name")
    }
    physical_raw_names = {
        str(channel.get("archive_column", raw_name)): raw_name
        for raw_name, channel in manifest_channels.items()
    }
    catalog_names = [
        str(manifest_channels.get(name, {}).get("archive_column", name))
        for name in definitions
    ]
    catalog_names.extend(name for name in HIGH_VALUE_RAW_CHANNELS if name not in catalog_names)
    catalog_names.extend(
        name for name in columns
        if name not in catalog_names and name not in namespaced_raw_columns
    )
    catalog_names.extend(name for name in CALCULATED_CHANNEL_UNITS if name not in catalog_names)

    summary: list[dict[str, Any]] = []
    for name in catalog_names:
        is_physical_raw = name in physical_raw_names
        logical_raw_name = physical_raw_names.get(name, name)
        # Boot metadata remains authoritative even when a synthetic/test cache
        # has no telemetry manifest yet.
        definition = (
            definitions.get(logical_raw_name)
            if is_physical_raw or not manifest_channels
            else None
        )
        manifest_channel = (
            manifest_channels.get(logical_raw_name)
            if is_physical_raw
            else manifest_by_canonical.get(name)
        )
        is_canonical_alias = definition is None and name in manifest_by_canonical
        source_definition = (
            definitions.get(str(manifest_channel.get("raw_name")))
            if is_canonical_alias and manifest_channel
            else definition
        )
        is_raw = definition is not None or name in HIGH_VALUE_RAW_CHANNELS
        is_calculated = not is_raw and not is_canonical_alias and (
            name in CALCULATED_CHANNEL_UNITS or (not is_raw and name in column_set)
        )
        in_column_set = (
            str(manifest_channel.get("archive_column")) in column_set
            if is_raw and manifest_channel and manifest_channel.get("archive_column")
            else name in column_set
        )
        summary.append(
            _build_summary_item(
                name,
                source_definition,
                is_raw,
                is_calculated,
                in_column_set,
                manifest_channel,
                is_canonical_alias,
            )
        )

    estimated_size = _estimate_telemetry_value_size(summary, set())
    with _TELEMETRY_ROWS_CACHE_LOCK:
        _CHANNEL_SUMMARY_CACHE.pop(key, None)
        if estimated_size <= _CHANNEL_SUMMARY_CACHE_MAX_ENTRY_BYTES:
            _CHANNEL_SUMMARY_CACHE[key] = _ChannelSummaryCacheEntry(
                signature=signature,
                summary=summary,
                size_bytes=estimated_size,
                last_access=time.time(),
            )
            _evict_channel_summary_if_needed()
    return deepcopy(summary)


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
    if not events or not rows:
        return indices

    pct_positions: list[float] = []
    distance_positions: list[float] = []
    pct_complete = True
    distance_complete = True
    for row in rows:
        row_pct = _numeric_value(row.get("lap_dist_pct_100"))
        if row_pct is None:
            raw_pct = _numeric_value(row.get("lap_dist_pct"))
            row_pct = raw_pct * 100.0 if raw_pct is not None and raw_pct <= 1.5 else raw_pct
        distance = _numeric_value(row.get("lap_dist_m"))
        if row_pct is None:
            pct_complete = False
        else:
            pct_positions.append(row_pct)
        if distance is None:
            distance_complete = False
        else:
            distance_positions.append(distance)

    pct_sorted = pct_complete and all(
        left <= right for left, right in zip(pct_positions, pct_positions[1:])
    )
    distance_sorted = distance_complete and all(
        left <= right for left, right in zip(distance_positions, distance_positions[1:])
    )

    def closest_index(positions: list[float], target: float) -> int:
        insertion = bisect_left(positions, target)
        candidates = [index for index in (insertion - 1, insertion) if 0 <= index < len(positions)]
        return min(candidates, key=lambda index: (abs(positions[index] - target), index))

    for event in events:
        if event.lap_pct_peak is not None and pct_sorted:
            indices.add(closest_index(pct_positions, event.lap_pct_peak))
            continue
        if event.lap_pct_peak is None and event.distance_m_peak is not None and distance_sorted:
            indices.add(closest_index(distance_positions, event.distance_m_peak))
            continue
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
        indices.add(start)
        indices.add(end - 1)
        minimums: list[tuple[float, int] | None] = [None] * len(preserve_channels)
        maximums: list[tuple[float, int] | None] = [None] * len(preserve_channels)
        for index in range(start, end):
            row = rows[index]
            for channel_index, channel in enumerate(preserve_channels):
                value = _numeric_value(row.get(channel))
                if value is None:
                    continue
                minimum = minimums[channel_index]
                maximum = maximums[channel_index]
                if minimum is None or value < minimum[0]:
                    minimums[channel_index] = (value, index)
                if maximum is None or value > maximum[0]:
                    maximums[channel_index] = (value, index)
        for minimum, maximum in zip(minimums, maximums):
            if minimum is not None:
                indices.add(minimum[1])
            if maximum is not None:
                indices.add(maximum[1])

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


def _extrema_aware_auto_bucket_size(
    rows: list[dict[str, Any]],
    channels: list[str],
    events: list[TelemetryEvent] | None,
) -> int:
    """Size auto buckets against the actual extrema-preserving output budget.

    A bucket can contribute its two endpoints plus a minimum and maximum for
    each active trace channel.  The previous ``rows / 1200`` sizing ignored
    those retained extrema, so an "auto" trace could return almost every raw
    sample.  This conservative bound keeps the response near its intended point
    budget without discarding local extrema or telemetry-event anchors.  If a
    caller requests so many channels that one minimum and maximum per channel
    alone exceeds the budget, evidence preservation takes precedence over the
    display-size target.
    """
    if len(rows) <= TRACE_AUTO_POINT_BUDGET:
        return 1
    available_columns = set(rows[0]) if rows else set()
    preserve_channels = {
        channel
        for channel in (*channels, *PRESERVE_EXTREMA_CHANNELS)
        if channel in available_columns
    }
    maximum_points_per_bucket = 2 + (2 * len(preserve_channels))
    event_budget = min(len(events or []), TRACE_AUTO_POINT_BUDGET - 1)
    bucket_budget = max(1, TRACE_AUTO_POINT_BUDGET - event_budget)
    maximum_bucket_count = max(1, bucket_budget // maximum_points_per_bucket)
    return max(2, math.ceil(len(rows) / maximum_bucket_count))


def _trace_channel_payload(rows: list[dict[str, Any]], channel: str) -> dict[str, Any]:
    stats = _channel_stats(rows, channel)
    return {
        "unit": TRACE_CHANNEL_UNITS.get(channel),
        "values": [row.get(channel) for row in rows],
        "missing_status": None if any(row.get(channel) is not None for row in rows) else "Channel unavailable for this run or lap.",
        **{key: stats[key] for key in ("min", "max", "mean")},
    }


def _raw_trace_sort_key(row: dict[str, Any]) -> tuple[float, float, float]:
    session_time = _numeric_value(row.get("session_time"))
    sample_index = _numeric_value(row.get("sample_index"))
    distance_ft = _numeric_value(row.get("lap_dist_ft"))
    return (
        session_time if session_time is not None else math.inf,
        sample_index if sample_index is not None else math.inf,
        distance_ft if distance_ft is not None else math.inf,
    )


def _ordered_sample_indices(rows: list[dict[str, Any]]) -> list[Any]:
    indices: list[Any] = []
    for row_index, row in enumerate(rows):
        value = row.get("sample_index")
        indices.append(value if value is not None else row_index)
    return indices


def _trace_meta(
    *,
    source_rows: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    bucket_size: int,
    downsample_label: int | str,
    raw_resolution: bool,
    start_ft: float | None,
    end_ft: float | None,
    car_path: Any = None,
) -> dict[str, Any]:
    session_times = [
        value for value in (_numeric_value(row.get("session_time")) for row in rows)
        if value is not None
    ]
    sample_indices = [
        value for value in (_numeric_value(row.get("sample_index")) for row in rows)
        if value is not None
    ]
    distances = [
        value for value in (_numeric_value(row.get("lap_dist_ft")) for row in rows)
        if value is not None
    ]
    time_deltas = [
        b - a for a, b in zip(session_times, session_times[1:])
        if b >= a
    ]
    sample_index_deltas = [
        b - a for a, b in zip(sample_indices, sample_indices[1:])
        if b >= a
    ]
    distance_deltas = [
        b - a for a, b in zip(distances, distances[1:])
    ]
    mean_time_delta = sum(time_deltas) / len(time_deltas) if time_deltas else None
    mean_sample_index_delta = sum(sample_index_deltas) / len(sample_index_deltas) if sample_index_deltas else None
    mean_distance_delta = sum(distance_deltas) / len(distance_deltas) if distance_deltas else None
    rounded_distances = [round(value, 6) for value in distances]
    duplicate_distance_count = len(rounded_distances) - len(set(rounded_distances))
    return {
        "raw_resolution": raw_resolution,
        "raw_source_row_count": len(source_rows),
        "returned_row_count": len(rows),
        "downsample_applied": bucket_size > 1,
        "downsample": downsample_label,
        "bucket_size": bucket_size,
        "window_start_ft": start_ft,
        "window_end_ft": end_ft,
        "session_time_delta_s_mean": mean_time_delta,
        "sample_index_delta_mean": mean_sample_index_delta,
        "distance_delta_ft_mean": mean_distance_delta,
        "approx_hz": (1.0 / mean_time_delta) if mean_time_delta and mean_time_delta > 0 else None,
        "distance_duplicate_count": duplicate_distance_count,
        "distance_rounded_or_deduped": False,
        "sample_identity": "sample_index/session_time",
        **trace_offset_metadata(rows, car_path=car_path),
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
    start_ft: float | None = None,
    end_ft: float | None = None,
    raw_resolution: bool = False,
    car_path: Any = None,
) -> dict[str, Any]:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    _assert_telemetry_cache_identity(
        data_root,
        run_id,
        _telemetry_cache_source(data_root, run_id),
    )
    selected_channels = channels or TRACE_DEFAULT_CHANNELS
    read_channels = list(selected_channels)
    should_refresh_lr_platform = car_path is not None and bool(LR_RIDE_HEIGHT_OFFSET_DERIVED_CHANNELS.intersection(selected_channels))
    if should_refresh_lr_platform:
        read_channels = list(dict.fromkeys([*read_channels, *LR_RIDE_HEIGHT_OFFSET_DEPENDENCIES]))
    needs_distance_window = start_ft is not None or end_ft is not None

    # Fast path: use column pruning to read only needed channels from parquet
    if importlib.util.find_spec("polars") is not None:
        pl = importlib.import_module("polars")
        path = parquet_path(data_root, run_id)
        if path.exists():
            needed_cols = list(dict.fromkeys(
                [
                    c for c in read_channels + (
                        ["lap", "lap_dist_ft", "lap_dist_pct", "session_time", "sample_index", "lap_dist_pct_100"]
                        if x_axis or needs_distance_window or raw_resolution
                        else ["lap"]
                    )
                ]
            ))
            # Only request columns that actually exist in the parquet file
            existing = set(_read_parquet_schema(path).keys())
            safe_cols = [c for c in needed_cols if c in existing]
            df = pl.scan_parquet(path).select(safe_cols) if safe_cols else pl.scan_parquet(path)
            if lap is not None:
                df = df.filter(pl.col("lap") == lap)
            if needs_distance_window and "lap_dist_ft" in safe_cols:
                bounds = [value for value in (start_ft, end_ft) if value is not None]
                low_ft = min(bounds) if bounds else None
                high_ft = max(bounds) if bounds else None
                if low_ft is not None:
                    df = df.filter(pl.col("lap_dist_ft") >= low_ft)
                if high_ft is not None:
                    df = df.filter(pl.col("lap_dist_ft") <= high_ft)
            rows = df.collect().to_dicts()
        else:
            rows = read_telemetry_rows(run_id, data_dir)
            if lap is not None:
                rows = [row for row in rows if row.get("lap") == lap]
    else:
        rows = read_telemetry_rows(run_id, data_dir)
        if lap is not None:
            rows = [row for row in rows if row.get("lap") == lap]

    if needs_distance_window:
        bounds = [value for value in (start_ft, end_ft) if value is not None]
        low_ft = min(bounds) if bounds else None
        high_ft = max(bounds) if bounds else None
        windowed_rows: list[dict[str, Any]] = []
        for row in rows:
            distance_ft = _numeric_value(row.get("lap_dist_ft"))
            if distance_ft is None:
                continue
            if low_ft is not None and distance_ft < low_ft:
                continue
            if high_ft is not None and distance_ft > high_ft:
                continue
            windowed_rows.append(row)
        rows = windowed_rows

    if raw_resolution:
        rows = sorted(rows, key=_raw_trace_sort_key)

    apply_next_gen_lr_ride_height_offset_to_rows(rows, car_path=car_path, recompute_derived=should_refresh_lr_platform)

    source_rows = rows
    selected_channels = channels or TRACE_DEFAULT_CHANNELS
    bucket_size, downsample_label = _resolve_bucket_size(len(rows), downsample)
    if downsample_label == "auto" and preserve_extrema:
        bucket_size = max(
            bucket_size,
            _extrema_aware_auto_bucket_size(rows, selected_channels, events),
        )
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
                "sample_index": _ordered_sample_indices(rows),
                "row_index": list(range(len(rows))),
                "lap_dist_pct_100": [row.get("lap_dist_pct_100") for row in rows],
            },
            "channels": {channel: _trace_channel_payload(rows, channel) for channel in selected_channels},
            "events": [event.model_dump(mode="json") for event in events or []],
            "sample_count": len(rows),
            "downsample": downsample_label,
            "preserve_extrema": preserve_extrema,
            "trace_meta": _trace_meta(
                source_rows=source_rows,
                rows=rows,
                bucket_size=bucket_size,
                downsample_label=downsample_label,
                raw_resolution=raw_resolution,
                start_ft=start_ft,
                end_ft=end_ft,
                car_path=car_path,
            ),
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


def _replace_run_scoped_id(value: str, old_run_id: str, new_run_id: str) -> str:
    if value == old_run_id:
        return new_run_id
    if value.startswith(f"{old_run_id}:"):
        return f"{new_run_id}{value[len(old_run_id):]}"
    # Import-owned IDs are expected to carry the run prefix.  Preserve a
    # deterministic namespace even for one malformed/legacy decoder result.
    return f"{new_run_id}:{value}"


def _replace_nested_run_identity(value: Any, old_run_id: str, new_run_id: str) -> Any:
    if isinstance(value, str):
        if value == old_run_id or value.startswith(f"{old_run_id}:"):
            return _replace_run_scoped_id(value, old_run_id, new_run_id)
        if value == f"run:{old_run_id}" or value.startswith(f"run:{old_run_id}:"):
            return f"run:{new_run_id}{value[len(f'run:{old_run_id}'):]}"
        return value
    if isinstance(value, list):
        return [_replace_nested_run_identity(item, old_run_id, new_run_id) for item in value]
    if isinstance(value, tuple):
        return tuple(_replace_nested_run_identity(item, old_run_id, new_run_id) for item in value)
    if isinstance(value, dict):
        return {
            key: _replace_nested_run_identity(item, old_run_id, new_run_id)
            for key, item in value.items()
        }
    return value


def _rebind_import_result_run_id(
    result: IBTImportResult,
    new_run_id: str,
) -> IBTImportResult:
    """Rebind a decoded legacy alias to its existing non-destructive owner."""

    overview = result.overview
    if overview is None or overview.run_id == new_run_id:
        return result
    old_run_id = overview.run_id
    laps = [
        lap.model_copy(
            update={
                "lap_id": _replace_run_scoped_id(lap.lap_id, old_run_id, new_run_id),
                "run_id": new_run_id,
            }
        )
        for lap in overview.laps
    ]
    lap_by_number = {lap.lap_number: lap for lap in laps}
    best_lap = (
        lap_by_number.get(overview.best_useful_lap.lap_number)
        if overview.best_useful_lap is not None
        else None
    )
    events = [
        event.model_copy(
            update={
                "event_id": _replace_run_scoped_id(
                    event.event_id, old_run_id, new_run_id
                ),
                "run_id": new_run_id,
                "evidence_json": _replace_nested_run_identity(
                    event.evidence_json, old_run_id, new_run_id
                ),
            }
        )
        for event in overview.events
    ]
    setup = overview.setup_snapshot
    rebound_setup = (
        setup.model_copy(
            update={
                "setup_id": _replace_run_scoped_id(
                    setup.setup_id, old_run_id, new_run_id
                ),
                "run_id": new_run_id,
            }
        )
        if setup is not None
        else None
    )
    result.overview = overview.model_copy(
        update={
            "run_id": new_run_id,
            "session": overview.session.model_copy(update={"run_id": new_run_id}),
            "best_useful_lap": best_lap,
            "laps": laps,
            "events": events,
            "setup_snapshot": rebound_setup,
            "engineering_blockers": [
                blocker.__class__.model_validate(
                    _replace_nested_run_identity(
                        blocker.model_dump(mode="python"), old_run_id, new_run_id
                    )
                )
                for blocker in overview.engineering_blockers
            ],
        }
    )
    return result


class ImportService:
    def __init__(self, db_path: str | Path | None = None, data_dir: str | Path | None = None):
        self.repository = RaceLabRepository(db_path)
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.last_import_timings: dict[str, float] = {}
        self.last_import_existing_run_updated = False

    def import_ibt_file(
        self,
        path: str | Path,
    ) -> tuple[IBTImportResult, TelemetryCacheResult | None]:
        _log = logging.getLogger(__name__)
        self.last_import_existing_run_updated = False
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
            self.last_import_existing_run_updated = False
            self.last_import_timings = dict(_timings)
            return result, None

        source_file_sha256 = (
            result.fingerprint.sha256
            if result.fingerprint is not None
            else result.overview.session.file_hash
        )
        if (
            result.fingerprint is not None
            and result.overview.session.file_hash
            and result.fingerprint.sha256 != result.overview.session.file_hash
        ):
            raise RuntimeError(
                "Telemetry import identity failed: decoded source fingerprints disagree."
            )
        content_addressed_name = normalize_source_sha256(Path(path).stem)
        if (
            result.fingerprint is not None
            and content_addressed_name is not None
            and result.fingerprint.sha256 != content_addressed_name
        ):
            raise RuntimeError(
                "Telemetry import identity failed: the immutable uploaded source "
                "does not match its content-addressed filename."
            )
        if result.fingerprint is not None:
            # A current decoder always has a full file fingerprint.  Prefer an
            # existing legacy owner so re-import upgrades its cache in place;
            # otherwise use the greenfield content-addressed run namespace.
            recording_owner = self.repository.find_recording_owner_run_id(
                source_file_sha256
            ) or canonical_recording_run_id(source_file_sha256)
            result = _rebind_import_result_run_id(result, recording_owner)

        run_id = result.overview.run_id
        existing_run_updated = self.repository.get_overview(run_id) is not None
        self.last_import_existing_run_updated = existing_run_updated

        t0 = time.perf_counter()
        cache_profile: dict[str, float] = {}
        normalized_frame = getattr(result, "get_normalized_frame", lambda: None)()
        manifest_header = result.header or IBTHeader(
            variable_count=len(result.variable_definitions),
            record_count=(normalized_frame.height if normalized_frame is not None else len(result.records)),
        )
        staged_cache = _stage_import_cache(
            run_id,
            result.records,
            result.variable_definitions,
            header=manifest_header,
            session_yaml=result.session_yaml,
            raw_archive_columns=result.raw_archive_columns,
            normalized_frame=normalized_frame,
            data_dir=self.data_dir,
            source_file_sha256=source_file_sha256,
            source_file_size_bytes=(
                result.fingerprint.file_size if result.fingerprint is not None else None
            ),
            analysis_engine="vectorized" if normalized_frame is not None else "row",
            decoder_path=result.decoder_path,
            decoder_fallback_reason=result.decoder_fallback_reason,
            profile_out=cache_profile,
        )
        _timings["write_parquet_cache"] = time.perf_counter() - t0
        for k, v in cache_profile.items():
            _timings[k] = float(v)

        try:
            t0 = time.perf_counter()
            cache_result = staged_cache.promote()
            _timings["promote_cache_artifacts"] = time.perf_counter() - t0

            t0 = time.perf_counter()
            self.repository.save_import(
                result.overview,
                result.fingerprint,
                analysis_mode="vectorized" if normalized_frame is not None else "row",
            )
            _timings["save_run_metadata"] = time.perf_counter() - t0
            staged_cache.commit()
        except Exception:
            staged_cache.rollback()
            staged_cache.cleanup()
            raise

        membership_warning: str | None = None
        try:
            from racelab_engine.services.session_service import (
                rebind_recording_alias_memberships,
            )

            aliases = self.repository.list_recording_alias_run_ids(
                source_file_sha256
            )
            rebind_recording_alias_memberships(
                run_id,
                aliases,
                db_path=self.repository.db_path,
            )
        except (OSError, TypeError, ValueError) as exc:
            membership_warning = (
                "Recording import succeeded, but legacy session aliases could not "
                f"be rebound to the canonical owner: {exc}"
            )

        # ── Post-import analysis ──────────────────────────────────
        rows_or_frame: Any = normalized_frame if normalized_frame is not None else result.records
        # 1. Build and persist segments
        t0 = time.perf_counter()
        segments_persisted = False
        segment_warning: str | None = None
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
            segments_persisted = True
            for k, v in segment_profile.items():
                _timings[f"segment_sub_{k}"] = float(v)
        except Exception as exc:
            _log.warning("Segment persistence failed for run %s: %s", run_id, exc)
            segment_warning = "Segment analysis could not be persisted; lap and run analysis remain available."
        _timings["segment_building"] = time.perf_counter() - t0

        numeric_timings = [(k, v) for k, v in _timings.items() if isinstance(v, (int, float))]
        _log.info(
            "Import stage timings for %s: %s",
            run_id,
            " | ".join(f"{k}={float(v):.2f}s" for k, v in sorted(numeric_timings, key=lambda x: -float(x[1]))),
        )
        self.last_import_timings = dict(_timings)

        implemented = list(result.status.implemented)
        completed_persistence = ["SQLite persistence", f"telemetry cache persistence ({cache_result.format})"]
        if segments_persisted:
            completed_persistence.append("segment persistence")
        for item in completed_persistence:
            if item not in implemented:
                implemented.append(item)
        status_message = "Existing run updated." if existing_run_updated else (
            "Imported and persisted iRacing .ibt header, variable definitions, "
            "session YAML, MVP telemetry channels, analysis summaries, "
            "telemetry cache, and segments."
        )
        warnings = list(result.status.warnings)
        if segment_warning:
            warnings.append(segment_warning)
        if membership_warning:
            warnings.append(membership_warning)
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
