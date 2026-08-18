from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable

from racelab_engine.analysis.channel_registry import (
    canonical_mapping_kind,
    canonical_name,
)
from racelab_engine.analysis.qualified_clock import build_qualified_telemetry_clock
from racelab_engine.io.ibt_types import IBTHeader, IBTVariableDefinition
from racelab_engine.io.session_yaml import parse_session_yaml

MANIFEST_SCHEMA_VERSION = 6
UNIVERSAL_ARCHIVE_VERSION = 1

# These raw fields are reviewed by role.  Lap timing and delta-validity fields
# may corroborate the qualified clock, but can never create timing or mechanism
# authority.  All other families remain collection candidates pending held-out
# validation.
_MEASUREMENT_CANDIDATE_FAMILIES: dict[str, tuple[str, ...]] = {
    "transport_integrity": ("ChanClockSkew", "ChanPartnerQuality"),
    "vehicle_condition": (
        "PlayerCarMyIncidentCount", "PlayerCarTeamIncidentCount", "PlayerCarDriverIncidentCount",
        "TowTime", "PitRepairLeft", "PitOptRepairLeft", "FastRepairUsed",
    ),
    "planned_tire_service": (
        "PitSvLFP", "PitSvRFP", "PitSvLRP", "PitSvRRP",
        "LFTiresAvailable", "RFTiresAvailable", "LRTiresAvailable", "RRTiresAvailable",
    ),
    "weather_context": (
        "WeatherDeclaredWet", "Precipitation", "TrackWetness", "SessionTimeOfDay",
        "SolarAltitude", "SolarAzimuth",
    ),
    "delta_validity": (
        "LapDeltaToSessionBestLap_OK", "LapDeltaToSessionOptimalLap_OK",
        "LapDeltaToBestLap_OK", "LapDeltaToOptimalLap_OK",
    ),
    "lap_timing_corroboration": (
        "LapCurrentLapTime", "LapLastLapTime", "LapBestLapTime",
    ),
}

_CLOCK_CORROBORATION_FAMILIES = frozenset({"delta_validity", "lap_timing_corroboration"})

# Engineering admission is explicit for every raw field in the audited Next
# Gen schema.  These roles constrain how a channel may be consumed; mapping a
# name never upgrades pit, control, corroboration, or integrity state into a
# continuous mechanism observation.
_CHANNEL_ENGINEERING_ROLES: dict[str, frozenset[str]] = {
    "measurement_candidate": frozenset({"HandbrakeRaw"}),
    "corroboration": frozenset({
        "SessionNum", "SessionUniqueID", "SessionJokerLapsRemain",
        "SessionOnJokerLap", "SessionTimeOfDay", "LapBestLap",
        "LapBestLapTime", "LapLastLapTime", "LapCurrentLapTime",
        "LapLasNLapSeq", "LapLastNLapTime", "LapBestNLapLap",
        "LapBestNLapTime", "LapDeltaToBestLap", "LapDeltaToBestLap_DD",
        "LapDeltaToBestLap_OK", "LapDeltaToOptimalLap",
        "LapDeltaToOptimalLap_DD", "LapDeltaToOptimalLap_OK",
        "LapDeltaToSessionBestLap", "LapDeltaToSessionBestLap_DD",
        "LapDeltaToSessionBestLap_OK", "LapDeltaToSessionOptimalLap",
        "LapDeltaToSessionOptimalLap_DD", "LapDeltaToSessionOptimalLap_OK",
        "LapDeltaToSessionLastlLap", "LapDeltaToSessionLastlLap_DD",
        "LapDeltaToSessionLastlLap_OK", "SolarAltitude", "SolarAzimuth",
        "WeatherDeclaredWet", "IsOnTrackCar",
    }),
    "pit_snapshot": frozenset({
        "PlayerFastRepairsUsed", "FastRepairUsed", "FastRepairAvailable",
        "LFTiresUsed", "RFTiresUsed", "LRTiresUsed", "RRTiresUsed",
        "LFTiresAvailable", "RFTiresAvailable", "LRTiresAvailable",
        "RRTiresAvailable", "PitSvLFP", "PitSvRFP", "PitSvLRP", "PitSvRRP",
    }),
    "control_state": frozenset({
        "PushToTalk", "PushToPass", "ManualBoost", "ManualNoBoost",
        "P2P_Status", "P2P_Count", "ShiftIndicatorPct", "dcStarter",
        "dpWindshieldTearoff", "dpFastRepair", "dpWeightJackerLeft",
        "dpWeightJackerRight",
    }),
    "integrity": frozenset({"ChanPartnerQuality", "ChanClockSkew"}),
    "inventory_debug": frozenset(),
}
_ROLE_BY_RAW_CHANNEL = {
    raw_name: role
    for role, raw_names in _CHANNEL_ENGINEERING_ROLES.items()
    for raw_name in raw_names
}
if sum(len(names) for names in _CHANNEL_ENGINEERING_ROLES.values()) != len(
    _ROLE_BY_RAW_CHANNEL
):
    raise RuntimeError("telemetry engineering-role registry contains duplicates")


def _engineering_admission(raw_name: str, canonical: str | None) -> tuple[str, str, str]:
    role = _ROLE_BY_RAW_CHANNEL.get(raw_name)
    if role is None:
        if canonical is not None:
            return (
                "admitted_analysis",
                "admitted",
                "Use remains subject to the owning analysis evidence contract.",
            )
        return (
            "inventory_debug",
            "archived_only",
            "Archived losslessly but not reviewed for runtime engineering use.",
        )
    state_by_role = {
        "measurement_candidate": "candidate",
        "corroboration": "corroboration_only",
        "pit_snapshot": "pit_boundary_only",
        "control_state": "context_only",
        "integrity": "integrity_only",
        "inventory_debug": "archived_only",
    }
    limit_by_role = {
        "measurement_candidate": "Cannot create mechanism or setup authority before held-out semantic validation.",
        "corroboration": "May validate context or timing but cannot replace the canonical producer.",
        "pit_snapshot": "Valid only at qualified pit/service boundaries; never continuous on-track evidence.",
        "control_state": "Driver/simulator request context only; cannot prove vehicle response.",
        "integrity": "May qualify data health but cannot create a handling mechanism.",
        "inventory_debug": "Archived for future review with no runtime engineering authority.",
    }
    return role, state_by_role[role], limit_by_role[role]


def _measurement_candidate_contracts(
    channels: list[dict[str, Any]],
    compatibility: dict[str, Any],
) -> list[dict[str, Any]]:
    """Describe measurement debt and narrow clock-corroboration admission."""

    by_name = {str(channel.get("raw_name")): channel for channel in channels}
    build_identity = {
        key: compatibility.get(key)
        for key in ("iracing_build_version", "iracing_build_type", "iracing_build_target")
    }
    result: list[dict[str, Any]] = []
    for family, names in _MEASUREMENT_CANDIDATE_FAMILIES.items():
        for name in names:
            channel = by_name.get(name)
            if channel is None:
                result.append({
                    "raw_name": name,
                    "family": family,
                    "state": "not_declared",
                    "runtime_mapping_admitted": False,
                    "raw_semantics": None,
                    "declared_unit": None,
                    "valid_record_count": 0,
                    "missing_fraction": 1.0,
                    "variation": "unavailable",
                    "raw_provenance": "ibt_variable_definition",
                    "build_applicability": build_identity,
                    "blockers": ["The source file did not declare this candidate channel."],
                })
                continue
            blockers: list[str] = []
            if not str(channel.get("description") or "").strip():
                blockers.append("The simulator supplied no channel semantics.")
            if not str(channel.get("unit") or "").strip():
                blockers.append("The simulator supplied no unit contract.")
            if channel.get("archive_status") != "cached":
                blockers.append("Raw samples were not archived.")
            if channel.get("health_status") != "healthy":
                blockers.append("Raw samples did not pass manifest health checks.")
            corroboration_admitted = bool(
                family in _CLOCK_CORROBORATION_FAMILIES
                and canonical_name(name) is not None
                and not blockers
            )
            result.append({
                "raw_name": name,
                "family": family,
                "state": (
                    "clock_corroboration_admitted"
                    if corroboration_admitted
                    else "source_contract_observed" if not blockers
                    else "data_locked"
                ),
                "runtime_mapping_admitted": corroboration_admitted,
                "engineering_role": (
                    "simulator_clock_corroboration_only"
                    if family in _CLOCK_CORROBORATION_FAMILIES
                    else "measurement_candidate"
                ),
                "authority_limit": (
                    "Cannot replace the qualified clock, create a lap-time delta, or support a mechanism claim."
                    if family in _CLOCK_CORROBORATION_FAMILIES
                    else "Not admitted to runtime engineering authority."
                ),
                "raw_semantics": channel.get("description"),
                "declared_unit": channel.get("unit"),
                "valid_record_count": channel.get("valid_record_count", 0),
                "missing_fraction": channel.get("missing_fraction", 1.0),
                "variation": channel.get("variation", "unavailable"),
                "raw_provenance": "ibt_variable_definition+lossless_raw_archive",
                "build_applicability": build_identity,
                "blockers": (
                    blockers
                    if blockers
                    else [] if corroboration_admitted
                    else ["Semantics still require a known-behavior held-out fixture before runtime mapping."]
                ),
            })
    return result


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
    continuity = manifest.get("sample_continuity", {})
    qualified_clock = (
        continuity.get("qualified_clock", {})
        if isinstance(continuity, dict)
        else {}
    )
    qualified_clock_state = qualified_clock.get("clock_state")
    health_clock_state = health.get("qualified_clock_state")
    qualified_clock_primary = qualified_clock.get("primary_clock")
    qualified_clock_decision_ready = bool(
        qualified_clock_state == "qualified"
        and health_clock_state == "qualified"
        and qualified_clock_primary == "session_tick"
        and not qualified_clock.get("blockers")
    )
    channels = manifest.get("channels", [])
    role_counts: dict[str, int] = {}
    admission_counts: dict[str, int] = {}
    for channel in channels if isinstance(channels, list) else []:
        role = str(channel.get("engineering_role") or "unclassified")
        admission = str(channel.get("engineering_admission_state") or "unclassified")
        role_counts[role] = role_counts.get(role, 0) + 1
        admission_counts[admission] = admission_counts.get(admission, 0) + 1
    return {
        "declared_channels": int(manifest.get("declared_channel_count") or 0),
        "cached_channels": int(manifest.get("cached_channel_count") or 0),
        "unmapped_channels": int(manifest.get("unmapped_channel_count") or 0),
        "warning_channels": int(health.get("warning_channel_count") or 0),
        "lossless_archive_complete": manifest.get("lossless_archive_complete") is True,
        "analysis_readiness_counts": readiness_counts,
        "engineering_role_counts": role_counts,
        "engineering_admission_counts": admission_counts,
        "qualified_clock_state": qualified_clock_state,
        "qualified_clock_primary": qualified_clock_primary,
        "qualified_clock_decision_ready": qualified_clock_decision_ready,
        "analysis_engine": manifest.get("analysis_engine"),
        "decoder_path": manifest.get("decoder_path"),
        "decoder_fallback_reason": manifest.get("decoder_fallback_reason"),
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
    assessment_failures: list[str] = []
    is_array = definition.data_type_id != 0 and definition.count > 1
    if is_array:
        try:
            values = values.explode().drop_nulls()
        except Exception as exc:
            assessment_failures.append(
                f"Array health expansion could not be assessed ({type(exc).__name__})."
            )
    distinct_assessed = True
    try:
        distinct_count = int(values.n_unique())
    except Exception as exc:
        distinct_assessed = False
        distinct_count = 0
        assessment_failures.append(
            f"Distinct-value health could not be assessed ({type(exc).__name__})."
        )
    if not distinct_assessed:
        variation = "not_assessed"
    elif len(values) == 0:
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
        except Exception as exc:
            assessment_failures.append(
                f"Numeric range health could not be assessed ({type(exc).__name__})."
            )

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
    if definition.data_type_id in {2, 3, 4, 5} and not assessment_failures:
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

    clipping_status = (
        "not_assessed"
        if assessment_failures
        else "possible_numeric_limit_clipping"
        if numeric_limit_hit_count
        else "none_detected"
    )
    saturation_status = "not_assessed" if assessment_failures else "none_detected"
    if (
        definition.name in {"Throttle", "Brake", "Clutch", "Handbrake"}
        and max(lower_occupancy, upper_occupancy) >= 0.05
    ):
        saturation_status = "normal_control_boundary_occupancy"

    warnings: list[str] = [*assessment_failures]
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
    health_status = "not_assessed" if assessment_failures else "warning" if warnings else "healthy"

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


def _sample_continuity(frame: Any, telemetry_rate_hz: int | None) -> dict[str, Any]:
    clock = build_qualified_telemetry_clock(
        frame,
        expected_sample_rate_hz=telemetry_rate_hz,
    )
    expected_dt = 1.0 / telemetry_rate_hz if telemetry_rate_hz else None
    if clock.sample_count < 2:
        status = "not_assessed"
    elif clock.clock_state == "qualified":
        status = "qualified_tick_clock"
    elif clock.clock_state == "degraded":
        status = "observed_session_time_only"
    else:
        status = "issues_detected"
    return {
        "status": status,
        "session_tick_available": bool(clock.session_tick_coverage_pct),
        "session_time_available": bool(clock.session_time_coverage_pct),
        "invalid_tick_sample_count": clock.invalid_tick_sample_count,
        "invalid_timestamp_sample_count": clock.invalid_session_time_sample_count,
        "duplicate_tick_transition_count": clock.duplicate_tick_transition_count,
        "reversed_tick_transition_count": clock.reversed_tick_transition_count,
        "estimated_dropped_tick_count": clock.dropped_tick_count,
        "tick_discontinuity_count": clock.tick_discontinuity_count,
        "reset_epoch_count": clock.reset_epoch_count,
        "non_monotonic_timestamp_transition_count": (
            clock.session_time_duplicate_count + clock.session_time_reverse_count
        ),
        "duplicate_timestamp_transition_count": clock.session_time_duplicate_count,
        "reversed_timestamp_transition_count": clock.session_time_reverse_count,
        "timestamp_gap_count": clock.timestamp_gap_count,
        "expected_timestamp_step_s": expected_dt,
        "largest_timestamp_step_s": clock.largest_timestamp_step_s,
        "qualified_clock": clock.model_dump(mode="json"),
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
    analysis_engine: str | None = None,
    decoder_path: str | None = None,
    decoder_fallback_reason: str | None = None,
) -> dict[str, Any]:
    declared = {definition.name for definition in definitions}
    channels: list[dict[str, Any]] = []
    for definition in definitions:
        canonical = canonical_name(definition.name)
        engineering_role, admission_state, authority_limit = _engineering_admission(
            definition.name,
            canonical,
        )
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
                "engineering_role": engineering_role,
                "engineering_admission_state": admission_state,
                "engineering_authority_limit": authority_limit,
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
    warning_channel_count = sum(
        channel["health_status"] in {"warning", "not_assessed"}
        for channel in channels
    )
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
    sample_continuity = _sample_continuity(frame, header.telemetry_rate_hz)
    qualified_clock = sample_continuity.get("qualified_clock", {})
    clock_state = qualified_clock.get("clock_state")
    clock_health_warning = clock_state in {"blocked", "unavailable"} and bool(
        {"SessionTick", "SessionTime"} & declared
    )
    manifest = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "universal_archive_version": UNIVERSAL_ARCHIVE_VERSION,
        # These values are supplied by the import service from the decoded file,
        # never inferred from the path used to read this manifest later.
        "run_id": run_id,
        "source_file_sha256": source_file_sha256,
        "source_file_size_bytes": source_file_size_bytes,
        "telemetry_cache_sha256": telemetry_cache_sha256,
        "analysis_engine": analysis_engine,
        "decoder_path": decoder_path,
        "decoder_fallback_reason": decoder_fallback_reason,
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
            "status": "warning" if warning_channel_count or clock_health_warning else "healthy",
            "warning_channel_count": warning_channel_count,
            "non_finite_sample_count": non_finite_count,
            "impossible_sample_count": impossible_count,
            "malformed_array_record_count": malformed_array_count,
            "qualified_clock_state": clock_state,
            "qualified_clock_blocker_count": len(qualified_clock.get("blockers", [])),
        },
        "sample_continuity": sample_continuity,
        "recording_session_time_bounds_s": {
            "start": min(session_times) if session_times else None,
            "end": max(session_times) if session_times else None,
        },
        "recording_canonical_time_bounds_s": {
            "start": qualified_clock.get("canonical_start_time_s"),
            "end": qualified_clock.get("canonical_end_time_s"),
        },
        "channels": channels,
        "capabilities": _capabilities(declared),
        "measurement_candidate_contracts": _measurement_candidate_contracts(channels, identity),
    }
    manifest["cache_compatibility"] = assess_cache_compatibility(manifest, cache_present=True)
    manifest["capability_summary"] = compact_capability_summary(manifest)
    return manifest
