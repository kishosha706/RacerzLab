from __future__ import annotations

import logging
import math
import re
import struct
import time
from pathlib import Path
from typing import Any, Collection, Mapping, cast

import polars as pl

from racelab_engine.analysis.calculated_channels import (
    CORE_REQUIRED_CHANNELS,
    HIGH_VALUE_RAW_CHANNELS,
    normalize_telemetry_rows,
)
from racelab_engine.analysis.constants import LOW_BRAKE_PCT, PLATFORM_VALID_MIN_SPEED_MPH, PLATFORM_VALID_THROTTLE_PCT
from racelab_engine.analysis.drag_scrub import detect_drag_scrub_risk_zones
from racelab_engine.analysis.evidence_contracts import (
    EvidenceEvaluationInput,
    EvidenceState,
    RUN_OBSERVATION_CONTRACT,
    evaluate_evidence_contract,
)
from racelab_engine.analysis.lap_classification import classify_laps
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.analysis.lap_detection import detect_laps
from racelab_engine.analysis.platform_events import PlatformEvent, detect_platform_events
from racelab_engine.analysis.proximity_context import classify_proximity_time_gap_window
from racelab_engine.analysis.time_alignment import detect_engineering_phases
from racelab_engine.io.file_fingerprint import fingerprint_file
from racelab_engine.io.ibt_types import IBTHeader, IBTImportResult, IBTVariableDefinition, ImportStatus
from racelab_engine.io.session_yaml import extract_session_summary, extract_setup_snapshot, parse_session_yaml
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.session import RunOverview


_log = logging.getLogger(__name__)
LAST_IMPORT_PROFILE: dict[str, Any] = {}


def _subprofile_enabled() -> bool:
    import os
    return os.environ.get("RACELAB_IMPORT_SUBPROFILE", "").strip().lower() in {"1", "true", "yes", "on"}


def _var_subprofile_enabled() -> bool:
    import os
    return os.environ.get("RACELAB_IMPORT_VAR_PROFILE", "").strip().lower() in {"1", "true", "yes", "on"}


class IBTParseError(ValueError):
    """Raised when an `.ibt` file does not match the expected iRacing SDK layout."""


DATA_TYPE_NAMES = {
    0: "char",
    1: "bool",
    2: "int",
    3: "bitfield",
    4: "float",
    5: "double",
}

DATA_TYPE_SIZES = {
    0: 1,
    1: 1,
    2: 4,
    3: 4,
    4: 4,
    5: 8,
}

TARGET_CHANNELS = list(dict.fromkeys([*CORE_REQUIRED_CHANNELS, *HIGH_VALUE_RAW_CHANNELS]))

_CANONICAL_SHOCK_DEFL_CHANNELS: tuple[str, ...] = (
    "LFshockDefl",
    "RFshockDefl",
    "LRshockDefl",
    "RRshockDefl",
)
_LEGACY_SHOCK_DEFL_CHANNELS: tuple[str, ...] = (
    "LFSHshockDefl",
    "RFSHshockDefl",
    "LRSHshockDefl",
    "RRSHshockDefl",
)
_CANONICAL_SHOCK_VEL_CHANNELS: tuple[str, ...] = (
    "LFshockVel",
    "RFshockVel",
    "LRshockVel",
    "RRshockVel",
)
_LEGACY_SHOCK_VEL_CHANNELS: tuple[str, ...] = (
    "LFSHshockVel",
    "RFSHshockVel",
    "LRSHshockVel",
    "RRSHshockVel",
)
_ALL_SHOCK_MOVEMENT_CHANNELS: frozenset[str] = frozenset(
    [
        *_CANONICAL_SHOCK_DEFL_CHANNELS,
        *_LEGACY_SHOCK_DEFL_CHANNELS,
        *_CANONICAL_SHOCK_VEL_CHANNELS,
        *_LEGACY_SHOCK_VEL_CHANNELS,
    ]
)
_SHOCK_MOVEMENT_UNAVAILABLE_WARNING = (
    "Shock movement telemetry is unavailable for this run. "
    "Garage damper settings from the setup snapshot can still be shown, "
    "but shock velocity/deflection analysis may be limited."
)


def _shock_movement_telemetry_available(available_channels: Collection[str]) -> bool:
    return any(channel in available_channels for channel in _ALL_SHOCK_MOVEMENT_CHANNELS)


def _build_missing_optional_warnings(
    missing_channels: list[str],
    available_channels: Collection[str],
) -> list[str]:
    warnings: list[str] = []
    non_shock_missing = [channel for channel in missing_channels if channel not in _ALL_SHOCK_MOVEMENT_CHANNELS]
    if non_shock_missing:
        warnings.append(f"Missing optional channels: {', '.join(non_shock_missing)}.")
    if not _shock_movement_telemetry_available(available_channels):
        warnings.append(_SHOCK_MOVEMENT_UNAVAILABLE_WARNING)
    return warnings


def _collect_missing_channels(available_channels: Collection[str]) -> list[str]:
    shock_available = _shock_movement_telemetry_available(available_channels)
    missing: list[str] = []
    for channel in CORE_REQUIRED_CHANNELS:
        if channel in _ALL_SHOCK_MOVEMENT_CHANNELS:
            if shock_available:
                continue
        elif channel in available_channels:
            continue
        missing.append(channel)
    return missing


def _read_bytes(path: str | Path) -> bytes:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)
    return file_path.read_bytes()


def _decode_c_string(value: bytes) -> str:
    return value.split(b"\0", 1)[0].decode("utf-8", errors="replace").strip()


def _parse_header(data: bytes, file_size: int) -> IBTHeader:
    if len(data) < 144:
        raise IBTParseError("File is too small to contain an iRacing telemetry header.")

    (
        version,
        status,
        tick_rate,
        session_info_update,
        session_info_length,
        session_info_offset,
        num_vars,
        var_header_offset,
        num_buf,
        buf_len,
        _pad_0,
        _pad_1,
    ) = struct.unpack_from("<12i", data, 0)

    if version <= 0 or tick_rate <= 0 or num_vars <= 0 or var_header_offset <= 0 or buf_len <= 0:
        raise IBTParseError("File header does not look like a supported iRacing .ibt file.")

    var_bufs: list[dict[str, int]] = []
    for index in range(4):
        tick_count, buf_offset = struct.unpack_from("<2i", data, 48 + index * 8)
        var_bufs.append({"index": index, "tick_count": tick_count, "offset": buf_offset})

    data_offset = next((item["offset"] for item in var_bufs if item["offset"] > 0), 0)
    if data_offset <= 0:
        data_offset = session_info_offset + session_info_length

    if data_offset > file_size:
        raise IBTParseError("Telemetry data offset is outside the file.")

    record_count = max(0, (file_size - data_offset) // buf_len)

    return IBTHeader(
        version=version,
        status=status,
        telemetry_rate_hz=tick_rate,
        session_info_update=session_info_update,
        session_info_length=session_info_length,
        session_info_offset=session_info_offset,
        variable_count=num_vars,
        variable_header_offset=var_header_offset,
        buffer_count=num_buf,
        record_length=buf_len,
        data_offset=data_offset,
        record_count=record_count,
        duration_seconds=record_count / tick_rate if tick_rate else None,
        raw_header={
            "var_bufs": var_bufs,
            "session_info_end": session_info_offset + session_info_length,
        },
    )


def read_header(path: str | Path) -> IBTHeader:
    """Read the iRacing SDK file header from an `.ibt` telemetry file."""

    data = _read_bytes(path)
    return _parse_header(data, len(data))


def _parse_variable_definitions(data: bytes, header: IBTHeader) -> list[IBTVariableDefinition]:
    if header.variable_count is None or header.variable_header_offset is None:
        raise IBTParseError("Header is missing variable metadata offsets.")

    definitions: list[IBTVariableDefinition] = []
    for index in range(header.variable_count):
        offset = header.variable_header_offset + index * 144
        chunk = data[offset : offset + 144]
        if len(chunk) != 144:
            raise IBTParseError(f"Variable definition {index} is truncated.")

        data_type_id, var_offset, count, count_as_time = struct.unpack_from("<4i", chunk, 0)
        definitions.append(
            IBTVariableDefinition(
                name=_decode_c_string(chunk[16:48]),
                description=_decode_c_string(chunk[48:112]) or None,
                unit=_decode_c_string(chunk[112:144]) or None,
                data_type=DATA_TYPE_NAMES.get(data_type_id, f"unknown:{data_type_id}"),
                data_type_id=data_type_id,
                offset=var_offset,
                count=count,
                count_as_time=bool(count_as_time),
            )
        )

    _validate_variable_definitions(header, definitions)
    return definitions


def _validate_variable_definitions(
    header: IBTHeader,
    definitions: Collection[IBTVariableDefinition],
) -> None:
    """Reject declarations that cannot map safely into a fixed telemetry record."""

    if header.record_length is None or header.record_length <= 0:
        raise IBTParseError("Header is missing a valid telemetry record length.")
    seen: set[str] = set()
    for index, definition in enumerate(definitions):
        label = definition.name or f"definition {index}"
        if not definition.name:
            raise IBTParseError(f"Variable definition {index} has an empty name.")
        if definition.name in seen:
            raise IBTParseError(f"Duplicate telemetry variable name: {definition.name}.")
        seen.add(definition.name)
        if definition.count <= 0:
            raise IBTParseError(f"Telemetry variable {label} has invalid element count {definition.count}.")
        if definition.offset < 0:
            raise IBTParseError(f"Telemetry variable {label} has a negative record offset.")
        element_size = DATA_TYPE_SIZES.get(
            definition.data_type_id if definition.data_type_id is not None else -1
        )
        if element_size is None:
            raise IBTParseError(
                f"Unsupported iRacing variable type {definition.data_type_id} for {label}."
            )
        byte_count = element_size * definition.count
        if definition.offset + byte_count > header.record_length:
            raise IBTParseError(
                f"Telemetry variable {label} exceeds the {header.record_length}-byte record "
                f"({definition.offset}+{byte_count})."
            )


def read_variable_definitions(path: str | Path) -> list[IBTVariableDefinition]:
    """Read iRacing variable definitions, including name, unit, type, offset, and count."""

    data = _read_bytes(path)
    return _parse_variable_definitions(data, _parse_header(data, len(data)))


def read_session_yaml(path: str | Path) -> str:
    """Extract the embedded iRacing session YAML text from an `.ibt` file."""

    data = _read_bytes(path)
    header = _parse_header(data, len(data))
    if header.session_info_offset is None or header.session_info_length is None:
        raise IBTParseError("Header is missing session YAML offsets.")

    start = header.session_info_offset
    end = start + header.session_info_length
    if end > len(data):
        raise IBTParseError("Session YAML block is outside the file.")

    return data[start:end].split(b"\0", 1)[0].decode("utf-8", errors="replace")


def _extract_session_yaml_from_data(data: bytes, header: IBTHeader) -> str:
    if header.session_info_offset is None or header.session_info_length is None:
        raise IBTParseError("Header is missing session YAML offsets.")
    start = header.session_info_offset
    end = start + header.session_info_length
    if end > len(data):
        raise IBTParseError("Session YAML block is outside the file.")
    return data[start:end].split(b"\0", 1)[0].decode("utf-8", errors="replace")


def _decode_scalar(data: bytes, absolute_offset: int, definition: IBTVariableDefinition) -> Any:
    data_type_id = definition.data_type_id
    if data_type_id == 0:
        raw = data[absolute_offset : absolute_offset + max(1, definition.count)]
        return _decode_c_string(raw)
    if data_type_id == 1:
        return struct.unpack_from("<?", data, absolute_offset)[0]
    if data_type_id == 2:
        return struct.unpack_from("<i", data, absolute_offset)[0]
    if data_type_id == 3:
        return struct.unpack_from("<I", data, absolute_offset)[0]
    if data_type_id == 4:
        return struct.unpack_from("<f", data, absolute_offset)[0]
    if data_type_id == 5:
        return struct.unpack_from("<d", data, absolute_offset)[0]
    raise IBTParseError(f"Unsupported iRacing variable type {data_type_id} for {definition.name}.")


def _decode_value(data: bytes, record_offset: int, definition: IBTVariableDefinition) -> Any:
    if definition.data_type_id == 0:
        return _decode_scalar(data, record_offset + definition.offset, definition)

    count = max(1, definition.count)
    data_type_id = definition.data_type_id
    if data_type_id is None:
        raise IBTParseError(f"Missing data type ID for {definition.name}.")
    size = DATA_TYPE_SIZES.get(data_type_id)  # type: ignore[arg-type]
    if size is None:
        raise IBTParseError(f"Unsupported iRacing variable type {definition.data_type_id} for {definition.name}.")

    if count == 1:
        return _decode_scalar(data, record_offset + definition.offset, definition)

    return [
        _decode_scalar(data, record_offset + definition.offset + item_index * size, definition)
        for item_index in range(count)
    ]


def _read_records_from_data(
    data: bytes,
    header: IBTHeader,
    definitions: list[IBTVariableDefinition],
    variables: Collection[str] | None = None,
) -> list[Mapping[str, object]]:
    if header.data_offset is None or header.record_length is None or header.record_count is None:
        raise IBTParseError("Header is missing telemetry record offsets.")

    selected = [definition for definition in definitions if variables is None or definition.name in variables]
    rows: list[dict[str, Any]] = []
    for sample_index in range(header.record_count):
        record_offset = header.data_offset + sample_index * header.record_length
        row: dict[str, Any] = {"sample_index": sample_index}
        for definition in selected:
            row[definition.name] = _decode_value(data, record_offset, definition)
        rows.append(row)
    return cast(list[Mapping[str, object]], rows)


# Precompiled struct formats for columnar fast path
_STRUCT_FORMATS: dict[int, struct.Struct] = {
    1: struct.Struct("<?"),
    2: struct.Struct("<i"),
    3: struct.Struct("<I"),
    4: struct.Struct("<f"),
    5: struct.Struct("<d"),
}


def _read_records_columnar(
    data: bytes,
    header: IBTHeader,
    definitions: list[IBTVariableDefinition],
    variables: Collection[str] | None = None,
    profile_out: dict[str, float] | None = None,
) -> dict[str, list[Any]]:
    """Fast columnar decoder using precompiled structs and memoryview."""
    record_count = header.record_count
    record_len = header.record_length
    data_offset = header.data_offset
    if record_count is None or record_len is None or data_offset is None:
        raise IBTParseError("Header is missing telemetry record offsets.")

    profile_enabled = profile_out is not None
    var_profile_enabled = profile_enabled and _var_subprofile_enabled()
    t_plan = time.perf_counter() if profile_enabled else 0.0
    selected = [d for d in definitions if variables is None or d.name in variables]
    profile_loop_by_kind: dict[str, float] = {
        "column_alloc_s": 0.0,
        "record_loop_total_s": 0.0,
        "scalar_numeric_decode_s": 0.0,
        "string_decode_s": 0.0,
        "array_numeric_decode_s": 0.0,
    }
    t_cols = time.perf_counter() if profile_enabled else 0.0
    columns: dict[str, list[Any]] = {d.name: [None] * record_count for d in selected}
    columns["sample_index"] = list(range(record_count))
    if profile_enabled:
        profile_loop_by_kind["column_alloc_s"] = time.perf_counter() - t_cols
    mv = memoryview(data)

    scalar_plans: list[tuple[str, list[Any], int, struct.Struct]] = []
    string_plans: list[tuple[str, list[Any], int, int]] = []
    array_plans: list[tuple[str, list[Any], int, int, struct.Struct]] = []
    type_counts: dict[str, int] = {"scalar": 0, "string": 0, "array": 0}
    for defn in selected:
        dt = defn.data_type_id
        if dt is None:
            raise IBTParseError(f"Missing data type ID for {defn.name}.")
        count = max(1, defn.count)
        if dt == 0:
            string_plans.append((defn.name, columns[defn.name], defn.offset, count))
            type_counts["string"] += 1
            continue
        fmt = _STRUCT_FORMATS.get(dt)
        if fmt is None:
            raise IBTParseError(f"Unsupported iRacing variable type {dt} for {defn.name}.")
        if count == 1:
            scalar_plans.append((defn.name, columns[defn.name], defn.offset, fmt))
            type_counts["scalar"] += 1
        else:
            array_plans.append((defn.name, columns[defn.name], defn.offset, count, fmt))
            type_counts["array"] += 1
    if profile_enabled:
        profile_out["decode_columnar_decode_plan_s"] = time.perf_counter() - t_plan
        profile_out["decode_columnar_variable_count"] = float(len(selected))
        profile_out["decode_columnar_record_count"] = float(record_count)
        profile_out["decode_columnar_estimated_scalar_values"] = float(record_count * len(selected))
        profile_out["decode_columnar_type_count_scalar"] = float(type_counts["scalar"])
        profile_out["decode_columnar_type_count_string"] = float(type_counts["string"])
        profile_out["decode_columnar_type_count_array"] = float(type_counts["array"])

    per_var_s: dict[str, float] = {}
    t_loop_total = time.perf_counter() if profile_enabled else 0.0
    rec_start = data_offset
    for row_idx in range(record_count):
        for name, out_col, offset, count in string_plans:
            abs_off = rec_start + offset
            var_t0 = time.perf_counter() if var_profile_enabled else 0.0
            out_col[row_idx] = _decode_c_string(bytes(mv[abs_off : abs_off + count]))
            if var_profile_enabled:
                profile_loop_by_kind["string_decode_s"] += time.perf_counter() - var_t0
        for name, out_col, offset, fmt in scalar_plans:
            abs_off = rec_start + offset
            var_t0 = time.perf_counter() if var_profile_enabled else 0.0
            out_col[row_idx] = fmt.unpack_from(mv, abs_off)[0]
            if var_profile_enabled:
                profile_loop_by_kind["scalar_numeric_decode_s"] += time.perf_counter() - var_t0
        for name, out_col, offset, count, fmt in array_plans:
            abs_off = rec_start + offset
            var_t0 = time.perf_counter() if var_profile_enabled else 0.0
            size = fmt.size
            out_col[row_idx] = [fmt.unpack_from(mv, abs_off + i * size)[0] for i in range(count)]
            if var_profile_enabled:
                profile_loop_by_kind["array_numeric_decode_s"] += time.perf_counter() - var_t0
            if var_profile_enabled:
                per_var_s[name] = per_var_s.get(name, 0.0) + (time.perf_counter() - var_t0)
        rec_start += record_len

    if profile_enabled:
        profile_loop_by_kind["record_loop_total_s"] = time.perf_counter() - t_loop_total
        profile_out.update({f"decode_columnar_{k}": v for k, v in profile_loop_by_kind.items()})
        if var_profile_enabled and per_var_s:
            top = sorted(per_var_s.items(), key=lambda item: item[1], reverse=True)[:10]
            for idx, (name, seconds) in enumerate(top, start=1):
                profile_out[f"decode_var_top_{idx:02d}_{name}_s"] = seconds
    return columns


def _analysis_columns(columns: Mapping[str, list[Any]], target_vars: Collection[str]) -> dict[str, list[Any]]:
    """Keep calculated-channel work narrow while the raw vault stays complete."""

    selected = {name: values for name, values in columns.items() if name == "sample_index" or name in target_vars}
    return selected


def _raw_archive_column_mapping(
    normalized_columns: Collection[str],
    raw_names: Collection[str],
) -> dict[str, str]:
    """Allocate a collision-free physical column for every raw source name."""

    used = set(normalized_columns)
    mapping: dict[str, str] = {}
    for raw_name in raw_names:
        archive_name = raw_name
        source_passthrough = raw_name in HIGH_VALUE_RAW_CHANNELS and raw_name in used
        while archive_name in used and not source_passthrough:
            archive_name = f"raw__{archive_name}"
        mapping[raw_name] = archive_name
        used.add(archive_name)
    return mapping


def _merge_raw_columns(normalized_frame: pl.DataFrame, raw_columns: Mapping[str, list[Any]]) -> pl.DataFrame:
    """Add untouched source columns after normalization has created aliases.

    Normalization intentionally renames a subset of iRacing names.  Adding the
    raw columns back makes provenance lossless without exposing every channel to
    every calculated-channel expression.
    """

    mapping = _raw_archive_column_mapping(normalized_frame.columns, raw_columns)
    additions = {
        archive_name: raw_columns[raw_name]
        for raw_name, archive_name in mapping.items()
        if archive_name != raw_name or raw_name not in normalized_frame.columns
    }
    if not additions:
        return normalized_frame
    raw_frame = pl.DataFrame(additions, strict=False)
    if raw_frame.height != normalized_frame.height:
        raise IBTParseError("Raw and normalized telemetry row counts do not match.")
    return normalized_frame.hstack(raw_frame)


def _merge_raw_rows(
    normalized_rows: list[dict[str, Any]],
    raw_rows: Collection[Mapping[str, object]],
) -> list[dict[str, Any]]:
    raw_list = list(raw_rows)
    if len(normalized_rows) != len(raw_list):
        raise IBTParseError("Raw and normalized telemetry row counts do not match.")
    normalized_names = normalized_rows[0].keys() if normalized_rows else ()
    raw_names = raw_list[0].keys() if raw_list else ()
    mapping = _raw_archive_column_mapping(normalized_names, raw_names)
    merged: list[dict[str, Any]] = []
    for raw, normalized in zip(raw_list, normalized_rows):
        row = dict(normalized)
        row.update({mapping[name]: value for name, value in raw.items()})
        merged.append(row)
    return merged


def read_records(path: str | Path, variables: Collection[str] | None = None) -> list[Mapping[str, object]]:
    """Decode telemetry records from an `.ibt` file.

    By default this decodes every variable. Pass `variables` to keep the in-memory
    structure narrow while the project still uses an internal list-of-dicts table.
    """

    data = _read_bytes(path)
    header = _parse_header(data, len(data))
    definitions = _parse_variable_definitions(data, header)
    return _read_records_from_data(data, header, definitions, variables=variables)


def read_normalized_records(path: str | Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Read the MVP telemetry channels and add calculated normalized fields."""

    data = _read_bytes(path)
    header = _parse_header(data, len(data))
    definitions = _parse_variable_definitions(data, header)
    available = {definition.name for definition in definitions}
    missing = [channel for channel in CORE_REQUIRED_CHANNELS if channel not in available]
    target_vars = [channel for channel in TARGET_CHANNELS if channel in available]

    # ── Columnar decoder (default, env-overridable) ─────────────
    import os
    import logging
    _dec_log = logging.getLogger(__name__)
    decoder_mode = os.environ.get("RACELAB_IBT_DECODER", "").strip().lower()
    use_columnar = decoder_mode != "row"

    if use_columnar:
        try:
            t0 = time.perf_counter()
            columns = _read_records_columnar(data, header, definitions, variables=target_vars)
            from racelab_engine.analysis.vectorized_channels import normalize_telemetry_frame, frame_to_rows
            df = normalize_telemetry_frame(columns)
            result = frame_to_rows(df)
            dt = time.perf_counter() - t0
            _dec_log.info(
                "decoder=columnar rows=%d channels=%d time=%.3fs",
                len(result), len(columns), dt,
            )
            if result and "Speed" not in result[0]:
                # Preserve legacy test/read contract that includes raw alias keys.
                result = normalize_telemetry_rows(result)
            if result and "Speed" not in result[0]:
                for row in result:
                    speed_mps = row.get("speed_mps")
                    if speed_mps is None and row.get("speed_mph") is not None:
                        speed_mps = float(row["speed_mph"]) / 2.23693629
                    row["Speed"] = speed_mps
            return result, missing
        except Exception:
            _dec_log.warning("Columnar decoder failed, falling back to row decoder", exc_info=True)

    raw_rows = _read_records_from_data(
        data, header, definitions,
        variables=target_vars,
    )
    return normalize_telemetry_rows(raw_rows), missing


def _slug_run_id(file_path: Path, file_hash: str) -> str:
    stem = re.sub(r"[^a-zA-Z0-9]+", "-", file_path.stem).strip("-").lower()
    return f"{stem[:48]}-{file_hash[:8]}"


_OVERVIEW_ROW_COLUMNS: frozenset[str] = frozenset({
    # Canonical lap eligibility and sample-integrity inputs.
    "lap",
    "lap_number",
    "lap_dist_pct",
    "lap_dist_pct_100",
    "lap_dist_m",
    "lap_dist_ft",
    "session_time",
    "session_tick",
    "session_flags",
    "speed_mps",
    "speed_mph",
    "rpm",
    "throttle_pct",
    "brake_pct",
    "dynamic_pressure_psf",
    "on_pit_road",
    "is_on_track",
    "player_track_surface",
    "player_incident_count",
    "player_driver_incident_count",
    "player_team_incident_count",
    # Platform-event location, validity, and sustained-risk inputs.
    "cfsr_height_mm",
    "cfs_ride_height_in",
    "cfs_ride_height_mm",
    "cfs_risk_score",
    "speed_rate_mph_s",
    "speed_rate_mph_1000ft",
    "track_x_ft",
    "track_y_ft",
    "zone_name",
    # Phase-at-event inputs. Keep this synchronized with _PHASE_CHANNELS in
    # time_alignment.py; this projection changes representation, not evidence.
    "steering_deg",
    "steering_rad",
    "abs_steering_deg",
    "yaw_rate",
    "lat_accel",
    "long_accel",
    "vert_accel",
    "vert_accel_g",
    "lat",
    "lon",
    "alt",
    "enter_exit_reset_state",
    "lf_shock_defl_in",
    "rf_shock_defl_in",
    "lr_shock_defl_in",
    "rr_shock_defl_in",
    "lf_shock_vel_in_s",
    "rf_shock_vel_in_s",
    "lr_shock_vel_in_s",
    "rr_shock_vel_in_s",
    "lf_ride_height_in",
    "rf_ride_height_in",
    "lr_ride_height_in",
    "rr_ride_height_in",
})

_PROXIMITY_ROW_COLUMNS: tuple[str, ...] = (
    "car_distance_ahead_m",
    "car_distance_behind_m",
    "speed_mps",
    "speed_mph",
    "CarDistAhead",
    "CarDistBehind",
    "Speed",
)

_FRAME_NATIVE_DRAG_COLUMNS: frozenset[str] = frozenset({
    "lap_dist_pct",
    "speed_mph",
    "rpm",
    "throttle_pct",
    "brake_pct",
    "speed_rate_mph_s",
    "dynamic_pressure_psf",
    "abs_steering_deg",
    "yaw_rate",
    "cfs_risk_score",
    "lat_accel",
    "cfsr_height_mm",
    "lap_dist_m",
})


def _platform_detection_rows(table: Any) -> list[dict[str, Any]]:
    if isinstance(table, pl.DataFrame):
        # A production frame contains the lossless raw archive (hundreds of
        # columns), while overview detectors consume only this explicit evidence
        # slice. Materializing the full vault into Python dictionaries multiplies
        # import time and peak memory without changing any conclusion.
        selected = [name for name in table.columns if name in _OVERVIEW_ROW_COLUMNS]
        return table.select(selected).to_dicts()
    if isinstance(table, list) and table and isinstance(table[0], dict):
        if "speed_mph" in table[0]:
            return cast(list[dict[str, Any]], table)
    return normalize_telemetry_rows(table)


def _usable_channel_names(table: Any) -> frozenset[str]:
    """Return channels with at least one observed value without row materialization."""

    if isinstance(table, pl.DataFrame):
        if table.is_empty():
            return frozenset()
        null_counts = table.null_count().row(0, named=True)
        return frozenset(
            name for name, count in null_counts.items()
            if int(count) < table.height
        )
    rows = _platform_detection_rows(table)
    return frozenset(
        key
        for row in rows
        for key, value in row.items()
        if value is not None
    )


def _safe_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


_PLATFORM_MAX_SPEED_MPH = 300.0
_PLATFORM_MIN_CLEARANCE_MM = -25.4
_PLATFORM_MAX_CLEARANCE_MM = 500.0
_PERCENT_MIN = 0.0
_PERCENT_MAX = 100.0


def _lap_pct_100(row: Mapping[str, Any]) -> float | None:
    explicit_pct = _safe_float(row.get("lap_dist_pct_100"))
    if explicit_pct is not None:
        return explicit_pct
    raw_pct = _safe_float(row.get("lap_dist_pct"))
    if raw_pct is None:
        return None
    return raw_pct * 100.0 if 0.0 <= raw_pct <= 1.5 else raw_pct


def _is_complete_lap(lap_rows: list[dict[str, Any]]) -> bool:
    lap_pcts = [pct for row in lap_rows if (pct := _lap_pct_100(row)) is not None]
    return bool(lap_pcts) and min(lap_pcts) <= 2.0 and max(lap_pcts) >= 98.0


def _platform_event_to_overview_marker(
    event: PlatformEvent,
    row: Mapping[str, Any],
    *,
    run_id: str,
    is_complete_lap: bool,
    is_eligible_lap: bool,
    has_sustained_risk: bool,
) -> TelemetryEvent:
    splitter_mm = _safe_float(row.get("cfsr_height_mm"))
    speed_mph = _safe_float(row.get("speed_mph"))
    throttle_pct = _safe_float(row.get("throttle_pct"))
    brake_pct = _safe_float(row.get("brake_pct"))
    plausible_numeric_context = (
        splitter_mm is not None
        and _PLATFORM_MIN_CLEARANCE_MM <= splitter_mm <= _PLATFORM_MAX_CLEARANCE_MM
        and speed_mph is not None
        and 0.0 < speed_mph <= _PLATFORM_MAX_SPEED_MPH
        and throttle_pct is not None
        and _PERCENT_MIN <= throttle_pct <= _PERCENT_MAX
        and brake_pct is not None
        and _PERCENT_MIN <= brake_pct <= _PERCENT_MAX
    )
    valid_for_tuning = (
        plausible_numeric_context
        and is_complete_lap
        and is_eligible_lap
        and event.display_scope in {"actionable", "watch"}
        and has_sustained_risk
        and speed_mph >= PLATFORM_VALID_MIN_SPEED_MPH
        and throttle_pct >= PLATFORM_VALID_THROTTLE_PCT
        and brake_pct <= LOW_BRAKE_PCT
    )
    lap_pct_peak = event.lap_pct if event.lap_pct is not None else _lap_pct_100(row)
    event_type = "PLATFORM_SCRAPE" if splitter_mm is not None and splitter_mm <= 0.0 else "PLATFORM_LOW"
    return TelemetryEvent(
        event_id=f"{run_id}:{event.event_id}",
        run_id=run_id,
        lap_number=event.lap,
        event_type=event_type,
        event_subtype=event.severity,
        lap_pct_start=lap_pct_peak,
        lap_pct_end=lap_pct_peak,
        lap_pct_peak=lap_pct_peak,
        distance_m_peak=_safe_float(row.get("lap_dist_m")),
        zone_name=row.get("zone_name"),
        severity=event.severity,
        confidence_score=0.75 if valid_for_tuning else 0.35,
        valid_for_tuning=valid_for_tuning,
        primary_metric_name="cfsr_height_mm",
        primary_metric_value=splitter_mm,
        evidence_json={
            "phase": row.get("engineering_phase"),
            "speed_mph": speed_mph,
            "throttle_pct": throttle_pct,
            "brake_pct": brake_pct,
            "splitter_height_mm": splitter_mm,
            "is_complete_lap": is_complete_lap,
            "is_eligible_lap": is_eligible_lap,
            "display_scope": event.display_scope,
            "has_sustained_risk": has_sustained_risk,
            "plausible_numeric_context": plausible_numeric_context,
            "validity_rule": (
                "eligible complete-lap high-speed full-throttle low-brake event"
                if valid_for_tuning
                else "not valid for tuning because the canonical lap gate or local operating context failed"
            ),
        },
        related_setup_keys=["front_ride_height", "front_springs", "packers", "steering_offset"],
        evidence_state=(
            EvidenceState.CALCULATED
            if valid_for_tuning
            else EvidenceState.BLOCKED_BY_CONTEXT
        ),
        source_channels=["lap_dist_pct", "cfsr_height_mm", "speed_mph", "throttle_pct", "brake_pct"],
        blocker_reasons=(
            []
            if valid_for_tuning
            else ["Canonical lap eligibility or the local operating-context gate failed."]
        ),
    )


def _sustained_platform_risk_interval(
    rows: list[dict[str, Any]], sample_index: int,
) -> tuple[int, int] | None:
    if not (0 <= sample_index < len(rows)):
        return None

    def is_low(sample: Mapping[str, Any]) -> bool:
        splitter_mm = _safe_float(sample.get("cfsr_height_mm"))
        if splitter_mm is not None:
            return splitter_mm <= 10.0
        cfs_in = _safe_float(sample.get("cfs_ride_height_in"))
        return cfs_in is not None and cfs_in <= 0.394

    start = sample_index
    end = sample_index
    while start > 0 and is_low(rows[start - 1]):
        start -= 1
    while end + 1 < len(rows) and is_low(rows[end + 1]):
        end += 1
    if end - start + 1 >= 3:
        return start, end
    start_ft = _safe_float(rows[start].get("lap_dist_ft"))
    end_ft = _safe_float(rows[end].get("lap_dist_ft"))
    if start_ft is not None and end_ft is not None and abs(end_ft - start_ft) >= 20.0:
        return start, end
    return None


def _has_sustained_platform_risk(rows: list[dict[str, Any]], sample_index: int) -> bool:
    return _sustained_platform_risk_interval(rows, sample_index) is not None


def _build_overview_platform_events(table: Any, run_id: str) -> list[TelemetryEvent]:
    rows = _platform_detection_rows(table)
    if not rows:
        return []
    eligible_lap_numbers = {
        lap.lap_number
        for lap in eligible_laps(classify_laps(detect_laps(rows, run_id=run_id)))
    }

    lap_numbers = sorted(
        {
            int(lap_value)
            for row in rows
            if (lap_value := _safe_float(row.get("lap"))) is not None
        }
    )
    lap_scope = lap_numbers or [None]
    events: list[TelemetryEvent] = []
    for lap_number in lap_scope:
        lap_rows = rows if lap_number is None else [row for row in rows if _safe_float(row.get("lap")) == float(lap_number)]
        if not lap_rows:
            continue
        platform_events = detect_platform_events(lap_rows, lap=lap_number, event_types=["MIN_SPLITTER"])
        if not platform_events:
            continue
        event = platform_events[0]
        if event.event_type != "MIN_SPLITTER":
            continue
        if not (0 <= event.sample_index < len(lap_rows)):
            continue
        event_row = lap_rows[event.sample_index]
        event_pct = event.lap_pct if event.lap_pct is not None else _lap_pct_100(event_row)
        if event_pct is not None:
            phase_by_position, _, _ = detect_engineering_phases(lap_rows)
            phase_index = max(0, min(len(phase_by_position) - 1, int(round(event_pct * 10.0))))
            event_row = {**event_row, "engineering_phase": phase_by_position[phase_index]}
        sustained_interval = _sustained_platform_risk_interval(lap_rows, event.sample_index)
        marker = _platform_event_to_overview_marker(
                event,
                event_row,
                run_id=run_id,
                is_complete_lap=_is_complete_lap(lap_rows),
                is_eligible_lap=lap_number is not None and lap_number in eligible_lap_numbers,
                has_sustained_risk=sustained_interval is not None,
            )
        if sustained_interval is not None:
            start_index, end_index = sustained_interval
            interval_start = _lap_pct_100(lap_rows[start_index])
            interval_end = _lap_pct_100(lap_rows[end_index])
            if interval_start is not None and interval_end is not None:
                marker = marker.model_copy(update={
                    "lap_pct_start": min(interval_start, interval_end),
                    "lap_pct_end": max(interval_start, interval_end),
                })
        events.append(marker)
    return events


def _build_primary_findings(best_lap: Any, platform_events: list[Any], drag_events: list[Any]) -> list[str]:
    findings: list[str] = []
    if best_lap is not None:
        findings.append(f"Lap {best_lap.lap_number} is the best useful lap.")
    if valid_drag_events := [event for event in drag_events if event.valid_for_tuning]:
        event = valid_drag_events[0]
        findings.append(
            f"{event.zone_name or 'A target zone'} behaves like a full-throttle drag/scrub risk zone."
        )
    if valid_platform := [event for event in platform_events if event.valid_for_tuning]:
        event = valid_platform[0]
        findings.append(
            f"Minimum valid splitter height is {event.primary_metric_value:.2f} mm near {event.lap_pct_peak:.2f}% lap."
        )
    return findings


def _qualify_overview_drag_events(
    events: list[TelemetryEvent],
    selected_lap_rows: list[dict[str, Any]],
) -> tuple[list[TelemetryEvent], str | None]:
    if not events:
        return [], None
    proximity = classify_proximity_time_gap_window(selected_lap_rows)
    if not proximity.blocks_relative_resistance:
        return [
            event.model_copy(
                update={
                    "evidence_json": {
                        **event.evidence_json,
                        "proximity_context": proximity.model_dump(mode="json"),
                    }
                }
            )
            for event in events
        ], None
    explanation = proximity.explanation
    return [
        event.model_copy(
            update={
                "valid_for_tuning": False,
                "confidence_score": min(event.confidence_score, 0.35),
                "evidence_state": EvidenceState.BLOCKED_BY_CONTEXT,
                "blocker_reasons": [explanation],
                "evidence_json": {
                    **event.evidence_json,
                    "proximity_context": proximity.model_dump(mode="json"),
                    "observation_withheld": True,
                },
            }
        )
        for event in events
    ], explanation


def _build_overview_drag_events(
    table: Any,
    *,
    run_id: str,
    best_lap: Any | None,
) -> tuple[list[TelemetryEvent], str | None]:
    """Detect drag-like observations only inside the canonical selected flying lap."""
    if best_lap is None:
        return [], None

    selected_lap_table: Any
    if isinstance(table, pl.DataFrame) and ({"lap", "lap_number"} & set(table.columns)):
        lap_expr = (
            pl.coalesce([pl.col("lap"), pl.col("lap_number")])
            if {"lap", "lap_number"}.issubset(table.columns)
            else pl.col("lap" if "lap" in table.columns else "lap_number")
        )
        selected_frame = table.filter(
            lap_expr.cast(pl.Int64, strict=False) == int(best_lap.lap_number)
        )
        selected_lap_rows = selected_frame.select(
            [name for name in _PROXIMITY_ROW_COLUMNS if name in selected_frame.columns]
        ).to_dicts()
        selected_lap_table = (
            selected_frame
            if _FRAME_NATIVE_DRAG_COLUMNS.issubset(selected_frame.columns)
            else _platform_detection_rows(selected_frame)
        )
    else:
        overview_rows = _platform_detection_rows(table)
        selected_lap_rows = [
            row
            for row in overview_rows
            if _safe_float(row.get("lap")) == float(best_lap.lap_number)
        ]
        selected_lap_table = selected_lap_rows
    detected = detect_drag_scrub_risk_zones(
        selected_lap_table,
        run_id=run_id,
        lap_number=best_lap.lap_number,
    )
    promoted = [
        event.model_copy(
            update={"valid_for_tuning": True}
        )
        if event.evidence_json.get("detector_observation_candidate") is True
        else event
        for event in detected
    ]
    return _qualify_overview_drag_events(promoted, selected_lap_rows)


def _best_useful_lap(rows: list[dict[str, Any]], run_id: str) -> Any:
    laps = classify_laps(detect_laps(rows, run_id=run_id))
    useful = eligible_laps(laps)
    return min(useful, key=lambda lap: lap.lap_time or 999999.0) if useful else None


def _setup_snapshot_has_recorded_values(setup: Any | None) -> bool:
    if setup is None:
        return False
    payload = setup.model_dump() if hasattr(setup, "model_dump") else dict(setup)
    ignored = {"setup_id", "run_id", "setup_name", "notes"}

    def recorded(value: Any) -> bool:
        if value is None or value == "":
            return False
        if isinstance(value, Mapping):
            return any(recorded(item) for item in value.values())
        if isinstance(value, (list, tuple, set)):
            return any(recorded(item) for item in value)
        return True

    return any(recorded(value) for key, value in payload.items() if key not in ignored)


def _build_overview(
    path: Path,
    file_hash: str,
    header: IBTHeader,
    session_yaml: str,
    telemetry_table: Any,
    missing_channels: list[str],
    available_channels: Collection[str],
) -> RunOverview:
    profile: dict[str, float] = {}
    t0 = time.perf_counter()
    run_id = _slug_run_id(path, file_hash)
    profile["overview_slug_run_id_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    parsed_yaml = parse_session_yaml(session_yaml)
    profile["overview_session_yaml_parse_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    session = extract_session_summary(session_yaml, run_id=run_id, parsed_data=parsed_yaml)
    session = session.model_copy(
        update={
            "source_file": str(path),
            "file_hash": file_hash,
            "telemetry_rate_hz": header.telemetry_rate_hz,
            "variable_count": header.variable_count,
            "record_count": header.record_count,
            "duration_seconds": header.duration_seconds,
        }
    )
    profile["overview_session_extract_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    setup = extract_setup_snapshot(session_yaml, run_id=run_id, parsed_data=parsed_yaml)
    profile["overview_setup_extract_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    detected_laps = detect_laps(telemetry_table, run_id=run_id)
    profile["overview_lap_detect_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    laps = classify_laps(detected_laps)
    profile["overview_lap_classify_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    useful_laps = eligible_laps(laps)
    best_lap = min(useful_laps, key=lambda lap: lap.lap_time or 999999.0) if useful_laps else None
    profile["overview_best_lap_pick_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    # Materialize the narrow row-only detector slice once. The normalized frame
    # also owns the complete raw archive, which must remain columnar here.
    overview_rows = _platform_detection_rows(telemetry_table)
    profile["overview_row_projection_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    platform_events = _build_overview_platform_events(overview_rows, run_id=run_id)
    profile["overview_platform_events_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    drag_events, proximity_warning = _build_overview_drag_events(
        telemetry_table,
        run_id=run_id,
        best_lap=best_lap,
    )
    profile["overview_drag_scrub_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    events = platform_events + drag_events
    usable_channels = _usable_channel_names(telemetry_table)
    profile["overview_usable_channels_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    linked_events = [
        event
        for event in events
        if event.valid_for_tuning
        and event.source_channels
        and set(event.source_channels).issubset(usable_channels)
    ]
    requested_outputs = frozenset({"located_engineering_observation"})
    setup_snapshot_captured = _setup_snapshot_has_recorded_values(setup)
    sample_integrity_observed_clear = (
        False
        if best_lap is not None and {"session_tick", "session_time"}.issubset(usable_channels)
        else None
    )
    sensitive_claim_requested = any(
        token in event.event_type.lower()
        for event in linked_events
        for token in ("degradation", "tire_wear", "cooling", "overheat")
    )
    missing_data_substitution_observed = (
        False
        if linked_events and RUN_OBSERVATION_CONTRACT.required_channels.issubset(usable_channels)
        else None
    )
    observation_evidence = evaluate_evidence_contract(
        RUN_OBSERVATION_CONTRACT,
        EvidenceEvaluationInput(
            usable_channels=usable_channels,
            condition_results={
                "complete_flying_lap_coverage": best_lap is not None,
                "setup_snapshot_captured": setup_snapshot_captured,
                "event_linked": bool(linked_events),
            },
            blocker_results={
                "junk_lap_context": best_lap is None,
                "sample_or_sim_integrity_failure": sample_integrity_observed_clear,
                "short_run_sensitive_claim": sensitive_claim_requested,
                "missing_data_substitution": missing_data_substitution_observed,
            },
            repetitions=len(useful_laps),
            requested_outputs=requested_outputs,
        ),
    )
    confidence_limit_reasons = [
        limit.message for limit in observation_evidence.confidence_limits
    ]
    if observation_evidence.eligible:
        events = [
            event.model_copy(
                update={
                    "confidence_score": min(
                        event.confidence_score,
                        observation_evidence.confidence_cap,
                    ),
                    "evidence_json": {
                        **event.evidence_json,
                        "evidence_confidence_limits": confidence_limit_reasons,
                    },
                }
            )
            if event.valid_for_tuning
            else event
            for event in events
        ]
    else:
        observation_blockers = [
            blocker.message for blocker in observation_evidence.blockers
        ]
        events = [
            event.model_copy(
                update={
                    "valid_for_tuning": False,
                    "confidence_score": min(event.confidence_score, 0.35),
                    "evidence_state": EvidenceState.BLOCKED_BY_CONTEXT,
                    "blocker_reasons": observation_blockers,
                    "evidence_json": {
                        **event.evidence_json,
                        "observation_withheld": True,
                        "evidence_contract_blockers": observation_blockers,
                    },
                }
            )
            if event.valid_for_tuning
            else event
            for event in events
        ]
    profile["overview_observation_contract_s"] = time.perf_counter() - t0
    invalid_scrapes = [
        event for event in platform_events if event.event_type == "PLATFORM_SCRAPE" and not event.valid_for_tuning
    ]

    warnings = [
        "Short runs cannot support strong tire degradation or cooling conclusions.",
        "Do not overclaim exact aerodynamic drag force from .ibt telemetry.",
    ]
    warnings.extend(_build_missing_optional_warnings(missing_channels, available_channels))
    if proximity_warning:
        warnings.append(
            f"Drag/scrub tuning was suppressed by nearby-car context: {proximity_warning}"
        )
    if invalid_scrapes:
        warnings.append("At least one low/negative splitter event occurred in slowdown context and is not valid setup evidence.")

    t0 = time.perf_counter()
    out = RunOverview(
        run_id=run_id,
        session=session,
        best_useful_lap=best_lap,
        laps=laps,
        events=events,
        setup_snapshot=setup,
        primary_findings=_build_primary_findings(
            best_lap,
            [event for event in events if "PLATFORM" in event.event_type],
            [event for event in events if event.event_type == "FULL_THROTTLE_SPEED_LOSS"],
        ),
        warnings=warnings,
    )
    profile["overview_model_build_s"] = time.perf_counter() - t0
    profile["overview_total_s"] = sum(profile.values())
    globals()["LAST_IMPORT_PROFILE"].update(profile)
    return out


def import_ibt(path: str | Path) -> IBTImportResult:
    """Import an `.ibt` file into the MVP RaceLab Garage contracts."""

    file_path = Path(path)
    if not file_path.exists():
        _log.warning("IBT file does not exist: %s", file_path)
        return IBTImportResult(
            status=ImportStatus(
                status="unavailable",
                message=f"File does not exist: {file_path}",
                implemented=[],
                remaining=["Provide a real .ibt path"],
            )
        )

    globals()["LAST_IMPORT_PROFILE"] = {}
    fingerprint = fingerprint_file(file_path)
    profile_enabled = _subprofile_enabled()
    try:
        t0 = time.time()
        data = _read_bytes(file_path)
        if profile_enabled:
            LAST_IMPORT_PROFILE["decode_file_read_s"] = time.time() - t0
        _log.info("IBT decoder: read %d bytes in %.3fs", len(data), time.time() - t0)

        t0 = time.time()
        header = _parse_header(data, len(data))
        if profile_enabled:
            LAST_IMPORT_PROFILE["decode_header_parse_s"] = time.time() - t0
        _log.info("IBT decoder: header parsed in %.3fs (vars=%s, records=%s, rate=%sHz)",
                  time.time() - t0, header.variable_count, header.record_count, header.telemetry_rate_hz)

        t0 = time.time()
        definitions = _parse_variable_definitions(data, header)
        if profile_enabled:
            LAST_IMPORT_PROFILE["decode_var_defs_s"] = time.time() - t0
        _log.info("IBT decoder: %d variable definitions parsed in %.3fs", len(definitions), time.time() - t0)

        t0 = time.time()
        session_yaml = _extract_session_yaml_from_data(data, header)
        if profile_enabled:
            LAST_IMPORT_PROFILE["decode_session_yaml_s"] = time.time() - t0
        _log.info("IBT decoder: session YAML extracted in %.3fs (%d chars)",
                  time.time() - t0, len(session_yaml))
        try:
            session_car_path = extract_session_summary(
                session_yaml,
                run_id=_slug_run_id(file_path, fingerprint.sha256),
                parsed_data=parse_session_yaml(session_yaml),
            ).car_path
        except Exception:
            session_car_path = None

        available = {definition.name for definition in definitions}
        missing = _collect_missing_channels(available)

        import os
        decoder_mode = os.environ.get("RACELAB_IBT_DECODER", "").strip().lower()
        use_columnar = decoder_mode != "row"
        target_vars = [channel for channel in TARGET_CHANNELS if channel in available]

        from racelab_engine.analysis.vectorized_channels import (
            get_analysis_engine_mode,
            normalize_telemetry_frame,
        )
        analysis_mode = get_analysis_engine_mode()
        normalized_frame = None
        raw_archive_columns: dict[str, str] = {}
        rows: list[dict[str, Any]]
        overview_table: Any | None = None
        if profile_enabled:
            LAST_IMPORT_PROFILE["normalized_frame_available"] = 0.0
            LAST_IMPORT_PROFILE["rows_materialized_during_import"] = 0.0
            LAST_IMPORT_PROFILE["frame_to_rows_count"] = 0.0
            LAST_IMPORT_PROFILE["frame_to_rows_s"] = 0.0
            LAST_IMPORT_PROFILE["frame_to_rows_reason"] = "none"
            LAST_IMPORT_PROFILE["cache_write_from_frame"] = 0.0

        t0 = time.time()
        if use_columnar:
            try:
                t_loop = time.time()
                columns = _read_records_columnar(
                    data, header, definitions,
                    variables=None,
                    profile_out=LAST_IMPORT_PROFILE if profile_enabled else None,
                )
                if profile_enabled:
                    LAST_IMPORT_PROFILE["decode_columnar_loop_s"] = time.time() - t_loop
                if analysis_mode == "row":
                    import polars as pl
                    raw_rows = pl.DataFrame(columns, strict=False).to_dicts()
                    declared_names = {definition.name for definition in definitions}
                    raw_archive_rows = [
                        {name: value for name, value in row.items() if name in declared_names}
                        for row in raw_rows
                    ]
                    analysis_rows = [
                        {name: value for name, value in row.items() if name == "sample_index" or name in target_vars}
                        for row in raw_rows
                    ]
                    normalized_rows = normalize_telemetry_rows(analysis_rows, car_path=session_car_path)
                    raw_archive_columns = _raw_archive_column_mapping(
                        normalized_rows[0].keys() if normalized_rows else (),
                        raw_archive_rows[0].keys() if raw_archive_rows else (),
                    )
                    rows = _merge_raw_rows(normalized_rows, raw_archive_rows)
                    _log.info(
                        "IBT decoder (columnar+row-normalize): %d records in %.3fs",
                        len(rows),
                        time.time() - t0,
                    )
                else:
                    t_norm = time.time()
                    df = normalize_telemetry_frame(
                        _analysis_columns(columns, target_vars),
                        car_path=session_car_path,
                    )
                    declared_columns = {
                        definition.name: columns[definition.name]
                        for definition in definitions
                    }
                    raw_archive_columns = _raw_archive_column_mapping(df.columns, declared_columns)
                    df = _merge_raw_columns(df, declared_columns)
                    # Polars now owns the decoded buffers. Drop the millions of
                    # boxed Python values before overview analysis and Parquet
                    # persistence instead of retaining a duplicate raw vault for
                    # the remainder of the import.
                    del declared_columns
                    columns.clear()
                    normalized_frame = df
                    overview_table = df
                    if profile_enabled:
                        LAST_IMPORT_PROFILE["normalized_frame_available"] = 1.0
                        LAST_IMPORT_PROFILE["normalize_vectorized_frame_s"] = time.time() - t_norm
                        try:
                            from racelab_engine.analysis import vectorized_channels as _vec_mod
                            for _k, _v in (getattr(_vec_mod, "LAST_NORMALIZE_PROFILE", {}) or {}).items():
                                if isinstance(_v, (int, float)):
                                    LAST_IMPORT_PROFILE[_k] = float(_v)
                        except Exception:
                            pass
                    rows = []
                    _log.info("IBT decoder (columnar+vectorized): %d records in %.3fs", len(rows), time.time() - t0)
            except Exception:
                _log.debug("Columnar fast path failed, using row decoder", exc_info=True)
                raw_rows = _read_records_from_data(
                    data, header, definitions,
                    variables=None,
                )
                declared_names = {definition.name for definition in definitions}
                raw_archive_rows = [
                    {name: value for name, value in row.items() if name in declared_names}
                    for row in raw_rows
                ]
                _log.info("IBT decoder (row): %d records decoded in %.3fs", len(raw_rows), time.time() - t0)
                t0 = time.time()
                analysis_rows = [
                    {name: value for name, value in row.items() if name == "sample_index" or name in target_vars}
                    for row in raw_rows
                ]
                normalized_rows = normalize_telemetry_rows(analysis_rows, car_path=session_car_path)
                raw_archive_columns = _raw_archive_column_mapping(
                    normalized_rows[0].keys() if normalized_rows else (),
                    raw_archive_rows[0].keys() if raw_archive_rows else (),
                )
                rows = _merge_raw_rows(normalized_rows, raw_archive_rows)
                overview_table = rows
                if profile_enabled:
                    LAST_IMPORT_PROFILE["decode_row_normalize_s"] = time.time() - t0
                    LAST_IMPORT_PROFILE["frame_to_rows_reason"] = "row_decoder_fallback"
                _log.info("IBT decoder (row normalize): %d rows in %.3fs", len(rows), time.time() - t0)
        else:
            raw_rows = _read_records_from_data(
                data, header, definitions,
                variables=None,
            )
            declared_names = {definition.name for definition in definitions}
            raw_archive_rows = [
                {name: value for name, value in row.items() if name in declared_names}
                for row in raw_rows
            ]
            _log.info("IBT decoder (forced row): %d records decoded in %.3fs", len(raw_rows), time.time() - t0)
            t0 = time.time()
            analysis_rows = [
                {name: value for name, value in row.items() if name == "sample_index" or name in target_vars}
                for row in raw_rows
            ]
            normalized_rows = normalize_telemetry_rows(analysis_rows, car_path=session_car_path)
            raw_archive_columns = _raw_archive_column_mapping(
                normalized_rows[0].keys() if normalized_rows else (),
                raw_archive_rows[0].keys() if raw_archive_rows else (),
            )
            rows = _merge_raw_rows(normalized_rows, raw_archive_rows)
            overview_table = rows
            if profile_enabled:
                LAST_IMPORT_PROFILE["decode_row_normalize_s"] = time.time() - t0
                LAST_IMPORT_PROFILE["frame_to_rows_reason"] = "forced_row_decoder"
            _log.info("IBT decoder (forced row normalize): %d rows in %.3fs", len(rows), time.time() - t0)

        t0 = time.time()
        if overview_table is None:
            overview_table = rows
        if profile_enabled and normalized_frame is not None:
            LAST_IMPORT_PROFILE["overview_consumers_frame_native"] = 1.0
            LAST_IMPORT_PROFILE["overview_legacy_consumers_remaining"] = "none"
        overview = _build_overview(file_path, fingerprint.sha256, header, session_yaml, overview_table, missing, available)
        _log.info("IBT decoder: overview built in %.3fs (laps=%d, events=%d)",
                  time.time() - t0, len(overview.laps), len(overview.events))
    except (OSError, IBTParseError, struct.error, UnicodeDecodeError) as exc:
        _log.error("IBT decoder failed: %s", exc)
        return IBTImportResult(
            fingerprint=fingerprint,
            status=ImportStatus(
                status="error",
                message=f"Failed to parse .ibt file: {exc}",
                implemented=["file fingerprint"],
                remaining=["Fix parser error before generating conclusions"],
            ),
        )

    out = IBTImportResult(
        fingerprint=fingerprint,
        header=header,
        variable_definitions=definitions,
        raw_archive_columns={
            definition.name: raw_archive_columns.get(definition.name, definition.name)
            for definition in definitions
        },
        session_yaml=session_yaml,
        records=rows,
        missing_channels=missing,
        overview=overview,
        status=ImportStatus(
            status="imported",
            message="Imported every file-declared iRacing telemetry channel plus selective normalized analysis channels.",
            implemented=[
                "file fingerprint",
                "binary header decoding",
                "variable definition decoding",
                "session YAML extraction",
                "lossless decoding of every file-declared telemetry channel",
                "array and sub-tick sample preservation",
                "raw-name provenance alongside canonical aliases",
                "normalized calculated channels",
                "baseline lap/platform/report contracts",
            ],
            remaining=[
                "decode every setup/source artifact",
                "advanced comparison and track-map workflows",
            ],
            warnings=[
                "No .sto decoding is claimed.",
                "No track map decoding is claimed.",
                "Exact aerodynamic drag force is not inferred from .ibt telemetry.",
            ],
        ),
    )
    if normalized_frame is not None:
        out.set_normalized_frame(normalized_frame)
    return out
