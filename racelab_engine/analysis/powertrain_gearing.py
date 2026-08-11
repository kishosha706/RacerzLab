"""Phase-aware powertrain and gearing evidence without inferred horsepower."""

from __future__ import annotations

from statistics import mean, median, pstdev
from typing import Any

from pydantic import Field

from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.analysis.p3_common import finite, lap_number, qualify_phase_engine, scope_phase_rows
from racelab_engine.analysis.p3_contracts import POWERTRAIN_GEARING_CONTRACT
from racelab_engine.models.engineering import EngineGate, EngineeringConclusion, EngineeringModel
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap import LapSummary


POWER_PHASES = {"initial_throttle", "full_throttle_exit", "straight"}
class ShiftEvent(EngineeringModel):
    lap_pct: float | None = None
    from_gear: int
    to_gear: int
    rpm_before: float
    rpm_after: float
    acceleration_loss_mps2: float | None = None


class PowertrainContextDiagnostics(EngineeringModel):
    selected_water_temp_c: float | None = None
    selected_oil_temp_c: float | None = None
    water_temp_trend_c_per_lap: float | None = None
    oil_temp_trend_c_per_lap: float | None = None
    temperature_context_stable: bool | None = None
    engine_warning_active_fraction_pct: float | None = None
    selected_fuel_level_l: float | None = None
    matched_fuel_spread_l: float | None = None
    fuel_mass_spread_kg: float | None = None
    fuel_mass_evidence_state: str = "unavailable_without_supported_density"
    fuel_context_matched: bool | None = None
    matched_phase_channel_coverage_pct: dict[str, float] = Field(default_factory=dict)
    comparable_laps: list[int] = Field(default_factory=list)
    gear_mismatch_laps: list[int] = Field(default_factory=list)
    gear_mismatch_fraction_by_lap: dict[int, float] = Field(default_factory=dict)
    gear_context_matched: bool = False
    context_comparable_for_observation: bool = False
    blocker_reasons: list[str] = Field(default_factory=list)


class PowertrainGearingReport(EngineeringModel):
    selected_lap: int
    phases: list[str] = Field(default_factory=list)
    gate: EngineGate
    rpm_occupancy_pct: dict[str, float] = Field(default_factory=dict)
    acceleration_by_rpm_bin_mps2: dict[str, float] = Field(default_factory=dict)
    speed_per_1000_rpm_by_gear_mph: dict[str, float] = Field(default_factory=dict)
    shift_events: list[ShiftEvent] = Field(default_factory=list)
    near_redline_occupancy_pct: float | None = None
    limiter_evidence_established: bool = False
    gearing_headroom_rpm: float | None = None
    pull_consistency_cv: float | None = None
    powered_repeatability_established: bool = False
    context_diagnostics: PowertrainContextDiagnostics | None = None
    conclusions: list[EngineeringConclusion] = Field(default_factory=list)


def _rpm_bin(rpm: float) -> str:
    lower = int(rpm // 1000) * 1000
    return f"{lower}-{lower + 999}"


def _mean_by(items: list[tuple[str, float]]) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for key, value in items:
        grouped.setdefault(key, []).append(value)
    return {key: round(mean(group), 5) for key, group in sorted(grouped.items())}


def _slope_by_lap(points: list[tuple[int, float]]) -> float | None:
    if len(points) < 2:
        return None
    x_mean = mean(number for number, _ in points)
    y_mean = mean(value for _, value in points)
    denominator = sum((number - x_mean) ** 2 for number, _ in points)
    if denominator <= 0.0:
        return None
    return sum((number - x_mean) * (value - y_mean) for number, value in points) / denominator


def _valid_context_value(channel: str, value: Any) -> float | None:
    number = finite(value)
    if number is None:
        return None
    bounds = {
        "fuel_level": (0.0, 1000.0),
        "water_temp": (-50.0, 250.0),
        "oil_temp": (-50.0, 300.0),
        "engine_warnings": (0.0, float(2**32 - 1)),
    }
    lower, upper = bounds[channel]
    if not lower <= number <= upper:
        return None
    if channel == "engine_warnings" and not number.is_integer():
        return None
    return number


def _contiguous_row_windows(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    ordered = sorted(
        rows,
        key=lambda row: finite(row.get("session_time")) or -1.0,
    )
    windows: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for row in ordered:
        if current:
            previous = current[-1]
            time = finite(row.get("session_time"))
            previous_time = finite(previous.get("session_time"))
            position = finite(row.get("lap_dist_pct"))
            previous_position = finite(previous.get("lap_dist_pct"))
            if position is not None and position <= 1.5:
                position *= 100.0
            if previous_position is not None and previous_position <= 1.5:
                previous_position *= 100.0
            contiguous = bool(
                time is not None
                and previous_time is not None
                and 0.0 < time - previous_time <= 0.25
                and position is not None
                and previous_position is not None
                and 0.0 <= position - previous_position <= 2.0
            )
            if not contiguous:
                windows.append(current)
                current = []
        current.append(row)
    if current:
        windows.append(current)
    return windows


def analyze_powertrain_gearing(
    rows: list[dict[str, Any]],
    lap_summaries: list[LapSummary] | None,
    *,
    selected_lap: int,
    sim_integrity_clear: bool | None,
    sim_integrity_confidence_cap: float = 1.0,
    redline_rpm: float | None = None,
) -> PowertrainGearingReport:
    redline_supplied = redline_rpm is not None
    redline_rpm = finite(redline_rpm)
    redline_invalid = bool(
        redline_supplied
        and (redline_rpm is None or not 500.0 <= redline_rpm <= 30_000.0)
    )
    if redline_invalid:
        redline_rpm = None
    diagnostic_contract_channels = {
        "fuel_level", "water_temp", "oil_temp", "engine_warnings",
    }
    diagnostic_contract_ready = all(
        any(_valid_context_value(channel, row.get(channel)) is not None for row in rows)
        for channel in diagnostic_contract_channels
    )
    requested_outputs = {"powertrain_phase_metrics", "gearing_discriminator_observation"}
    if diagnostic_contract_ready:
        requested_outputs.add("powertrain_context_diagnostics")
    scoped, phases, evaluation, gate = qualify_phase_engine(
        POWERTRAIN_GEARING_CONTRACT,
        rows,
        lap_summaries,
        selected_lap=selected_lap,
        target_phases=POWER_PHASES,
        sim_integrity_clear=sim_integrity_clear,
        sim_integrity_confidence_cap=sim_integrity_confidence_cap,
        requested_outputs=frozenset(requested_outputs),
    )
    if not evaluation.eligible:
        return PowertrainGearingReport(
            selected_lap=selected_lap,
            phases=sorted(phases & POWER_PHASES),
            gate=gate,
            conclusions=[EngineeringConclusion(
                key="powertrain_blocked",
                summary="Powertrain/gearing analysis is blocked for this phase window.",
                evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
                confidence_score=0.0,
                blocker_reasons=gate.blocker_reasons,
            )],
        )

    samples: list[tuple[dict[str, Any], float, int, float, float, float]] = []
    for row in scoped:
        rpm = finite(row.get("rpm"))
        gear_value = finite(row.get("gear"))
        speed = finite(row.get("speed_mph"))
        throttle = finite(row.get("throttle_pct"))
        accel = finite(row.get("long_accel"))
        if None not in (rpm, gear_value, speed, throttle, accel) and int(gear_value) > 0:
            samples.append((row, float(rpm), int(gear_value), float(speed), float(throttle), float(accel)))
    all_powered_samples = [item for item in samples if item[4] >= 90.0]
    powered_gears = [item[2] for item in all_powered_samples]
    dominant_power_gear = max(set(powered_gears), key=powered_gears.count) if powered_gears else None
    powered_samples = [item for item in all_powered_samples if item[2] == dominant_power_gear]
    rpms = [item[1] for item in powered_samples]
    occupancy_counts: dict[str, int] = {}
    acceleration_items: list[tuple[str, float]] = []
    ratio_items: list[tuple[str, float]] = []
    for _, rpm, gear, speed, throttle, accel in samples:
        key = _rpm_bin(rpm)
        occupancy_counts[key] = occupancy_counts.get(key, 0) + 1
        if throttle >= 90.0:
            acceleration_items.append((key, accel))
        if rpm > 0:
            ratio_items.append((str(gear), speed / rpm * 1000.0))
    occupancy = {
        key: round(count / len(samples) * 100.0, 4)
        for key, count in sorted(occupancy_counts.items())
    } if samples else {}

    shifts: list[ShiftEvent] = []
    samples_by_row = {id(item[0]): item for item in samples}
    for row_window in _contiguous_row_windows([item[0] for item in samples]):
        sample_window = [samples_by_row[id(row)] for row in row_window]
        for index, (left, right) in enumerate(zip(sample_window, sample_window[1:])):
            if right[2] <= left[2]:
                continue
            before_accel = mean(item[5] for item in sample_window[max(0, index - 2):index + 1])
            after_window = sample_window[index + 1:index + 4]
            after_accel = mean(item[5] for item in after_window) if after_window else None
            shifts.append(ShiftEvent(
                lap_pct=finite(right[0].get("lap_dist_pct")),
                from_gear=left[2],
                to_gear=right[2],
                rpm_before=left[1],
                rpm_after=right[1],
                acceleration_loss_mps2=(before_accel - after_accel) if after_accel is not None else None,
            ))

    near_redline_occupancy = None
    headroom = None
    if rpms and redline_rpm is not None and redline_rpm > 0:
        near_redline_occupancy = sum(rpm >= redline_rpm * 0.99 for rpm in rpms) / len(rpms) * 100.0
        headroom = redline_rpm - max(rpms)

    eligible_numbers = {lap.lap_number for lap in eligible_laps(lap_summaries or [])}
    selected_positions = {
        round(float(scaled_position))
        for row, *_ in powered_samples
        if (position := finite(row.get("lap_dist_pct"))) is not None
        for scaled_position in [position * 100.0 if position <= 1.0 else position]
    }
    selected_rpm_median = median(rpms) if rpms else None
    selected_gear_by_position = {
        round(float(position * 100.0 if position <= 1.0 else position)): gear
        for row, _rpm, gear, _speed, _throttle, _accel in all_powered_samples
        if (position := finite(row.get("lap_dist_pct"))) is not None
    }
    per_lap_pull: list[float] = []
    per_lap_limiter: list[float] = []
    per_lap_headroom: list[float] = []
    per_lap_limiter_evidence: list[bool] = []
    comparable_laps: list[int] = []
    gear_mismatch_laps: list[int] = []
    fuel_by_lap: list[tuple[int, float]] = []
    water_temp_by_lap: list[tuple[int, float]] = []
    oil_temp_by_lap: list[tuple[int, float]] = []
    warning_samples: list[float] = []
    coverage_by_channel: dict[str, list[float]] = {
        channel: [] for channel in diagnostic_contract_channels
    }
    gear_mismatch_fraction_by_lap: dict[int, float] = {}
    for number in sorted(eligible_numbers):
        lap_phase_rows, _ = scope_phase_rows(
            [row for row in rows if lap_number(row) == number],
            POWER_PHASES,
        )
        lap_powered_rows = [
            row for row in lap_phase_rows
            if (finite(row.get("throttle_pct")) or 0.0) >= 90.0
        ]
        comparable_rows = [
            row for row in lap_powered_rows
            if (position := finite(row.get("lap_dist_pct"))) is not None
            and round(float(position * 100.0 if position <= 1.0 else position)) in selected_positions
        ]
        comparable_times = [
            float(value) for row in comparable_rows
            if (value := finite(row.get("session_time"))) is not None
        ]
        if (
            len(comparable_rows) >= 20
            and len(comparable_times) >= 2
            and max(comparable_times) - min(comparable_times) >= 0.5
        ):
            comparable_laps.append(number)
            ordered_gear_checks = []
            for row in sorted(
                comparable_rows,
                key=lambda item: finite(item.get("lap_dist_pct")) or -1.0,
            ):
                position = finite(row.get("lap_dist_pct"))
                gear = finite(row.get("gear"))
                if position is None or gear is None:
                    continue
                position_key = round(float(position * 100.0 if position <= 1.0 else position))
                reference_gear = selected_gear_by_position.get(position_key)
                if reference_gear is not None:
                    ordered_gear_checks.append(int(gear) != reference_gear)
            mismatch_fraction = (
                sum(ordered_gear_checks) / len(ordered_gear_checks)
                if ordered_gear_checks else 1.0
            )
            longest_mismatch_run = 0
            current_mismatch_run = 0
            for mismatch in ordered_gear_checks:
                current_mismatch_run = current_mismatch_run + 1 if mismatch else 0
                longest_mismatch_run = max(longest_mismatch_run, current_mismatch_run)
            gear_mismatch_fraction_by_lap[number] = round(mismatch_fraction, 4)
            if mismatch_fraction >= 0.10 and longest_mismatch_run >= 5:
                gear_mismatch_laps.append(number)
            for channel, destination in (
                ("fuel_level", fuel_by_lap),
                ("water_temp", water_temp_by_lap),
                ("oil_temp", oil_temp_by_lap),
            ):
                channel_values = [
                    float(value) for row in comparable_rows
                    if (value := _valid_context_value(channel, row.get(channel))) is not None
                ]
                coverage = len(channel_values) / len(comparable_rows)
                coverage_by_channel[channel].append(coverage)
                if coverage >= 0.90:
                    destination.append((number, median(channel_values)))
            lap_warning_samples = [
                float(value) for row in comparable_rows
                if (value := _valid_context_value("engine_warnings", row.get("engine_warnings")))
                is not None
            ]
            warning_coverage = len(lap_warning_samples) / len(comparable_rows)
            coverage_by_channel["engine_warnings"].append(warning_coverage)
            if warning_coverage >= 0.90:
                warning_samples.extend(lap_warning_samples)
        matched_rows = [
            row for row in lap_phase_rows
            if (finite(row.get("throttle_pct")) or 0.0) >= 90.0
            and finite(row.get("gear")) == dominant_power_gear
        ]
        positions = {
            round(float(scaled_position))
            for row in matched_rows
            if (position := finite(row.get("lap_dist_pct"))) is not None
            for scaled_position in [position * 100.0 if position <= 1.0 else position]
        }
        lap_rpms = [float(value) for row in matched_rows if (value := finite(row.get("rpm"))) is not None]
        lap_accel = [float(value) for row in matched_rows if (value := finite(row.get("long_accel"))) is not None]
        lap_times = [float(value) for row in matched_rows if (value := finite(row.get("session_time"))) is not None]
        position_overlap = len(positions & selected_positions) / len(selected_positions) if selected_positions else 0.0
        context_matched = (
            len(matched_rows) >= 20
            and len(lap_times) >= 2
            and max(lap_times) - min(lap_times) >= 0.5
            and position_overlap >= 0.8
            and lap_rpms
            and selected_rpm_median is not None
            and abs(median(lap_rpms) - selected_rpm_median) <= 300.0
        )
        if context_matched and lap_accel:
            per_lap_pull.append(mean(lap_accel))
            if redline_rpm is not None and redline_rpm > 0:
                per_lap_limiter.append(sum(rpm >= redline_rpm * 0.99 for rpm in lap_rpms) / len(lap_rpms) * 100.0)
                per_lap_headroom.append(redline_rpm - max(lap_rpms))
                ordered_windows = [
                    sorted([
                        (float(time), int(gear), float(rpm), row)
                        for row in row_window
                        if (time := finite(row.get("session_time"))) is not None
                        and (gear := finite(row.get("gear"))) is not None
                        and (rpm := finite(row.get("rpm"))) is not None
                        and (finite(row.get("throttle_pct")) or 0.0) >= 90.0
                    ], key=lambda item: item[0])
                    for row_window in _contiguous_row_windows(lap_phase_rows)
                ]
                ordered = [item for window in ordered_windows for item in window]
                normal_upshift = any(
                    left[1] == dominant_power_gear and right[1] > left[1]
                    for window in ordered_windows
                    for left, right in zip(window, window[1:])
                )
                near = [item for item in ordered if item[1] == dominant_power_gear and item[2] >= redline_rpm * 0.99]
                sustained_plateau = any(
                    len(near_window) >= 3
                    and near_window[-1][0] - near_window[0][0] >= 0.5
                    and max(item[2] for item in near_window) - min(item[2] for item in near_window) <= redline_rpm * 0.005
                    for window in ordered_windows
                    for near_window in [[item for item in window if item[1] == dominant_power_gear and item[2] >= redline_rpm * 0.99]]
                )
                shift_indicator = sum(
                    (finite(item[3].get("shift_indicator_pct")) or 0.0) >= 99.0
                    for item in near
                ) >= 3
                end_of_zone_runout = bool(
                    near
                    and not normal_upshift
                    and any(
                        window
                        and window[-1][1] == dominant_power_gear
                        and window[-1][2] >= redline_rpm * 0.99
                        for window in ordered_windows
                    )
                )
                per_lap_limiter_evidence.append(
                    shift_indicator or sustained_plateau or end_of_zone_runout
                )
    pull_cv = (
        pstdev(per_lap_pull) / abs(mean(per_lap_pull))
        if len(per_lap_pull) >= 2 and abs(mean(per_lap_pull)) > 1e-9 else None
    )
    powered_repeatable = len(per_lap_pull) >= 2
    limiter_evidence = bool(
        powered_repeatable
        and len(per_lap_limiter_evidence) == len(per_lap_pull)
        and all(per_lap_limiter_evidence)
    )
    fuel_values = [value for _, value in fuel_by_lap]
    fuel_spread = max(fuel_values) - min(fuel_values) if len(fuel_values) >= 2 else None
    fuel_context_matched = (
        bool(
            len(fuel_by_lap) == len(comparable_laps)
            and fuel_spread is not None
            and fuel_spread <= max(1.0, abs(median(fuel_values)) * 0.05)
        )
        if len(comparable_laps) >= 2 else None
    )
    minimum_coverage = {
        channel: round(min(values) * 100.0, 3) if values else 0.0
        for channel, values in coverage_by_channel.items()
    }
    water_trend = _slope_by_lap(water_temp_by_lap)
    oil_trend = _slope_by_lap(oil_temp_by_lap)
    temperature_stable = (
        bool(
            len(water_temp_by_lap) == len(comparable_laps)
            and len(oil_temp_by_lap) == len(comparable_laps)
            and water_trend is not None and abs(water_trend) <= 0.5
            and oil_trend is not None and abs(oil_trend) <= 0.5
        )
        if len(comparable_laps) >= 2 else None
    )
    warning_fraction = (
        sum(value != 0.0 for value in warning_samples) / len(warning_samples) * 100.0
        if warning_samples and minimum_coverage["engine_warnings"] >= 90.0
        else None
    )
    gear_context_matched = len(comparable_laps) >= 2 and not gear_mismatch_laps
    diagnostics_blockers: list[str] = []
    if fuel_context_matched is not True:
        diagnostics_blockers.append(
            "FuelLevel is implausible, below 90% matched-phase coverage, or differs beyond 1 L / 5% across comparable powered laps."
        )
    if temperature_stable is not True:
        diagnostics_blockers.append(
            "Water/oil temperature is implausible, below 90% matched-phase coverage, or changes by more than 0.5 °C per lap."
        )
    if warning_fraction is None:
        diagnostics_blockers.append("EngineWarnings coverage is insufficient for a clear powertrain context.")
    elif warning_fraction > 0.0:
        diagnostics_blockers.append(
            "EngineWarnings is active in the matched window; the bitfield does not identify one cause here."
        )
    if not gear_context_matched:
        diagnostics_blockers.append(
            "Comparable laps use a different dominant gear or lack two matched-gear repetitions."
        )
    diagnostics_clear = not diagnostics_blockers
    selected_fuel = dict(fuel_by_lap).get(selected_lap)
    selected_water = dict(water_temp_by_lap).get(selected_lap)
    selected_oil = dict(oil_temp_by_lap).get(selected_lap)
    diagnostics = PowertrainContextDiagnostics(
        selected_water_temp_c=selected_water,
        selected_oil_temp_c=selected_oil,
        water_temp_trend_c_per_lap=water_trend,
        oil_temp_trend_c_per_lap=oil_trend,
        temperature_context_stable=temperature_stable,
        engine_warning_active_fraction_pct=warning_fraction,
        selected_fuel_level_l=selected_fuel,
        matched_fuel_spread_l=fuel_spread,
        fuel_mass_spread_kg=None,
        fuel_context_matched=fuel_context_matched,
        matched_phase_channel_coverage_pct=minimum_coverage,
        comparable_laps=comparable_laps,
        gear_mismatch_laps=gear_mismatch_laps,
        gear_mismatch_fraction_by_lap=gear_mismatch_fraction_by_lap,
        gear_context_matched=gear_context_matched,
        context_comparable_for_observation=diagnostics_clear,
        blocker_reasons=diagnostics_blockers,
    )
    sources = [
        "lap_dist_pct", "session_time", "speed_mph", "rpm", "gear",
        "throttle_pct", "long_accel",
    ]
    diagnostic_sources = [
        channel for channel in ("fuel_level", "water_temp", "oil_temp", "engine_warnings")
        if any(finite(row.get(channel)) is not None for row in scoped)
    ]
    support = [
        f"{len(samples)} phase-matched samples across {len(occupancy)} RPM bins.",
        f"{len(shifts)} upshifts measured; acceleration loss is a before/after response, not drivetrain power.",
        f"Pull consistency CV {pull_cv:.4f}." if pull_cv is not None else "Repeatable pull consistency is unavailable.",
        (
            f"Declared redline context {redline_rpm:.0f} RPM; this value is user-declared or setup-derived, not measured from telemetry."
            if redline_rpm is not None
            else "Declared redline context was invalid and ignored; expected 500-30,000 RPM."
            if redline_invalid
            else "Declared redline context is unavailable."
        ),
        (
            f"Near-redline occupancy {near_redline_occupancy:.2f}% with {headroom:.1f} RPM headroom."
            if near_redline_occupancy is not None and headroom is not None
            else "Near-redline occupancy/headroom is unavailable without a declared redline."
        ),
        (
            f"Limiter/runout evidence {'established' if limiter_evidence else 'not established'}; "
            f"matched-lap near-redline occupancies: {', '.join(f'{value:.2f}%' for value in per_lap_limiter) or 'none'}."
        ),
        (
            f"Matched FuelLevel volume/load-proxy spread {fuel_spread:.3f} L; fuel mass is unavailable without a supported density source."
            if fuel_spread is not None
            else "Fuel-load/mass-spread context is unavailable."
        ),
        (
            f"Water/oil trends {water_trend:+.3f}/{oil_trend:+.3f} °C per lap."
            if water_trend is not None and oil_trend is not None
            else "Water/oil temperature trends are unavailable."
        ),
        f"Gear mismatch laps: {gear_mismatch_laps or 'none'}.",
        f"Minimum matched-phase diagnostic coverage: {minimum_coverage}.",
    ]
    contradictions = [
        "Telemetry RPM and acceleration do not measure engine horsepower or drivetrain loss.",
        "Gear-ratio changes trade acceleration, shift placement, limiter exposure, and wheel-torque sensitivity.",
        "FuelLevel is a measured volume/load proxy; fuel mass is not calculated without a supported density source.",
        *diagnostics_blockers,
    ]
    direction_observation = None
    if redline_rpm is None:
        contradictions.append(
            "A finite declared redline/limiter value from 500 to 30,000 RPM is required before a gearing change is proposed."
        )
    elif (
        near_redline_occupancy is not None and near_redline_occupancy > 1.0
        and powered_repeatable and per_lap_limiter and all(value > 1.0 for value in per_lap_limiter)
        and limiter_evidence
        and pull_cv is not None and pull_cv <= 0.05
        and diagnostics_clear
    ):
        direction_observation = (
            "Repeated near-limiter exposure was observed in the matched powered phase; "
            "this is a gearing discriminator, not a setup direction."
        )
    elif (
        headroom is not None and headroom > redline_rpm * 0.12
        and powered_repeatable and per_lap_headroom and all(value > redline_rpm * 0.12 for value in per_lap_headroom)
        and pull_cv is not None and pull_cv <= 0.05
        and diagnostics_clear
    ):
        direction_observation = (
            "Repeated RPM headroom was observed in the matched powered phase; "
            "this is a gearing discriminator, not a setup direction."
        )
    return PowertrainGearingReport(
        selected_lap=selected_lap,
        phases=sorted(phases & POWER_PHASES),
        gate=gate,
        rpm_occupancy_pct=occupancy,
        acceleration_by_rpm_bin_mps2=_mean_by(acceleration_items),
        speed_per_1000_rpm_by_gear_mph=_mean_by(ratio_items),
        shift_events=shifts,
        near_redline_occupancy_pct=near_redline_occupancy,
        limiter_evidence_established=limiter_evidence,
        gearing_headroom_rpm=headroom,
        pull_consistency_cv=pull_cv,
        powered_repeatability_established=powered_repeatable,
        context_diagnostics=diagnostics,
        conclusions=[
            EngineeringConclusion(
                key="powertrain_phase_metrics",
                summary="Powertrain response is calculated by engineering phase and RPM bin.",
                evidence_state=EvidenceState.CALCULATED,
                confidence_score=min(0.85, gate.confidence_cap),
                source_channels=sources,
                supporting_evidence=support,
                contradicting_evidence=contradictions,
            ),
            (
                EngineeringConclusion(
                key="powertrain_context_diagnostics",
                summary=(
                    "Temperature, fuel-load, warning-state, and matched-gear context are comparable for this observation."
                    if diagnostics_clear
                    else "Powertrain context has unresolved temperature, fuel-load, warning-state, or gear-mismatch blockers."
                ),
                evidence_state=EvidenceState.CALCULATED,
                confidence_score=min(0.75 if diagnostics_clear else 0.4, gate.confidence_cap),
                source_channels=[*sources, *diagnostic_sources],
                supporting_evidence=support,
                contradicting_evidence=contradictions,
                )
                if diagnostic_contract_ready else EngineeringConclusion(
                    key="powertrain_context_diagnostics",
                    summary="Powertrain temperature, fuel-load, and warning diagnostics are unavailable.",
                    evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
                    confidence_score=0.0,
                    blocker_reasons=[
                        "Record FuelLevel, WaterTemp, OilTemp, and EngineWarnings through comparable powered laps."
                    ],
                )
            ),
            EngineeringConclusion(
                key="gearing_discriminator_observation",
                summary=(
                    direction_observation
                    or "No repeatable gearing-direction discriminator was established by the current evidence."
                ),
                evidence_state=EvidenceState.NEEDS_CONFIRMATION,
                confidence_score=min(0.7 if direction_observation else 0.45, gate.confidence_cap),
                source_channels=sources,
                supporting_evidence=support,
                contradicting_evidence=contradictions,
            ),
        ],
    )


__all__ = [
    "PowertrainContextDiagnostics", "PowertrainGearingReport", "ShiftEvent",
    "analyze_powertrain_gearing",
]
