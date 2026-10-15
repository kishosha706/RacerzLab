"""Automatic handling-balance assessment: phase-local, multi-lap, evidence-gated.

Scientific contract (see handling_balance_contracts.py) after the physics
audit of 2026-10-13:

- Planar kinematics: course angle chi = heading psi + sideslip beta, so
  d(chi)/dt = speed x path-curvature = yaw_rate + d(beta)/dt. The residual
  speed x path-curvature - yaw_rate is therefore the planar sideslip RATE.
  It is zero in steady-state cornering no matter how unbalanced the car is
  (a persistently tight car with constant sideslip shows no residual), and
  it moves during transients without implying imbalance. Consequences:
    * The residual is a KINEMATIC DIAGNOSTIC, never primary balance evidence.
    * It can never, by itself, establish a tight/loose-family symptom.
    * The former planar sideslip-rate proxy (lat_accel / speed - yaw_rate) is
      the SAME identity and was removed: it cannot corroborate itself.
- A deficit/excess signature may carry a canonical Dial-In symptom only when
  a second, independent strand corroborates it under comparable conditions:
  steering demand per achieved path curvature (steering_rad vs curvature),
  compared against the leave-one-out run-local reference at matched speeds.
  The residual strand uses (speed, curvature, yaw); the demand strand uses
  (steering, curvature, speed) - different relationships, so alignment of the
  two is genuine independent corroboration, still observation-only.
- Actual-path curvature is NOT the driver's intended path, so a positive
  residual is honestly reported as "reduced rotation response", never as
  understeer. When the car fails to rotate, the path itself widens and the
  reference follows it; the residual is a conservative lower bound on the
  rotation-response signature, not a calibrated handle for balance.
- The run-local reference (leave-one-out lap medians) separates lap-relative
  and phase-relative signatures from the noise of the run itself. A car-wide
  uniform balance offset cannot be separated from that reference; detecting
  it requires an independent external reference (historical same-car/same-
  track sessions or a reviewed vehicle-response model), which this producer
  does not have and therefore reports as unavailable instead of inventing.
- No setup authorization. No Keep/Undo/Retest. No DriverIntent. The authority
  field is structurally fixed to observation_only.
"""

from __future__ import annotations

import hashlib
import math
from statistics import median
from typing import Any, Iterable, Sequence

from racelab_engine.analysis.comparison import build_lap_grid, interpolate_run_to_grid
from racelab_engine.analysis.evidence_contracts import (
    EvidenceEvaluationInput,
    evaluate_evidence_contract,
)
from racelab_engine.analysis.handling_balance_contracts import HANDLING_BALANCE_CONTRACT
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.analysis.p3_common import bounded_confidence, finite, lap_number
from racelab_engine.analysis.phase_engineering import (
    _geometric_curvature,
    _gps_geometry_healthy,
)
from racelab_engine.analysis.time_alignment import (
    _PHASE_CHANNELS,
    detect_engineering_phases,
)
from racelab_engine.models.engineering import EngineGate, EngineeringConclusion
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.handling_balance import (
    HandlingAuthority,
    HandlingBalanceAssessment,
    HandlingBalanceReport,
    HandlingClassification,
    HandlingCorroboration,
    HandlingPhaseObservation,
)
from racelab_engine.models.lap import LapSummary
from racelab_engine.knowledge.setup.handling_symptom_bridge import resolve_canonical_symptom

# ── Tunable constants (documented, run-local semantics) ────────

# Phases that carry steering demand and rotation evidence. Everything else
# (brake transients, straights, bumps) is excluded from classification.
_HANDLING_PHASES = frozenset({
    "turn_in", "entry", "apex_region", "center", "initial_throttle", "full_throttle_exit",
})

# Minimum |steering| (deg) for a phase bin to count as rotation demand.
_STEERING_DEMAND_FLOOR_DEG = 3.0
# Minimum sustained |expected yaw| for the response ratio to be meaningful.
_RESPONSE_RATIO_YAW_FLOOR_RAD_S = 0.02
# Absolute resolution floor for a qualified kinematic residual (rad/s). Below
# this, measured yaw noise and curvature smoothing dominate the signal.
_ABSOLUTE_DEFICIT_FLOOR_RAD_S = 0.02
# Run-local noise floor applied to the robust scale before classification.
_NOISE_FLOOR_RAD_S = 0.015
# A lap's deviation must exceed this many robust scales of the reference group.
_QUALIFICATION_SCALE_FACTOR = 1.5
# Minimum phase coverage per lap for a phase to participate.
_MIN_PHASE_COVERAGE = 0.7
# Minimum samples per phase for a lap-level estimate.
_MIN_PHASE_SAMPLES = 5
# Minimum bins for a phase to be reported at run level.
_MIN_REPORT_BINS = 5
# Transient anomaly factor: phase max |dyaw/dt| must exceed this multiple of
# the run-wide cornering median.
_TRANSIENT_ANOMALY_FACTOR = 4.0
# Correction anomaly factor versus the run-wide phase median.
_CORRECTION_ANOMALY_FACTOR = 2.0
# Minimum eligible laps for the whole producer (mirrors the contract).
_MIN_ELIGIBLE_LAPS = 2
# Grid step for phase detection (percent of lap).
_GRID_STEP_PCT = 0.2

# ── Strand B (steering demand per achieved curvature) constants ─
# Minimum |path curvature| (1/m) for demand-per-curvature to be meaningful.
_DEMAND_CURVATURE_FLOOR_1_PER_M = 0.001
# Minimum |steering| (deg) for the demand strand (mirrors the phase floor).
_DEMAND_STEERING_FLOOR_DEG = 1.0
# Absolute noise floor for demand-per-curvature deviations (deg per 1/m).
_DEMAND_NOISE_FLOOR_ABS_DEG_M = 5.0
# Relative noise floor as a fraction of the reference group median.
_DEMAND_NOISE_FLOOR_REL = 0.05
# Comparable-conditions guard: a lap's median phase speed may deviate from the
# group median by at most this much (m/s) to participate in the demand strand.
_SPEED_MATCH_FLOOR_MPS = 5.0

# Steering channel variants tolerated on input rows.
_STEERING_KEYS = ("steering_deg", "steering_rad")
_YAW_KEYS = ("yaw_rate",)
_LAT_ACCEL_KEYS = ("lat_accel",)
_SPEED_KEYS = ("speed_mps", "speed_mph")
_CURVATURE_KEYS = ("curvature_1_per_m",)


def _first(values: Iterable[str | None], keys: tuple[str, ...]) -> str | None:
    return next((key for key in keys if key in values), None)


def _values(values: Iterable[float | None]) -> list[float]:
    return [value for item in values if (value := finite(item)) is not None]


def _percentile(values: Iterable[float | None], fraction: float) -> float | None:
    ordered = sorted(_values(values))
    if not ordered:
        return None
    position = fraction * (len(ordered) - 1)
    left = int(math.floor(position))
    right = int(math.ceil(position))
    if left == right:
        return ordered[left]
    weight = position - left
    return ordered[left] * (1.0 - weight) + ordered[right] * weight


def _median_absolute_deviation(values: Iterable[float]) -> float | None:
    items = sorted(values)
    if not items:
        return None
    center = median(items)
    return median([abs(item - center) for item in items])


def _robust_scale(values: Iterable[float], floor: float) -> float | None:
    mad = _median_absolute_deviation(list(values))
    if mad is None:
        return None
    return max(1.4826 * mad, floor)


def _coverage(values: Iterable[Any]) -> float:
    items = list(values)
    return len(_values(items)) / len(items) if items else 0.0


def _steering_reversal_count(steering: list[float | None]) -> int:
    """Count sustained sign reversals in a steering trace (correction demand)."""
    count = 0
    last_sign = 0
    for value in steering:
        if value is None:
            continue
        sign = 1 if value > 0 else -1 if value < 0 else 0
        if sign and last_sign and sign != last_sign:
            count += 1
        if sign:
            last_sign = sign
    return count


def _yaw_rate_of_change(
    session_time: list[float | None],
    yaw_rate: list[float | None],
    indices: Sequence[int],
) -> float | None:
    paired = [
        (time_value, yaw_value)
        for index in indices
        if (time_value := session_time[index]) is not None
        and (yaw_value := yaw_rate[index]) is not None
    ]
    if len(paired) < 3:
        return None
    slopes: list[float] = []
    for (t0, y0), (t1, y1) in zip(paired, paired[1:]):
        if 0.0 < t1 - t0 <= 0.5:
            slopes.append(abs(y1 - y0) / (t1 - t0))
    return _percentile(slopes, 0.9) if slopes else None


def _phase_rows_by_lap(
    rows: list[dict[str, Any]],
    eligible_numbers: set[int],
) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        lap = lap_number(row)
        if lap is not None and lap in eligible_numbers:
            grouped.setdefault(lap, []).append(row)
    return grouped


def _lap_phase_metrics(
    lap_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Compute per-phase response metrics for one lap.

    Returns (phase_metrics, curvature_info, warnings).
    """
    grid = build_lap_grid(0.0, 100.0, _GRID_STEP_PCT)
    interpolated_channels = list(dict.fromkeys([
        *_PHASE_CHANNELS, "velocity_y", "curvature_1_per_m", "steering_rad",
    ]))
    channels = interpolate_run_to_grid(lap_rows, interpolated_channels, grid)
    # The canonical archive carries steering_rad; steering_deg is a derived
    # convenience. Fill the phase detector's expected channel from the source
    # so rows that only archive steering_rad still phase-classify correctly.
    for index, value in enumerate(channels.get("steering_deg", [])):
        if value is None and (rad := channels.get("steering_rad", [])[index]) is not None:
            channels["steering_deg"][index] = math.degrees(rad)
    phases, _intervals, _phase_channels = detect_engineering_phases(
        lap_rows,
        grid=grid,
        _interpolated_channels=channels,
    )
    gps_healthy = _gps_geometry_healthy(lap_rows)
    curvature, curvature_basis = _geometric_curvature(
        grid,
        channels,
        gps_geometry_healthy=gps_healthy,
    )
    speed_mps = [
        value if value is not None else (
            mph / 2.2369362920544 if (mph := channels["speed_mph"][index]) is not None else None
        )
        for index, value in enumerate(channels["speed_mps"])
    ]
    steering_deg = [
        value if value is not None else (
            math.degrees(rad) if (rad := channels["steering_rad"][index]) is not None else None
        )
        for index, value in enumerate(channels["steering_deg"])
    ]
    warnings: list[str] = []
    if curvature_basis == "unavailable":
        warnings.append("No usable path curvature; rotation-response diagnostics are unavailable.")
    if not gps_healthy and curvature_basis != "direct_curvature":
        warnings.append("GPS geometry failed its health check; direct curvature was used when available.")
    if curvature_basis == "gps_fallback_direct_unhealthy":
        warnings.append("Direct curvature failed its health cross-check; GPS-derived curvature was used.")

    phase_metrics: dict[str, Any] = {}
    for index, phase in enumerate(phases):
        if phase not in _HANDLING_PHASES:
            continue
        phase_metrics.setdefault(phase, {"indices": []})["indices"].append(index)

    result: dict[str, Any] = {}
    for phase, bucket in phase_metrics.items():
        indices = bucket["indices"]
        if len(indices) < _MIN_PHASE_SAMPLES:
            continue
        steer = [steering_deg[index] for index in indices]
        yaw = [channels["yaw_rate"][index] for index in indices]
        curvature_values = [curvature[index] for index in indices]
        speeds = [speed_mps[index] for index in indices]
        times = [channels["session_time"][index] for index in indices]

        expected: list[float | None] = []
        deficits: list[float | None] = []
        ratios: list[float | None] = []
        efficiency: list[float | None] = []
        demand_per_curvature: list[float | None] = []
        for pos in range(len(indices)):
            speed_value = speeds[pos]
            yaw_value = yaw[pos]
            steer_value = steer[pos]
            curvature_value = curvature_values[pos]
            expected_value: float | None
            if speed_value is not None and curvature_value is not None:
                expected_value = speed_value * curvature_value
                expected.append(expected_value)
            else:
                expected_value = None
                expected.append(None)
            if expected_value is not None and yaw_value is not None:
                deficits.append(expected_value - yaw_value)
            else:
                deficits.append(None)
            if (
                expected_value is not None
                and yaw_value is not None
                and abs(expected_value) >= _RESPONSE_RATIO_YAW_FLOOR_RAD_S
            ):
                ratios.append(yaw_value / expected_value)
            else:
                ratios.append(None)
            if (
                curvature_value is not None
                and steer_value is not None
                and abs(steer_value) >= 1.0
            ):
                efficiency.append(abs(curvature_value) / abs(steer_value))
            else:
                efficiency.append(None)
            if (
                steer_value is not None
                and abs(steer_value) >= _DEMAND_STEERING_FLOOR_DEG
                and curvature_value is not None
                and abs(curvature_value) >= _DEMAND_CURVATURE_FLOOR_1_PER_M
            ):
                demand_per_curvature.append(abs(steer_value) / abs(curvature_value))
            else:
                demand_per_curvature.append(None)
        steering_demand = _percentile(
            [abs(value) for value in steer if value is not None],
            0.5,
        )
        coverage = (
            len(_values(deficits)) / len(indices),
            len(_values(ratios)) / len(indices),
            len(_values(efficiency)) / len(indices),
            len(_values(demand_per_curvature)) / len(indices),
        )
        result[phase] = {
            "sample_bins": len(indices),
            "steering_demand_median_deg": steering_demand,
            "expected_yaw_median_rad_s": _percentile(expected, 0.5),
            "measured_yaw_median_rad_s": _percentile(yaw, 0.5),
            "deficit_median_rad_s": _percentile(deficits, 0.5),
            "deficit_abs_p90_rad_s": _percentile([abs(value) for value in deficits if value is not None], 0.9),
            "response_ratio_median": _percentile(ratios, 0.5),
            "steering_efficiency_median": _percentile(efficiency, 0.5),
            "steering_demand_per_curvature_median": _percentile(demand_per_curvature, 0.5),
            "speed_median_mps": _percentile(speeds, 0.5),
            "correction_count": _steering_reversal_count(steer),
            "max_yaw_rate_of_change_rad_s2": _yaw_rate_of_change(times, yaw, range(len(indices))),
            "deficit_coverage": coverage[0],
            "ratio_coverage": coverage[1],
            "efficiency_coverage": coverage[2],
            "demand_coverage": coverage[3],
        }
    return result, {"basis": curvature_basis, "gps_healthy": gps_healthy}, warnings


def _assessment_id(run_id: str, phase: str, lap_numbers: tuple[int, ...]) -> str:
    digest = hashlib.sha256(
        f"{run_id}|{phase}|{','.join(str(lap) for lap in lap_numbers)}".encode()
    ).hexdigest()
    return f"hba_{digest[:24]}"


def _blocked_report(
    run_id: str,
    session_id: str | None,
    selected_lap: int | None,
    gate: EngineGate,
    warnings: tuple[str, ...],
) -> HandlingBalanceReport:
    assessment = HandlingBalanceAssessment(
        assessment_id=_assessment_id(run_id, "unavailable", ()),
        run_id=run_id,
        session_id=session_id,
        classification=HandlingClassification.UNAVAILABLE,
        observation_text="Handling balance could not be assessed from this recording.",
        evidence_state=EvidenceState.UNAVAILABLE,
        confidence_score=0.0,
        repeatability="unavailable",
        blocker_reasons=tuple(gate.blocker_reasons) if gate.blocker_reasons else ("Required evidence is unavailable.",),
        contradicting_evidence=(
            "Absence of an assessment is not evidence of neutral balance.",
        ),
    )
    return HandlingBalanceReport(
        run_id=run_id,
        session_id=session_id,
        selected_lap=selected_lap,
        eligible_laps=0,
        reference_lap_count=0,
        classification=HandlingClassification.UNAVAILABLE,
        assessments=(assessment,),
        gate=gate,
        warnings=warnings,
        conclusions=(EngineeringConclusion(
            key="handling_balance_blocked",
            summary="The handling-balance producer failed closed on its evidence contract.",
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            confidence_score=0.0,
            blocker_reasons=list(gate.blocker_reasons) if gate.blocker_reasons else ["Required evidence is unavailable."],
        ),),
    )


def analyze_handling_balance(
    rows: list[dict[str, Any]],
    lap_summaries: list[LapSummary] | None,
    *,
    run_id: str = "unknown-run",
    selected_lap: int | None = None,
    session_id: str | None = None,
    sim_integrity_clear: bool | None = None,
    sim_integrity_confidence_cap: float = 1.0,
    setup_change_isolated: bool = True,
) -> HandlingBalanceReport:
    """Aggregate phase-local rotation-response signatures over a run.

    rows may span the whole run; eligible laps are selected through the
    canonical eligibility gate, and the selected lap only anchors reporting.
    """
    eligible = eligible_laps(lap_summaries or [])
    eligible_numbers = {lap.lap_number for lap in eligible}
    warnings: list[str] = []

    usable = frozenset(
        channel for row in rows for channel, value in row.items() if finite(value) is not None
    )
    phase_capable = bool(
        "steering_deg" in usable or "steering_rad" in usable
    ) and "yaw_rate" in usable
    evaluation = evaluate_evidence_contract(
        HANDLING_BALANCE_CONTRACT,
        EvidenceEvaluationInput(
            usable_channels=usable,
            condition_results={
                "eligible_laps": len(eligible) >= _MIN_ELIGIBLE_LAPS,
                "physical_alignment": "lap_dist_pct_100" in usable,
                "phase_coverage": phase_capable,
                "steering_demand": phase_capable,
                "independent_response_corroboration": phase_capable,
            },
            blocker_results={
                "junk_lap_context": False,
                "sample_integrity_failure": (
                    None if sim_integrity_clear is None
                    else not sim_integrity_clear
                ),
                "unisolated_setup_change": not setup_change_isolated,
            },
            repetitions=len(eligible),
            requested_outputs=frozenset({
                "handling_phase_observations",
                "handling_balance_signature",
                "handling_canonical_symptom",
            }),
        ),
    )
    gate = EngineGate(
        contract_key=evaluation.contract_key,
        eligible=evaluation.eligible,
        confidence_cap=min(evaluation.confidence_cap, bounded_confidence(sim_integrity_confidence_cap)),
        blocker_reasons=[blocker.message for blocker in evaluation.blockers],
        needed_measurements=[measurement.instruction for measurement in evaluation.needed_measurements],
    )
    if not evaluation.eligible:
        return _blocked_report(run_id, session_id, selected_lap, gate, tuple(warnings))

    grouped = _phase_rows_by_lap(rows, eligible_numbers)
    ordered_laps = sorted(grouped)
    if len(ordered_laps) < _MIN_ELIGIBLE_LAPS:
        gate = EngineGate(
            contract_key=evaluation.contract_key,
            eligible=False,
            confidence_cap=gate.confidence_cap,
            blocker_reasons=[*gate.blocker_reasons, "Fewer than two eligible laps contain telemetry rows."],
            needed_measurements=gate.needed_measurements,
        )
        return _blocked_report(run_id, session_id, selected_lap, gate, tuple(warnings))

    # ── Lap-level phase metrics ─────────────────────────────────
    lap_metrics: dict[int, dict[str, Any]] = {}
    curvature_bases: set[str] = set()
    for lap in ordered_laps:
        metrics, curvature_info, lap_warnings = _lap_phase_metrics(grouped[lap])
        if curvature_info["basis"] != "unavailable":
            lap_metrics[lap] = metrics
        curvature_bases.add(curvature_info["basis"])
        warnings.extend(lap_warnings)
    warnings = list(dict.fromkeys(warnings))

    if not lap_metrics:
        gate = EngineGate(
            contract_key=evaluation.contract_key,
            eligible=False,
            confidence_cap=gate.confidence_cap,
            blocker_reasons=[*gate.blocker_reasons, "No eligible lap produced usable path curvature."],
            needed_measurements=gate.needed_measurements,
        )
        return _blocked_report(run_id, session_id, selected_lap, gate, tuple(warnings))

    # ── Run-level aggregation with leave-one-out references ─────
    phases = sorted({phase for metrics in lap_metrics.values() for phase in metrics})
    phase_observations: list[HandlingPhaseObservation] = []
    assessments: list[HandlingBalanceAssessment] = []
    classified_phases: dict[str, HandlingClassification] = {}
    phase_directions: dict[str, int] = {}

    for phase in phases:
        lap_values = {
            lap: metrics[phase]
            for lap, metrics in lap_metrics.items()
            if phase in metrics
            and metrics[phase].get("deficit_coverage", 0.0) >= _MIN_PHASE_COVERAGE
            and (metrics[phase].get("steering_demand_median_deg") or 0.0) >= _STEERING_DEMAND_FLOOR_DEG
            and metrics[phase].get("sample_bins", 0) >= _MIN_PHASE_SAMPLES
        }
        if len(lap_values) < _MIN_ELIGIBLE_LAPS:
            continue
        deficit_by_lap: dict[int, float] = {}
        for lap, metrics in lap_values.items():
            deficit_value = metrics.get("deficit_median_rad_s")
            if deficit_value is not None:
                deficit_by_lap[lap] = deficit_value
        if len(deficit_by_lap) < _MIN_ELIGIBLE_LAPS:
            continue

        group_deficit_median = _percentile(deficit_by_lap.values(), 0.5)
        group_deficit_p90 = _percentile(
            [abs(metrics["deficit_abs_p90_rad_s"]) for metrics in lap_values.values()
             if metrics.get("deficit_abs_p90_rad_s") is not None],
            0.5,
        )
        reference_laps = tuple(sorted(lap_values))
        reference_scale = _robust_scale(
            deficit_by_lap.values(),
            _NOISE_FLOOR_RAD_S,
        )
        deficit_qualified: list[int] = []
        excess_qualified: list[int] = []
        for lap, deficit in deficit_by_lap.items():
            others = [value for other, value in deficit_by_lap.items() if other != lap]
            if len(others) < 1:
                continue
            # Deviation against the leave-one-out reference median, scaled by
            # the GROUP robust scale: the whole eligible lap group is the
            # run-local reference population, so a lap must stand out from
            # its peers against the group's own noise envelope.
            deviation = deficit - median(others)
            scale = reference_scale or _NOISE_FLOOR_RAD_S
            if deviation > _QUALIFICATION_SCALE_FACTOR * scale and deviation > _ABSOLUTE_DEFICIT_FLOOR_RAD_S:
                deficit_qualified.append(lap)
            elif deviation < -_QUALIFICATION_SCALE_FACTOR * scale and deviation < -_ABSOLUTE_DEFICIT_FLOOR_RAD_S:
                excess_qualified.append(lap)

        correction_medians = [
            metrics.get("correction_count", 0)
            for metrics in lap_values.values()
            if metrics.get("correction_count") is not None
        ]

        # ── Strand A: the kinematic residual (planar sideslip rate) ─
        absolute_deficit = group_deficit_median is not None and abs(group_deficit_median) > _ABSOLUTE_DEFICIT_FLOOR_RAD_S
        sustained = reference_scale is not None and group_deficit_median is not None and (
            abs(group_deficit_median) > _QUALIFICATION_SCALE_FACTOR * reference_scale
        )
        sustained_deficit = bool(group_deficit_median is not None and group_deficit_median > 0 and sustained)
        sustained_excess = bool(group_deficit_median is not None and group_deficit_median < 0 and sustained)
        repetition_threshold = max(2, math.ceil(len(deficit_by_lap) / 2))
        # Unidirectional: a direction qualifies only with a strict majority of
        # individually qualified laps, so a bimodal lap group can never feed
        # two opposing signatures into classification order.
        residual_deficit = sustained_deficit or (
            len(deficit_qualified) >= repetition_threshold
            and len(deficit_qualified) > len(excess_qualified)
        )
        residual_excess = sustained_excess or (
            len(excess_qualified) >= repetition_threshold
            and len(excess_qualified) > len(deficit_qualified)
        )

        # ── Strand B: steering demand per achieved path curvature ─
        # Independent of the residual identity: it relates steering to
        # achieved curvature at comparable speeds, so it can corroborate a
        # rotation-response signature that strand A alone cannot establish.
        demand_by_lap: dict[int, float] = {}
        for lap, metrics in lap_values.items():
            demand_value = metrics.get("steering_demand_per_curvature_median")
            if (
                demand_value is not None
                and metrics.get("demand_coverage", 0.0) >= _MIN_PHASE_COVERAGE
            ):
                demand_by_lap[lap] = demand_value
        speed_by_lap: dict[int, float] = {}
        for lap, metrics in lap_values.items():
            speed_value = metrics.get("speed_median_mps")
            if speed_value is not None:
                speed_by_lap[lap] = speed_value
        group_speed_median = _percentile(speed_by_lap.values(), 0.5) if speed_by_lap else None
        demand_comparable: dict[int, float] = {}
        for lap, demand in demand_by_lap.items():
            lap_speed = speed_by_lap.get(lap)
            if (
                group_speed_median is None
                or lap_speed is None
                or abs(lap_speed - group_speed_median) <= _SPEED_MATCH_FLOOR_MPS
            ):
                demand_comparable[lap] = demand
        elevated_qualified: list[int] = []
        reduced_qualified: list[int] = []
        demand_deviations: list[float] = []
        demand_values = list(demand_comparable.values())
        demand_scale: float | None = None
        if len(demand_values) >= _MIN_ELIGIBLE_LAPS:
            demand_median = median(demand_values)
            demand_floor = max(
                _DEMAND_NOISE_FLOOR_ABS_DEG_M,
                _DEMAND_NOISE_FLOOR_REL * abs(demand_median) if demand_median else 0.0,
            )
            demand_scale = _robust_scale(demand_values, demand_floor) or demand_floor
        for lap, demand in demand_comparable.items():
            others = [value for other, value in demand_comparable.items() if other != lap]
            if len(others) < 1 or demand_scale is None:
                continue
            # Group-scale leave-one-out deviation, mirroring the residual
            # strand: a bimodal demand split raises the group scale and
            # cannot qualify either direction.
            deviation = demand - median(others)
            demand_deviations.append(deviation / demand_scale)
            if deviation > _QUALIFICATION_SCALE_FACTOR * demand_scale:
                elevated_qualified.append(lap)
            elif deviation < -_QUALIFICATION_SCALE_FACTOR * demand_scale:
                reduced_qualified.append(lap)
        demand_threshold = max(2, math.ceil(len(demand_comparable) / 2)) if demand_comparable else 0
        # Unidirectional, mirroring the residual strand: a bimodal demand
        # split cannot corroborate either direction.
        demand_elevated = bool(demand_comparable) and (
            len(elevated_qualified) >= demand_threshold
            and len(elevated_qualified) > len(reduced_qualified)
        )
        demand_reduced = bool(demand_comparable) and (
            len(reduced_qualified) >= demand_threshold
            and len(reduced_qualified) > len(elevated_qualified)
        )

        # ── Two-strand classification ────────────────────────────
        if residual_deficit and demand_elevated:
            classification = HandlingClassification.ROTATION_RESPONSE_DEFICIT
        elif residual_excess and demand_reduced:
            classification = HandlingClassification.ROTATION_RESPONSE_EXCESS
        elif residual_deficit or residual_excess:
            classification = HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION
        elif demand_elevated or demand_reduced:
            classification = HandlingClassification.STEERING_DEMAND_ANOMALY
        else:
            classification = HandlingClassification.NO_SIGNIFICANT_IMBALANCE_QUALIFIED
        if classification != HandlingClassification.NO_SIGNIFICANT_IMBALANCE_QUALIFIED:
            classified_phases[phase] = classification
        if residual_deficit:
            phase_directions[phase] = 1
        elif residual_excess:
            phase_directions[phase] = -1

        steering_demand_median = _percentile(
            [metrics.get("steering_demand_median_deg") for metrics in lap_values.values()],
            0.5,
        )
        expected_yaw = _percentile(
            [metrics.get("expected_yaw_median_rad_s") for metrics in lap_values.values()],
            0.5,
        )
        measured_yaw = _percentile(
            [metrics.get("measured_yaw_median_rad_s") for metrics in lap_values.values()],
            0.5,
        )
        efficiency = _percentile(
            [metrics.get("steering_efficiency_median") for metrics in lap_values.values()],
            0.5,
        )
        ratios = _percentile(
            [metrics.get("response_ratio_median") for metrics in lap_values.values()],
            0.5,
        )
        demand_per_curvature = _percentile(
            [metrics.get("steering_demand_per_curvature_median") for metrics in lap_values.values()],
            0.5,
        )
        transient_p90 = _percentile(
            [metrics.get("max_yaw_rate_of_change_rad_s2") for metrics in lap_values.values()],
            0.9,
        )
        corroboration = HandlingCorroboration(
            kinematic_residual_strand_qualified=residual_deficit or residual_excess,
            steering_response_strand_qualified=demand_elevated or demand_reduced,
            steering_response_direction=(
                "elevated" if demand_elevated else "reduced" if demand_reduced else None
            ),
            aligned=(residual_deficit and demand_elevated) or (residual_excess and demand_reduced),
            corroborated=classification in {
                HandlingClassification.ROTATION_RESPONSE_DEFICIT,
                HandlingClassification.ROTATION_RESPONSE_EXCESS,
            },
        )
        observation = HandlingPhaseObservation(
            phase=phase,
            eligible_laps=len(lap_values),
            sample_bins=sum(metrics.get("sample_bins", 0) for metrics in lap_values.values()),
            steering_demand_median_deg=round(steering_demand_median, 3) if steering_demand_median is not None else None,
            steering_demand_floor_deg=_STEERING_DEMAND_FLOOR_DEG,
            path_kinematic_expected_yaw_median_rad_s=round(expected_yaw, 4) if expected_yaw is not None else None,
            measured_yaw_median_rad_s=round(measured_yaw, 4) if measured_yaw is not None else None,
            rotation_response_deficit_median_rad_s=round(group_deficit_median, 4) if group_deficit_median is not None else None,
            rotation_response_deficit_abs_p90_rad_s=round(group_deficit_p90, 4) if group_deficit_p90 is not None else None,
            rotation_response_ratio_median=round(ratios, 3) if ratios is not None else None,
            steering_efficiency_median_curvature_per_rad=round(efficiency, 5) if efficiency is not None else None,
            steering_demand_per_curvature_median_deg_per_inv_m=round(demand_per_curvature, 2) if demand_per_curvature is not None else None,
            steering_demand_relative_deviation_scale_units=(
                round(median(demand_deviations), 3) if demand_deviations else None
            ),
            speed_median_mps=round(group_speed_median, 2) if group_speed_median is not None else None,
            correction_count_median=round(float(median(correction_medians)), 2) if correction_medians else None,
            max_yaw_rate_of_change_rad_s2=round(transient_p90, 4) if transient_p90 is not None else None,
            noise_scale_deficit_rad_s=round(reference_scale, 4) if reference_scale is not None else None,
            coverage_fraction=round(float(median([
                metrics.get("deficit_coverage", 0.0) for metrics in lap_values.values()
            ])), 3),
            reference_lap_group=reference_laps,
            corroboration=corroboration,
        )
        phase_observations.append(observation)

        # Resolve the reported classification first so a located-only
        # residual observation still occupies the phase and cannot be
        # double-reported by the transient/correction anomaly screens.
        assessment_classification = classification
        located_only = (
            classification == HandlingClassification.NO_SIGNIFICANT_IMBALANCE_QUALIFIED
            and absolute_deficit
        )
        if located_only:
            assessment_classification = HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION
        if assessment_classification != HandlingClassification.NO_SIGNIFICANT_IMBALANCE_QUALIFIED:
            classified_phases[phase] = assessment_classification
        if classification == HandlingClassification.NO_SIGNIFICANT_IMBALANCE_QUALIFIED and not absolute_deficit:
            continue

        assessment_laps = tuple(sorted(lap_values))
        support: list[str] = []
        contradictions: list[str] = [
            "The kinematic residual equals the planar sideslip rate (speed x curvature - yaw rate); it is blind to a constant sideslip angle and moves during transients without implying imbalance.",
            "The reference is actual-path curvature, not the driver's intended path.",
        ]
        if assessment_classification in {
            HandlingClassification.ROTATION_RESPONSE_DEFICIT,
            HandlingClassification.ROTATION_RESPONSE_EXCESS,
        }:
            support.extend((
                f"Median signed kinematic residual {group_deficit_median:+.4f} rad/s against the path-kinematic reference over {len(deficit_by_lap)} eligible laps.",
                f"Steering demand per achieved curvature independently {'exceeds' if demand_elevated else 'falls below'} the run-local reference on {len(elevated_qualified) if demand_elevated else len(reduced_qualified)}/{len(demand_comparable)} comparable-speed laps; the two strands align.",
                "The two strands share measured path curvature and the run-local reference group; corroboration qualifies the symptom mapping without counting independent evidence units twice.",
            ))
        elif assessment_classification == HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION:
            support.append(
                f"Median signed kinematic residual {group_deficit_median:+.4f} rad/s against the path-kinematic reference over {len(deficit_by_lap)} eligible laps."
            )
            contradictions.append(
                "Steering-response evidence does not corroborate the residual; a kinematic residual alone can never establish a tight/loose-family symptom."
            )
            if located_only:
                contradictions.append(
                    "The residual exceeds the resolution floor but not the run-local noise envelope; it is reported as a located observation, not a qualified signature."
                )
        elif assessment_classification == HandlingClassification.STEERING_DEMAND_ANOMALY:
            support.append(
                f"Steering demand per achieved curvature is {'elevated' if demand_elevated else 'reduced'} relative to the run-local reference on {len(elevated_qualified) if demand_elevated else len(reduced_qualified)}/{len(demand_comparable)} comparable-speed laps."
            )
            contradictions.append(
                "Driver-line or technique changes can move steering demand without a vehicle change; no kinematic residual corroborates this divergence."
            )
        if len(deficit_qualified) > 0 and assessment_classification == HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION and not located_only:
            contradictions.append("Some laps qualified individually, but the phase did not reach the repetition threshold.")
        canonical_symptom = resolve_canonical_symptom(assessment_classification, phase)[0]
        if canonical_symptom:
            support.append(
                f"Canonical symptom association {canonical_symptom} is telemetry-observed; it is not driver testimony."
            )
        assessment_text = _assessment_text(
            assessment_classification,
            phase,
            len(assessment_laps),
            located_only=located_only,
            demand_elevated=demand_elevated,
            demand_reduced=demand_reduced,
        )
        evidence_state = EvidenceState.OBSERVED_CORRELATION
        if assessment_classification in {
            HandlingClassification.ROTATION_RESPONSE_DEFICIT,
            HandlingClassification.ROTATION_RESPONSE_EXCESS,
        }:
            # Dependence discount: the two strands share measured path
            # curvature and the run-local reference group, so corroboration
            # is partial and cannot earn the single-strand maximum.
            confidence = min(gate.confidence_cap, 0.55 if len(deficit_by_lap) >= 5 else 0.45)
            repeatability = (
                f"{len(deficit_qualified)}/{len(deficit_by_lap)} residual laps and "
                f"{len(elevated_qualified)}/{len(demand_comparable)} demand laps beyond the run-local envelopes"
            )
        else:
            confidence = min(gate.confidence_cap, 0.4)
            repeatability = (
                "kinematic residual beyond the run-local envelope; steering response unaligned"
                if assessment_classification == HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION
                else "steering demand beyond the run-local envelope; kinematic residual unaligned"
            )
        assessments.append(HandlingBalanceAssessment(
            assessment_id=_assessment_id(run_id, phase, assessment_laps),
            run_id=run_id,
            session_id=session_id,
            lap_numbers=assessment_laps,
            phase=phase,
            classification=assessment_classification,
            canonical_symptom_id=canonical_symptom,
            observation_text=assessment_text,
            evidence_state=evidence_state,
            confidence_score=round(confidence, 3),
            repeatability=repeatability,
            source_channels=tuple(sorted({
                "lap_dist_pct_100", "session_time", "speed_mps", "yaw_rate",
                "steering_deg", "steering_rad", "lat_accel",
                *({"lat", "lon"} if curvature_bases <= {"gps_derived", "gps_fallback_direct_unhealthy"} else set()),
                *({"curvature_1_per_m"} if curvature_bases <= {"direct_curvature", "gps_fallback_direct_unhealthy"} else set()),
            })),
            supporting_evidence=tuple(support),
            contradicting_evidence=tuple(contradictions),
            alternative_explanations=tuple(sorted({
                "Driver-line variation between laps.",
                "Banked-track geometry shifting the planar reference.",
                "Operating-speed differences between laps.",
                "Tire-state progression within the stint.",
            })),
            phase_observations=(observation,),
        ))

    # ── Transient and correction anomaly screening ──────────────
    cornering_transients = [
        observation.max_yaw_rate_of_change_rad_s2
        for observation in phase_observations
        if observation.max_yaw_rate_of_change_rad_s2 is not None
    ]
    transient_anomaly_phases: list[str] = []
    if len(cornering_transients) >= 2:
        baseline_transient = median(cornering_transients)
        if baseline_transient and baseline_transient > 0.01:
            for observation in phase_observations:
                if (
                    observation.max_yaw_rate_of_change_rad_s2 is not None
                    and observation.max_yaw_rate_of_change_rad_s2 >= _TRANSIENT_ANOMALY_FACTOR * baseline_transient
                    and observation.phase not in classified_phases
                ):
                    transient_anomaly_phases.append(observation.phase)
                    classified_phases[observation.phase] = HandlingClassification.TRANSIENT_ROTATION_ANOMALY
                    assessments.append(HandlingBalanceAssessment(
                        assessment_id=_assessment_id(run_id, observation.phase, observation.reference_lap_group),
                        run_id=run_id,
                        session_id=session_id,
                        lap_numbers=observation.reference_lap_group,
                        phase=observation.phase,
                        classification=HandlingClassification.TRANSIENT_ROTATION_ANOMALY,
                        observation_text=(
                            f"Transient yaw development in {observation.phase} exceeds the run-local cornering envelope "
                            "without a sustained rotation-response deficit."
                        ),
                        evidence_state=EvidenceState.OBSERVED_CORRELATION,
                        confidence_score=round(min(gate.confidence_cap, 0.45), 3),
                        repeatability="run-local transient envelope",
                        source_channels=("lap_dist_pct_100", "session_time", "yaw_rate", "steering_deg", "steering_rad"),
                        supporting_evidence=(
                            f"Phase P90 |dyaw/dt| {observation.max_yaw_rate_of_change_rad_s2:.3f} rad/s^2 against a cornering median of {baseline_transient:.3f} rad/s^2.",
                        ),
                        contradicting_evidence=(
                            "A yaw transient is not proof of oversteer; braking, bump, or driver input timing can produce the same signature.",
                        ),
                        alternative_explanations=(
                            "Brake-release weight transfer.",
                            "Throttle-application weight transfer.",
                            "Surface disturbance or bump input.",
                        ),
                        phase_observations=(observation,),
                    ))

    correction_anomaly_phases: list[str] = []
    correction_values = [
        observation.correction_count_median
        for observation in phase_observations
        if observation.correction_count_median is not None
    ]
    if len(correction_values) >= 2:
        baseline_correction = median(correction_values)
        if baseline_correction and baseline_correction >= 0.5:
            for observation in phase_observations:
                if (
                    observation.correction_count_median is not None
                    and observation.correction_count_median >= _CORRECTION_ANOMALY_FACTOR * baseline_correction
                    and observation.phase not in classified_phases
                ):
                    correction_anomaly_phases.append(observation.phase)
                    classified_phases[observation.phase] = HandlingClassification.STEERING_RESPONSE_ANOMALY
                    assessments.append(HandlingBalanceAssessment(
                        assessment_id=_assessment_id(run_id, observation.phase, observation.reference_lap_group),
                        run_id=run_id,
                        session_id=session_id,
                        lap_numbers=observation.reference_lap_group,
                        phase=observation.phase,
                        classification=HandlingClassification.STEERING_RESPONSE_ANOMALY,
                        observation_text=(
                            f"Correction demand in {observation.phase} exceeds the run-local phase envelope "
                            "without a sustained rotation-response deficit."
                        ),
                        evidence_state=EvidenceState.OBSERVED_CORRELATION,
                        confidence_score=round(min(gate.confidence_cap, 0.45), 3),
                        repeatability="run-local correction envelope",
                        source_channels=("lap_dist_pct_100", "session_time", "steering_deg", "steering_rad", "yaw_rate"),
                        supporting_evidence=(
                            f"Median correction count {observation.correction_count_median:.1f} against a phase median of {baseline_correction:.1f}.",
                        ),
                        contradicting_evidence=(
                            "Corrections can be a response to instability or driver preference, not its cause.",
                        ),
                        alternative_explanations=(
                            "Driver-style corrections.",
                            "Traffic or line adjustments.",
                            "Surface feedback.",
                        ),
                        phase_observations=(observation,),
                    ))

    # ── Run-level classification ────────────────────────────────
    if not phase_observations:
        gate = EngineGate(
            contract_key=evaluation.contract_key,
            eligible=False,
            confidence_cap=gate.confidence_cap,
            blocker_reasons=[*gate.blocker_reasons, "No phase met steering demand and coverage floors."],
            needed_measurements=gate.needed_measurements,
        )
        return _blocked_report(run_id, session_id, selected_lap, gate, tuple(warnings))

    deficit_phases = {phase for phase, kind in classified_phases.items() if kind == HandlingClassification.ROTATION_RESPONSE_DEFICIT}
    excess_phases = {phase for phase, kind in classified_phases.items() if kind == HandlingClassification.ROTATION_RESPONSE_EXCESS}
    residual_observation_phases = {
        phase for phase, kind in classified_phases.items()
        if kind == HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION
    }
    demand_anomaly_phases = {
        phase for phase, kind in classified_phases.items()
        if kind == HandlingClassification.STEERING_DEMAND_ANOMALY
    }
    direction_set = set(phase_directions.values())
    if {1, -1} <= direction_set or (deficit_phases and excess_phases):
        run_classification = HandlingClassification.MIXED_PHASE_DEPENDENT
    elif deficit_phases:
        run_classification = HandlingClassification.ROTATION_RESPONSE_DEFICIT
    elif excess_phases:
        run_classification = HandlingClassification.ROTATION_RESPONSE_EXCESS
    elif transient_anomaly_phases and not correction_anomaly_phases:
        run_classification = HandlingClassification.TRANSIENT_ROTATION_ANOMALY
    elif correction_anomaly_phases and not transient_anomaly_phases:
        run_classification = HandlingClassification.STEERING_RESPONSE_ANOMALY
    elif residual_observation_phases:
        run_classification = HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION
    elif demand_anomaly_phases:
        run_classification = HandlingClassification.STEERING_DEMAND_ANOMALY
    elif assessments:
        run_classification = HandlingClassification.INCONCLUSIVE
    else:
        run_classification = HandlingClassification.NO_SIGNIFICANT_IMBALANCE_QUALIFIED

    mapped_symptoms = sorted({
        assessment.canonical_symptom_id
        for assessment in assessments
        if assessment.canonical_symptom_id
    })
    if mapped_symptoms:
        symptom_conclusion = EngineeringConclusion(
            key="handling_canonical_symptom",
            summary=(
                "Qualified signatures map to canonical Dial-In symptoms "
                + ", ".join(mapped_symptoms)
                + "; the association is telemetry-observed and never driver testimony."
            ),
            evidence_state=EvidenceState.OBSERVED_CORRELATION,
            confidence_score=round(min(gate.confidence_cap, 0.5), 3),
            source_channels=sorted(HANDLING_BALANCE_CONTRACT.required_channels),
            supporting_evidence=[
                "Resolved against the loaded Dial-In symptom vocabulary.",
                "The association carries no setup authority and no DriverIntent.",
            ],
            contradicting_evidence=["Driver-reported feeling remains separately sourced."],
        )
    else:
        symptom_conclusion = EngineeringConclusion(
            key="handling_canonical_symptom",
            summary=(
                "No canonical symptom association was made; the qualified signature "
                "remains a descriptive rotation-response observation."
            ),
            evidence_state=EvidenceState.NEEDS_CONFIRMATION,
            confidence_score=round(min(gate.confidence_cap, 0.4), 3),
            source_channels=sorted(HANDLING_BALANCE_CONTRACT.required_channels),
            supporting_evidence=[
                "Symptom mapping requires a corroborated deficit/excess signature: the kinematic residual AND the steering-demand-to-response strand must both qualify and align.",
            ],
            contradicting_evidence=["A telemetry label is not driver testimony."],
        )
    conclusions = [
        EngineeringConclusion(
            key="handling_balance_signature",
            summary=_classification_text(run_classification),
            evidence_state=(
                EvidenceState.BLOCKED_BY_CONTEXT if run_classification == HandlingClassification.UNAVAILABLE
                else EvidenceState.OBSERVED_CORRELATION
            ),
            confidence_score=round(min(gate.confidence_cap, 0.6 if len(ordered_laps) >= 5 else 0.5), 3),
            source_channels=sorted(HANDLING_BALANCE_CONTRACT.required_channels),
            supporting_evidence=[
                f"Aggregated {len(phase_observations)} phases over {len(ordered_laps)} eligible laps.",
                "The reference is speed x actual-path curvature; it is not the driver's intended path.",
                "The kinematic residual equals the planar sideslip rate; deficit/excess signatures require independent steering-demand corroboration.",
            ],
            contradicting_evidence=[
                "Absence of a qualified signature is not proof of neutral balance: the residual is blind to a constant sideslip angle.",
                "A car-wide uniform balance offset cannot be separated from a run-local reference; detecting it requires an independent external reference.",
                "This producer cannot authorize a setup change.",
            ],
            blocker_reasons=[] if run_classification != HandlingClassification.UNAVAILABLE else list(gate.blocker_reasons),
        ),
        symptom_conclusion,
    ]
    return HandlingBalanceReport(
        run_id=run_id,
        session_id=session_id,
        selected_lap=selected_lap,
        eligible_laps=len(eligible),
        reference_lap_count=len(ordered_laps),
        classification=run_classification,
        assessments=tuple(assessments),
        conclusions=tuple(conclusions),
        gate=gate,
        warnings=tuple(warnings),
    )


def _assessment_text(
    classification: HandlingClassification,
    phase: str,
    lap_count: int,
    *,
    located_only: bool = False,
    demand_elevated: bool = False,
    demand_reduced: bool = False,
) -> str:
    if classification == HandlingClassification.ROTATION_RESPONSE_DEFICIT:
        return (
            f"Reduced rotation response corroborated in {phase}: the kinematic residual and "
            f"the steering-demand response agree across {lap_count} eligible laps."
        )
    if classification == HandlingClassification.ROTATION_RESPONSE_EXCESS:
        return (
            f"Excess rotation-like response corroborated in {phase}: the kinematic residual and "
            f"the steering-demand response agree across {lap_count} eligible laps."
        )
    if classification == HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION:
        located = " as a located observation within the run-local envelope" if located_only else ""
        return (
            f"A kinematic residual in {phase} (speed x path-curvature - yaw rate; the planar "
            f"sideslip-rate identity) is reported{located} across {lap_count} eligible laps "
            "without steering-response corroboration."
        )
    if classification == HandlingClassification.STEERING_DEMAND_ANOMALY:
        direction = "elevated" if demand_elevated else "reduced" if demand_reduced else "divergent"
        return (
            f"Steering demand per achieved curvature is {direction} relative to the run-local "
            f"reference in {phase} across {lap_count} eligible laps, without a corroborating "
            "kinematic residual."
        )
    return _classification_text(classification)


def _classification_text(classification: HandlingClassification) -> str:
    return {
        HandlingClassification.NO_SIGNIFICANT_IMBALANCE_QUALIFIED:
            "No rotation-response imbalance qualified beyond the run-local noise envelope; the kinematic residual is blind to a constant sideslip angle, so this is not proof of neutral balance.",
        HandlingClassification.KINEMATIC_RESIDUAL_OBSERVATION:
            "Kinematic residual observed (the planar sideslip-rate identity) beyond the run-local noise envelope without steering-response corroboration; it cannot establish a tight/loose-family symptom on its own.",
        HandlingClassification.ROTATION_RESPONSE_DEFICIT:
            "Corroborated reduced rotation response: the kinematic residual and the steering-demand-to-response strand both qualify and align.",
        HandlingClassification.ROTATION_RESPONSE_EXCESS:
            "Corroborated excess rotation-like response: the kinematic residual and the steering-demand-to-response strand both qualify and align.",
        HandlingClassification.MIXED_PHASE_DEPENDENT:
            "Opposing phase-local rotation-response signatures observed; no single whole-corner label is justified.",
        HandlingClassification.TRANSIENT_ROTATION_ANOMALY:
            "Transient rotation anomaly observed without a sustained response signature.",
        HandlingClassification.STEERING_RESPONSE_ANOMALY:
            "Elevated correction demand observed without a sustained response signature.",
        HandlingClassification.STEERING_DEMAND_ANOMALY:
            "Steering-demand divergence observed without a corroborating kinematic residual; it cannot establish a tight/loose-family symptom on its own.",
        HandlingClassification.INCONCLUSIVE:
            "Handling balance could not be qualified from this recording.",
        HandlingClassification.UNAVAILABLE:
            "Handling balance assessment is unavailable.",
    }[classification]


__all__ = [
    "HandlingAuthority",
    "HandlingBalanceAssessment",
    "HandlingBalanceReport",
    "HandlingClassification",
    "HandlingPhaseObservation",
    "analyze_handling_balance",
]
