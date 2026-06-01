from __future__ import annotations

import logging
import re
import struct
import time
from pathlib import Path
from statistics import mean
from typing import Any, Collection, Mapping, cast

_log = logging.getLogger(__name__)

from racelab_engine.analysis.calculated_channels import (
    CORE_REQUIRED_CHANNELS,
    HIGH_VALUE_RAW_CHANNELS,
    normalize_telemetry_rows,
)
from racelab_engine.analysis.drag_scrub import detect_drag_scrub_risk_zones
from racelab_engine.analysis.dynamic_crew_chief import build_recommendations
from racelab_engine.analysis.lap_classification import classify_laps
from racelab_engine.analysis.lap_detection import detect_laps
from racelab_engine.analysis.platform import detect_platform_events
from racelab_engine.io.file_fingerprint import fingerprint_file
from racelab_engine.io.ibt_types import IBTHeader, IBTImportResult, IBTVariableDefinition, ImportStatus
from racelab_engine.io.session_yaml import extract_session_summary, extract_setup_snapshot
from racelab_engine.models.session import RunOverview


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

TARGET_CHANNELS = list(dict.fromkeys(HIGH_VALUE_RAW_CHANNELS))


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

    return definitions


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
) -> dict[str, list[Any]]:
    """Fast columnar decoder using precompiled structs and memoryview."""
    record_count = header.record_count
    record_len = header.record_length
    data_offset = header.data_offset
    if record_count is None or record_len is None or data_offset is None:
        raise IBTParseError("Header is missing telemetry record offsets.")

    selected = [d for d in definitions if variables is None or d.name in variables]
    columns: dict[str, list[Any]] = {d.name: [None] * record_count for d in selected}
    columns["sample_index"] = list(range(record_count))
    mv = memoryview(data)

    for row_idx in range(record_count):
        rec_start = data_offset + row_idx * record_len
        for defn in selected:
            dt = defn.data_type_id
            if dt is None:
                raise IBTParseError(f"Missing data type ID for {defn.name}.")
            if dt == 0:
                raw = bytes(mv[rec_start + defn.offset : rec_start + defn.offset + max(1, defn.count)])
                value = _decode_c_string(raw)
            elif dt in _STRUCT_FORMATS:
                count = max(1, defn.count)
                fmt = _STRUCT_FORMATS[dt]
                if count == 1:
                    value = fmt.unpack_from(mv, rec_start + defn.offset)[0]
                else:
                    size = fmt.size
                    value = [fmt.unpack_from(mv, rec_start + defn.offset + i * size)[0] for i in range(count)]
            else:
                raise IBTParseError(f"Unsupported iRacing variable type {dt} for {defn.name}.")
            columns[defn.name][row_idx] = value

    return columns


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


def _build_primary_findings(best_lap: Any, platform_events: list[Any], drag_events: list[Any]) -> list[str]:
    findings: list[str] = []
    if best_lap is not None:
        findings.append(f"Lap {best_lap.lap_number} is the best useful lap.")
    if drag_events:
        event = drag_events[0]
        findings.append(
            f"{event.zone_name or 'A target zone'} behaves like a full-throttle drag/scrub risk zone."
        )
    if valid_platform := [event for event in platform_events if event.valid_for_tuning]:
        event = valid_platform[0]
        findings.append(
            f"Minimum valid splitter height is {event.primary_metric_value:.2f} mm near {event.lap_pct_peak:.2f}% lap."
        )
    return findings


def _best_useful_lap(rows: list[dict[str, Any]], run_id: str) -> Any:
    laps = classify_laps(detect_laps(rows, run_id=run_id))
    useful = [lap for lap in laps if lap.is_useful]
    return min(useful, key=lambda lap: lap.lap_time or 999999.0) if useful else None


def _build_overview(
    path: Path,
    file_hash: str,
    header: IBTHeader,
    session_yaml: str,
    rows: list[dict[str, Any]],
    missing_channels: list[str],
) -> RunOverview:
    run_id = _slug_run_id(path, file_hash)
    session = extract_session_summary(session_yaml, run_id=run_id)
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
    setup = extract_setup_snapshot(session_yaml, run_id=run_id)
    laps = classify_laps(detect_laps(rows, run_id=run_id))
    useful_laps = [lap for lap in laps if lap.is_useful]
    best_lap = min(useful_laps, key=lambda lap: lap.lap_time or 999999.0) if useful_laps else None
    platform_events = detect_platform_events(rows, run_id=run_id)
    best_lap_rows = [row for row in rows if best_lap is not None and row.get("lap") == best_lap.lap_number]
    drag_events = detect_drag_scrub_risk_zones(best_lap_rows, run_id=run_id, lap_number=best_lap.lap_number if best_lap else None)
    events = platform_events + drag_events
    recommendations = build_recommendations(run_id, [event for event in events if event.valid_for_tuning])
    invalid_scrapes = [
        event for event in platform_events if event.event_type == "PLATFORM_SCRAPE" and not event.valid_for_tuning
    ]

    warnings = [
        "Short runs cannot support strong tire degradation or cooling conclusions.",
        "Do not overclaim exact aerodynamic drag force from .ibt telemetry.",
    ]
    if missing_channels:
        warnings.append(f"Missing optional channels: {', '.join(missing_channels)}.")
    if invalid_scrapes:
        warnings.append("At least one low/negative splitter event occurred in slowdown context and is not valid setup evidence.")

    return RunOverview(
        run_id=run_id,
        session=session,
        best_useful_lap=best_lap,
        laps=laps,
        events=events,
        setup_snapshot=setup,
        recommendations=recommendations,
        primary_findings=_build_primary_findings(best_lap, platform_events, drag_events),
        warnings=warnings,
        crew_chief_summary=(
            "Use Lap 2-style complete laps for setup evidence. Focus the next controlled test on platform/scrub behavior."
            if best_lap
            else "No complete useful lap was identified."
        ),
        next_test=(
            "Run one controlled platform/scrub test. Compare speed, minimum splitter, steering angle, and RPM in the same lap-distance zone."
            if best_lap
            else "Import a complete run with at-speed telemetry before making setup conclusions."
        ),
    )


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

    fingerprint = fingerprint_file(file_path)
    try:
        t0 = time.time()
        data = _read_bytes(file_path)
        _log.info("IBT decoder: read %d bytes in %.3fs", len(data), time.time() - t0)

        t0 = time.time()
        header = _parse_header(data, len(data))
        _log.info("IBT decoder: header parsed in %.3fs (vars=%s, records=%s, rate=%sHz)",
                  time.time() - t0, header.variable_count, header.record_count, header.telemetry_rate_hz)

        t0 = time.time()
        definitions = _parse_variable_definitions(data, header)
        _log.info("IBT decoder: %d variable definitions parsed in %.3fs", len(definitions), time.time() - t0)

        t0 = time.time()
        session_yaml = read_session_yaml(file_path)
        _log.info("IBT decoder: session YAML extracted in %.3fs (%d chars)",
                  time.time() - t0, len(session_yaml))

        available = {definition.name for definition in definitions}
        missing = [channel for channel in CORE_REQUIRED_CHANNELS if channel not in available]

        t0 = time.time()
        try:
            columns = _read_records_columnar(
                data, header, definitions,
                variables=[channel for channel in TARGET_CHANNELS if channel in available],
            )
            from racelab_engine.analysis.vectorized_channels import normalize_telemetry_frame, frame_to_rows
            df = normalize_telemetry_frame(columns)
            rows = frame_to_rows(df)
            _log.info("IBT decoder (columnar): %d records + normalized in %.3fs", len(rows), time.time() - t0)
        except Exception:
            _log.debug("Columnar fast path failed, using row decoder", exc_info=True)
            raw_rows = _read_records_from_data(
                data, header, definitions,
                variables=[channel for channel in TARGET_CHANNELS if channel in available],
            )
            _log.info("IBT decoder: %d records decoded in %.3fs", len(raw_rows), time.time() - t0)
            t0 = time.time()
            rows = normalize_telemetry_rows(raw_rows)
            _log.info("IBT decoder: normalized %d rows in %.3fs", len(rows), time.time() - t0)

        t0 = time.time()
        overview = _build_overview(file_path, fingerprint.sha256, header, session_yaml, rows, missing)
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

    return IBTImportResult(
        fingerprint=fingerprint,
        header=header,
        variable_definitions=definitions,
        session_yaml=session_yaml,
        records=rows,
        missing_channels=missing,
        overview=overview,
        status=ImportStatus(
            status="imported",
            message="Imported iRacing .ibt header, variable definitions, session YAML, and MVP telemetry channels.",
            implemented=[
                "file fingerprint",
                "binary header decoding",
                "variable definition decoding",
                "session YAML extraction",
                "telemetry record decoding for MVP channels",
                "normalized calculated channels",
                "baseline lap/platform/report contracts",
            ],
            remaining=[
                "persist normalized telemetry cache",
                "decode every setup/source artifact",
                "advanced comparison and track-map workflows",
            ],
            warnings=[
                "No .sto decoding is claimed.",
                "No .mt2 decoding is claimed.",
                "Exact aerodynamic drag force is not inferred from .ibt telemetry.",
            ],
        ),
    )
