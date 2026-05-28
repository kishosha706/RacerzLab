from __future__ import annotations

import csv
import importlib.util
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from racelab_engine.analysis.calculated_channels import (
    CALCULATED_CHANNEL_UNITS,
    HIGH_VALUE_RAW_CHANNELS,
    channel_metadata,
    normalize_telemetry_rows,
)
from racelab_engine.analysis.constants import FORCE_PROXY_WARNING, FORCE_PROXY_CHANNELS
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


def default_data_dir() -> Path:
    return Path(os.environ.get("RACELAB_DATA_DIR", "data"))


def parquet_path(data_dir: Path, run_id: str) -> Path:
    return data_dir / "cache" / "parquet" / f"{run_id}.parquet"


def csv_path(data_dir: Path, run_id: str) -> Path:
    return data_dir / "cache" / "normalized" / f"{run_id}.csv"


def channel_metadata_path(data_dir: Path, run_id: str) -> Path:
    return data_dir / "cache" / "normalized" / f"{run_id}.channels.json"


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
) -> Path:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    path = channel_metadata_path(data_root, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([definition.model_dump() for definition in definitions], indent=2),
        encoding="utf-8",
    )
    return path


def read_channel_metadata(run_id: str, data_dir: str | Path | None = None) -> list[dict[str, Any]]:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    path = channel_metadata_path(data_root, run_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def write_telemetry_cache(run_id: str, rows: list[dict[str, Any]], data_dir: str | Path | None = None) -> TelemetryCacheResult:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    data_root.mkdir(parents=True, exist_ok=True)

    if importlib.util.find_spec("polars") is not None:
        pl = importlib.import_module("polars")

        path = parquet_path(data_root, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        columns = _scalar_columns(rows)
        data = [{column: row.get(column) for column in columns} for row in rows]
        try:
            pl.DataFrame(data).write_parquet(path)
        except Exception:
            # Fallback: build with full schema inference for mixed-type columns
            pl.DataFrame(data, infer_schema_length=None).write_parquet(path)
        return TelemetryCacheResult(path=path, format="parquet", used_fallback=False)

    if importlib.util.find_spec("pandas") is not None and importlib.util.find_spec("pyarrow") is not None:
        pd = importlib.import_module("pandas")

        path = parquet_path(data_root, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        columns = _scalar_columns(rows)
        data = [{column: row.get(column) for column in columns} for row in rows]
        pd.DataFrame(data).to_parquet(path)
        return TelemetryCacheResult(path=path, format="parquet", used_fallback=False)

    return _write_csv(rows, csv_path(data_root, run_id))


def _coerce_number(value: str) -> Any:
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return value
    return int(number) if number.is_integer() else number


def read_telemetry_rows(run_id: str, data_dir: str | Path | None = None) -> list[dict[str, Any]]:
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    parquet = parquet_path(data_root, run_id)
    if parquet.exists() and importlib.util.find_spec("polars") is not None:
        pl = importlib.import_module("polars")

        return normalize_telemetry_rows([dict(row) for row in pl.read_parquet(parquet).to_dicts()])
    if parquet.exists() and importlib.util.find_spec("pandas") is not None:
        pd = importlib.import_module("pandas")

        return normalize_telemetry_rows(pd.read_parquet(parquet).to_dict("records"))

    csv_file = csv_path(data_root, run_id)
    if not csv_file.exists():
        return []
    with csv_file.open("r", newline="", encoding="utf-8") as file_obj:
        rows = [
            {key: _coerce_number(value) for key, value in row.items()}
            for row in csv.DictReader(file_obj)
        ]
    return normalize_telemetry_rows(rows)


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
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    stats = _channel_stats(rows, name)
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


def build_channel_catalog(run_id: str, data_dir: str | Path | None = None) -> list[dict[str, Any]]:
    rows = read_telemetry_rows(run_id, data_dir)
    columns = _scalar_columns(rows)
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
        catalog.append(_build_catalog_item(name, definition, is_raw, is_calculated, name in column_set, rows))
    return catalog


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

    def import_ibt_file(self, path: str | Path) -> tuple[IBTImportResult, TelemetryCacheResult | None]:
        import logging
        _log = logging.getLogger(__name__)
        _timings: dict[str, float] = {}

        t0 = time.time()
        result = import_ibt(path)
        _timings["decode_ibt"] = time.time() - t0

        if result.overview is None:
            return result, None

        run_id = result.overview.run_id

        t0 = time.time()
        cache_result = write_telemetry_cache(run_id, result.records, self.data_dir)
        _timings["write_parquet_cache"] = time.time() - t0

        t0 = time.time()
        write_channel_metadata(result.overview.run_id, result.variable_definitions, self.data_dir)
        _timings["write_channel_metadata"] = time.time() - t0

        t0 = time.time()
        self.repository.save_import(result.overview, result.fingerprint)
        _timings["save_run_metadata"] = time.time() - t0

        # ── Post-import analysis ──────────────────────────────────
        # 1. Build and persist segments
        t0 = time.time()
        try:
            from racelab_engine.analysis.segments import build_fixed_pct_segments
            from racelab_engine.models.segment import SegmentSummary as ModelSegment
            rows = read_telemetry_rows(run_id, self.data_dir)
            if raw_segments := build_fixed_pct_segments(rows, run_id=run_id):
                model_segments = [
                    ModelSegment(**seg.model_dump()) for seg in raw_segments
                ]
                self.repository.save_segments(run_id, model_segments)
                _log.info("Saved %d segments for run %s", len(model_segments), run_id)
        except Exception as exc:
            _log.warning("Segment persistence failed for run %s: %s", run_id, exc)
        _timings["segment_building"] = time.time() - t0

        # 2. Run draft detection on each useful lap
        t0 = time.time()
        try:
            from racelab_engine.analysis.draft_detection import classify_draft_status
            rows = read_telemetry_rows(run_id, self.data_dir)
            tags_updated = False
            for lap in result.overview.laps:
                if not lap.is_useful:
                    continue
                draft = classify_draft_status(rows, lap_number=lap.lap_number)
                if draft.status.value != "UNKNOWN_DRAFT_STATUS":
                    tag = draft.status.value
                    if not lap.classification_tags:
                        lap.classification_tags = []
                    if tag not in lap.classification_tags:
                        lap.classification_tags.append(tag)
                        tags_updated = True
                    if draft.warnings:
                        for w in draft.warnings:
                            if w not in result.overview.warnings:
                                result.overview.warnings.append(w)
            if tags_updated:
                self.repository.save_import(result.overview, result.fingerprint)
                _log.info("Draft tags updated for run %s", run_id)
        except Exception as exc:
            _log.warning("Draft detection failed for run %s: %s", run_id, exc)
        _timings["draft_detection"] = time.time() - t0

        _log.info("Import stage timings for %s: %s", run_id,
                  " | ".join(f"{k}={v:.2f}s" for k, v in sorted(_timings.items(), key=lambda x: -x[1])))

        implemented = list(result.status.implemented)
        for item in ["SQLite persistence", f"telemetry cache persistence ({cache_result.format})",
                      "segment persistence", "draft detection"]:
            if item not in implemented:
                implemented.append(item)
        result.status = result.status.model_copy(
            update={
                "message": (
                    "Imported and persisted iRacing .ibt header, variable definitions, "
                    "session YAML, MVP telemetry channels, analysis summaries, "
                    "telemetry cache, segments, and draft detection."
                ),
                "implemented": implemented,
                "remaining": [
                    item for item in result.status.remaining if item != "persist normalized telemetry cache"
                ],
            }
        )
        return result, cache_result
