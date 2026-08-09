from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable

from racelab_engine.analysis.channel_registry import canonical_mapping_kind, canonical_name
from racelab_engine.io.ibt_types import IBTHeader, IBTVariableDefinition
from racelab_engine.io.session_yaml import parse_session_yaml


MANIFEST_SCHEMA_VERSION = 4
UNIVERSAL_ARCHIVE_VERSION = 1


def assess_cache_compatibility(
    manifest: dict[str, Any],
    *,
    cache_present: bool,
) -> dict[str, Any]:
    """State the cache migration policy without pretending old caches are lossless."""
    def version_number(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError, OverflowError):
            return None

    version = version_number(manifest.get("universal_archive_version"))
    schema_version = version_number(manifest.get("manifest_schema_version"))
    if not cache_present:
        status = "missing_cache"
        reason = "No telemetry cache is available for this run."
        action = "reimport_original_ibt"
    elif not manifest:
        status = "reimport_required"
        reason = "This run predates the universal telemetry manifest; omitted raw channels cannot be reconstructed."
        action = "reimport_original_ibt"
    elif (
        version is None
        or schema_version is None
        or version < UNIVERSAL_ARCHIVE_VERSION
        or schema_version < MANIFEST_SCHEMA_VERSION
    ):
        status = "reimport_required"
        reason = "This cache predates the current lossless archive or telemetry-manifest contract."
        action = "reimport_original_ibt"
    elif version > UNIVERSAL_ARCHIVE_VERSION or schema_version > MANIFEST_SCHEMA_VERSION:
        status = "app_upgrade_required"
        reason = "This cache was written by a newer RacerZLab archive schema."
        action = "upgrade_racerzlab"
    elif manifest.get("lossless_archive_complete") is not True:
        status = "reimport_required"
        reason = "The archive invariant is incomplete, so this cache cannot support universal telemetry claims."
        action = "reimport_original_ibt"
    else:
        status = "current"
        reason = "The cache matches the current universal archive contract."
        action = "none"
    return {
        "status": status,
        "reason": reason,
        "required_action": action,
        "automatic_migration_supported": False,
        "replacement_policy": (
            "Re-import from the original .ibt. RacerZLab stages the replacement and promotes it only after "
            "all declared channels pass the archive invariant."
        ),
    }


def compact_capability_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    capabilities = manifest.get("capabilities", [])
    readiness_counts: dict[str, int] = {}
    for capability in capabilities if isinstance(capabilities, list) else []:
        readiness = str(capability.get("analysis_readiness", "unknown"))
        readiness_counts[readiness] = readiness_counts.get(readiness, 0) + 1
    health = manifest.get("health_summary", {})
    return {
        "declared_channels": int(manifest.get("declared_channel_count") or 0),
        "cached_channels": int(manifest.get("cached_channel_count") or 0),
        "unmapped_channels": int(manifest.get("unmapped_channel_count") or 0),
        "warning_channels": int(health.get("warning_channel_count") or 0),
        "lossless_archive_complete": manifest.get("lossless_archive_complete") is True,
        "analysis_readiness_counts": readiness_counts,
    }


def _nested(mapping: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key, {})
    return current if isinstance(current, dict) else {}


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    return next((mapping[key] for key in keys if mapping.get(key) not in (None, "")), None)


def _driver_entry(driver: dict[str, Any]) -> dict[str, Any]:
    car_index = driver.get("DriverCarIdx")
    drivers = driver.get("Drivers", [])
    if not isinstance(drivers, list):
        return {}
    return next(
        (
            entry
            for entry in drivers
            if isinstance(entry, dict) and entry.get("CarIdx") == car_index
        ),
        {},
    )


def _current_session(session_info: dict[str, Any]) -> dict[str, Any]:
    sessions = session_info.get("Sessions", [])
    if not isinstance(sessions, list):
        return {}
    current_number = session_info.get("CurrentSessionNum")
    matching = next(
        (
            session
            for session in sessions
            if isinstance(session, dict) and session.get("SessionNum") == current_number
        ),
        None,
    )
    if isinstance(matching, dict):
        return matching
    return next((session for session in sessions if isinstance(session, dict)), {})


def compatibility_identity(session_yaml: str | None) -> dict[str, Any]:
    """Return only file-supported identity used to qualify cross-run comparisons."""

    try:
        data = parse_session_yaml(session_yaml or "")
    except Exception:
        data = {}
    weekend = _nested(data, "WeekendInfo")
    driver = _nested(data, "DriverInfo")
    driver_car = _driver_entry(driver)
    session = _current_session(_nested(data, "SessionInfo"))
    identity = {
        "car_id": _first(driver_car, "CarID"),
        "car_path": _first(driver, "DriverCarPath", "CarPath") or _first(driver_car, "CarPath"),
        "car_name": _first(driver, "DriverCarName", "CarScreenName", "CarName")
        or _first(driver_car, "CarScreenName", "CarName"),
        "car_configuration_id": _first(driver_car, "CarCfg"),
        "car_configuration_name": _first(driver_car, "CarCfgName"),
        "car_version": _first(driver, "DriverCarVersion"),
        # File-supported durable identities used to scope driver-specific
        # learning.  Names are intentionally not persisted here.
        "driver_user_id": _first(driver_car, "UserID")
        or _first(driver, "DriverUserID", "UserID"),
        "team_id": _first(driver_car, "TeamID")
        or _first(driver, "DriverTeamID", "TeamID"),
        "track_id": _first(weekend, "TrackID"),
        "track_name": _first(weekend, "TrackName"),
        "track_configuration_name": _first(weekend, "TrackConfigName"),
        "track_version": _first(weekend, "TrackVersion"),
        "iracing_build_version": _first(weekend, "BuildVersion"),
        "iracing_build_type": _first(weekend, "BuildType"),
        "iracing_build_target": _first(weekend, "BuildTarget"),
        "session_type": _first(session, "SessionType", "SessionName")
        or _first(weekend, "EventType"),
        "session_name": _first(session, "SessionName"),
        "session_subtype": _first(session, "SessionSubType"),
    }
    required = (
        "car_id",
        "car_path",
        "car_version",
        "track_id",
        "track_version",
        "iracing_build_version",
        "session_type",
    )
    identity["missing_required_fields"] = [name for name in required if identity[name] is None]
    identity["source"] = "ibt_session_yaml" if data else "unavailable"
    return identity


def compatibility_fingerprint(schema_id: str, identity: dict[str, Any]) -> str:
    """Fingerprint schema plus the physics/context identity present in the file."""

    payload = {
        "schema_fingerprint": schema_id,
        "identity": {
            key: value
            for key, value in identity.items()
            if key not in {
                "missing_required_fields",
                "source",
                # Driver/team identity scopes learned effects but is not part
                # of the car/track physics compatibility fingerprint.
                "driver_user_id",
                "team_id",
            }
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def schema_fingerprint(header: IBTHeader, definitions: Iterable[IBTVariableDefinition]) -> str:
    """Fingerprint the file-declared telemetry schema, independent of samples."""

    payload = {
        "ibt_version": header.version,
        "telemetry_rate_hz": header.telemetry_rate_hz,
        "record_length": header.record_length,
        "variables": [
            {
                "name": definition.name,
                "description": definition.description,
                "unit": definition.unit,
                "data_type_id": definition.data_type_id,
                "offset": definition.offset,
                "count": definition.count,
                "count_as_time": definition.count_as_time,
            }
            for definition in definitions
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


_KNOWN_BOUNDS: dict[str, tuple[float | None, float | None, str]] = {
    "Throttle": (0.0, 1.0, "normalized driver input must be within 0..1"),
    "Brake": (0.0, 1.0, "normalized driver input must be within 0..1"),
    "Clutch": (0.0, 1.0, "normalized driver input must be within 0..1"),
    "Handbrake": (0.0, 1.0, "normalized driver input must be within 0..1"),
    "Speed": (0.0, None, "vehicle speed magnitude cannot be negative"),
    "RPM": (0.0, None, "engine speed cannot be negative"),
}

_INTEGER_LIMITS: dict[int, tuple[int, ...]] = {
    2: (-(2**31), 2**31 - 1),
    3: (2**32 - 1,),
}


def _flat_samples(series: Any) -> tuple[list[Any], list[int]]:
    samples = series.to_list()
    flat: list[Any] = []
    lengths: list[int] = []
    for sample in samples:
        if isinstance(sample, (list, tuple)):
            lengths.append(len(sample))
            flat.extend(sample)
        else:
            flat.append(sample)
    return flat, lengths


def _numeric_samples(values: Iterable[Any]) -> tuple[list[float], int]:
    finite: list[float] = []
    non_finite = 0
    for value in values:
        if value is None or isinstance(value, bool):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            finite.append(number)
        else:
            non_finite += 1
    return finite, non_finite


def _impossible_bounds(definition: IBTVariableDefinition) -> tuple[float | None, float | None, str | None]:
    known = _KNOWN_BOUNDS.get(definition.name)
    if known:
        return known
    lower_name = definition.name.lower()
    unit = (definition.unit or "").strip().lower()
    if "pressure" in lower_name or "linepress" in lower_name:
        return 0.0, None, "pressure cannot be negative"
    if unit in {"c", "deg c", "°c"} or "temp" in lower_name:
        return -273.15, None, "temperature cannot be below absolute zero"
    return None, None, None


def _numeric_health_metrics(
    values: Any,
    definition: IBTVariableDefinition,
    minimum: float | None,
    maximum: float | None,
) -> tuple[int, int, int, float, float]:
    """Calculate scalar health counts in the column engine when available.

    Manifest generation runs once for every declared channel. Converting each
    numeric Series to Python objects made health validation dominate imports and
    temporarily duplicated the telemetry vault. The fallback preserves support
    for non-Polars frame implementations used by tests and optional runtimes.
    """

    lower_tolerance = max(1e-6, abs(minimum or 0.0) * 1e-6)
    upper_tolerance = max(1e-6, abs(maximum or 0.0) * 1e-6)
    integer_limits = _INTEGER_LIMITS.get(definition.data_type_id or -1)
    is_control = definition.name in {"Throttle", "Brake", "Clutch", "Handbrake"}

    try:
        finite_mask = values.is_finite()
        finite_values = values.filter(finite_mask)
        finite_count = len(finite_values)
        non_finite_count = len(values) - finite_count

        outside = None
        if minimum is not None:
            outside = finite_values < minimum - lower_tolerance
        if maximum is not None:
            upper_outside = finite_values > maximum + upper_tolerance
            outside = upper_outside if outside is None else outside | upper_outside
        impossible_count = int(outside.sum() or 0) if outside is not None else 0
        numeric_limit_hit_count = (
            sum(int((finite_values == limit).sum() or 0) for limit in integer_limits)
            if integer_limits
            else 0
        )

        lower_occupancy = 0.0
        upper_occupancy = 0.0
        if finite_count:
            if minimum is not None:
                lower_occupancy = int((finite_values == minimum).sum() or 0) / finite_count
            if maximum is not None:
                upper_occupancy = int((finite_values == maximum).sum() or 0) / finite_count
            if is_control:
                physical_lower, physical_upper, _reason = _KNOWN_BOUNDS[definition.name]
                lower_occupancy = int(
                    ((finite_values - float(physical_lower)).abs() <= 1e-6).sum() or 0
                ) / finite_count
                upper_occupancy = int(
                    ((finite_values - float(physical_upper)).abs() <= 1e-6).sum() or 0
                ) / finite_count
        return (
            non_finite_count,
            impossible_count,
            numeric_limit_hit_count,
            lower_occupancy,
            upper_occupancy,
        )
    except Exception:
        numeric_values, non_finite_count = _numeric_samples(values.to_list())

    def outside_bounds(value: float) -> bool:
        return (minimum is not None and value < minimum - lower_tolerance) or (
            maximum is not None and value > maximum + upper_tolerance
        )

    impossible_count = sum(outside_bounds(value) for value in numeric_values)
    numeric_limit_hit_count = (
        sum(value in integer_limits for value in numeric_values)
        if integer_limits
        else 0
    )
    lower_occupancy = 0.0
    upper_occupancy = 0.0
    if numeric_values:
        if minimum is not None:
            lower_occupancy = sum(value == minimum for value in numeric_values) / len(numeric_values)
        if maximum is not None:
            upper_occupancy = sum(value == maximum for value in numeric_values) / len(numeric_values)
        if is_control:
            physical_lower, physical_upper, _reason = _KNOWN_BOUNDS[definition.name]
            lower_occupancy = sum(
                abs(value - float(physical_lower)) <= 1e-6 for value in numeric_values
            ) / len(numeric_values)
            upper_occupancy = sum(
                abs(value - float(physical_upper)) <= 1e-6 for value in numeric_values
            ) / len(numeric_values)
    return (
        non_finite_count,
        impossible_count,
        numeric_limit_hit_count,
        lower_occupancy,
        upper_occupancy,
    )


def _series_health(
    frame: Any,
    definition: IBTVariableDefinition,
    archive_column: str,
) -> dict[str, Any]:
    if frame is None or archive_column not in getattr(frame, "columns", []):
        return {
            "archive_status": "metadata_only",
            "record_count": 0,
            "valid_record_count": 0,
            "missing_fraction": 1.0,
            "distinct_value_count": 0,
            "variation": "not_cached",
            "observed_min": None,
            "observed_max": None,
            "health_status": "not_assessed",
            "health_warnings": ["Declared channel has no archived raw sample column."],
            "non_finite_sample_count": 0,
            "impossible_sample_count": 0,
            "malformed_array_record_count": 0,
            "null_element_count": 0,
            "clipping_status": "not_assessed",
            "saturation_status": "not_assessed",
        }

    series = frame.get_column(archive_column)
    record_count = len(series)
    null_count = int(series.null_count())
    values = series.drop_nulls()
    is_array = definition.data_type_id != 0 and definition.count > 1
    if is_array:
        try:
            values = values.explode().drop_nulls()
        except Exception:
            pass
    try:
        distinct_count = int(values.n_unique())
    except Exception:
        distinct_count = 0
    if len(values) == 0:
        variation = "no_valid_samples"
    elif distinct_count <= 1:
        variation = "constant"
    else:
        variation = "varying"

    observed_min: int | float | None = None
    observed_max: int | float | None = None
    if definition.data_type_id in {1, 2, 3, 4, 5} and len(values) > 0:
        try:
            observed_min = _json_number(values.min())
            observed_max = _json_number(values.max())
        except Exception:
            pass

    array_lengths: list[int] = []
    null_element_count = 0
    if is_array:
        array_samples = series.to_list()
        for sample in array_samples:
            if not isinstance(sample, (list, tuple)):
                continue
            array_lengths.append(len(sample))
            null_element_count += sum(item is None for item in sample)
    minimum, maximum, bounds_reason = _impossible_bounds(definition)
    if definition.data_type_id in {2, 3, 4, 5}:
        (
            non_finite_count,
            impossible_count,
            numeric_limit_hit_count,
            lower_occupancy,
            upper_occupancy,
        ) = _numeric_health_metrics(values, definition, minimum, maximum)
    else:
        non_finite_count = 0
        impossible_count = 0
        numeric_limit_hit_count = 0
        lower_occupancy = 0.0
        upper_occupancy = 0.0
    malformed_array_count = sum(length != definition.count for length in array_lengths)

    clipping_status = "possible_numeric_limit_clipping" if numeric_limit_hit_count else "none_detected"
    saturation_status = "none_detected"
    if (
        definition.name in {"Throttle", "Brake", "Clutch", "Handbrake"}
        and max(lower_occupancy, upper_occupancy) >= 0.05
    ):
        saturation_status = "normal_control_boundary_occupancy"

    warnings: list[str] = []
    if null_count:
        warnings.append(f"{null_count} raw record(s) are null.")
    if null_element_count:
        warnings.append(f"{null_element_count} array element(s) are null.")
    if non_finite_count:
        warnings.append(f"{non_finite_count} non-finite numeric sample(s).")
    if impossible_count:
        warnings.append(f"{impossible_count} sample(s) violate: {bounds_reason}.")
    if malformed_array_count:
        warnings.append(
            f"{malformed_array_count} array record(s) do not contain the declared {definition.count} elements."
        )
    if numeric_limit_hit_count:
        warnings.append(f"{numeric_limit_hit_count} sample(s) equal the storage type limit.")
    health_status = "warning" if warnings else "healthy"

    return {
        "archive_status": "cached",
        "record_count": record_count,
        "valid_record_count": record_count - null_count,
        "missing_fraction": round(null_count / record_count, 8) if record_count else 1.0,
        "distinct_value_count": distinct_count,
        "variation": variation,
        "observed_min": observed_min,
        "observed_max": observed_max,
        "health_status": health_status,
        "health_warnings": warnings,
        "non_finite_sample_count": non_finite_count,
        "impossible_sample_count": impossible_count,
        "impossible_range_rule": bounds_reason,
        "malformed_array_record_count": malformed_array_count,
        "null_element_count": null_element_count,
        "numeric_limit_hit_count": numeric_limit_hit_count,
        "clipping_status": clipping_status,
        "saturation_status": saturation_status,
        "lower_bound_occupancy_fraction": round(lower_occupancy, 8),
        "upper_bound_occupancy_fraction": round(upper_occupancy, 8),
    }


def _numeric_column(frame: Any, name: str) -> list[float]:
    if frame is None or name not in getattr(frame, "columns", []):
        return []
    values, _ = _flat_samples(frame.get_column(name))
    numeric, _ = _numeric_samples(values)
    return numeric


def _sample_continuity(frame: Any, telemetry_rate_hz: int | None) -> dict[str, Any]:
    ticks = _numeric_column(frame, "SessionTick")
    times = _numeric_column(frame, "SessionTime")
    tick_record_count = (
        len(frame.get_column("SessionTick"))
        if frame is not None and "SessionTick" in getattr(frame, "columns", [])
        else 0
    )
    time_record_count = (
        len(frame.get_column("SessionTime"))
        if frame is not None and "SessionTime" in getattr(frame, "columns", [])
        else 0
    )
    invalid_tick_samples = tick_record_count - len(ticks)
    invalid_time_samples = time_record_count - len(times)
    tick_deltas = [right - left for left, right in zip(ticks, ticks[1:])]
    time_deltas = [right - left for left, right in zip(times, times[1:])]
    expected_dt = 1.0 / telemetry_rate_hz if telemetry_rate_hz else None
    duplicate_ticks = sum(delta == 0 for delta in tick_deltas)
    reversed_ticks = sum(delta < 0 for delta in tick_deltas)
    dropped_ticks = sum(max(0, int(round(delta)) - 1) for delta in tick_deltas if delta > 1)
    non_monotonic_times = sum(delta <= 0 for delta in time_deltas)
    timestamp_gap_count = (
        sum(delta > expected_dt * 1.5 for delta in time_deltas)
        if expected_dt is not None
        else 0
    )
    hard_issues = (
        duplicate_ticks
        + reversed_ticks
        + dropped_ticks
        + non_monotonic_times
        + invalid_tick_samples
        + invalid_time_samples
    )
    assessed = bool(tick_deltas or time_deltas)
    status = "not_assessed"
    if assessed:
        if hard_issues:
            status = "issues_detected"
        elif timestamp_gap_count:
            status = "timestamp_gap_observed_with_contiguous_ticks" if tick_deltas else "issues_detected"
        else:
            status = "healthy"
    return {
        "status": status,
        "session_tick_available": bool(ticks),
        "session_time_available": bool(times),
        "invalid_tick_sample_count": invalid_tick_samples,
        "invalid_timestamp_sample_count": invalid_time_samples,
        "duplicate_tick_transition_count": duplicate_ticks,
        "reversed_tick_transition_count": reversed_ticks,
        "estimated_dropped_tick_count": dropped_ticks,
        "non_monotonic_timestamp_transition_count": non_monotonic_times,
        "timestamp_gap_count": timestamp_gap_count,
        "expected_timestamp_step_s": expected_dt,
        "largest_timestamp_step_s": max(time_deltas) if time_deltas else None,
    }


def _capability(
    capability_id: str,
    label: str,
    declared: set[str],
    required: Iterable[str],
    enhanced_by: Iterable[str] = (),
    *,
    caveat: str | None = None,
) -> dict[str, Any]:
    required_names = list(required)
    enhanced_names = list(enhanced_by)
    present_required = [name for name in required_names if name in declared]
    missing_required = [name for name in required_names if name not in declared]
    present_enhanced = [name for name in enhanced_names if name in declared]
    missing_enhanced = [name for name in enhanced_names if name not in declared]
    if not present_required:
        status = "unavailable"
    elif missing_required:
        status = "partial"
    elif missing_enhanced:
        status = "available"
    else:
        status = "full"
    return {
        "capability_id": capability_id,
        "label": label,
        "channel_coverage": status,
        "analysis_readiness": "pending_evidence_qualification",
        "required_channels": required_names,
        "present_required_channels": present_required,
        "missing_required_channels": missing_required,
        "enhancement_channels": enhanced_names,
        "present_enhancement_channels": present_enhanced,
        "missing_enhancement_channels": missing_enhanced,
        "caveat": caveat
        or "Channel coverage is not proof that a lap or comparison is eligible for this analysis.",
    }


def _capabilities(declared: set[str]) -> list[dict[str, Any]]:
    canonical_shock_deflection = ["LFshockDefl", "RFshockDefl", "LRshockDefl", "RRshockDefl"]
    legacy_shock_deflection = ["LFSHshockDefl", "RFSHshockDefl", "LRSHshockDefl", "RRSHshockDefl"]
    canonical_shock_velocity = ["LFshockVel", "RFshockVel", "LRshockVel", "RRshockVel"]
    legacy_shock_velocity = ["LFSHshockVel", "RFSHshockVel", "LRSHshockVel", "RRSHshockVel"]
    shock_deflection = (
        canonical_shock_deflection
        if any(name in declared for name in canonical_shock_deflection)
        else legacy_shock_deflection
    )
    shock_velocity = (
        canonical_shock_velocity
        if any(name in declared for name in canonical_shock_velocity)
        else legacy_shock_velocity
    )
    return [
        _capability(
            "lap_position_and_timing",
            "Lap position and timing",
            declared,
            ["SessionTime", "SessionTick", "Lap", "LapDistPct", "Speed"],
            ["LapCompleted", "LapCurrentLapTime", "LapLastLapTime"],
        ),
        _capability(
            "driver_inputs",
            "Driver inputs",
            declared,
            ["Throttle", "Brake", "SteeringWheelAngle"],
            ["ThrottleRaw", "BrakeRaw", "ClutchRaw"],
        ),
        _capability(
            "four_corner_braking",
            "Four-corner brake response",
            declared,
            ["Brake"],
            ["LFbrakeLinePress", "RFbrakeLinePress", "LRbrakeLinePress", "RRbrakeLinePress"],
        ),
        _capability(
            "tire_state",
            "Tire pressure, temperature, wear, and age",
            declared,
            ["LFpressure", "RFpressure", "LRpressure", "RRpressure"],
            [
                "LFtempL", "LFtempM", "LFtempR", "RFtempL", "RFtempM", "RFtempR",
                "LRtempL", "LRtempM", "LRtempR", "RRtempL", "RRtempM", "RRtempR",
                "LFwearL", "RFwearL", "LRwearL", "RRwearL",
                "LFodometer", "RFodometer", "LRodometer", "RRodometer",
            ],
        ),
        _capability(
            "suspension_motion",
            "Four-corner suspension motion",
            declared,
            shock_deflection,
            shock_velocity,
        ),
        _capability(
            "aero_platform_proxy",
            "Aero-platform proxy comparison",
            declared,
            ["Speed", "CFSRrideHeight", "LFrideHeight", "RFrideHeight", "LRrideHeight", "RRrideHeight"],
            ["AirDensity", "Pitch", "Roll"],
            caveat="Ride height and dynamic-pressure results are measured/proxy comparisons, not absolute aerodynamic force.",
        ),
        _capability(
            "steering_effort",
            "Steering effort and oscillation",
            declared,
            ["SteeringWheelAngle", "SteeringWheelTorque"],
            ["SteeringWheelTorque_ST", "SteeringWheelPctTorqueSign"],
        ),
        _capability(
            "nearby_car_context",
            "Nearby-car distance context",
            declared,
            ["CarDistAhead", "CarDistBehind"],
            caveat="Distance channels provide context only. RacerZLab does not infer draft or clean-air state from presence alone.",
        ),
        _capability(
            "powertrain",
            "Powertrain and gearing",
            declared,
            ["RPM", "Gear", "Speed", "Throttle"],
            ["ShiftPowerPct", "EngineWarnings", "FuelUsePerHour"],
        ),
        _capability(
            "environment",
            "Weather and track environment",
            declared,
            ["AirTemp", "TrackTemp", "AirDensity"],
            ["WindVel", "WindDir", "RelativeHumidity", "TrackWetness"],
        ),
        _capability(
            "simulator_integrity",
            "Simulator and connection integrity",
            declared,
            ["CpuUsageFG", "ChanLatency"],
            ["CpuUsageBG", "ChanAvgLatency", "MemPageFaultSec", "MemSoftPageFaultSec"],
        ),
        {
            "capability_id": "absolute_aerodynamic_drag",
            "label": "Absolute aerodynamic drag",
            "channel_coverage": "blocked",
            "analysis_readiness": "blocked",
            "required_channels": [],
            "present_required_channels": [],
            "missing_required_channels": [],
            "enhancement_channels": [],
            "present_enhancement_channels": [],
            "missing_enhancement_channels": [],
            "caveat": "An .ibt does not provide the complete measurements and vehicle constants needed to claim exact aerodynamic drag force or coefficient.",
        },
    ]


def build_telemetry_manifest(
    header: IBTHeader,
    definitions: list[IBTVariableDefinition],
    frame: Any,
    session_yaml: str | None = None,
    raw_archive_columns: dict[str, str] | None = None,
    *,
    run_id: str | None = None,
    source_file_sha256: str | None = None,
    source_file_size_bytes: int | None = None,
    telemetry_cache_sha256: str | None = None,
) -> dict[str, Any]:
    declared = {definition.name for definition in definitions}
    channels: list[dict[str, Any]] = []
    for definition in definitions:
        canonical = canonical_name(definition.name)
        archive_column = (raw_archive_columns or {}).get(definition.name, definition.name)
        effective_rate = None
        if header.telemetry_rate_hz:
            effective_rate = header.telemetry_rate_hz * definition.count if definition.count_as_time else header.telemetry_rate_hz
        channels.append(
            {
                **definition.model_dump(),
                "raw_name": definition.name,
                "archive_column": archive_column,
                "canonical_name": canonical,
                "registry_status": "mapped" if canonical else "unmapped",
                "canonical_mapping_kind": canonical_mapping_kind(definition.name),
                "provenance": "ibt_variable_definition",
                "base_sample_rate_hz": header.telemetry_rate_hz,
                "effective_sample_rate_hz": effective_rate,
                "samples_per_record": max(1, definition.count) if definition.data_type_id != 0 else 1,
                "string_buffer_bytes": definition.count if definition.data_type_id == 0 else None,
                **_series_health(frame, definition, archive_column),
            }
        )

    cached_count = sum(channel["archive_status"] == "cached" for channel in channels)
    varying_count = sum(channel["variation"] == "varying" for channel in channels)
    constant_count = sum(channel["variation"] == "constant" for channel in channels)
    schema_id = schema_fingerprint(header, definitions)
    identity = compatibility_identity(session_yaml)
    malformed_array_count = sum(channel["malformed_array_record_count"] for channel in channels)
    non_finite_count = sum(channel["non_finite_sample_count"] for channel in channels)
    impossible_count = sum(channel["impossible_sample_count"] for channel in channels)
    warning_channel_count = sum(channel["health_status"] == "warning" for channel in channels)
    expected_record_count = (
        header.record_count
        if header.record_count is not None
        else getattr(frame, "height", None)
    )
    complete_channel_count = sum(
        channel["archive_status"] == "cached"
        and channel["record_count"] == expected_record_count
        and channel["valid_record_count"] == expected_record_count
        and channel["null_element_count"] == 0
        and channel["malformed_array_record_count"] == 0
        for channel in channels
    )
    session_times: list[float] = []
    if frame is not None and "SessionTime" in getattr(frame, "columns", []):
        for value in frame.get_column("SessionTime").to_list():
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                session_times.append(number)
    manifest = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "universal_archive_version": UNIVERSAL_ARCHIVE_VERSION,
        # These values are supplied by the import service from the decoded file,
        # never inferred from the path used to read this manifest later.
        "run_id": run_id,
        "source_file_sha256": source_file_sha256,
        "source_file_size_bytes": source_file_size_bytes,
        "telemetry_cache_sha256": telemetry_cache_sha256,
        "schema_fingerprint": schema_id,
        "compatibility_fingerprint": compatibility_fingerprint(schema_id, identity),
        "compatibility_identity": identity,
        "archive_policy": "Archive every file-declared variable; calculate selectively; display intentionally.",
        "telemetry_rate_hz": header.telemetry_rate_hz,
        "record_count": header.record_count,
        "declared_channel_count": len(definitions),
        "cached_channel_count": cached_count,
        "scalar_channel_count": sum(
            definition.count == 1 or definition.data_type_id == 0
            for definition in definitions
        ),
        "array_channel_count": sum(
            definition.count > 1 and definition.data_type_id != 0
            for definition in definitions
        ),
        "subtick_channel_count": sum(definition.count_as_time for definition in definitions),
        "varying_channel_count": varying_count,
        "constant_channel_count": constant_count,
        "unmapped_channel_count": sum(channel["registry_status"] == "unmapped" for channel in channels),
        "lossless_archive_complete": complete_channel_count == len(definitions),
        "complete_channel_count": complete_channel_count,
        "health_summary": {
            "status": "warning" if warning_channel_count else "healthy",
            "warning_channel_count": warning_channel_count,
            "non_finite_sample_count": non_finite_count,
            "impossible_sample_count": impossible_count,
            "malformed_array_record_count": malformed_array_count,
        },
        "sample_continuity": _sample_continuity(frame, header.telemetry_rate_hz),
        "recording_session_time_bounds_s": {
            "start": min(session_times) if session_times else None,
            "end": max(session_times) if session_times else None,
        },
        "channels": channels,
        "capabilities": _capabilities(declared),
    }
    manifest["cache_compatibility"] = assess_cache_compatibility(manifest, cache_present=True)
    manifest["capability_summary"] = compact_capability_summary(manifest)
    return manifest
