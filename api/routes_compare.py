from __future__ import annotations

import hashlib
import math

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from api.routes_runs import repository
from racelab_engine.analysis.compare_delta_traces import (
    DEFAULT_DELTA_CHANNELS,
    DeltaTraceResponse,
    compute_delta_traces,
)
from racelab_engine.analysis.compare_math import (
    aggregate_corner_stats,
    aggregate_driver_stats,
    aggregate_platform_stats,
    aggregate_powertrain_stats,
    aggregate_shock_comparison,
    aggregate_tire_comparison,
    compute_whole_car_index,
)
from racelab_engine.analysis.comparison import (
    COMPARE_CHANNELS,
    ContextChange,
    EnhancedComparisonSummary,
    compare_target_zone,
)
from racelab_engine.analysis.did_it_work import compute_observation
from racelab_engine.analysis.lap_eligibility import (
    eligible_laps,
    find_lap,
    lap_ineligibility_reasons,
    lap_is_eligible,
    longest_contiguous_eligible_lap_count,
)
from racelab_engine.analysis.pace_comparison import build_pace_comparison
from racelab_engine.analysis.phase_engineering import analyze_phase_engineering_systems
from racelab_engine.analysis.proximity_context import (
    ProximityContext,
    ProximityState,
    classify_proximity_time_gap_window,
)
from racelab_engine.analysis.setup_diff import (
    diff_context,
    diff_setups,
    setup_control_coverage,
    setup_controls_comparable,
    unmapped_setup_change_paths,
)
from racelab_engine.analysis.sim_integrity import (
    build_sim_integrity_certificate,
    comparison_integrity_gate,
)
from racelab_engine.analysis.test_discipline import score_test_discipline
from racelab_engine.analysis.time_alignment import analyze_time_alignment
from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.phase_engineering import EngineeringSystemsResponse
from racelab_engine.recording_identity import (
    RecordingIdentityError,
    SameRecordingError,
    require_independent_recordings,
    resolve_recording_sha256,
)
from racelab_engine.services.import_service import (
    read_telemetry_manifest,
    read_telemetry_rows,
)
from racelab_engine.services.insight_service import build_comparison_insights

router = APIRouter(prefix="/api/compare", tags=["compare"])


class _StrictCompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompareRequest(_StrictCompareRequest):
    baseline_run_id: str
    test_run_id: str
    baseline_lap: int | None = None
    test_lap: int | None = None
    target_zone_start_pct: float = 55.0
    target_zone_end_pct: float = 70.0


class ComparePreviewResponse(BaseModel):
    baseline_laps: list[int]
    test_laps: list[int]
    suggested_baseline_lap: int | None
    suggested_test_lap: int | None
    setup_changes: list[dict]
    context_changes: list[dict]
    warnings: list[str]
    compare_identity: dict


class DeltaTraceRequest(_StrictCompareRequest):
    baseline_run_id: str
    test_run_id: str
    baseline_lap: int | None = None
    test_lap: int | None = None
    channels: list[str] | None = None
    x_axis: str = "lap_dist_ft"
    start_pct: float = 0.0
    end_pct: float = 100.0
    step_pct: float = 0.1
    target_zone_start_pct: float = 55.0
    target_zone_end_pct: float = 70.0


class TimeAnalysisRequest(_StrictCompareRequest):
    baseline_run_id: str
    test_run_id: str
    baseline_lap: int | None = None
    test_lap: int | None = None
    start_pct: float = 0.0
    end_pct: float = 100.0
    step_pct: float = 0.1


def _make_comparison_id(identity_payload: dict) -> str:
    identity = canonical_json_sha256(identity_payload).encode("utf-8")
    return f"cmp_{hashlib.sha256(identity).hexdigest()[:20]}"


def _compare_run_identity(run_id: str, repo) -> dict:
    manifest = read_telemetry_manifest(run_id)
    setup = repo.get_setup_snapshot(run_id)
    return {
        "run_id": run_id,
        "source_file_sha256": manifest.get("source_file_sha256"),
        "telemetry_cache_sha256": manifest.get("telemetry_cache_sha256"),
        "compatibility_fingerprint": manifest.get("compatibility_fingerprint"),
        "build_identity": manifest.get("compatibility_identity"),
        "setup_id": setup.setup_id if setup is not None else None,
        "setup_sha256": canonical_json_sha256(setup) if setup is not None else None,
    }


def _assert_independent_compare_recordings(
    baseline_run_id: str,
    test_run_id: str,
    repo,
) -> tuple[str, str]:
    """Fail closed when run aliases point at one physical ``.ibt`` source."""

    source_by_run: dict[str, str] = {}
    for run_id in (baseline_run_id, test_run_id):
        manifest = read_telemetry_manifest(run_id)
        get_recording_sha256 = getattr(repo, "get_recording_sha256", None)
        stored_sha = (
            get_recording_sha256(run_id)
            if callable(get_recording_sha256)
            else getattr(
                getattr(repo.get_overview(run_id), "session", None),
                "file_hash",
                None,
            )
        )
        try:
            source_by_run[run_id] = resolve_recording_sha256(
                run_id=run_id,
                stored_source_sha256=stored_sha,
                manifest_source_sha256=manifest.get("source_file_sha256"),
            )
        except RecordingIdentityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        independent = require_independent_recordings(
            source_by_run,
            ordered_run_ids=(baseline_run_id, test_run_id),
        )
    except (SameRecordingError, RecordingIdentityError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return independent[0], independent[1]


def _compare_identity(req: CompareRequest, repo, baseline_lap: int | None, test_lap: int | None) -> dict:
    payload = {
        "schema_version": "p31.compare-identity.v1",
        "baseline": _compare_run_identity(req.baseline_run_id, repo),
        "test": _compare_run_identity(req.test_run_id, repo),
        "baseline_lap": baseline_lap,
        "test_lap": test_lap,
        "target_zone_start_pct": req.target_zone_start_pct,
        "target_zone_end_pct": req.target_zone_end_pct,
    }
    return {**payload, "identity_sha256": canonical_json_sha256(payload)}


_COMPARE_READ_CHANNELS = list(dict.fromkeys([
    "lap_dist_pct",
    "lap_dist_pct_100",
    "lap_dist_ft",
    "session_time",
    "session_tick",
    "frame_rate",
    "cpu_usage_foreground",
    "cpu_usage_background",
    "gpu_usage",
    "memory_page_faults_per_s",
    "memory_soft_page_faults_per_s",
    "channel_latency_s",
    "channel_average_latency_s",
    "channel_quality",
    "SessionTick",
    "SessionTime",
    "FrameRate",
    "CpuUsageFG",
    "CpuUsageBG",
    "GpuUsage",
    "MemPageFaultSec",
    "MemSoftPageFaultSec",
    "ChanLatency",
    "ChanAvgLatency",
    "ChanQuality",
    "fuel_level",
    "speed_mps",
    "car_distance_ahead_m",
    "car_distance_behind_m",
    "air_density",
    "air_temp",
    "track_temp",
    "wind_vel",
    "wind_dir",
    "precipitation",
    "track_wetness",
    "player_tire_compound",
    "lf_cold_pressure",
    "rf_cold_pressure",
    "lr_cold_pressure",
    "rr_cold_pressure",
    "lf_tire_distance_m",
    "rf_tire_distance_m",
    "lr_tire_distance_m",
    "rr_tire_distance_m",
    *COMPARE_CHANNELS,
    "abs_steering_deg",
    "front_avg_rh_in",
    "rear_avg_rh_in",
    "lf_ride_height_in",
    "rf_ride_height_in",
    "lr_ride_height_in",
    "rr_ride_height_in",
    "water_temp",
    "oil_temp",
    "gear",
    *[
        channel
        for corner in ("lf", "rf", "lr", "rr")
        for channel in (
            f"{corner}_shock_defl_in",
            f"{corner}_shock_vel_in_s",
            f"{corner}_slip_ratio",
            f"{corner}_pressure_gain",
            f"{corner}_temp_spread",
            f"{corner}_wear_spread",
            f"{corner}_camber_temp_bias_c",
            f"{corner}_shock_velocity_rms",
            f"{corner}_shock_activity_index",
        )
    ],
    "LFspeed", "RFspeed", "LRspeed", "RRspeed",
    "LFpressure", "RFpressure", "LRpressure", "RRpressure",
    "shock_activity_index",
    "shock_velocity_rms",
    "damper_energy_proxy",
    "damper_work_proxy",
]))

_TIME_ALIGNMENT_CHANNELS = [
    "lap_dist_pct_100", "lap_dist_ft", "session_time", "speed_mps", "speed_mph",
    "throttle_pct", "brake_pct", "steering_deg", "yaw_rate", "lat_accel",
    "long_accel", "vert_accel", "vert_accel_g", "lat", "lon", "alt",
    "on_pit_road", "enter_exit_reset_state", "lf_shock_defl_in", "rf_shock_defl_in",
    "lr_shock_defl_in", "rr_shock_defl_in", "lf_shock_vel_in_s",
    "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s",
    "lf_ride_height_in", "rf_ride_height_in", "lr_ride_height_in",
    "rr_ride_height_in", "cfs_ride_height_in",
    "fuel_level", "air_temp", "track_temp", "wind_vel",
    "lf_tire_distance_m", "rf_tire_distance_m", "lr_tire_distance_m",
    "rr_tire_distance_m",
]

_SIM_INTEGRITY_CHANNELS = [
    "session_tick", "frame_rate", "cpu_usage_foreground", "cpu_usage_background",
    "gpu_usage", "memory_page_faults_per_s", "memory_soft_page_faults_per_s",
    "channel_latency_s", "channel_average_latency_s", "channel_quality",
    "SessionTick", "SessionTime", "FrameRate", "CpuUsageFG", "CpuUsageBG",
    "GpuUsage", "MemPageFaultSec", "MemSoftPageFaultSec", "ChanLatency",
    "ChanAvgLatency", "ChanQuality",
]

_PHASE_ENGINEERING_CHANNELS = list(dict.fromkeys([
    *_TIME_ALIGNMENT_CHANNELS,
    *_SIM_INTEGRITY_CHANNELS,
    "curvature_1_per_m", "front_avg_rh_in", "rear_avg_rh_in",
    "center_rake_fs_in", "side_rake_in", "dynamic_pressure_psf",
    "cfs_risk_score", "throttle_pct", "brake_pct", "steering_deg",
    "yaw_rate", "lat_accel", "long_accel",
]))


_COMPATIBILITY_FIELDS = {
    "driver_user_id": "driver identity",
    "car_id": "car ID",
    "car_path": "car path",
    "car_version": "car version",
    "track_id": "track ID",
    "track_version": "track version",
    "iracing_build_version": "simulator build",
    "session_type": "session type",
}
_OPTIONAL_COMPATIBILITY_FIELDS = {
    "car_configuration_id": "car configuration",
    "track_configuration_name": "track configuration",
}


def _assert_run_compatibility(baseline_run_id: str, test_run_id: str) -> list[str]:
    baseline_identity = read_telemetry_manifest(baseline_run_id).get("compatibility_identity") or {}
    test_identity = read_telemetry_manifest(test_run_id).get("compatibility_identity") or {}
    missing = [
        label
        for key, label in _COMPATIBILITY_FIELDS.items()
        if baseline_identity.get(key) is None or test_identity.get(key) is None
    ]
    mismatches = [
        label
        for key, label in _COMPATIBILITY_FIELDS.items()
        if baseline_identity.get(key) is not None
        and test_identity.get(key) is not None
        and str(baseline_identity.get(key)) != str(test_identity.get(key))
    ]
    for key, label in _OPTIONAL_COMPATIBILITY_FIELDS.items():
        baseline_value = baseline_identity.get(key)
        test_value = test_identity.get(key)
        if (baseline_value is None) != (test_value is None):
            missing.append(label)
        elif baseline_value is not None and str(baseline_value) != str(test_value):
            mismatches.append(label)
    if mismatches:
        raise HTTPException(
            400,
            "Runs are not compatible for setup attribution; mismatched " + ", ".join(mismatches) + ".",
        )
    return missing


def _load_compare_rows(
    run_id: str,
    lap: int | None,
    channels: list[str] | None = None,
) -> list[dict]:
    selected = list(dict.fromkeys(["lap_dist_pct", "lap_dist_pct_100", "lap_dist_ft", *(channels or _COMPARE_READ_CHANNELS)]))
    return read_telemetry_rows(run_id, lap=lap, columns=selected)


def _resolve_eligible_lap(overview, requested_lap: int | None, role: str) -> int:
    if requested_lap is None:
        if overview.best_useful_lap and lap_is_eligible(overview.best_useful_lap):
            return overview.best_useful_lap.lap_number
        raise HTTPException(400, f"No eligible {role} lap is available.")
    lap = find_lap(overview.laps, requested_lap)
    if lap is None:
        raise HTTPException(404, f"{role.title()} lap {requested_lap} was not found.")
    if not lap_is_eligible(lap):
        reasons = "; ".join(lap_ineligibility_reasons(lap)) or "failed the evidence gate"
        raise HTTPException(400, f"{role.title()} lap {requested_lap} is not eligible: {reasons}.")
    return requested_lap


def _first_finite(rows: list[dict], key: str) -> float | None:
    for row in rows:
        value = row.get(key)
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == number and number not in (float("inf"), float("-inf")):
            return number
    return None


def _safe_finite(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _telemetry_context_changes(baseline_rows: list[dict], test_rows: list[dict]) -> list[ContextChange]:
    changes: list[ContextChange] = []
    baseline_fuel = _first_finite(baseline_rows, "fuel_level")
    test_fuel = _first_finite(test_rows, "fuel_level")
    if baseline_fuel is None or test_fuel is None:
        changes.append(ContextChange(
            key="fuel_level_coverage",
            label="Fuel level coverage",
            baseline_value=baseline_fuel,
            test_value=test_fuel,
            warning="Fuel level is missing from one or both laps, so fuel context cannot be matched.",
            is_problem=True,
        ))
    elif abs(test_fuel - baseline_fuel) > 2.0:
        changes.append(ContextChange(
            key="fuel_level",
            label="Fuel Level",
            baseline_value=baseline_fuel,
            test_value=test_fuel,
            warning="Starting fuel differed by more than 2 L; pace attribution is confounded.",
            is_problem=True,
        ))

    matched_context = (
        ("air_density", "Air density", 0.05, "Air density changed by more than 0.05 kg/m³."),
        ("air_temp", "Air temperature", 5.0, "Air temperature changed by more than 5 °C."),
        ("track_temp", "Track temperature", 5.0, "Track temperature changed by more than 5 °C."),
        ("wind_vel", "Wind speed", 2.0, "Wind speed changed by more than 2 m/s."),
    )
    for key, label, threshold, warning in matched_context:
        baseline_value = _first_finite(baseline_rows, key)
        test_value = _first_finite(test_rows, key)
        if baseline_value is None or test_value is None:
            changes.append(ContextChange(
                key=f"{key}_coverage",
                label=f"{label} coverage",
                baseline_value=baseline_value,
                test_value=test_value,
                warning=f"{label} is missing from one or both laps, so the environment cannot be matched.",
                is_problem=True,
            ))
        elif abs(test_value - baseline_value) > threshold:
            changes.append(ContextChange(
                key=key,
                label=label,
                baseline_value=baseline_value,
                test_value=test_value,
                warning=warning,
                is_problem=True,
            ))

    discrete_context = (
        ("track_wetness", "Track wetness"),
        ("player_tire_compound", "Tire compound"),
    )
    for key, label in discrete_context:
        baseline_value = _first_finite(baseline_rows, key)
        test_value = _first_finite(test_rows, key)
        if baseline_value is None or test_value is None:
            changes.append(ContextChange(
                key=f"{key}_coverage",
                label=f"{label} coverage",
                baseline_value=baseline_value,
                test_value=test_value,
                warning=f"{label} is missing from one or both laps, so it cannot be matched.",
                is_problem=True,
            ))
        elif baseline_value != test_value:
            changes.append(ContextChange(
                key=key,
                label=label,
                baseline_value=baseline_value,
                test_value=test_value,
                warning=f"{label} differed between the compared laps.",
                is_problem=True,
            ))

    baseline_precipitation = _first_finite(baseline_rows, "precipitation")
    test_precipitation = _first_finite(test_rows, "precipitation")
    if baseline_precipitation is None or test_precipitation is None:
        changes.append(ContextChange(
            key="precipitation_coverage",
            label="Precipitation coverage",
            baseline_value=baseline_precipitation,
            test_value=test_precipitation,
            warning="Precipitation is missing from one or both laps, so weather state cannot be matched.",
            is_problem=True,
        ))
    elif abs(test_precipitation - baseline_precipitation) > 0.001:
        changes.append(ContextChange(
            key="precipitation",
            label="Precipitation",
            baseline_value=baseline_precipitation,
            test_value=test_precipitation,
            warning="Precipitation differed between the compared laps.",
            is_problem=True,
        ))

    cold_pressure_keys = (
        "lf_cold_pressure", "rf_cold_pressure", "lr_cold_pressure", "rr_cold_pressure",
    )
    baseline_cold_pressures = [_first_finite(baseline_rows, key) for key in cold_pressure_keys]
    test_cold_pressures = [_first_finite(test_rows, key) for key in cold_pressure_keys]
    if any(value is None for value in [*baseline_cold_pressures, *test_cold_pressures]):
        changes.append(ContextChange(
            key="cold_pressure_coverage",
            label="Cold tire-pressure coverage",
            baseline_value=baseline_cold_pressures,
            test_value=test_cold_pressures,
            warning="One or more cold tire pressures are missing, so starting tire state cannot be matched.",
            is_problem=True,
        ))
    elif any(
        abs(float(test) - float(baseline)) > 1.0
        for baseline, test in zip(baseline_cold_pressures, test_cold_pressures)
    ):
        changes.append(ContextChange(
            key="cold_pressure",
            label="Cold tire pressures",
            baseline_value=baseline_cold_pressures,
            test_value=test_cold_pressures,
            warning="At least one cold tire pressure differed by more than 1 kPa (0.15 psi).",
            is_problem=True,
        ))
    baseline_wind_dir = _first_finite(baseline_rows, "wind_dir")
    test_wind_dir = _first_finite(test_rows, "wind_dir")
    if baseline_wind_dir is None or test_wind_dir is None:
        changes.append(ContextChange(
            key="wind_dir_coverage",
            label="Wind direction coverage",
            baseline_value=baseline_wind_dir,
            test_value=test_wind_dir,
            warning="Wind direction is missing from one or both laps, so wind context cannot be matched.",
            is_problem=True,
        ))
    else:
        wind_delta_rad = abs(math.atan2(
            math.sin(test_wind_dir - baseline_wind_dir),
            math.cos(test_wind_dir - baseline_wind_dir),
        ))
        if wind_delta_rad > math.radians(20.0):
            changes.append(ContextChange(
                key="wind_dir",
                label="Wind direction",
                baseline_value=baseline_wind_dir,
                test_value=test_wind_dir,
                warning="Wind direction changed by more than 20 degrees.",
                is_problem=True,
            ))

    tire_keys = ("lf_tire_distance_m", "rf_tire_distance_m", "lr_tire_distance_m", "rr_tire_distance_m")
    baseline_tire = [_first_finite(baseline_rows, key) for key in tire_keys]
    test_tire = [_first_finite(test_rows, key) for key in tire_keys]
    if any(value is None for value in [*baseline_tire, *test_tire]):
        changes.append(ContextChange(
            key="tire_distance_coverage",
            label="Tire-age coverage",
            baseline_value=baseline_tire,
            test_value=test_tire,
            warning="One or more tire odometers are missing, so tire age cannot be matched.",
            is_problem=True,
        ))
    else:
        max_tire_delta = max(
            abs(float(test) - float(baseline))
            for baseline, test in zip(baseline_tire, test_tire)
        )
        if max_tire_delta > 1_000.0:
            changes.append(ContextChange(
                key="tire_distance",
                label="Tire age",
                baseline_value=baseline_tire,
                test_value=test_tire,
                warning="At least one tire odometer differs by more than 1,000 m.",
                is_problem=True,
            ))
    return changes


def _format_proximity_context(context: ProximityContext) -> str:
    if context.state is ProximityState.CONTEXT_UNKNOWN:
        return f"Unknown ({context.coverage_fraction:.0%} channel coverage)"
    parts = [context.state.value.replace("_", " ").title()]
    if context.min_time_gap_ahead_s is not None and context.min_time_gap_ahead_s <= 1.5:
        parts.append(f"ahead {context.min_time_gap_ahead_s:.2f} s")
    if context.min_time_gap_behind_s is not None and context.min_time_gap_behind_s <= 0.5:
        parts.append(f"behind {context.min_time_gap_behind_s:.2f} s")
    return "; ".join(parts)


def _proximity_attribution_warning(*contexts: ProximityContext) -> str:
    states = {context.state for context in contexts}
    has_ahead = bool(
        states & {ProximityState.NEARBY_CAR_AHEAD, ProximityState.NEARBY_CARS_AHEAD_AND_BEHIND}
    )
    has_behind = bool(
        states & {ProximityState.NEARBY_CAR_BEHIND, ProximityState.NEARBY_CARS_AHEAD_AND_BEHIND}
    )
    has_unknown = ProximityState.CONTEXT_UNKNOWN in states

    if has_ahead and has_behind:
        influence = "Nearby cars within 1.5 s ahead or 0.5 s behind could alter the measured speed"
    elif has_behind:
        influence = "A car was within 0.5 s behind, so traffic influence on the measured speed cannot be ruled out"
    elif has_ahead:
        influence = "A car within 1.5 s ahead could alter the measured speed"
    else:
        influence = "Traffic-channel coverage is incomplete, so an external speed influence cannot be ruled out"
    if has_unknown and (has_ahead or has_behind):
        influence += ", and the other run's traffic context is incomplete"
    return (
        f"The lap and its measured speed remain valid. {influence}, so the difference cannot "
        "be credited solely to the setup until a matched repeat confirms it."
    )


def _proximity_context_changes(
    baseline_rows: list[dict],
    test_rows: list[dict],
) -> tuple[list[ContextChange], bool, list[str]]:
    baseline = classify_proximity_time_gap_window(baseline_rows)
    test = classify_proximity_time_gap_window(test_rows)
    blocks_attribution = baseline.blocks_relative_resistance or test.blocks_relative_resistance
    if not blocks_attribution:
        return [], False, []

    baseline_text = _format_proximity_context(baseline)
    test_text = _format_proximity_context(test)
    evidence = [f"Baseline proximity: {baseline_text}.", f"Test proximity: {test_text}."]
    return [
        ContextChange(
            key="nearby_car_proximity",
            label="Nearby-car proximity",
            baseline_value=baseline_text,
            test_value=test_text,
            warning=_proximity_attribution_warning(baseline, test),
            is_problem=True,
        )
    ], True, evidence


def _eligible_timed_lap_numbers(overview) -> list[int]:
    return [
        lap.lap_number
        for lap in sorted(eligible_laps(overview.laps), key=lambda item: item.lap_number)
        if lap.lap_time is not None and math.isfinite(float(lap.lap_time))
    ]


def _eligible_time_lap_rows(run_id: str, overview) -> list[list[dict]]:
    lap_numbers = set(_eligible_timed_lap_numbers(overview))
    if not lap_numbers:
        return []
    rows_by_lap: dict[int, list[dict]] = {lap_number: [] for lap_number in lap_numbers}
    for row in _load_compare_rows(
        run_id,
        None,
        [
            "lap", "lap_dist_pct_100", "session_time", "fuel_level",
            "air_temp", "track_temp", "wind_vel", "lf_tire_distance_m",
            "rf_tire_distance_m", "lr_tire_distance_m", "rr_tire_distance_m",
        ],
    ):
        try:
            lap_number = int(row.get("lap"))
        except (TypeError, ValueError):
            continue
        if lap_number in rows_by_lap:
            rows_by_lap[lap_number].append(row)
    return [rows_by_lap[lap_number] for lap_number in sorted(lap_numbers) if rows_by_lap[lap_number]]


def _eligible_platform_lap_rows(run_id: str, overview) -> list[list[dict]]:
    lap_numbers = set(_eligible_timed_lap_numbers(overview))
    if not lap_numbers:
        return []
    rows_by_lap: dict[int, list[dict]] = {lap_number: [] for lap_number in lap_numbers}
    channels = [
        "lap", "lap_dist_pct_100", "session_time", "speed_mph", "speed_mps",
        "cfs_ride_height_in", "front_avg_rh_in", "rear_avg_rh_in",
        "center_rake_fs_in", "side_rake_in", "dynamic_pressure_psf",
    ]
    for row in _load_compare_rows(run_id, None, channels):
        try:
            lap_number = int(row.get("lap"))
        except (TypeError, ValueError):
            continue
        if lap_number in rows_by_lap:
            rows_by_lap[lap_number].append(row)
    return [rows_by_lap[lap_number] for lap_number in sorted(lap_numbers) if rows_by_lap[lap_number]]


def _finite_range(rows: list[dict], channels: tuple[str, ...]) -> list[float] | None:
    values = [
        value
        for row in rows
        for channel in channels
        if (value := _safe_finite(row.get(channel))) is not None
    ]
    return [min(values), max(values)] if values else None


def _pace_cohort_proximity_changes(
    baseline_run_id: str,
    test_run_id: str,
    baseline_overview,
    test_overview,
    baseline_selected_lap: int,
    test_selected_lap: int,
    baseline_selected_rows: list[dict],
    test_selected_rows: list[dict],
) -> tuple[list[ContextChange], bool, list[str]]:
    baseline_laps = _eligible_timed_lap_numbers(baseline_overview)
    test_laps = _eligible_timed_lap_numbers(test_overview)
    cohort_size = min(len(baseline_laps), len(test_laps))
    if cohort_size < 3:
        return [], False, []

    affected: dict[str, list[tuple[int, str]]] = {"Baseline": [], "Test": []}
    specifications = (
        (
            "Baseline",
            baseline_run_id,
            baseline_laps[:cohort_size],
            baseline_selected_lap,
            baseline_selected_rows,
        ),
        (
            "Test",
            test_run_id,
            test_laps[:cohort_size],
            test_selected_lap,
            test_selected_rows,
        ),
    )
    proximity_channels = ["lap", "speed_mps", "car_distance_ahead_m", "car_distance_behind_m"]
    for role, run_id, lap_numbers, selected_lap, selected_rows in specifications:
        rows_by_lap: dict[int, list[dict]] = {lap_number: [] for lap_number in lap_numbers}
        for row in _load_compare_rows(run_id, None, proximity_channels):
            try:
                row_lap = int(row.get("lap"))
            except (TypeError, ValueError):
                continue
            if row_lap in rows_by_lap:
                rows_by_lap[row_lap].append(row)
        for lap_number in lap_numbers:
            rows = (
                selected_rows
                if lap_number == selected_lap
                else rows_by_lap.get(lap_number, [])
            )
            context = classify_proximity_time_gap_window(rows)
            if context.blocks_relative_resistance:
                affected[role].append((lap_number, _format_proximity_context(context)))

    def _summarize(items: list[tuple[int, str]], cohort_count: int) -> str:
        if not items:
            return "Outside configured windows"
        examples = "; ".join(
            f"lap {lap_number}: {description}"
            for lap_number, description in items[:3]
        )
        remaining = len(items) - 3
        suffix = f"; plus {remaining} more" if remaining > 0 else ""
        return f"{len(items)}/{cohort_count} laps affected ({examples}{suffix})"

    baseline_summary = _summarize(affected["Baseline"], cohort_size)
    test_summary = _summarize(affected["Test"], cohort_size)

    evidence = [
        f"{role} pace cohort proximity: {_summarize(items, cohort_size)}."
        for role, items in affected.items()
        if items
    ]
    if not evidence:
        return [], False, []
    return [
        ContextChange(
            key="pace_cohort_proximity",
            label="Pace-cohort nearby-car proximity",
            baseline_value=baseline_summary,
            test_value=test_summary,
            warning=(
                "At least one lap used by the repeatable-pace cohort has nearby-car or missing "
                "proximity context, so cohort pace remains observational."
            ),
            is_problem=True,
        )
    ], True, evidence


def _context_evidence(changes: list[ContextChange], extra: list[str]) -> list[str]:
    evidence = [f"{change.label}: {change.warning}" for change in changes if change.is_problem]
    return list(dict.fromkeys([*evidence, *extra]))


def _analysis_evidence_changes(platform, driver) -> list[ContextChange]:
    changes: list[ContextChange] = []
    if platform.cfs_height is None or platform.cfs_height.delta_avg is None:
        changes.append(ContextChange(
            key="platform_evidence_coverage",
            label="Platform evidence coverage",
            warning="CFS ride-height evidence is missing, so platform risk cannot be compared.",
            is_problem=True,
        ))
    if driver.driver_verdict == "unavailable":
        changes.append(ContextChange(
            key="driver_input_coverage",
            label="Driver-input coverage",
            warning="Throttle, brake, or steering evidence is missing, so driver repeatability is unknown.",
            is_problem=True,
        ))
    return changes


def _setup_evidence_changes(
    baseline_setup,
    test_setup,
    setup_changes,
) -> tuple[list[ContextChange], list[str]]:
    changes: list[ContextChange] = []
    unmapped = unmapped_setup_change_paths(baseline_setup, test_setup, setup_changes)
    if not setup_controls_comparable(baseline_setup, test_setup):
        baseline_coverage = setup_control_coverage(baseline_setup)
        test_coverage = setup_control_coverage(test_setup)
        changes.append(ContextChange(
            key="setup_coverage",
            label="Setup coverage",
            baseline_value=f"{baseline_coverage[0]}/{baseline_coverage[1]}",
            test_value=f"{test_coverage[0]}/{test_coverage[1]}",
            warning="Setup coverage is incomplete or cannot distinguish unavailable controls from missing data.",
            is_problem=True,
        ))
    if unmapped:
        changes.append(ContextChange(
            key="unmapped_setup_changes",
            label="Unmapped setup changes",
            baseline_value=None,
            test_value=unmapped[:5],
            warning="Raw garage settings changed outside the app's mapped setup controls.",
            is_problem=True,
        ))
    return changes, unmapped


def _validate_zone(start_pct: float, end_pct: float, *, label: str = "Target zone") -> None:
    if not 0.0 <= start_pct < end_pct <= 100.0:
        raise HTTPException(400, f"{label} must satisfy 0 <= start < end <= 100.")


@router.post("")
def run_comparison(req: CompareRequest) -> dict:
    _validate_zone(req.target_zone_start_pct, req.target_zone_end_pct)
    repo = repository()
    bl_overview = repo.get_overview(req.baseline_run_id)
    t_overview = repo.get_overview(req.test_run_id)
    if bl_overview is None:
        raise HTTPException(404, f"Baseline run not found: {req.baseline_run_id}")
    if t_overview is None:
        raise HTTPException(404, f"Test run not found: {req.test_run_id}")
    compatibility_missing = _assert_run_compatibility(req.baseline_run_id, req.test_run_id)
    _assert_independent_compare_recordings(
        req.baseline_run_id, req.test_run_id, repo
    )

    bl_lap = _resolve_eligible_lap(bl_overview, req.baseline_lap, "baseline")
    t_lap = _resolve_eligible_lap(t_overview, req.test_lap, "test")

    is_same = req.baseline_run_id == req.test_run_id and bl_lap == t_lap and bl_lap is not None

    bl_rows = _load_compare_rows(req.baseline_run_id, bl_lap, _COMPARE_READ_CHANNELS)
    t_rows = _load_compare_rows(req.test_run_id, t_lap, _COMPARE_READ_CHANNELS)
    if not bl_rows:
        raise HTTPException(400, f"Baseline lap {bl_lap} has no telemetry data.")
    if not t_rows:
        raise HTTPException(400, f"Test lap {t_lap} has no telemetry data.")

    baseline_integrity = build_sim_integrity_certificate(
        bl_rows,
        expected_sample_rate_hz=bl_overview.session.telemetry_rate_hz,
    )
    test_integrity = build_sim_integrity_certificate(
        t_rows,
        expected_sample_rate_hz=t_overview.session.telemetry_rate_hz,
    )
    integrity_clear, integrity_confidence_cap, integrity_warnings = comparison_integrity_gate(
        baseline_integrity,
        test_integrity,
    )

    s = req.target_zone_start_pct
    e = req.target_zone_end_pct

    # target zone
    target_zone = compare_target_zone(bl_rows, t_rows, s, e)

    # whole-car comparison sub-systems
    platform = aggregate_platform_stats(bl_rows, t_rows, s, e)
    corners = aggregate_corner_stats(bl_rows, t_rows, s, e)
    driver = aggregate_driver_stats(bl_rows, t_rows, s, e)
    powertrain = aggregate_powertrain_stats(bl_rows, t_rows, s, e)
    tire_comparison = aggregate_tire_comparison(
        bl_rows, t_rows, s, e,
        lap_count=min(
            longest_contiguous_eligible_lap_count(bl_overview.laps),
            longest_contiguous_eligible_lap_count(t_overview.laps),
        ),
    )
    shock_comparison = aggregate_shock_comparison(bl_rows, t_rows, s, e)

    # setup diff
    bl_setup = repo.get_setup_snapshot(req.baseline_run_id)
    t_setup = repo.get_setup_snapshot(req.test_run_id)
    setup_changes = diff_setups(bl_setup, t_setup)

    # context diff
    bl_lap_summary = find_lap(bl_overview.laps, bl_lap)
    t_lap_summary = find_lap(t_overview.laps, t_lap)
    bl_lap_valid = bl_lap_summary is not None and lap_is_eligible(bl_lap_summary)
    t_lap_valid = t_lap_summary is not None and lap_is_eligible(t_lap_summary)
    context_changes = diff_context(bl_overview.session, t_overview.session, bl_lap_valid, t_lap_valid)
    if integrity_clear is not True:
        context_changes.append(ContextChange(
            key="sim_integrity_certificate",
            label="Simulator/data integrity",
            baseline_value=baseline_integrity.status,
            test_value=test_integrity.status,
            warning=(
                integrity_warnings[0]
                if integrity_warnings
                else "Simulator/data integrity could not be certified for both laps."
            ),
            is_problem=True,
        ))
    if compatibility_missing:
        context_changes.append(ContextChange(
            key="compatibility_identity",
            label="Run compatibility identity",
            baseline_value="Missing",
            test_value="Missing",
            warning=(
                "Compatibility identity is incomplete ("
                + ", ".join(compatibility_missing)
                + "). Reimport both .ibt files before accepting setup attribution."
            ),
            is_problem=True,
        ))
    context_changes.extend(_telemetry_context_changes(bl_rows, t_rows))
    context_changes.extend(_analysis_evidence_changes(platform, driver))
    setup_evidence_changes, unmapped_setup_changes = _setup_evidence_changes(
        bl_setup,
        t_setup,
        setup_changes,
    )
    context_changes.extend(setup_evidence_changes)
    proximity_changes, proximity_blocks_attribution, proximity_evidence = _proximity_context_changes(
        bl_rows,
        t_rows,
    )
    context_changes.extend(proximity_changes)
    cohort_changes, cohort_blocks_attribution, cohort_evidence = _pace_cohort_proximity_changes(
        req.baseline_run_id,
        req.test_run_id,
        bl_overview,
        t_overview,
        bl_lap,
        t_lap,
        bl_rows,
        t_rows,
    )
    context_changes.extend(cohort_changes)
    context_blocks_attribution = bool(any(change.is_problem for change in context_changes))
    context_evidence = _context_evidence(
        context_changes,
        [*proximity_evidence, *cohort_evidence],
    )

    # ── Context status ──────────────────────────────────────
    # discipline
    context_problems = sum(c.is_problem for c in context_changes)
    setup_data_available = (
        setup_controls_comparable(bl_setup, t_setup)
        and not unmapped_setup_changes
    )
    discipline = score_test_discipline(
        setup_changes,
        context_problems,
        setup_data_available=setup_data_available,
    )

    # observational comparison result
    pace = build_pace_comparison(bl_overview.laps, t_overview.laps, bl_lap, t_lap)
    observation = compute_observation(
        target_zone,
        discipline,
        is_same_run=is_same,
        pace=pace,
        driver_changed=driver.driver_verdict == "changed",
        driver_evidence_available=driver.driver_verdict != "unavailable",
        context_blocks_attribution=context_blocks_attribution,
        context_evidence=context_evidence,
    )

    # whole car index
    target_speed_delta = next(
        (delta.delta for delta in target_zone.channel_deltas if delta.channel == "speed_mph"),
        None,
    )
    wci = None
    if not context_blocks_attribution and discipline.is_reliable:
        wci = compute_whole_car_index(
            platform,
            driver,
            powertrain,
            discipline.score,
            context_problems,
            speed_delta_mph=target_speed_delta,
        )

    compare_identity = _compare_identity(req, repo, bl_lap, t_lap)
    comparison_id = _make_comparison_id(compare_identity)
    non_authority_warning = (
        "Comparison is observational; only the controlled P19 workflow may authorize "
        "a setup action or policy."
    )
    observation_evidence_state = (
        EvidenceState.BLOCKED_BY_CONTEXT
        if context_blocks_attribution
        else EvidenceState.OBSERVED_CORRELATION
    )
    observation_source_channels = sorted(
        {
            delta.channel
            for delta in target_zone.channel_deltas
            if delta.baseline_avg is not None and delta.test_avg is not None
        }
    )
    observation_blockers = list(dict.fromkeys([
        *context_evidence,
        *discipline.negative_factors,
        non_authority_warning,
    ]))

    summary = EnhancedComparisonSummary(
        comparison_id=comparison_id,
        baseline_run_id=req.baseline_run_id,
        test_run_id=req.test_run_id,
        baseline_lap=bl_lap,
        test_lap=t_lap,
        target_zone_start_pct=s,
        target_zone_end_pct=e,
        target_zone=target_zone,
        whole_car_index=wci,
        pace_comparison=pace,
        platform=platform,
        corner_matrix=corners,
        tire_comparison=tire_comparison,
        shock_comparison=shock_comparison,
        driver_comparison=driver,
        powertrain_comparison=powertrain,
        setup_changes=[{"setup_key": c.setup_key, "label": c.label, "group": c.group,
                         "baseline_value": c.baseline_value, "test_value": c.test_value,
                         "unit": c.unit, "delta": c.delta, "significance": c.significance,
                         "magnitude_basis": c.magnitude_basis,
                         "relative_delta_percent": c.relative_delta_percent,
                         "related_to_target_issue": c.related_to_target_issue} for c in setup_changes],
        context_changes=[{"key": c.key, "label": c.label, "baseline_value": c.baseline_value,
                          "test_value": c.test_value, "warning": c.warning,
                          "is_problem": c.is_problem} for c in context_changes],
        test_discipline={"score": discipline.score, "label": discipline.label,
                         "positive_factors": discipline.positive_factors,
                         "negative_factors": discipline.negative_factors,
                         "measurement_note": discipline.measurement_note},
        observation={
                 "observation_state": observation.observation_state,
                 "confidence_score": min(observation.confidence_score, integrity_confidence_cap),
                 "headline": observation.headline,
                 "evidence": observation.evidence,
                 "warnings": [*observation.warnings, non_authority_warning],
                 "evidence_state": observation_evidence_state.value,
                 "source_channels": observation_source_channels,
                 "blocker_reasons": observation_blockers},
        sim_integrity={
            "baseline": baseline_integrity.model_dump(mode="json"),
            "test": test_integrity.model_dump(mode="json"),
            "comparison_clear": integrity_clear,
            "confidence_cap": integrity_confidence_cap,
            "warnings": integrity_warnings,
        },
        warnings=(
            (["Same run/lap comparison — reference only. Import a second .ibt to compare."] if is_same else [])
            + list(pace.confidence_notes)
            + integrity_warnings
            + [non_authority_warning]
        ),
        confidence_score=min(observation.confidence_score, integrity_confidence_cap),
    )
    return {**summary.as_dict(), "compare_identity": compare_identity}


@router.get("/preview")
def compare_preview(baseline_run_id: str, test_run_id: str) -> ComparePreviewResponse:
    repo = repository()
    bl = repo.get_overview(baseline_run_id)
    t = repo.get_overview(test_run_id)
    if bl is None or t is None:
        raise HTTPException(404, "One or both runs not found.")
    _assert_independent_compare_recordings(baseline_run_id, test_run_id, repo)

    bl_setup = repo.get_setup_snapshot(baseline_run_id)
    t_setup = repo.get_setup_snapshot(test_run_id)
    setup_changes = diff_setups(bl_setup, t_setup)
    context_changes = diff_context(bl.session, t.session)
    baseline_coverage = setup_control_coverage(bl_setup)
    test_coverage = setup_control_coverage(t_setup)
    warnings: list[str] = []
    if baseline_coverage[0] < baseline_coverage[1]:
        warnings.append(f"Baseline setup coverage is {baseline_coverage[0]}/{baseline_coverage[1]} controls.")
    if test_coverage[0] < test_coverage[1]:
        warnings.append(f"Test setup coverage is {test_coverage[0]}/{test_coverage[1]} controls.")

    return ComparePreviewResponse(
        baseline_laps=[lap.lap_number for lap in eligible_laps(bl.laps)],
        test_laps=[lap.lap_number for lap in eligible_laps(t.laps)],
        suggested_baseline_lap=bl.best_useful_lap.lap_number if bl.best_useful_lap else None,
        suggested_test_lap=t.best_useful_lap.lap_number if t.best_useful_lap else None,
        setup_changes=[{"setup_key": c.setup_key, "label": c.label, "group": c.group,
                         "baseline_value": c.baseline_value, "test_value": c.test_value,
                         "unit": c.unit, "delta": c.delta, "significance": c.significance,
                         "magnitude_basis": c.magnitude_basis,
                         "relative_delta_percent": c.relative_delta_percent,
                         "related_to_target_issue": c.related_to_target_issue} for c in setup_changes],
        context_changes=[{"key": c.key, "label": c.label, "baseline_value": c.baseline_value,
                          "test_value": c.test_value, "warning": c.warning,
                          "is_problem": c.is_problem} for c in context_changes],
        warnings=warnings,
        compare_identity=_compare_identity(
            CompareRequest(baseline_run_id=baseline_run_id, test_run_id=test_run_id),
            repo,
            bl.best_useful_lap.lap_number if bl.best_useful_lap else None,
            t.best_useful_lap.lap_number if t.best_useful_lap else None,
        ),
    )


@router.post("/delta-traces")
def get_delta_traces(req: DeltaTraceRequest) -> dict:
    """Return per-channel baseline, test, and delta traces on a shared lap-percent grid."""
    _validate_zone(req.start_pct, req.end_pct, label="Trace range")
    _validate_zone(req.target_zone_start_pct, req.target_zone_end_pct)
    if not 0.01 <= req.step_pct <= 10.0:
        raise HTTPException(400, "Trace step must be between 0.01 and 10 percentage points.")
    repo = repository()
    bl_overview = repo.get_overview(req.baseline_run_id)
    t_overview = repo.get_overview(req.test_run_id)
    if bl_overview is None:
        raise HTTPException(404, f"Baseline run not found: {req.baseline_run_id}")
    if t_overview is None:
        raise HTTPException(404, f"Test run not found: {req.test_run_id}")
    _assert_run_compatibility(req.baseline_run_id, req.test_run_id)
    _assert_independent_compare_recordings(
        req.baseline_run_id, req.test_run_id, repo
    )

    bl_lap = _resolve_eligible_lap(bl_overview, req.baseline_lap, "baseline")
    t_lap = _resolve_eligible_lap(t_overview, req.test_lap, "test")

    # Block same-run comparison
    if req.baseline_run_id == req.test_run_id and bl_lap == t_lap:
        raise HTTPException(400, "Same run and lap compared. Select a different test run or lap.")

    trace_channels = list(dict.fromkeys([*(req.channels or DEFAULT_DELTA_CHANNELS), req.x_axis]))
    bl_rows = _load_compare_rows(req.baseline_run_id, bl_lap, trace_channels)
    t_rows = _load_compare_rows(req.test_run_id, t_lap, trace_channels)

    if not bl_rows:
        raise HTTPException(400, f"Baseline lap {bl_lap} has no telemetry data.")
    if not t_rows:
        raise HTTPException(400, f"Test lap {t_lap} has no telemetry data.")

    result = compute_delta_traces(
        bl_rows, t_rows,
        channels=req.channels,
        x_axis=req.x_axis,
        start_pct=req.start_pct,
        end_pct=req.end_pct,
        step_pct=req.step_pct,
        target_zone_start_pct=req.target_zone_start_pct,
        target_zone_end_pct=req.target_zone_end_pct,
    )

    return DeltaTraceResponse(
        baseline_run_id=req.baseline_run_id,
        test_run_id=req.test_run_id,
        baseline_lap=bl_lap,
        test_lap=t_lap,
        x_axis=result.x_axis,
        x_unit=result.x_unit,
        x_values=result.x_values,
        lap_pct_values=result.lap_pct_values,
        target_zone_start_pct=result.target_zone_start_pct,
        target_zone_end_pct=result.target_zone_end_pct,
        channels=result.channels,
        warnings=result.warnings,
        missing_channels=result.missing_channels,
    ).as_dict()


@router.post("/time-analysis")
def get_time_analysis(req: TimeAnalysisRequest) -> dict:
    """Return phase-aware cumulative time at matched physical track positions.

    Percentage bins remain the storage index.  The response includes the local
    geometry/curvature/road-profile evidence, uncertainty, and explicit gaps so
    consumers cannot draw a continuous line across unavailable coverage.
    Repeatability statistics use eligible laps as experiments, never 60 Hz rows.
    """
    _validate_zone(req.start_pct, req.end_pct, label="Time-analysis range")
    if not 0.02 <= req.step_pct <= 2.0:
        raise HTTPException(400, "Time-analysis step must be between 0.02 and 2 percentage points.")
    repo = repository()
    baseline_overview = repo.get_overview(req.baseline_run_id)
    test_overview = repo.get_overview(req.test_run_id)
    if baseline_overview is None:
        raise HTTPException(404, f"Baseline run not found: {req.baseline_run_id}")
    if test_overview is None:
        raise HTTPException(404, f"Test run not found: {req.test_run_id}")
    missing_identity = _assert_run_compatibility(req.baseline_run_id, req.test_run_id)
    if missing_identity:
        raise HTTPException(
            400,
            "Time analysis requires complete compatibility identity; missing "
            + ", ".join(missing_identity)
            + ". Reimport both runs.",
        )
    _assert_independent_compare_recordings(
        req.baseline_run_id, req.test_run_id, repo
    )
    baseline_lap = _resolve_eligible_lap(baseline_overview, req.baseline_lap, "baseline")
    test_lap = _resolve_eligible_lap(test_overview, req.test_lap, "test")
    if req.baseline_run_id == req.test_run_id and baseline_lap == test_lap:
        raise HTTPException(400, "Same run and lap compared. Select a different test run or lap.")

    baseline_rows = _load_compare_rows(req.baseline_run_id, baseline_lap, _TIME_ALIGNMENT_CHANNELS)
    test_rows = _load_compare_rows(req.test_run_id, test_lap, _TIME_ALIGNMENT_CHANNELS)
    if not baseline_rows:
        raise HTTPException(400, f"Baseline lap {baseline_lap} has no telemetry data.")
    if not test_rows:
        raise HTTPException(400, f"Test lap {test_lap} has no telemetry data.")

    baseline_manifest = read_telemetry_manifest(req.baseline_run_id)
    test_manifest = read_telemetry_manifest(req.test_run_id)
    baseline_identity = baseline_manifest.get("compatibility_identity") or {}
    test_identity = test_manifest.get("compatibility_identity") or {}
    baseline_setup = repo.get_setup_snapshot(req.baseline_run_id)
    test_setup = repo.get_setup_snapshot(req.test_run_id)
    time_setup_changes = diff_setups(baseline_setup, test_setup)
    time_unmapped_changes = unmapped_setup_change_paths(
        baseline_setup,
        test_setup,
        time_setup_changes,
    )
    baseline_lap_rows = _eligible_time_lap_rows(req.baseline_run_id, baseline_overview)
    test_lap_rows = _eligible_time_lap_rows(req.test_run_id, test_overview)
    baseline_cohort_rows = [row for lap_rows in baseline_lap_rows for row in lap_rows] or baseline_rows
    test_cohort_rows = [row for lap_rows in test_lap_rows for row in lap_rows] or test_rows
    noise_context_key = {
        "baseline_driver_identity": baseline_identity.get("driver_user_id") or baseline_identity.get("driver_id"),
        "test_driver_identity": test_identity.get("driver_user_id") or test_identity.get("driver_id"),
        "car": test_identity.get("car_id"),
        "car_version": test_identity.get("car_version"),
        "track": test_identity.get("track_id"),
        "track_configuration": test_identity.get("track_configuration_name"),
        "track_version": test_identity.get("track_version"),
        "baseline_setup_fingerprint": (
            hashlib.sha256(repr(baseline_setup).encode("utf-8")).hexdigest()[:16]
            if baseline_setup is not None else None
        ),
        "test_setup_fingerprint": (
            hashlib.sha256(repr(test_setup).encode("utf-8")).hexdigest()[:16]
            if test_setup is not None else None
        ),
        "baseline_tire_age_range_m": _finite_range(
            baseline_cohort_rows,
            ("lf_tire_distance_m", "rf_tire_distance_m", "lr_tire_distance_m", "rr_tire_distance_m"),
        ),
        "test_tire_age_range_m": _finite_range(
            test_cohort_rows,
            ("lf_tire_distance_m", "rf_tire_distance_m", "lr_tire_distance_m", "rr_tire_distance_m"),
        ),
        "baseline_fuel_range": _finite_range(baseline_cohort_rows, ("fuel_level",)),
        "test_fuel_range": _finite_range(test_cohort_rows, ("fuel_level",)),
        "baseline_weather_range": {
            channel: _finite_range(baseline_cohort_rows, (channel,))
            for channel in ("air_temp", "track_temp", "wind_vel")
        },
        "test_weather_range": {
            channel: _finite_range(test_cohort_rows, (channel,))
            for channel in ("air_temp", "track_temp", "wind_vel")
        },
        "run_type": test_identity.get("session_type"),
        "phase": "per_phase",
        "controlled_setup_change_count": len(time_setup_changes),
        "unmapped_setup_changes": bool(time_unmapped_changes),
    }

    result = analyze_time_alignment(
        baseline_rows,
        test_rows,
        baseline_lap_times_s=[
            float(lap.lap_time)
            for lap in eligible_laps(baseline_overview.laps)
            if lap.lap_time is not None and math.isfinite(float(lap.lap_time))
        ],
        test_lap_times_s=[
            float(lap.lap_time)
            for lap in eligible_laps(test_overview.laps)
            if lap.lap_time is not None and math.isfinite(float(lap.lap_time))
        ],
        baseline_lap_rows=baseline_lap_rows,
        test_lap_rows=test_lap_rows,
        noise_context_key=noise_context_key,
        start_pct=req.start_pct,
        end_pct=req.end_pct,
        step_pct=req.step_pct,
    )
    return {
        "baseline_run_id": req.baseline_run_id,
        "test_run_id": req.test_run_id,
        "baseline_lap": baseline_lap,
        "test_lap": test_lap,
        **result.as_dict(),
    }


@router.post("/engineering-systems", response_model=EngineeringSystemsResponse)
def get_engineering_systems(req: TimeAnalysisRequest) -> dict:
    """Return contract-gated driver, rotation, and platform evidence systems."""
    _validate_zone(req.start_pct, req.end_pct, label="Engineering-analysis range")
    if not 0.05 <= req.step_pct <= 1.0:
        raise HTTPException(400, "Engineering-analysis step must be between 0.05 and 1 percentage point.")
    repo = repository()
    baseline_overview = repo.get_overview(req.baseline_run_id)
    test_overview = repo.get_overview(req.test_run_id)
    if baseline_overview is None:
        raise HTTPException(404, f"Baseline run not found: {req.baseline_run_id}")
    if test_overview is None:
        raise HTTPException(404, f"Test run not found: {req.test_run_id}")
    missing_identity = _assert_run_compatibility(req.baseline_run_id, req.test_run_id)
    if missing_identity:
        raise HTTPException(
            400,
            "Engineering systems require complete compatibility identity; missing "
            + ", ".join(missing_identity)
            + ". Reimport both runs.",
        )
    _assert_independent_compare_recordings(
        req.baseline_run_id, req.test_run_id, repo
    )
    baseline_lap = _resolve_eligible_lap(baseline_overview, req.baseline_lap, "baseline")
    test_lap = _resolve_eligible_lap(test_overview, req.test_lap, "test")
    if req.baseline_run_id == req.test_run_id and baseline_lap == test_lap:
        raise HTTPException(400, "Same run and lap compared. Select a different test run or lap.")

    baseline_rows = _load_compare_rows(req.baseline_run_id, baseline_lap, _PHASE_ENGINEERING_CHANNELS)
    test_rows = _load_compare_rows(req.test_run_id, test_lap, _PHASE_ENGINEERING_CHANNELS)
    if not baseline_rows or not test_rows:
        raise HTTPException(400, "One or both selected laps have no engineering telemetry data.")
    alignment = analyze_time_alignment(
        baseline_rows,
        test_rows,
        start_pct=req.start_pct,
        end_pct=req.end_pct,
        step_pct=req.step_pct,
    )
    baseline_integrity = build_sim_integrity_certificate(
        baseline_rows,
        expected_sample_rate_hz=baseline_overview.session.telemetry_rate_hz,
    )
    test_integrity = build_sim_integrity_certificate(
        test_rows,
        expected_sample_rate_hz=test_overview.session.telemetry_rate_hz,
    )
    integrity_clear, integrity_confidence_cap, integrity_warnings = comparison_integrity_gate(
        baseline_integrity,
        test_integrity,
    )
    baseline_setup = repo.get_setup_snapshot(req.baseline_run_id)
    test_setup = repo.get_setup_snapshot(req.test_run_id)
    setup_changes = diff_setups(baseline_setup, test_setup)
    setup_change_isolated = (
        setup_controls_comparable(baseline_setup, test_setup)
        and len(setup_changes) <= 1
        and not unmapped_setup_change_paths(baseline_setup, test_setup, setup_changes)
    )
    report = analyze_phase_engineering_systems(
        baseline_rows,
        test_rows,
        alignment,
        baseline_run_id=req.baseline_run_id,
        test_run_id=req.test_run_id,
        baseline_lap=baseline_lap,
        test_lap=test_lap,
        eligible_laps=True,
        # Driver and rotation analyze this selected aligned pair only. Their
        # confidence must not borrow repetition credit from unrelated summaries.
        repetitions=1,
        setup_change_isolated=setup_change_isolated,
        sim_integrity_clear=integrity_clear,
        sim_integrity_confidence_cap=integrity_confidence_cap,
        baseline_sim_integrity_status=baseline_integrity.status,
        test_sim_integrity_status=test_integrity.status,
        sim_integrity_warnings=integrity_warnings,
        baseline_platform_laps=_eligible_platform_lap_rows(req.baseline_run_id, baseline_overview),
        test_platform_laps=_eligible_platform_lap_rows(req.test_run_id, test_overview),
    )
    return report.model_dump(mode="json")


class InsightsRequest(_StrictCompareRequest):
    baseline_run_id: str
    test_run_id: str
    baseline_lap: int | None = None
    test_lap: int | None = None
    target_zone_start_pct: float = 55.0
    target_zone_end_pct: float = 70.0
    channels: list[str] | None = None


@router.post("/insights")
def get_comparison_insights(req: InsightsRequest) -> dict:
    """Run all insight engines and return combined analysis."""
    _validate_zone(req.target_zone_start_pct, req.target_zone_end_pct)
    repo = repository()
    bl_overview = repo.get_overview(req.baseline_run_id)
    t_overview = repo.get_overview(req.test_run_id)
    if bl_overview is None:
        raise HTTPException(404, f"Baseline run not found: {req.baseline_run_id}")
    if t_overview is None:
        raise HTTPException(404, f"Test run not found: {req.test_run_id}")
    compatibility_missing = _assert_run_compatibility(req.baseline_run_id, req.test_run_id)
    _assert_independent_compare_recordings(
        req.baseline_run_id, req.test_run_id, repo
    )

    bl_lap = _resolve_eligible_lap(bl_overview, req.baseline_lap, "baseline")
    t_lap = _resolve_eligible_lap(t_overview, req.test_lap, "test")

    # Block same-run
    if req.baseline_run_id == req.test_run_id and bl_lap == t_lap:
        raise HTTPException(400, "Same run and lap compared. Select a different test run or lap.")

    insight_channels = list(dict.fromkeys([*_COMPARE_READ_CHANNELS, *(req.channels or DEFAULT_DELTA_CHANNELS)]))
    bl_rows = _load_compare_rows(req.baseline_run_id, bl_lap, insight_channels)
    t_rows = _load_compare_rows(req.test_run_id, t_lap, insight_channels)

    if not bl_rows:
        raise HTTPException(400, f"Baseline lap {bl_lap} has no telemetry data.")
    if not t_rows:
        raise HTTPException(400, f"Test lap {t_lap} has no telemetry data.")

    # Gather context for confidence weighting
    bl_setup = repo.get_setup_snapshot(req.baseline_run_id)
    t_setup = repo.get_setup_snapshot(req.test_run_id)
    from racelab_engine.analysis.test_discipline import score_test_discipline
    setup_changes = diff_setups(bl_setup, t_setup)
    context_changes = diff_context(bl_overview.session, t_overview.session)
    if compatibility_missing:
        context_changes.append(ContextChange(
            key="compatibility_identity",
            label="Run compatibility identity",
            baseline_value="Missing",
            test_value="Missing",
            warning=(
                "Compatibility identity is incomplete ("
                + ", ".join(compatibility_missing)
                + "). Reimport both .ibt files before accepting setup attribution."
            ),
            is_problem=True,
        ))
    context_changes.extend(_telemetry_context_changes(bl_rows, t_rows))
    platform = aggregate_platform_stats(
        bl_rows,
        t_rows,
        req.target_zone_start_pct,
        req.target_zone_end_pct,
    )
    driver = aggregate_driver_stats(bl_rows, t_rows, req.target_zone_start_pct, req.target_zone_end_pct)
    context_changes.extend(_analysis_evidence_changes(platform, driver))
    setup_evidence_changes, unmapped_setup_changes = _setup_evidence_changes(
        bl_setup,
        t_setup,
        setup_changes,
    )
    context_changes.extend(setup_evidence_changes)
    proximity_changes, proximity_blocks_attribution, proximity_evidence = _proximity_context_changes(
        bl_rows,
        t_rows,
    )
    context_changes.extend(proximity_changes)
    cohort_changes, cohort_blocks_attribution, cohort_evidence = _pace_cohort_proximity_changes(
        req.baseline_run_id,
        req.test_run_id,
        bl_overview,
        t_overview,
        bl_lap,
        t_lap,
        bl_rows,
        t_rows,
    )
    context_changes.extend(cohort_changes)
    context_blocks_attribution = bool(any(change.is_problem for change in context_changes))
    context_evidence = _context_evidence(
        context_changes,
        [*proximity_evidence, *cohort_evidence],
    )
    context_problems = sum(c.is_problem for c in context_changes)
    discipline = score_test_discipline(
        setup_changes,
        context_problems,
        setup_data_available=(
            setup_controls_comparable(bl_setup, t_setup)
            and not unmapped_setup_changes
        ),
    )

    # Get the base observation
    from racelab_engine.analysis.comparison import compare_target_zone
    target_zone = compare_target_zone(bl_rows, t_rows, req.target_zone_start_pct, req.target_zone_end_pct)
    from racelab_engine.analysis.did_it_work import compute_observation
    pace = build_pace_comparison(bl_overview.laps, t_overview.laps, bl_lap, t_lap)
    observation = compute_observation(
        target_zone,
        discipline,
        pace=pace,
        driver_changed=driver.driver_verdict == "changed",
        driver_evidence_available=driver.driver_verdict != "unavailable",
        context_blocks_attribution=context_blocks_attribution,
        context_evidence=context_evidence,
    )

    comparison_id = _make_comparison_id(req.baseline_run_id, req.test_run_id, bl_lap, t_lap)

    insights = build_comparison_insights(
        comparison_id=comparison_id,
        baseline_run_id=req.baseline_run_id,
        test_run_id=req.test_run_id,
        baseline_lap=bl_lap,
        test_lap=t_lap,
        baseline_rows=bl_rows,
        test_rows=t_rows,
        target_zone_start_pct=req.target_zone_start_pct,
        target_zone_end_pct=req.target_zone_end_pct,
        discipline_label=discipline.label,
        discipline_score=discipline.score,
        context_problems=context_problems,
        observation_state=observation.observation_state,
        base_confidence=observation.confidence_score,
        channels=req.channels,
        causal_attribution_blocked=context_blocks_attribution,
        causal_block_reason=(
            "Uncontrolled or missing comparison context prevents crediting the observed change to the setup."
            if context_blocks_attribution
            else None
        ),
        causal_block_reasons=context_evidence if context_blocks_attribution else None,
    )
    return insights.as_dict()
