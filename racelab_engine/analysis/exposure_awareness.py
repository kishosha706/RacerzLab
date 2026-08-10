"""Observation-only whole-car response and exposure analysis for P20."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import math
from statistics import median
from typing import Any

import polars as pl

from racelab_engine.models.engineering_awareness import (
    DerivedMetricContract,
    MetricProvenance,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.exposure_awareness import (
    BrakePressureVelocityExposureDescriptor,
    ChassisResponseDescriptor,
    CombinedAccelerationOccupancyDescriptor,
    CornerValue,
    ExposureAnalysisResult,
    RelativeSlipExposureDescriptor,
    TireThermalCornerResponse,
    TireThermalResponseDescriptor,
    TrackDisturbanceSignature,
)
from racelab_engine.models.lap_engineering_context import ChannelUpdateSemantic
from racelab_engine.models.transient_awareness import ExactAnalysisWindow
from racelab_engine.models.vehicle_engineering_profile import VehicleEngineeringProfile


_PRODUCER = "p20.exposure_awareness"
_MODULE = "racelab_engine.analysis.exposure_awareness"
_CORNERS = ("lf", "rf", "lr", "rr")
_VALID_PHASES = (
    "straight",
    "following_straight_carry",
    "brake_application",
    "threshold_braking",
    "brake_release",
    "turn_in",
    "entry",
    "center",
    "apex_region",
    "initial_throttle",
    "full_throttle_exit",
    "bump_curb",
    "lift",
    "transition",
)


def _contract(
    key: str,
    version: str,
    label: str,
    state: EvidenceState,
    required: tuple[str, ...],
    allowed: tuple[str, ...],
    forbidden: tuple[str, ...],
    description: str,
    *,
    profile: tuple[str, ...] = (),
    repetitions: int = 1,
) -> DerivedMetricContract:
    return DerivedMetricContract(
        metric_key=key,
        formula_version=version,
        label=label,
        evidence_state=state,
        required_channels=required,
        preferred_channels=(),
        allowed_channel_semantics=(ChannelUpdateSemantic.CONTINUOUS,),
        required_vehicle_profile_fields=profile,
        valid_phases=_VALID_PHASES,
        hard_blockers=(
            "junk_or_ineligible_lap",
            "unhealthy_sample_clock",
            "insufficient_window_coverage",
            "missing_required_channel",
        ),
        minimum_sample_coverage=0.9,
        minimum_repetitions=repetitions,
        allowed_outputs=allowed,
        forbidden_claims=forbidden,
        authority_ceiling="observation_only",
        description=description,
        provenance=MetricProvenance(
            producer_id=_PRODUCER,
            source_module=_MODULE,
            source_contract_ids=("p19.exact_physical_position", "p19.lap_eligibility"),
            reference_ids=(f"p20_request.{key}",),
        ),
    )


CHASSIS_RESPONSE_CONTRACT = _contract(
    "chassis_response_matrix",
    "p20.chassis_response.v1",
    "Chassis response matrix",
    EvidenceState.ESTIMATED_PROXY,
    (
        "session_time",
        "lap_dist_pct_100",
        "lat_accel",
        "long_accel",
        "lf_ride_height_mm",
        "rf_ride_height_mm",
        "lr_ride_height_mm",
        "rr_ride_height_mm",
        "lf_shock_vel_in_s",
        "rf_shock_vel_in_s",
        "lr_shock_vel_in_s",
        "rr_shock_vel_in_s",
    ),
    (
        "front_roll_motion_response_proxy",
        "rear_roll_motion_response_proxy",
        "pitch_motion_response_proxy",
        "diagonal_motion_proxy",
        "shock_abs_velocity_distribution",
    ),
    (
        "load_transfer",
        "wheel_load",
        "dynamic_crossweight",
        "spring_force",
        "arb_force",
        "tire_force",
    ),
    "Ride-height and shock-motion response descriptors; they are not wheel-load or force estimates.",
)

RELATIVE_SLIP_EXPOSURE_CONTRACT = _contract(
    "relative_slip_distance_exposure",
    "p20.relative_slip_distance.v1",
    "Relative slip-distance exposure",
    EvidenceState.ESTIMATED_PROXY,
    (
        "session_time",
        "lap_dist_pct_100",
        "speed_mps",
        "LFspeed",
        "RFspeed",
        "LRspeed",
        "RRspeed",
    ),
    ("relative_slip_distance_by_corner", "geometry_basis"),
    (
        "tire_force",
        "grip",
        "friction_coefficient",
        "tire_wear",
        "tire_energy",
        "power_loss",
    ),
    "Time-integral of absolute expected-versus-observed wheel-speed difference; not tire force or grip.",
)

BRAKE_EXPOSURE_CONTRACT = _contract(
    "brake_pressure_velocity_exposure",
    "p20.brake_pressure_velocity.v1",
    "Brake pressure-velocity exposure",
    EvidenceState.ESTIMATED_PROXY,
    (
        "session_time",
        "lap_dist_pct_100",
        "lf_brake_line_pressure_bar",
        "rf_brake_line_pressure_bar",
        "lr_brake_line_pressure_bar",
        "rr_brake_line_pressure_bar",
        "LFspeed",
        "RFspeed",
        "LRspeed",
        "RRspeed",
    ),
    (
        "pressure_velocity_exposure_by_corner",
        "front_exposure_fraction",
        "abs_intervention_fraction",
    ),
    (
        "brake_torque",
        "brake_force",
        "brake_energy",
        "rotor_temperature",
        "pad_friction",
    ),
    "Integrated line-pressure times absolute wheel velocity; no brake hardware constants are inferred.",
)

TIRE_THERMAL_RESPONSE_CONTRACT = _contract(
    "tire_thermal_response",
    "p20.tire_thermal_response.v1",
    "Tire thermal response episodes",
    EvidenceState.OBSERVED_CORRELATION,
    (
        "session_time",
        "lap_dist_pct_100",
        "lf_temp_inner",
        "lf_temp_middle",
        "lf_temp_outer",
    ),
    (
        "surface_temperature_change",
        "running_pressure_change",
        "tire_distance_change",
        "surface_gradient_change",
        "associated_exposure_artifact_ids",
    ),
    (
        "thermal_energy",
        "heat_flux",
        "friction_coefficient",
        "optimum_pressure",
        "safe_threshold",
        "live_snapshot_trend",
    ),
    "Continuous tire surface, pressure, and distance response only; snapshots are retained as excluded context.",
)

COMBINED_ACCELERATION_CONTRACT = _contract(
    "observed_combined_acceleration_occupancy",
    "p20.combined_acceleration.v1",
    "Observed combined-acceleration occupancy",
    EvidenceState.CALCULATED,
    ("session_time", "lap_dist_pct_100", "lat_accel", "long_accel"),
    (
        "lateral_abs_p95",
        "longitudinal_abs_p95",
        "combined_magnitude_p50",
        "combined_magnitude_p95",
    ),
    (
        "friction_circle",
        "grip_utilization",
        "friction_coefficient",
        "available_grip",
        "banking_compensated_acceleration",
    ),
    "Observed body-axis acceleration occupancy with gravity and banking explicitly uncompensated.",
)

TRACK_DISTURBANCE_CONTRACT = _contract(
    "track_disturbance_signature",
    "p20.track_disturbance.v1",
    "Track disturbance signature",
    EvidenceState.OBSERVED_CORRELATION,
    (
        "session_time",
        "lap_dist_pct_100",
        "vert_accel",
        "lf_shock_vel_in_s",
        "rf_shock_vel_in_s",
        "lr_shock_vel_in_s",
        "rr_shock_vel_in_s",
        "lf_ride_height_mm",
        "rf_ride_height_mm",
        "lr_ride_height_mm",
        "rr_ride_height_mm",
    ),
    (
        "first_affected_corner",
        "corner_response_sequence",
        "vertical_response",
        "ride_height_response",
        "oscillation_count",
        "settling_time",
        "repeat_count",
        "separated_observations",
    ),
    (
        "track_surface_cause",
        "damper_setup_recommendation",
        "damper_regime",
        "wheel_load",
        "setup_cause",
    ),
    "Repeatable position-locked disturbance observation with track, vehicle, driver, and consequence kept separate.",
    repetitions=2,
)


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[int(round((len(ordered) - 1) * fraction))]


def _scope_rows(
    data: pl.DataFrame | Sequence[Mapping[str, Any]],
    window: ExactAnalysisWindow,
    columns: Sequence[str],
) -> list[dict[str, Any]]:
    names = tuple(
        dict.fromkeys(
            (
                "run_id",
                "lap",
                "lap_number",
                "session_time",
                "lap_dist_pct_100",
                *columns,
            )
        )
    )
    if isinstance(data, pl.DataFrame):
        frame = data.select([name for name in names if name in data.columns])
        lap_key = (
            "lap"
            if "lap" in frame.columns
            else "lap_number"
            if "lap_number" in frame.columns
            else None
        )
        if lap_key:
            frame = frame.filter(
                pl.col(lap_key).cast(pl.Int64, strict=False) == window.lap_number
            )
        if "lap_dist_pct_100" in frame.columns:
            frame = frame.filter(
                pl.col("lap_dist_pct_100").is_between(
                    window.lap_pct_start, window.lap_pct_end, closed="both"
                )
            )
        if "session_time" in frame.columns:
            frame = frame.filter(
                pl.col("session_time").is_between(
                    window.session_time_start, window.session_time_end, closed="both"
                )
            )
        rows = frame.to_dicts()
    else:
        rows = []
        for row in data:
            lap = _finite(row.get("lap", row.get("lap_number")))
            pct, time = (
                _finite(row.get("lap_dist_pct_100")),
                _finite(row.get("session_time")),
            )
            if (
                lap == window.lap_number
                and pct is not None
                and time is not None
                and window.lap_pct_start <= pct <= window.lap_pct_end
                and window.session_time_start <= time <= window.session_time_end
            ):
                rows.append({name: row.get(name) for name in names if name in row})
    return sorted(rows, key=lambda row: _finite(row.get("session_time")) or 0.0)


def _series(rows: Sequence[Mapping[str, Any]], channel: str) -> list[float] | None:
    values = [_finite(row.get(channel)) for row in rows]
    return (
        None
        if not values or any(value is None for value in values)
        else [float(value) for value in values if value is not None]
    )


def _blockers(
    rows: Sequence[Mapping[str, Any]],
    window: ExactAnalysisWindow,
    lap_eligible: bool,
    required: Sequence[str],
    expected_rate: float,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not lap_eligible:
        blockers.append("The selected lap is not canonically eligible.")
    times = _series(rows, "session_time")
    if (
        times is None
        or len(times) < 3
        or any(right <= left for left, right in zip(times, times[1:]))
    ):
        blockers.append("The exact window requires a healthy monotonic sample clock.")
    expected = max(
        1,
        int(
            math.floor(
                max(0.0, window.session_time_end - window.session_time_start)
                * expected_rate
            )
        )
        + 1,
    )
    if len(rows) / expected < 0.9:
        blockers.append("The exact window has less than 90% expected sample coverage.")
    for channel in required:
        if _series(rows, channel) is None:
            blockers.append(
                f"Continuous channel {channel} is required in the exact window."
            )
    if any(
        str(row.get("run_id")) != window.run_id
        for row in rows
        if row.get("run_id") is not None
    ):
        blockers.append("A telemetry sample belongs to a different run.")
    return tuple(dict.fromkeys(blockers))


def _identity(prefix: str, window: ExactAnalysisWindow, version: str) -> str:
    raw = f"{window.model_dump_json()}|{version}"
    return f"{prefix}:" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def _delta_median(values: Sequence[float]) -> float:
    count = max(1, len(values) // 3)
    return float(median(values[-count:]) - median(values[:count]))


def analyze_chassis_response(
    data: pl.DataFrame | Sequence[Mapping[str, Any]],
    *,
    window: ExactAnalysisWindow,
    lap_eligible: bool,
    profile: VehicleEngineeringProfile | None = None,
    expected_sample_rate_hz: float = 60.0,
) -> ExposureAnalysisResult:
    contract = CHASSIS_RESPONSE_CONTRACT
    rows = _scope_rows(data, window, contract.required_channels)
    blockers = _blockers(
        rows, window, lap_eligible, contract.required_channels, expected_sample_rate_hz
    )
    if blockers:
        return ExposureAnalysisResult(
            status="blocked",
            metric_key=contract.metric_key,
            contract=contract,
            blocker_reasons=blockers,
        )
    values = {channel: _series(rows, channel) for channel in contract.required_channels}
    assert all(item is not None for item in values.values())
    lat_delta, long_delta = (
        _delta_median(values["lat_accel"]),
        _delta_median(values["long_accel"]),
    )
    front_split = [
        rf - lf
        for lf, rf in zip(values["lf_ride_height_mm"], values["rf_ride_height_mm"])
    ]
    rear_split = [
        rr - lr
        for lr, rr in zip(values["lr_ride_height_mm"], values["rr_ride_height_mm"])
    ]
    pitch = [
        (lf + rf) / 2.0 - (lr + rr) / 2.0
        for lf, rf, lr, rr in zip(
            values["lf_ride_height_mm"],
            values["rf_ride_height_mm"],
            values["lr_ride_height_mm"],
            values["rr_ride_height_mm"],
        )
    ]
    shock = {corner: values[f"{corner}_shock_vel_in_s"] for corner in _CORNERS}
    profile_ok = bool(
        profile and profile.shock_sign_convention and profile.damper_diagnostic_bands
    )
    artifact = ChassisResponseDescriptor(
        artifact_id=_identity("chassis", window, contract.formula_version),
        formula_version=contract.formula_version,
        window=window,
        front_roll_motion_response_proxy=_delta_median(front_split) / lat_delta
        if abs(lat_delta) > 1e-9
        else None,
        rear_roll_motion_response_proxy=_delta_median(rear_split) / lat_delta
        if abs(lat_delta) > 1e-9
        else None,
        pitch_motion_response_proxy=_delta_median(pitch) / long_delta
        if abs(long_delta) > 1e-9
        else None,
        diagonal_motion_proxy=_delta_median(
            [
                rf + lr - lf - rr
                for lf, rf, lr, rr in zip(
                    values["lf_ride_height_mm"],
                    values["rf_ride_height_mm"],
                    values["lr_ride_height_mm"],
                    values["rr_ride_height_mm"],
                )
            ]
        ),
        shock_abs_velocity_p50_by_corner=tuple(
            CornerValue(
                corner=corner, value=_percentile([abs(v) for v in shock[corner]], 0.5)
            )
            for corner in _CORNERS
        ),
        shock_abs_velocity_p95_by_corner=tuple(
            CornerValue(
                corner=corner, value=_percentile([abs(v) for v in shock[corner]], 0.95)
            )
            for corner in _CORNERS
        ),
        damper_band_classification_available=profile_ok,
        vehicle_profile_id=profile.profile_id if profile_ok else None,
        vehicle_profile_hash=profile.profile_hash if profile_ok else None,
        sample_count=len(rows),
        sample_coverage=min(
            1.0,
            len(rows)
            / max(
                1,
                int(
                    (window.session_time_end - window.session_time_start)
                    * expected_sample_rate_hz
                )
                + 1,
            ),
        ),
    )
    limitations = (
        ()
        if profile_ok
        else (
            "No source-backed damper bands and shock sign convention are available; only descriptive shock-velocity distributions are exposed.",
        )
    )
    return ExposureAnalysisResult(
        status="limited" if limitations else "ready",
        metric_key=contract.metric_key,
        contract=contract,
        artifact=artifact,
        blocker_reasons=limitations,
    )


def _integrate(values: Sequence[float], times: Sequence[float]) -> float:
    return sum(
        (abs(left) + abs(right)) * 0.5 * (t1 - t0)
        for left, right, t0, t1 in zip(values, values[1:], times, times[1:])
    )


def analyze_relative_slip_exposure(
    data: pl.DataFrame | Sequence[Mapping[str, Any]],
    *,
    window: ExactAnalysisWindow,
    lap_eligible: bool,
    profile: VehicleEngineeringProfile | None = None,
    expected_sample_rate_hz: float = 60.0,
) -> ExposureAnalysisResult:
    contract = RELATIVE_SLIP_EXPOSURE_CONTRACT
    required = list(contract.required_channels)
    corner_phase = window.phase not in {"straight", "following_straight_carry"}
    if corner_phase:
        required.append("yaw_rate")
    rows = _scope_rows(data, window, required)
    blockers = list(
        _blockers(rows, window, lap_eligible, required, expected_sample_rate_hz)
    )
    geometry_ok = bool(
        profile
        and profile.front_track_width_m
        and profile.rear_track_width_m
        and profile.wheel_speed_semantics
        and profile.body_axis_convention
    )
    if corner_phase and not geometry_ok:
        blockers.append(
            "Corner slip-distance exposure requires verified track widths, wheel-speed semantics, and body-axis convention."
        )
    if blockers:
        return ExposureAnalysisResult(
            status="blocked",
            metric_key=contract.metric_key,
            contract=contract,
            blocker_reasons=tuple(dict.fromkeys(blockers)),
        )
    times, speed = _series(rows, "session_time"), _series(rows, "speed_mps")
    assert times is not None and speed is not None
    yaw = _series(rows, "yaw_rate") if corner_phase else [0.0] * len(rows)
    assert yaw is not None
    widths = {
        "lf": profile.front_track_width_m if profile else 0.0,
        "rf": profile.front_track_width_m if profile else 0.0,
        "lr": profile.rear_track_width_m if profile else 0.0,
        "rr": profile.rear_track_width_m if profile else 0.0,
    }
    signs = {"lf": -1.0, "lr": -1.0, "rf": 1.0, "rr": 1.0}
    exposures = []
    for corner, raw in zip(_CORNERS, ("LFspeed", "RFspeed", "LRspeed", "RRspeed")):
        observed = _series(rows, raw)
        assert observed is not None
        expected = [
            v + signs[corner] * r * float(widths[corner] or 0.0) / 2.0
            for v, r in zip(speed, yaw)
        ]
        exposures.append(
            CornerValue(
                corner=corner,
                value=_integrate(
                    [obs - exp for obs, exp in zip(observed, expected)], times
                ),
            )
        )
    artifact = RelativeSlipExposureDescriptor(
        artifact_id=_identity("slip", window, contract.formula_version),
        formula_version=contract.formula_version,
        window=window,
        geometry_basis="verified_vehicle_profile" if corner_phase else "straight_line",
        exposure_m_by_corner=tuple(exposures),
        vehicle_profile_id=profile.profile_id if corner_phase and profile else None,
        vehicle_profile_hash=profile.profile_hash if corner_phase and profile else None,
        sample_count=len(rows),
    )
    return ExposureAnalysisResult(
        status="ready",
        metric_key=contract.metric_key,
        contract=contract,
        artifact=artifact,
    )


def analyze_brake_pressure_velocity_exposure(
    data: pl.DataFrame | Sequence[Mapping[str, Any]],
    *,
    window: ExactAnalysisWindow,
    lap_eligible: bool,
    expected_sample_rate_hz: float = 60.0,
) -> ExposureAnalysisResult:
    contract = BRAKE_EXPOSURE_CONTRACT
    rows = _scope_rows(data, window, (*contract.required_channels, "abs_active"))
    blockers = _blockers(
        rows, window, lap_eligible, contract.required_channels, expected_sample_rate_hz
    )
    if blockers:
        return ExposureAnalysisResult(
            status="blocked",
            metric_key=contract.metric_key,
            contract=contract,
            blocker_reasons=blockers,
        )
    times = _series(rows, "session_time")
    assert times is not None
    exposures: list[CornerValue] = []
    for corner, wheel in zip(_CORNERS, ("LFspeed", "RFspeed", "LRspeed", "RRspeed")):
        pressure, velocity = (
            _series(rows, f"{corner}_brake_line_pressure_bar"),
            _series(rows, wheel),
        )
        assert pressure is not None and velocity is not None
        exposures.append(
            CornerValue(
                corner=corner,
                value=_integrate(
                    [max(0.0, p) * abs(v) for p, v in zip(pressure, velocity)], times
                ),
            )
        )
    total = sum(item.value for item in exposures)
    abs_values = [_finite(row.get("abs_active")) for row in rows]
    abs_fraction = (
        None
        if all(value is None for value in abs_values)
        else sum(bool(value) for value in abs_values if value is not None)
        / sum(value is not None for value in abs_values)
    )
    artifact = BrakePressureVelocityExposureDescriptor(
        artifact_id=_identity("brake-exposure", window, contract.formula_version),
        formula_version=contract.formula_version,
        window=window,
        exposure_bar_m_by_corner=tuple(exposures),
        front_exposure_fraction=(
            sum(item.value for item in exposures[:2]) / total if total > 0 else None
        ),
        abs_intervention_fraction=abs_fraction,
        sample_count=len(rows),
    )
    return ExposureAnalysisResult(
        status="ready",
        metric_key=contract.metric_key,
        contract=contract,
        artifact=artifact,
    )


def analyze_tire_thermal_response(
    data: pl.DataFrame | Sequence[Mapping[str, Any]],
    *,
    window: ExactAnalysisWindow,
    lap_eligible: bool,
    channel_semantics: Mapping[str, ChannelUpdateSemantic],
    associated_slip_artifact_ids: Sequence[str] = (),
    associated_brake_artifact_ids: Sequence[str] = (),
    expected_sample_rate_hz: float = 60.0,
) -> ExposureAnalysisResult:
    contract = TIRE_THERMAL_RESPONSE_CONTRACT
    candidates = tuple(
        f"{corner}_{suffix}"
        for corner in _CORNERS
        for suffix in (
            "temp_inner",
            "temp_middle",
            "temp_outer",
            "pressure",
            "tire_distance_m",
            "carcass_temp_l",
            "wear_inner",
        )
    )
    continuous = tuple(
        channel
        for channel in candidates
        if channel_semantics.get(channel) is ChannelUpdateSemantic.CONTINUOUS
    )
    excluded = tuple(
        channel
        for channel in candidates
        if channel_semantics.get(channel)
        in {ChannelUpdateSemantic.PIT_SNAPSHOT, ChannelUpdateSemantic.CONSTANT}
    )
    rows = _scope_rows(data, window, continuous)
    blockers = list(
        _blockers(
            rows,
            window,
            lap_eligible,
            ("session_time", "lap_dist_pct_100"),
            expected_sample_rate_hz,
        )
    )
    surface = tuple(
        channel
        for channel in continuous
        if "temp_" in channel and "carcass" not in channel
    )
    if not surface:
        blockers.append(
            "No continuously updating tire surface-temperature channels are available."
        )
    if blockers:
        return ExposureAnalysisResult(
            status="blocked",
            metric_key=contract.metric_key,
            contract=contract,
            blocker_reasons=tuple(dict.fromkeys(blockers)),
        )
    responses = []
    for corner in _CORNERS:
        temps = [
            _series(rows, f"{corner}_temp_{band}")
            for band in ("inner", "middle", "outer")
        ]
        temp_change = (
            None
            if any(values is None for values in temps)
            else median([values[-1] - values[0] for values in temps])
        )
        gradient_change = (
            None
            if any(values is None for values in temps)
            else ((temps[0][-1] - temps[2][-1]) - (temps[0][0] - temps[2][0]))
        )
        pressure, distance = (
            _series(rows, f"{corner}_pressure"),
            _series(rows, f"{corner}_tire_distance_m"),
        )
        responses.append(
            TireThermalCornerResponse(
                corner=corner,
                surface_temperature_change_c=temp_change,
                running_pressure_change=(
                    pressure[-1] - pressure[0] if pressure else None
                ),
                tire_distance_change_m=(
                    max(0.0, distance[-1] - distance[0]) if distance else None
                ),
                inner_middle_outer_gradient_change_c=gradient_change,
            )
        )
    artifact = TireThermalResponseDescriptor(
        artifact_id=_identity("thermal", window, contract.formula_version),
        formula_version=contract.formula_version,
        window=window,
        corner_responses=tuple(responses),
        continuous_source_channels=continuous,
        snapshot_channels_excluded=excluded,
        associated_slip_artifact_ids=tuple(dict.fromkeys(associated_slip_artifact_ids)),
        associated_brake_artifact_ids=tuple(
            dict.fromkeys(associated_brake_artifact_ids)
        ),
        sample_count=len(rows),
    )
    limitations = (
        (
            "Snapshot or constant tire channels were excluded from live thermal response.",
        )
        if excluded
        else ()
    )
    return ExposureAnalysisResult(
        status="limited" if limitations else "ready",
        metric_key=contract.metric_key,
        contract=contract,
        artifact=artifact,
        blocker_reasons=limitations,
    )


def analyze_combined_acceleration_occupancy(
    data: pl.DataFrame | Sequence[Mapping[str, Any]],
    *,
    window: ExactAnalysisWindow,
    lap_eligible: bool,
    expected_sample_rate_hz: float = 60.0,
) -> ExposureAnalysisResult:
    contract = COMBINED_ACCELERATION_CONTRACT
    rows = _scope_rows(data, window, contract.required_channels)
    blockers = _blockers(
        rows, window, lap_eligible, contract.required_channels, expected_sample_rate_hz
    )
    if blockers:
        return ExposureAnalysisResult(
            status="blocked",
            metric_key=contract.metric_key,
            contract=contract,
            blocker_reasons=blockers,
        )
    lateral, longitudinal = _series(rows, "lat_accel"), _series(rows, "long_accel")
    assert lateral is not None and longitudinal is not None
    combined = [math.hypot(lat, lon) for lat, lon in zip(lateral, longitudinal)]
    artifact = CombinedAccelerationOccupancyDescriptor(
        artifact_id=_identity("combined-accel", window, contract.formula_version),
        formula_version=contract.formula_version,
        window=window,
        point_count=len(rows),
        lateral_abs_p95_mps2=_percentile([abs(v) for v in lateral], 0.95),
        longitudinal_abs_p95_mps2=_percentile([abs(v) for v in longitudinal], 0.95),
        combined_magnitude_p50_mps2=_percentile(combined, 0.5),
        combined_magnitude_p95_mps2=_percentile(combined, 0.95),
    )
    return ExposureAnalysisResult(
        status="ready",
        metric_key=contract.metric_key,
        contract=contract,
        artifact=artifact,
    )


def _zero_crossings(values: Sequence[float]) -> int:
    signs = [1 if value > 0 else -1 if value < 0 else 0 for value in values]
    signs = [value for value in signs if value]
    return sum(left != right for left, right in zip(signs, signs[1:]))


def build_track_disturbance_signature(
    data_by_window: Sequence[
        tuple[ExactAnalysisWindow, pl.DataFrame | Sequence[Mapping[str, Any]]]
    ],
    *,
    lap_eligibility: Mapping[int, bool],
    track_identity: str,
    build_identity: str,
    source_artifact_ids: Sequence[str],
    expected_sample_rate_hz: float = 60.0,
    performance_consequence_s: float | None = None,
) -> ExposureAnalysisResult:
    contract = TRACK_DISTURBANCE_CONTRACT
    blockers: list[str] = []
    if len(data_by_window) < 2:
        blockers.append(
            "A disturbance signature requires at least two distinct eligible laps."
        )
    windows = [item[0] for item in data_by_window]
    if len({window.lap_number for window in windows}) != len(windows):
        blockers.append("Disturbance repetitions must cite distinct lap numbers.")
    if any(not lap_eligibility.get(window.lap_number, False) for window in windows):
        blockers.append(
            "Every disturbance repetition must be on a canonically eligible lap."
        )
    physical = {
        (window.context_id, window.phase, window.lap_pct_start, window.lap_pct_end)
        for window in windows
    }
    if len(physical) > 1:
        blockers.append(
            "Disturbance repetitions must share one exact backend physical-position window."
        )
    if len(source_artifact_ids) < len(data_by_window):
        blockers.append(
            "Each disturbance repetition requires an immutable source artifact identity."
        )
    scoped: list[list[dict[str, Any]]] = []
    for window, data in data_by_window:
        rows = _scope_rows(data, window, contract.required_channels)
        blockers.extend(
            _blockers(
                rows,
                window,
                lap_eligibility.get(window.lap_number, False),
                contract.required_channels,
                expected_sample_rate_hz,
            )
        )
        scoped.append(rows)
    if blockers:
        return ExposureAnalysisResult(
            status="blocked",
            metric_key=contract.metric_key,
            contract=contract,
            blocker_reasons=tuple(dict.fromkeys(blockers)),
        )
    peak_times: dict[str, list[float]] = {corner: [] for corner in _CORNERS}
    peak_values: dict[str, list[float]] = {corner: [] for corner in _CORNERS}
    ride_response: dict[str, list[float]] = {corner: [] for corner in _CORNERS}
    vertical: list[float] = []
    oscillations: list[int] = []
    peak_pcts: list[float] = []
    settle: list[float] = []
    for rows in scoped:
        times, pcts = _series(rows, "session_time"), _series(rows, "lap_dist_pct_100")
        vert = _series(rows, "vert_accel")
        assert times and pcts and vert
        vertical.append(max(abs(value) for value in vert))
        oscillations.append(_zero_crossings(vert))
        peak_index = max(range(len(vert)), key=lambda i: abs(vert[i]))
        peak_pcts.append(pcts[peak_index])
        threshold = max(abs(vert[peak_index]) * 0.1, 0.05)
        settle_index = next(
            (
                i
                for i in range(peak_index, len(vert))
                if all(abs(v) <= threshold for v in vert[i:])
            ),
            None,
        )
        if settle_index is not None:
            settle.append(times[settle_index] - times[peak_index])
        for corner in _CORNERS:
            shock, ride = (
                _series(rows, f"{corner}_shock_vel_in_s"),
                _series(rows, f"{corner}_ride_height_mm"),
            )
            assert shock and ride
            index = max(range(len(shock)), key=lambda i: abs(shock[i]))
            peak_times[corner].append(times[index] - times[0])
            peak_values[corner].append(abs(shock[index]))
            ride_response[corner].append(max(ride) - min(ride))
    ordered = tuple(sorted(_CORNERS, key=lambda corner: median(peak_times[corner])))
    first = ordered[0]
    base = windows[0]
    identity = f"{track_identity}|{build_identity}|{base.context_id}|{base.lap_pct_start}|{base.lap_pct_end}|{sorted(w.lap_number for w in windows)}|{contract.formula_version}"
    artifact = TrackDisturbanceSignature(
        signature_id="disturbance:"
        + hashlib.sha256(identity.encode()).hexdigest()[:24],
        formula_version=contract.formula_version,
        track_identity=track_identity,
        build_identity=build_identity,
        lap_numbers=tuple(window.lap_number for window in windows),
        lap_pct_start=base.lap_pct_start,
        lap_pct_end=base.lap_pct_end,
        lap_pct_peak=float(median(peak_pcts)),
        first_affected_corner=first,
        corner_response_sequence=ordered,
        vertical_acceleration_response_mps2=float(median(vertical)),
        shock_peak_abs_velocity_by_corner=tuple(
            CornerValue(corner=corner, value=float(median(peak_values[corner])))
            for corner in _CORNERS
        ),
        ride_height_response_by_corner=tuple(
            CornerValue(corner=corner, value=float(median(ride_response[corner])))
            for corner in _CORNERS
        ),
        oscillation_count=int(round(median(oscillations))),
        settling_time_s=float(median(settle)) if settle else None,
        repetition_count=len(windows),
        track_input_observation=(
            "Track input was not directly measured; a repeatable position lock was "
            f"observed near {median(peak_pcts):.3f}% lap distance on "
            f"{len(windows)} eligible laps."
        ),
        vehicle_response_observation=f"The earliest peak shock-velocity response was {first.upper()}, followed by {'/'.join(c.upper() for c in ordered[1:])}.",
        driver_response_observation="Driver response is not attributed without a separately cited driver-control artifact.",
        performance_consequence_observation=(
            f"The separately measured local time consequence was {performance_consequence_s:+.3f} s."
            if performance_consequence_s is not None
            else "No independently measured local time consequence was supplied."
        ),
        source_channels=contract.required_channels,
        source_artifact_ids=tuple(source_artifact_ids[: len(windows)]),
    )
    return ExposureAnalysisResult(
        status="ready",
        metric_key=contract.metric_key,
        contract=contract,
        artifact=artifact,
    )


__all__ = [
    "BRAKE_EXPOSURE_CONTRACT",
    "CHASSIS_RESPONSE_CONTRACT",
    "COMBINED_ACCELERATION_CONTRACT",
    "RELATIVE_SLIP_EXPOSURE_CONTRACT",
    "TIRE_THERMAL_RESPONSE_CONTRACT",
    "TRACK_DISTURBANCE_CONTRACT",
    "analyze_brake_pressure_velocity_exposure",
    "analyze_chassis_response",
    "analyze_combined_acceleration_occupancy",
    "analyze_relative_slip_exposure",
    "analyze_tire_thermal_response",
    "build_track_disturbance_signature",
]
