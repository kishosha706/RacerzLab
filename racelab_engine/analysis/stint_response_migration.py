"""Qualified, observation-only lap-progression response signatures.

This producer compares consecutive eligible laps on one immutable physical
position grid.  It deliberately does not identify a tire, cooling, component,
or setup cause.  Tire inventory, carcass temperature, and wear are read only
from explicit pit-boundary samples and are never promoted to continuous
on-track evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import math
from statistics import median
from typing import Any, Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.analysis.lap_eligibility import lap_is_eligible
from racelab_engine.analysis.qualified_clock import build_qualified_telemetry_clock
from racelab_engine.models.lap import LapSummary
from racelab_engine.recording_identity import normalize_source_sha256


_FORMULA_VERSION = "p354.stint_response_migration.v1"
_MINIMUM_TREND_LAPS = 10
_CORNERS = ("lf", "rf", "lr", "rr")
_SETUP_ID_CHANNELS = (
    "setup_snapshot_sha256",
    "setup_fingerprint_sha256",
    "setup_id",
)
_PIT_CHANNELS = (
    "on_pit_road",
    "pitstop_active",
    "player_in_pit_stall",
    "player_car_in_pit_stall",
)
_RESET_CHANNELS = (
    "enter_exit_reset_state",
    "reset_discontinuity",
    "active_reset",
    "tow_active",
)
_RECORDING_ID_CHANNELS = ("source_file_sha256", "recording_sha256")


class _MigrationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PhysicalPhaseWindow(_MigrationModel):
    """One caller-owned phase on an immutable lap-position axis."""

    scope_id: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    grid_step_pct: float = Field(default=1.0, gt=0.0, le=5.0, allow_inf_nan=False)
    max_interpolation_gap_pct: float = Field(
        default=2.0,
        gt=0.0,
        le=10.0,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def require_non_wrapping_physical_scope(self) -> PhysicalPhaseWindow:
        if self.lap_pct_end <= self.lap_pct_start:
            raise ValueError("stint-response windows must be non-wrapping physical scopes")
        if self.max_interpolation_gap_pct < self.grid_step_pct:
            raise ValueError("interpolation gap cannot be smaller than the physical grid step")
        return self


class LapPhaseResponse(_MigrationModel):
    lap_number: int = Field(ge=0)
    scope_id: str = Field(min_length=1)
    matched_position_count: int = Field(ge=2)
    phase_time_s: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    steering_demand_rms_deg: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    yaw_response_rms_rad_s: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    steering_to_yaw_gain_proxy_rad_s_per_deg: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    throttle_pickup_position_pct: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        allow_inf_nan=False,
    )
    front_clearance_min_mm: float | None = Field(default=None, allow_inf_nan=False)
    rear_clearance_min_mm: float | None = Field(default=None, allow_inf_nan=False)
    whole_platform_clearance_min_mm: float | None = Field(default=None, allow_inf_nan=False)
    clock_primary: Literal["session_tick"] = "session_tick"
    clock_state: Literal["qualified"] = "qualified"
    source_channels: tuple[str, ...] = Field(min_length=2)
    evidence_state: Literal["calculated"] = "calculated"
    authority: Literal["observation_only"] = "observation_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def require_unique_provenance_and_a_metric(self) -> LapPhaseResponse:
        if len(self.source_channels) != len(set(self.source_channels)):
            raise ValueError("lap-phase response channels must be unique")
        if all(
            value is None
            for value in (
                self.phase_time_s,
                self.steering_demand_rms_deg,
                self.yaw_response_rms_rad_s,
                self.throttle_pickup_position_pct,
                self.whole_platform_clearance_min_mm,
            )
        ):
            raise ValueError("lap-phase response requires at least one observed metric")
        return self


TrendState = Literal["observed", "blocked", "unavailable"]


class ProgressionTrend(_MigrationModel):
    metric: Literal[
        "phase_time_s",
        "steering_demand_rms_deg",
        "yaw_response_rms_rad_s",
        "steering_to_yaw_gain_proxy_rad_s_per_deg",
        "throttle_pickup_position_pct",
        "front_clearance_min_mm",
        "rear_clearance_min_mm",
        "whole_platform_clearance_min_mm",
    ]
    units: Literal["s", "deg", "rad/s", "rad/s/deg", "% lap", "mm"]
    state: TrendState
    lap_numbers: tuple[int, ...] = ()
    robust_slope_per_lap: float | None = Field(default=None, allow_inf_nan=False)
    observed_change: float | None = Field(default=None, allow_inf_nan=False)
    repeatability_residual_mad: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    above_empirical_noise: bool | None = None
    direction: Literal["increasing", "decreasing", "not_established"] = "not_established"
    source_channels: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    evidence_state: Literal["observed_correlation", "blocked_by_context", "unavailable"]
    attribution: Literal["unresolved_observational"] = "unresolved_observational"
    authority: Literal["observation_only"] = "observation_only"
    setup_authorized: Literal[False] = False
    tire_degradation_authorized: Literal[False] = False
    cooling_conclusion_authorized: Literal[False] = False

    @model_validator(mode="after")
    def trend_claims_require_long_complete_history(self) -> ProgressionTrend:
        values = (
            self.robust_slope_per_lap,
            self.observed_change,
            self.repeatability_residual_mad,
            self.above_empirical_noise,
        )
        if self.state == "observed":
            if len(self.lap_numbers) < _MINIMUM_TREND_LAPS:
                raise ValueError("observed stint migration requires ten qualified laps")
            if any(value is None for value in values):
                raise ValueError("observed stint migration requires trend and repeatability values")
            if self.evidence_state != "observed_correlation":
                raise ValueError("observed stint migration is correlation-only evidence")
            if self.blocker_reasons or not self.source_channels:
                raise ValueError("observed stint migration requires unblocked provenance")
        else:
            if any(value is not None for value in values) or self.direction != "not_established":
                raise ValueError("blocked migration cannot expose a trend result")
            if not self.blocker_reasons:
                raise ValueError("blocked migration requires explicit blockers")
        return self


class PhaseProgressionSignature(_MigrationModel):
    scope: PhysicalPhaseWindow
    physical_grid_pct: tuple[float, ...] = Field(min_length=2)
    lap_responses: tuple[LapPhaseResponse, ...] = ()
    trends: tuple[ProgressionTrend, ...] = ()
    status: Literal["ready", "limited", "blocked"]
    blocker_reasons: tuple[str, ...] = ()
    authority: Literal["observation_only"] = "observation_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def grid_and_scope_are_exact(self) -> PhaseProgressionSignature:
        if self.physical_grid_pct[0] != self.scope.lap_pct_start:
            raise ValueError("physical grid must begin at the exact scope boundary")
        if self.physical_grid_pct[-1] != self.scope.lap_pct_end:
            raise ValueError("physical grid must end at the exact scope boundary")
        if any(right <= left for left, right in zip(self.physical_grid_pct, self.physical_grid_pct[1:])):
            raise ValueError("physical grid must be strictly increasing")
        if self.status == "ready" and (not self.lap_responses or self.blocker_reasons):
            raise ValueError("ready phase signatures require responses without blockers")
        if self.status == "blocked" and not self.blocker_reasons:
            raise ValueError("blocked phase signatures require blockers")
        return self


class StintMigrationSegment(_MigrationModel):
    segment_id: str = Field(pattern=r"^stint-migration:[0-9a-f]{24}$")
    run_id: str = Field(min_length=1)
    source_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    setup_identity: str = Field(min_length=1)
    clock_epoch: int = Field(ge=0)
    lap_numbers: tuple[int, ...] = Field(min_length=1)
    phase_signatures: tuple[PhaseProgressionSignature, ...] = Field(min_length=1)
    status: Literal["ready", "limited"]
    right_censored: Literal[True] = True
    authority: Literal["observation_only"] = "observation_only"
    component_cause_authorized: Literal[False] = False
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def segment_is_consecutive_and_single_setup(self) -> StintMigrationSegment:
        if any(right != left + 1 for left, right in zip(self.lap_numbers, self.lap_numbers[1:])):
            raise ValueError("stint migration cannot bridge a lap-number boundary")
        return self


class PitTireCornerSnapshot(_MigrationModel):
    corner: Literal["lf", "rf", "lr", "rr"]
    tires_used: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    tires_available: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    running_pressure: float | None = Field(default=None, allow_inf_nan=False)
    cold_pressure: float | None = Field(default=None, allow_inf_nan=False)
    carcass_temp_l: float | None = Field(default=None, allow_inf_nan=False)
    carcass_temp_m: float | None = Field(default=None, allow_inf_nan=False)
    carcass_temp_r: float | None = Field(default=None, allow_inf_nan=False)
    wear_l: float | None = Field(default=None, allow_inf_nan=False)
    wear_m: float | None = Field(default=None, allow_inf_nan=False)
    wear_r: float | None = Field(default=None, allow_inf_nan=False)
    tire_distance_m: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    update_semantic: Literal["pit_snapshot"] = "pit_snapshot"
    continuous_on_track_authorized: Literal[False] = False
    mechanism_authorized: Literal[False] = False


class PitTireSnapshot(_MigrationModel):
    snapshot_id: str = Field(pattern=r"^pit-tire:[0-9a-f]{24}$")
    boundary: Literal["pit_entry", "pit_exit", "pit_observation"]
    lap_number: int | None = Field(default=None, ge=0)
    session_tick: int | None = Field(default=None, ge=0)
    corners: tuple[PitTireCornerSnapshot, ...] = Field(min_length=4, max_length=4)
    source_channels: tuple[str, ...] = Field(min_length=1)
    evidence_state: Literal["measured"] = "measured"
    authority: Literal["inventory_snapshot_only"] = "inventory_snapshot_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def snapshot_has_all_corners_and_unique_sources(self) -> PitTireSnapshot:
        if {item.corner for item in self.corners} != set(_CORNERS):
            raise ValueError("pit tire snapshot requires every corner exactly once")
        if len(self.source_channels) != len(set(self.source_channels)):
            raise ValueError("pit tire snapshot channels must be unique")
        return self


class StintResponseMigrationReport(_MigrationModel):
    schema_version: Literal["p354.stint-response-migration.v1"] = (
        "p354.stint-response-migration.v1"
    )
    run_id: str = Field(min_length=1)
    source_file_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    status: Literal["ready", "limited", "blocked"]
    segments: tuple[StintMigrationSegment, ...] = ()
    pit_tire_snapshots: tuple[PitTireSnapshot, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    source_channels: tuple[str, ...] = ()
    formula_version: Literal["p354.stint_response_migration.v1"] = _FORMULA_VERSION
    position_authority: Literal["lap_distance_percentage"] = "lap_distance_percentage"
    clock_contract: Literal["QualifiedTelemetryClock"] = "QualifiedTelemetryClock"
    tire_update_semantic: Literal["pit_snapshot_only"] = "pit_snapshot_only"
    authority: Literal["observation_only"] = "observation_only"
    component_cause_authorized: Literal[False] = False
    setup_authorized: Literal[False] = False
    tire_degradation_authorized: Literal[False] = False
    cooling_conclusion_authorized: Literal[False] = False

    @model_validator(mode="after")
    def report_never_claims_more_than_it_observed(self) -> StintResponseMigrationReport:
        if self.status == "blocked" and (self.segments or not self.blocker_reasons):
            raise ValueError("blocked migration reports require blockers and no stint segments")
        if self.status == "ready" and not any(item.status == "ready" for item in self.segments):
            raise ValueError("ready migration reports require a ready segment")
        if self.status == "ready" and self.blocker_reasons:
            raise ValueError("ready migration reports cannot hide skipped or boundary context")
        if len(self.source_channels) != len(set(self.source_channels)):
            raise ValueError("migration report channels must be unique")
        if self.segments and self.source_file_sha256 is None:
            raise ValueError("publishable stint segments require exact recording identity")
        if any(
            segment.source_file_sha256 != self.source_file_sha256
            for segment in self.segments
        ):
            raise ValueError("stint segments must retain the report recording identity")
        return self


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _truth(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    number = _finite(value)
    return bool(number) if number is not None else bool(value)


def _rows(data: pl.DataFrame | Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(data, pl.DataFrame):
        return data.to_dicts()
    return [dict(row) for row in data]


def _source_binding(
    rows: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    expected_run_id: str | None,
    expected_source_file_sha256: str | None,
) -> tuple[str | None, tuple[str, ...]]:
    """Require complete row labels or explicit caller-owned source bindings."""

    trusted_run_id = (
        str(expected_run_id).strip()
        if expected_run_id is not None and str(expected_run_id).strip()
        else None
    )
    if expected_run_id is not None and trusted_run_id is None:
        return None, ("The caller-owned run identity is empty.",)
    if trusted_run_id is not None and trusted_run_id != run_id:
        return None, ("The caller-owned run identity does not match the lap inventory.",)
    expected = normalize_source_sha256(expected_source_file_sha256)
    if expected_source_file_sha256 is not None and expected is None:
        return None, ("The caller-owned recording SHA-256 is invalid.",)

    row_run_ids = [
        str(row.get("run_id")).strip()
        if row.get("run_id") is not None and str(row.get("run_id")).strip()
        else None
        for row in rows
    ]
    if any(value is not None for value in row_run_ids):
        if any(value is None for value in row_run_ids):
            return None, (
                "Telemetry rows mix labeled and unlabeled run identity; exact source binding is unavailable.",
            )
        foreign = sorted({value for value in row_run_ids if value != run_id})
        if foreign:
            return None, (
                "Telemetry rows belong to a foreign run and cannot enter this stint producer.",
            )
    elif trusted_run_id is None:
        return None, (
            "Unlabeled telemetry rows require an explicit caller-owned run identity.",
        )

    row_recordings: list[str | None] = []
    for row in rows:
        raw_values = [
            row.get(channel)
            for channel in _RECORDING_ID_CHANNELS
            if row.get(channel) is not None and str(row.get(channel)).strip()
        ]
        normalized = [normalize_source_sha256(value) for value in raw_values]
        if any(value is None for value in normalized):
            return None, ("A telemetry-row recording SHA-256 is malformed.",)
        identities = {value for value in normalized if value is not None}
        if len(identities) > 1:
            return None, ("A telemetry row contains conflicting recording identities.",)
        row_recordings.append(next(iter(identities), None))
    if any(value is not None for value in row_recordings):
        if any(value is None for value in row_recordings):
            return None, (
                "Telemetry rows mix labeled and unlabeled recording identity; exact source binding is unavailable.",
            )
        observed = {value for value in row_recordings if value is not None}
        if len(observed) != 1:
            return None, ("Telemetry rows contain more than one recording identity.",)
        observed_identity = next(iter(observed))
        if expected is not None and observed_identity != expected:
            return None, (
                "Telemetry recording identity does not match the caller-owned recording.",
            )
        return observed_identity, ()
    if expected is None:
        return None, (
            "Unlabeled telemetry rows require an explicit caller-owned recording SHA-256.",
        )
    return expected, ()


def _lap_number(row: Mapping[str, Any]) -> int | None:
    value = _finite(row.get("lap", row.get("lap_number", row.get("Lap"))))
    if value is None or not math.isclose(value, round(value), abs_tol=1e-9):
        return None
    return int(round(value))


def _position_pct(row: Mapping[str, Any]) -> float | None:
    value = _finite(row.get("lap_dist_pct_100"))
    if value is None:
        value = _finite(row.get("lap_dist_pct", row.get("LapDistPct")))
        if value is not None and 0.0 <= value <= 1.5:
            value *= 100.0
    return value if value is not None and 0.0 <= value <= 100.0 else None


def _is_pit(row: Mapping[str, Any]) -> bool:
    return any(_truth(row.get(channel)) for channel in _PIT_CHANNELS)


def _is_reset(row: Mapping[str, Any]) -> bool:
    return any(_truth(row.get(channel)) for channel in _RESET_CHANNELS)


def _physical_grid(scope: PhysicalPhaseWindow) -> tuple[float, ...]:
    points = [scope.lap_pct_start]
    current = scope.lap_pct_start + scope.grid_step_pct
    while current < scope.lap_pct_end - 1e-9:
        points.append(round(current, 9))
        current += scope.grid_step_pct
    points.append(scope.lap_pct_end)
    return tuple(points)


def _interpolate(
    positions: Sequence[float],
    values: Sequence[float | None],
    targets: Sequence[float],
    *,
    max_gap: float,
) -> list[float] | None:
    paired = sorted(
        (position, value)
        for position, value in zip(positions, values)
        if math.isfinite(position) and value is not None
    )
    if len(paired) < 2:
        return None
    collapsed: list[tuple[float, float]] = []
    for position, value in paired:
        if collapsed and math.isclose(position, collapsed[-1][0], abs_tol=1e-9):
            collapsed[-1] = (position, float(median((collapsed[-1][1], value))))
        else:
            collapsed.append((position, value))
    result: list[float] = []
    for target in targets:
        exact = next(
            (value for position, value in collapsed if math.isclose(position, target, abs_tol=1e-9)),
            None,
        )
        if exact is not None:
            result.append(exact)
            continue
        bracket = next(
            (
                (left_position, left_value, right_position, right_value)
                for (left_position, left_value), (right_position, right_value) in zip(
                    collapsed,
                    collapsed[1:],
                )
                if left_position < target < right_position
            ),
            None,
        )
        if bracket is None or bracket[2] - bracket[0] > max_gap:
            return None
        left_position, left_value, right_position, right_value = bracket
        fraction = (target - left_position) / (right_position - left_position)
        result.append(left_value + fraction * (right_value - left_value))
    return result


def _channel_values(
    rows: Sequence[Mapping[str, Any]], aliases: Sequence[str]
) -> tuple[list[float | None], str | None]:
    candidates: list[tuple[int, int, str, list[float | None]]] = []
    for order, channel in enumerate(aliases):
        if not any(channel in row for row in rows):
            continue
        values = [_finite(row.get(channel)) for row in rows]
        candidates.append((sum(value is not None for value in values), -order, channel, values))
    if not candidates:
        return [None] * len(rows), None
    _coverage, _order, channel, values = max(candidates, key=lambda item: (item[0], item[1]))
    return values, channel


_METRICS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("phase_time_s", "s", ("session_tick", "SessionTick", "lap_dist_pct_100")),
    ("steering_demand_rms_deg", "deg", ("steering_deg", "SteeringWheelAngle")),
    ("yaw_response_rms_rad_s", "rad/s", ("yaw_rate", "YawRate")),
    (
        "steering_to_yaw_gain_proxy_rad_s_per_deg",
        "rad/s/deg",
        ("steering_deg", "SteeringWheelAngle", "yaw_rate", "YawRate"),
    ),
    ("throttle_pickup_position_pct", "% lap", ("throttle_pct", "Throttle")),
    (
        "front_clearance_min_mm",
        "mm",
        ("cfs_ride_height_mm", "lf_ride_height_mm", "rf_ride_height_mm"),
    ),
    ("rear_clearance_min_mm", "mm", ("lr_ride_height_mm", "rr_ride_height_mm")),
    (
        "whole_platform_clearance_min_mm",
        "mm",
        (
            "cfs_ride_height_mm",
            "lf_ride_height_mm",
            "rf_ride_height_mm",
            "lr_ride_height_mm",
            "rr_ride_height_mm",
        ),
    ),
)


def _lap_response(
    rows: Sequence[Mapping[str, Any]],
    *,
    lap_number: int,
    scope: PhysicalPhaseWindow,
    expected_sample_rate_hz: float,
) -> tuple[LapPhaseResponse | None, tuple[str, ...]]:
    clock = build_qualified_telemetry_clock(
        rows,
        expected_sample_rate_hz=expected_sample_rate_hz,
    )
    if (
        clock.clock_state != "qualified"
        or clock.primary_clock != "session_tick"
        or clock.epoch_count != 1
    ):
        return None, tuple(
            dict.fromkeys(
                (
                    f"Lap {lap_number} lacks a qualified SessionTick clock.",
                    *(f"QualifiedTelemetryClock: {reason}." for reason in clock.blockers),
                )
            )
        )
    positions = [_position_pct(row) for row in rows]
    chronological_positions = [value for value in positions if value is not None]
    if (
        len(chronological_positions) < 2
        or any(right < left for left, right in zip(chronological_positions, chronological_positions[1:]))
    ):
        return None, (f"Lap {lap_number} has non-monotonic physical-position coverage.",)
    grid = _physical_grid(scope)
    numeric_positions = [value if value is not None else math.nan for value in positions]
    sources: list[str] = [*clock.source_channels]

    def interpolated(aliases: Sequence[str]) -> tuple[list[float] | None, str | None]:
        values, channel = _channel_values(rows, aliases)
        result = _interpolate(
            numeric_positions,
            values,
            grid,
            max_gap=scope.max_interpolation_gap_pct,
        )
        if channel is not None and result is not None:
            sources.append(channel)
        return result, channel

    canonical = list(clock.canonical_elapsed_time_s)
    times = _interpolate(
        numeric_positions,
        canonical,
        grid,
        max_gap=scope.max_interpolation_gap_pct,
    )
    if times is None or times[-1] <= times[0]:
        return None, (f"Lap {lap_number} lacks canonical clock coverage across {scope.scope_id}.",)
    steering, _ = interpolated(("steering_deg", "SteeringWheelAngle"))
    if steering is not None and "steering_deg" not in sources and "SteeringWheelAngle" in sources:
        steering = [math.degrees(value) for value in steering]
    yaw, _ = interpolated(("yaw_rate", "YawRate"))
    throttle, _ = interpolated(("throttle_pct", "Throttle"))
    if throttle is not None and max(throttle, default=0.0) <= 1.5:
        throttle = [value * 100.0 for value in throttle]

    clearance_series: dict[str, list[float]] = {}
    for key, aliases in (
        ("cfs", ("cfs_ride_height_mm", "cfsr_height_mm")),
        ("lf", ("lf_ride_height_mm",)),
        ("rf", ("rf_ride_height_mm",)),
        ("lr", ("lr_ride_height_mm",)),
        ("rr", ("rr_ride_height_mm",)),
    ):
        values, _ = interpolated(aliases)
        if values is not None:
            clearance_series[key] = values

    front_values = [
        value
        for key in ("cfs", "lf", "rf")
        for value in clearance_series.get(key, ())
    ]
    rear_values = [
        value
        for key in ("lr", "rr")
        for value in clearance_series.get(key, ())
    ]
    platform_values = [value for values in clearance_series.values() for value in values]
    steering_rms = (
        math.sqrt(sum(value * value for value in steering) / len(steering))
        if steering
        else None
    )
    yaw_rms = (
        math.sqrt(sum(value * value for value in yaw) / len(yaw))
        if yaw
        else None
    )
    gain = (
        yaw_rms / steering_rms
        if yaw_rms is not None and steering_rms is not None and steering_rms > 1e-6
        else None
    )
    pickup = None
    if throttle is not None:
        pickup = next(
            (
                grid[index]
                for index in range(len(throttle) - 1)
                if throttle[index] >= 20.0 and throttle[index + 1] >= 20.0
            ),
            None,
        )
    return LapPhaseResponse(
        lap_number=lap_number,
        scope_id=scope.scope_id,
        matched_position_count=len(grid),
        phase_time_s=times[-1] - times[0],
        steering_demand_rms_deg=steering_rms,
        yaw_response_rms_rad_s=yaw_rms,
        steering_to_yaw_gain_proxy_rad_s_per_deg=gain,
        throttle_pickup_position_pct=pickup,
        front_clearance_min_mm=min(front_values) if front_values else None,
        rear_clearance_min_mm=min(rear_values) if rear_values else None,
        whole_platform_clearance_min_mm=min(platform_values) if platform_values else None,
        source_channels=tuple(dict.fromkeys((*sources, "lap_dist_pct_100"))),
    ), ()


def _theil_sen(laps: Sequence[int], values: Sequence[float]) -> tuple[float, float, float, bool]:
    slope = float(median(
        (values[right] - values[left]) / (laps[right] - laps[left])
        for left in range(len(laps))
        for right in range(left + 1, len(laps))
    ))
    intercept = float(median(value - slope * lap for lap, value in zip(laps, values)))
    residuals = [value - (intercept + slope * lap) for lap, value in zip(laps, values)]
    residual_center = float(median(residuals))
    residual_mad = float(median(abs(value - residual_center) for value in residuals))
    change = slope * (laps[-1] - laps[0])
    above_noise = abs(change) > max(2.0 * 1.4826 * residual_mad, 1e-12)
    return slope, change, residual_mad, above_noise


def _trends(responses: Sequence[LapPhaseResponse]) -> tuple[ProgressionTrend, ...]:
    trends: list[ProgressionTrend] = []
    laps = tuple(item.lap_number for item in responses)
    for metric, units, declared_sources in _METRICS:
        values = [getattr(item, metric) for item in responses]
        sources = tuple(
            dict.fromkeys(
                channel
                for item in responses
                for channel in item.source_channels
                if channel in declared_sources
                or (metric == "phase_time_s" and channel in {"session_tick", "SessionTick"})
            )
        )
        if any(value is None for value in values):
            trends.append(
                ProgressionTrend(
                    metric=metric,  # type: ignore[arg-type]
                    units=units,  # type: ignore[arg-type]
                    state="unavailable",
                    lap_numbers=laps,
                    source_channels=sources,
                    blocker_reasons=(
                        f"{metric} lacks complete coverage on every matched lap.",
                    ),
                    evidence_state="unavailable",
                )
            )
            continue
        if len(responses) < _MINIMUM_TREND_LAPS:
            trends.append(
                ProgressionTrend(
                    metric=metric,  # type: ignore[arg-type]
                    units=units,  # type: ignore[arg-type]
                    state="blocked",
                    lap_numbers=laps,
                    source_channels=sources,
                    blocker_reasons=(
                        "At least ten uninterrupted qualified same-setup laps are required "
                        "for a descriptive progression trend; short runs cannot support tire "
                        "degradation or cooling conclusions.",
                    ),
                    evidence_state="blocked_by_context",
                )
            )
            continue
        numeric = [float(value) for value in values if value is not None]
        slope, change, residual_mad, above_noise = _theil_sen(laps, numeric)
        direction: Literal["increasing", "decreasing", "not_established"] = (
            "increasing"
            if above_noise and slope > 0.0
            else "decreasing"
            if above_noise and slope < 0.0
            else "not_established"
        )
        trends.append(
            ProgressionTrend(
                metric=metric,  # type: ignore[arg-type]
                units=units,  # type: ignore[arg-type]
                state="observed",
                lap_numbers=laps,
                robust_slope_per_lap=slope,
                observed_change=change,
                repeatability_residual_mad=residual_mad,
                above_empirical_noise=above_noise,
                direction=direction,
                source_channels=sources,
                evidence_state="observed_correlation",
            )
        )
    return tuple(trends)


def _phase_signature(
    lap_rows: Sequence[tuple[int, Sequence[Mapping[str, Any]]]],
    *,
    scope: PhysicalPhaseWindow,
    expected_sample_rate_hz: float,
) -> PhaseProgressionSignature:
    responses: list[LapPhaseResponse] = []
    blockers: list[str] = []
    for lap_number, rows in lap_rows:
        response, lap_blockers = _lap_response(
            rows,
            lap_number=lap_number,
            scope=scope,
            expected_sample_rate_hz=expected_sample_rate_hz,
        )
        if response is None:
            blockers.extend(lap_blockers)
        else:
            responses.append(response)
    if blockers:
        return PhaseProgressionSignature(
            scope=scope,
            physical_grid_pct=_physical_grid(scope),
            lap_responses=tuple(responses),
            status="blocked",
            blocker_reasons=tuple(dict.fromkeys(blockers)),
        )
    trends = _trends(responses)
    status: Literal["ready", "limited", "blocked"] = (
        "ready" if any(item.state == "observed" for item in trends) else "limited"
    )
    return PhaseProgressionSignature(
        scope=scope,
        physical_grid_pct=_physical_grid(scope),
        lap_responses=tuple(responses),
        trends=trends,
        status=status,
    )


def _row_setup_id(
    rows: Sequence[Mapping[str, Any]],
    *,
    lap_number: int,
    supplied: Mapping[int, str] | None,
) -> tuple[str | None, str | None]:
    observed = {
        str(row[channel]).strip()
        for row in rows
        for channel in _SETUP_ID_CHANNELS
        if row.get(channel) is not None and str(row[channel]).strip()
    }
    supplied_value = str(supplied[lap_number]).strip() if supplied and lap_number in supplied else None
    if len(observed) > 1:
        return None, f"Lap {lap_number} contains more than one setup identity."
    if supplied_value and observed and supplied_value not in observed:
        return None, f"Lap {lap_number} setup identity conflicts with telemetry provenance."
    identity = supplied_value or next(iter(observed), None)
    if not identity:
        return None, f"Lap {lap_number} lacks an exact setup identity."
    return identity, None


def _value_with_alias(
    row: Mapping[str, Any], aliases: Sequence[str]
) -> tuple[float | None, str | None]:
    for alias in aliases:
        value = _finite(row.get(alias))
        if value is not None:
            return value, alias
    return None, None


def _pit_corner(
    row: Mapping[str, Any], corner: str
) -> tuple[PitTireCornerSnapshot, tuple[str, ...]]:
    raw_prefix = corner.upper()
    aliases = {
        "tires_used": (f"{corner}_tires_used", f"{raw_prefix}TiresUsed"),
        "tires_available": (f"{corner}_tires_available", f"{raw_prefix}TiresAvailable"),
        "running_pressure": (f"{corner}_pressure", f"{raw_prefix}pressure"),
        "cold_pressure": (f"{corner}_cold_pressure", f"{raw_prefix}coldPressure"),
        "carcass_temp_l": (f"{corner}_carcass_temp_l", f"{raw_prefix}tempCL"),
        "carcass_temp_m": (f"{corner}_carcass_temp_m", f"{raw_prefix}tempCM"),
        "carcass_temp_r": (f"{corner}_carcass_temp_r", f"{raw_prefix}tempCR"),
        "wear_l": (f"{corner}_wear_left", f"{raw_prefix}wearL"),
        "wear_m": (f"{corner}_wear_middle", f"{raw_prefix}wearM"),
        "wear_r": (f"{corner}_wear_right", f"{raw_prefix}wearR"),
        "tire_distance_m": (f"{corner}_tire_distance_m", f"{raw_prefix}odometer"),
    }
    payload: dict[str, Any] = {"corner": corner}
    sources: list[str] = []
    for key, channel_aliases in aliases.items():
        value, source = _value_with_alias(row, channel_aliases)
        payload[key] = value
        if source is not None:
            sources.append(source)
    return PitTireCornerSnapshot(**payload), tuple(sources)


def _pit_snapshots(rows: Sequence[Mapping[str, Any]]) -> tuple[PitTireSnapshot, ...]:
    blocks: list[list[tuple[int, Mapping[str, Any]]]] = []
    current: list[tuple[int, Mapping[str, Any]]] = []
    for index, row in enumerate(rows):
        if _is_pit(row):
            current.append((index, row))
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    snapshots: list[PitTireSnapshot] = []
    for block in blocks:
        selections: list[tuple[Literal["pit_entry", "pit_exit", "pit_observation"], int, Mapping[str, Any]]]
        if len(block) == 1:
            selections = [("pit_observation", block[0][0], block[0][1])]
        else:
            selections = [
                ("pit_entry", block[0][0], block[0][1]),
                ("pit_exit", block[-1][0], block[-1][1]),
            ]
        for boundary, index, row in selections:
            corners: list[PitTireCornerSnapshot] = []
            sources: list[str] = []
            for corner in _CORNERS:
                snapshot, corner_sources = _pit_corner(row, corner)
                corners.append(snapshot)
                sources.extend(corner_sources)
            if not sources:
                continue
            lap = _lap_number(row)
            tick_value = _finite(row.get("session_tick", row.get("SessionTick")))
            tick = (
                int(round(tick_value))
                if tick_value is not None and tick_value >= 0.0 and math.isclose(tick_value, round(tick_value), abs_tol=1e-9)
                else None
            )
            identity = f"{index}|{boundary}|{lap}|{tick}|{'|'.join(dict.fromkeys(sources))}"
            snapshots.append(
                PitTireSnapshot(
                    snapshot_id="pit-tire:" + hashlib.sha256(identity.encode()).hexdigest()[:24],
                    boundary=boundary,
                    lap_number=lap,
                    session_tick=tick,
                    corners=tuple(corners),
                    source_channels=tuple(dict.fromkeys(sources)),
                )
            )
    return tuple(snapshots)


def analyze_stint_response_migration(
    data: pl.DataFrame | Sequence[Mapping[str, Any]],
    *,
    laps: Sequence[LapSummary],
    phase_windows: Sequence[PhysicalPhaseWindow],
    expected_sample_rate_hz: float,
    setup_identity_by_lap: Mapping[int, str] | None = None,
    expected_run_id: str | None = None,
    expected_source_file_sha256: str | None = None,
) -> StintResponseMigrationReport:
    """Build non-causal phase response progression for uninterrupted stints.

    Every publishable segment is bound to one run and one recording SHA-256.
    Rows may carry complete uniform ``run_id``/recording labels themselves. If
    either label family is wholly absent, the caller must supply the matching
    ``expected_run_id`` or ``expected_source_file_sha256`` trusted binding.
    Partially labeled or conflicting rows always fail closed.
    """

    rows = _rows(data)
    run_ids = {lap.run_id for lap in laps}
    if len(run_ids) != 1:
        return StintResponseMigrationReport(
            run_id=next(iter(run_ids), "unresolved-run"),
            status="blocked",
            blocker_reasons=("Exactly one source run is required.",),
        )
    run_id = next(iter(run_ids))
    source_file_sha256, source_blockers = _source_binding(
        rows,
        run_id=run_id,
        expected_run_id=expected_run_id,
        expected_source_file_sha256=expected_source_file_sha256,
    )
    if source_blockers:
        return StintResponseMigrationReport(
            run_id=run_id,
            status="blocked",
            blocker_reasons=source_blockers,
        )
    if not phase_windows:
        return StintResponseMigrationReport(
            run_id=run_id,
            source_file_sha256=source_file_sha256,
            status="blocked",
            blocker_reasons=("At least one exact physical phase window is required.",),
        )
    if expected_sample_rate_hz <= 0.0 or not math.isfinite(expected_sample_rate_hz):
        return StintResponseMigrationReport(
            run_id=run_id,
            source_file_sha256=source_file_sha256,
            status="blocked",
            blocker_reasons=("A positive declared telemetry rate is required.",),
        )

    indexed_by_lap: dict[int, list[tuple[int, dict[str, Any]]]] = {}
    for index, row in enumerate(rows):
        lap_number = _lap_number(row)
        if lap_number is not None:
            indexed_by_lap.setdefault(lap_number, []).append((index, row))
    global_clock = build_qualified_telemetry_clock(
        rows,
        expected_sample_rate_hz=expected_sample_rate_hz,
    )
    epochs = global_clock.epoch_index_by_sample

    candidates: dict[int, tuple[str, int, list[dict[str, Any]], int, int]] = {}
    blockers: list[str] = []
    for lap in sorted(laps, key=lambda item: item.lap_number):
        if not lap_is_eligible(lap):
            blockers.append(f"Lap {lap.lap_number} is not canonically eligible and splits the stint.")
            continue
        indexed = indexed_by_lap.get(lap.lap_number, [])
        if not indexed:
            blockers.append(f"Lap {lap.lap_number} has no telemetry rows and splits the stint.")
            continue
        lap_rows = [row for _index, row in indexed]
        if any(_is_pit(row) or _is_reset(row) for row in lap_rows):
            blockers.append(f"Lap {lap.lap_number} contains a pit/reset boundary and splits the stint.")
            continue
        setup_identity, setup_blocker = _row_setup_id(
            lap_rows,
            lap_number=lap.lap_number,
            supplied=setup_identity_by_lap,
        )
        if setup_identity is None:
            blockers.append(setup_blocker or f"Lap {lap.lap_number} setup identity is unavailable.")
            continue
        lap_clock = build_qualified_telemetry_clock(
            lap_rows,
            expected_sample_rate_hz=expected_sample_rate_hz,
        )
        if (
            lap_clock.clock_state != "qualified"
            or lap_clock.primary_clock != "session_tick"
            or lap_clock.epoch_count != 1
        ):
            blockers.append(f"Lap {lap.lap_number} lacks a qualified telemetry clock and splits the stint.")
            continue
        lap_epochs = {epochs[index] for index, _row in indexed if index < len(epochs)}
        if len(lap_epochs) != 1:
            blockers.append(f"Lap {lap.lap_number} crosses a clock reset epoch and splits the stint.")
            continue
        candidates[lap.lap_number] = (
            setup_identity,
            next(iter(lap_epochs)),
            lap_rows,
            indexed[0][0],
            indexed[-1][0],
        )

    groups: list[list[tuple[int, tuple[str, int, list[dict[str, Any]], int, int]]]] = []
    current: list[tuple[int, tuple[str, int, list[dict[str, Any]], int, int]]] = []
    for lap in sorted(laps, key=lambda item: item.lap_number):
        candidate = candidates.get(lap.lap_number)
        if candidate is None:
            if current:
                groups.append(current)
                current = []
            continue
        if current:
            previous_lap, previous = current[-1]
            between = rows[previous[4] + 1 : candidate[3]]
            boundary = any(_is_pit(row) or _is_reset(row) for row in between)
            bridge_clock = build_qualified_telemetry_clock(
                rows[previous[4] : candidate[3] + 1],
                expected_sample_rate_hz=expected_sample_rate_hz,
            )
            clock_continuous = (
                bridge_clock.clock_state == "qualified"
                and bridge_clock.primary_clock == "session_tick"
                and bridge_clock.epoch_count == 1
            )
            continuous = (
                lap.lap_number == previous_lap + 1
                and candidate[0] == previous[0]
                and candidate[1] == previous[1]
                and not boundary
                and clock_continuous
            )
            if not continuous:
                if lap.lap_number != previous_lap + 1:
                    blockers.append(
                        f"The lap-number boundary before lap {lap.lap_number} splits the stint."
                    )
                if candidate[0] != previous[0]:
                    blockers.append(
                        f"The setup identity changes before lap {lap.lap_number} and splits the stint."
                    )
                if candidate[1] != previous[1]:
                    blockers.append(
                        f"The clock reset epoch changes before lap {lap.lap_number} and splits the stint."
                    )
                if boundary:
                    blockers.append(
                        f"A pit/reset boundary before lap {lap.lap_number} splits the stint."
                    )
                if not clock_continuous:
                    blockers.append(
                        f"The clock boundary before lap {lap.lap_number} is not qualified and splits the stint."
                    )
                groups.append(current)
                current = []
        current.append((lap.lap_number, candidate))
    if current:
        groups.append(current)

    segments: list[StintMigrationSegment] = []
    for group in groups:
        lap_numbers = tuple(item[0] for item in group)
        setup_identity = group[0][1][0]
        epoch = group[0][1][1]
        lap_rows = [(lap_number, candidate[2]) for lap_number, candidate in group]
        signatures = tuple(
            _phase_signature(
                lap_rows,
                scope=scope,
                expected_sample_rate_hz=expected_sample_rate_hz,
            )
            for scope in phase_windows
        )
        identity = (
            f"{run_id}|{source_file_sha256}|{setup_identity}|{epoch}|{lap_numbers}|"
            f"{tuple(scope.scope_id for scope in phase_windows)}|{_FORMULA_VERSION}"
        )
        segment_status: Literal["ready", "limited"] = (
            "ready" if any(signature.status == "ready" for signature in signatures) else "limited"
        )
        segments.append(
            StintMigrationSegment(
                segment_id="stint-migration:" + hashlib.sha256(identity.encode()).hexdigest()[:24],
                run_id=run_id,
                source_file_sha256=source_file_sha256,
                setup_identity=setup_identity,
                clock_epoch=epoch,
                lap_numbers=lap_numbers,
                phase_signatures=signatures,
                status=segment_status,
            )
        )

    snapshots = _pit_snapshots(rows)
    source_channels = tuple(
        dict.fromkeys(
            channel
            for segment in segments
            for signature in segment.phase_signatures
            for response in signature.lap_responses
            for channel in response.source_channels
        )
    )
    if not segments:
        return StintResponseMigrationReport(
            run_id=run_id,
            source_file_sha256=source_file_sha256,
            status="blocked",
            pit_tire_snapshots=snapshots,
            blocker_reasons=tuple(
                dict.fromkeys(blockers or ("No uninterrupted qualified same-setup stint is available.",))
            ),
            source_channels=source_channels,
        )
    status: Literal["ready", "limited", "blocked"] = (
        "ready"
        if any(segment.status == "ready" for segment in segments) and not blockers
        else "limited"
    )
    return StintResponseMigrationReport(
        run_id=run_id,
        source_file_sha256=source_file_sha256,
        status=status,
        segments=tuple(segments),
        pit_tire_snapshots=snapshots,
        blocker_reasons=tuple(dict.fromkeys(blockers)),
        source_channels=source_channels,
    )


__all__ = [
    "LapPhaseResponse",
    "PhysicalPhaseWindow",
    "PhaseProgressionSignature",
    "PitTireCornerSnapshot",
    "PitTireSnapshot",
    "ProgressionTrend",
    "StintMigrationSegment",
    "StintResponseMigrationReport",
    "analyze_stint_response_migration",
]
