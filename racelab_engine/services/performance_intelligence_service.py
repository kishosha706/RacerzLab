"""Build the P32 empirical lap-time mechanics projection.

The service reuses ``analyze_time_alignment`` as the only time-delta engine and
reads one narrow, qualified lap pair once per immutable workspace identity.
All relationships remain measured, contextual, or mechanically expected.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from statistics import median
from threading import RLock
from typing import Any, Iterable, Sequence

from racelab_engine.analysis.comparison import interpolate_run_to_grid
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.analysis.proximity_context import (
    proximity_time_gap_exposure_fraction,
)
from racelab_engine.analysis.time_alignment import (
    PhaseTimeEffect,
    TimeAlignmentResult,
    analyze_time_alignment,
    nearest_sorted_index,
)
from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.crew_chief import EngineeringObjective
from racelab_engine.models.evidence import (
    EngineeringBlockTarget,
    engineering_blockers_for,
)
from racelab_engine.models.performance_intelligence import (
    ComponentPerformanceInfluence,
    CornerPerformanceChain,
    DriverVehicleResult,
    DriverVehicleSeparation,
    LapTimeOpportunity,
    LapTimeOpportunityMap,
    PerformanceExplanationChain,
    PerformanceExplanationEdge,
    PerformanceIntelligenceProjection,
    PerformanceMechanismDefinition,
    PerformanceObjectiveEnvelope,
    PerformanceOutcome,
    PerformancePhaseState,
    PerformancePrinciple,
    PerformanceResponseRecord,
    RunPerformanceBasis,
    SpeedStory,
    TimeOriginKind,
    TrackDemandProfile,
)
from racelab_engine.services.import_service import (
    read_telemetry_manifest,
    read_telemetry_rows,
)
from racelab_engine.services.run_intelligence_service import RunIntelligenceBundle
from racelab_engine.storage.db import default_db_path
from racelab_engine.storage.repository import RaceLabRepository

_KNOWLEDGE_VERSION = "2026.08.p32-performance.v1"
_P26_UNAVAILABLE_SHA256 = canonical_json_sha256(
    {"producer": "p26.vehicle-systems", "state": "unavailable"}
)
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
_ALL_PHASES = ("braking", "entry", "center", "exit", "straight", "transition")
_ALL_OBJECTIVES = tuple(item.value for item in EngineeringObjective)
_TIME_SOURCE = ("racerzlab_time_alignment_reciprocal_speed_v1",)
_GENERAL_SOURCES = ("iracing_setup_guide", "nascar_nextgen_manual")
_COLUMNS = (
    "lap",
    "lap_number",
    "lap_dist_pct_100",
    "session_time",
    "lap_dist_ft",
    "speed_mps",
    "speed_mph",
    "throttle_pct",
    "brake_pct",
    "steering_deg",
    "yaw_rate",
    "lat_accel",
    "long_accel",
    "vert_accel",
    "vert_accel_g",
    "lat",
    "lon",
    "alt",
    "rpm",
    "gear",
    "rear_wheel_speed_mismatch",
    "car_distance_ahead_m",
    "car_distance_behind_m",
    "on_pit_road",
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
    "cfs_ride_height_in",
)
_STATE_CHANNELS = (
    "speed_mph",
    "throttle_pct",
    "brake_pct",
    "steering_deg",
    "yaw_rate",
    "long_accel",
    "lat",
    "lon",
)
_CORNER_PHASES = {
    "brake_application",
    "threshold_braking",
    "brake_release",
    "turn_in",
    "entry",
    "center",
    "apex_region",
    "initial_throttle",
    "full_throttle_exit",
}
_PHASE_GROUPS = {
    "approach": {"straight", "lift"},
    "braking": {"brake_application", "threshold_braking", "brake_release"},
    "entry": {"turn_in", "entry"},
    "center": {"center", "apex_region"},
    "exit": {"initial_throttle", "full_throttle_exit"},
    "carry": {"following_straight_carry", "straight"},
}
_MECHANISM_COMPONENTS = {
    "braking_realization": ("brakes", "tires", "weight_distribution"),
    "brake_release_transition": ("brakes", "dampers", "weight_distribution"),
    "turn_in_response": ("steering", "alignment", "anti_roll_bars", "dampers"),
    "entry_rotation": ("weight_distribution", "anti_roll_bars", "brakes"),
    "center_rotation": ("anti_roll_bars", "springs", "tires", "alignment"),
    "speed_retention": ("tires", "alignment", "platform"),
    "throttle_realization": ("differential", "tires", "weight_distribution"),
    "exit_traction": ("differential", "tires", "springs", "dampers"),
    "exit_carry": ("differential", "tires", "final_drive"),
    "straight_acceleration": ("final_drive", "tires", "cooling_configuration"),
    "gearing_headroom": ("final_drive",),
    "path_efficiency": ("steering", "alignment", "tires"),
    "stability_workload": ("steering", "dampers", "weight_distribution"),
    "tire_state_migration": ("tires", "alignment", "springs"),
    "platform_consistency": ("platform", "springs", "dampers"),
    "disturbance_compliance": ("dampers", "springs", "tires"),
    "traffic_robustness": ("tires", "differential", "steering"),
}
_PHASE_MECHANISMS = {
    "brake_application": ("braking_realization",),
    "threshold_braking": ("braking_realization",),
    "brake_release": ("brake_release_transition", "entry_rotation"),
    "turn_in": ("turn_in_response", "entry_rotation"),
    "entry": ("entry_rotation", "path_efficiency"),
    "center": ("center_rotation", "speed_retention", "path_efficiency"),
    "apex_region": ("center_rotation", "speed_retention"),
    "initial_throttle": ("throttle_realization", "exit_traction"),
    "full_throttle_exit": ("exit_traction", "exit_carry"),
    "following_straight_carry": ("exit_carry",),
    "straight": ("straight_acceleration", "gearing_headroom"),
    "transition": ("stability_workload", "platform_consistency"),
    "bump_curb": ("disturbance_compliance", "platform_consistency"),
}
_PROJECTION_CACHE_LOCK = RLock()
_PROJECTION_CACHE: dict[str, PerformanceIntelligenceProjection] = {}


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _median(values: Iterable[float | None]) -> float | None:
    usable = [value for value in values if value is not None]
    return median(usable) if usable else None


def _mean(values: Iterable[float | None]) -> float | None:
    usable = [value for value in values if value is not None]
    return sum(usable) / len(usable) if usable else None


def _principle(
    principle_id: str,
    statement: str,
    required: tuple[str, ...],
    forbidden: tuple[str, ...],
    *,
    phases: tuple[str, ...] = _ALL_PHASES,
    sources: tuple[str, ...] = _TIME_SOURCE + _GENERAL_SOURCES,
) -> PerformancePrinciple:
    return PerformancePrinciple(
        principle_id=principle_id,
        statement=statement,
        applicable_phases=phases,
        applicable_objectives=_ALL_OBJECTIVES,
        required_evidence=required,
        forbidden_claims=forbidden,
        source_ids=sources,
    )


@lru_cache(maxsize=1)
def performance_principles() -> tuple[PerformancePrinciple, ...]:
    measured_time = ("qualified physical scope", "measured elapsed-time basis")
    no_local_proxy = ("peak or minimum speed alone establishes performance",)
    return (
        _principle(
            "time_not_peak_speed",
            "A performance gain must reduce elapsed time over a qualified physical scope.",
            measured_time,
            no_local_proxy,
        ),
        _principle(
            "performance_connects_downstream",
            "Entry changes center opportunity, center changes throttle opportunity, and exit changes following-straight carry.",
            measured_time + ("connected phase windows",),
            ("one phase can be judged without downstream countereffects",),
        ),
        _principle(
            "origin_differs_from_location",
            "The place where a deficit is visible may differ from the place where it was generated.",
            measured_time + ("cumulative time trace",),
            ("a straight deficit is automatically a powertrain deficit",),
        ),
        _principle(
            "line_and_speed_together",
            "Driven path, speed, and elapsed time must be evaluated together where geometry is available.",
            measured_time
            + ("measured path geometry or an explicit unavailable state",),
            ("a shorter path or higher local speed is automatically faster",),
        ),
        _principle(
            "driver_vehicle_coproduction",
            "Driver demand and vehicle response co-produce the measured result.",
            ("driver-input channels", "vehicle-response channels", "matched context"),
            ("driver caused the loss",),
        ),
        _principle(
            "finite_tire_capability",
            "Braking, turning, and acceleration demands compete for finite tire capability.",
            ("qualified input and response exposure",),
            ("exact tire force or wheel load from unavailable channels",),
            sources=_GENERAL_SOURCES,
        ),
        _principle(
            "setup_redistributes_capability",
            "Setup changes trade response across phases, transients, compliance, peak pace, and durability.",
            ("one-factor controlled evidence", "target and protected outcomes"),
            ("generic setup knowledge authorizes a change",),
            sources=_GENERAL_SOURCES,
        ),
        _principle(
            "transient_differs_from_steady_state",
            "The transition into a state and the sustained state require separate evidence.",
            ("phase transitions", "sustained phase window"),
            ("a damper observation alone establishes sustained center balance",),
            sources=_GENERAL_SOURCES,
        ),
        _principle(
            "protected_failure_cannot_hide",
            "A local gain cannot cancel a protected stability, safety, tire, workload, or platform failure.",
            ("target outcome", "protected outcomes", "countereffects"),
            ("net time alone overrides a protected failure",),
        ),
        _principle(
            "repeatability_matters",
            "One trace is an observation; repeated qualified laps establish opportunity; A/B/A2 establishes treatment response.",
            ("independent eligible laps", "empirical noise basis"),
            ("one unusually fast lap is repeatable evidence",),
        ),
        _principle(
            "objective_changes_policy_not_physics",
            "The objective changes protected outcomes and P19 policy, not measured elapsed time.",
            ("one measured time basis", "typed objective envelope"),
            ("objective selection rewrites measured time",),
        ),
        _principle(
            "exact_history_outranks_generic",
            "Current exact evidence and exact-context controlled history outrank generic component knowledge.",
            ("exact context identity", "P19 verdict provenance"),
            ("generic knowledge outranks an exact Undo",),
        ),
    )


def _mechanism(
    mechanism_id: str,
    phases: tuple[str, ...],
    telemetry: tuple[str, ...],
    metrics: tuple[str, ...],
    outcome: str,
) -> PerformanceMechanismDefinition:
    return PerformanceMechanismDefinition(
        mechanism_id=mechanism_id,
        statement=f"Ask whether measured {mechanism_id.replace('_', ' ')} changed time; do not assume cause.",
        operating_phases=phases,
        required_telemetry=telemetry,
        derived_metrics=metrics,
        driver_confounders=("input timing", "input magnitude", "racing line"),
        context_blockers=(
            "traffic",
            "junk lap",
            "incomplete physical coverage",
            "unmatched tire or fuel state",
        ),
        p20_mechanism_families=(
            "driver_execution",
            "braking_response",
            "corner_rotation",
            "tire_state",
            "platform_response",
            "powertrain_response",
        ),
        p26_component_families=_MECHANISM_COMPONENTS[mechanism_id],
        performance_outcomes=(outcome,),
        countereffects=(
            "A local gain may surrender time or violate a protected outcome downstream.",
        ),
        forbidden_claims=(
            "This performance question establishes component cause or setup authority.",
        ),
        source_ids=_TIME_SOURCE + _GENERAL_SOURCES,
    )


@lru_cache(maxsize=1)
def performance_mechanisms() -> tuple[PerformanceMechanismDefinition, ...]:
    specs = (
        (
            "braking_realization",
            ("braking",),
            ("brake_pct", "long_accel", "speed_mph"),
            ("brake onset", "deceleration response"),
            "entry_time",
        ),
        (
            "brake_release_transition",
            ("braking", "entry"),
            ("brake_pct", "steering_deg", "yaw_rate"),
            ("release timing", "yaw buildup"),
            "entry_time",
        ),
        (
            "turn_in_response",
            ("entry",),
            ("steering_deg", "yaw_rate", "speed_mph"),
            ("steering demand", "yaw response"),
            "entry_time",
        ),
        (
            "entry_rotation",
            ("entry",),
            ("steering_deg", "yaw_rate", "lat_accel"),
            ("entry yaw response",),
            "entry_time",
        ),
        (
            "center_rotation",
            ("center",),
            ("steering_deg", "yaw_rate", "speed_mph"),
            ("center steering demand", "center yaw response"),
            "center_time",
        ),
        (
            "speed_retention",
            ("center",),
            ("speed_mph", "session_time"),
            ("phase speed profile", "phase elapsed time"),
            "center_time",
        ),
        (
            "throttle_realization",
            ("exit",),
            ("throttle_pct", "steering_deg", "long_accel"),
            ("throttle pickup", "usable acceleration"),
            "exit_time",
        ),
        (
            "exit_traction",
            ("exit",),
            ("throttle_pct", "rear_wheel_speed_mismatch", "long_accel"),
            ("wheel-speed mismatch", "exit acceleration"),
            "exit_time",
        ),
        (
            "exit_carry",
            ("exit", "straight"),
            ("speed_mph", "session_time"),
            ("downstream speed markers", "delta persistence"),
            "following_straight_time",
        ),
        (
            "straight_acceleration",
            ("straight",),
            ("throttle_pct", "speed_mph", "long_accel"),
            ("full-throttle acceleration response",),
            "straight_time",
        ),
        (
            "gearing_headroom",
            ("straight",),
            ("rpm", "gear", "speed_mph"),
            ("RPM headroom", "shift zones"),
            "straight_time",
        ),
        (
            "path_efficiency",
            ("entry", "center", "exit"),
            ("lat", "lon", "session_time"),
            ("driven distance", "elapsed time"),
            "complete_corner_time",
        ),
        (
            "stability_workload",
            _ALL_PHASES,
            ("steering_deg", "yaw_rate"),
            ("steering correction demand",),
            "repeatability",
        ),
        (
            "tire_state_migration",
            _ALL_PHASES,
            ("speed_mph", "steering_deg", "lap"),
            ("qualified lap-to-lap response migration",),
            "long_run_pace",
        ),
        (
            "platform_consistency",
            _ALL_PHASES,
            ("cfs_ride_height_in", "speed_mph"),
            ("clearance proxy consistency",),
            "repeatability",
        ),
        (
            "disturbance_compliance",
            ("transition", "center", "exit"),
            ("vert_accel", "shock_vel_in_s"),
            ("disturbance response",),
            "repeatability",
        ),
        (
            "traffic_robustness",
            _ALL_PHASES,
            ("car_distance_ahead_m", "car_distance_behind_m"),
            ("traffic exposure",),
            "traffic_robustness",
        ),
    )
    return tuple(_mechanism(*spec) for spec in specs)


@lru_cache(maxsize=1)
def performance_outcomes() -> tuple[PerformanceOutcome, ...]:
    return (
        PerformanceOutcome(
            outcome_id="peak_eligible_lap",
            label="Peak eligible lap",
            measured_by=("eligible lap time",),
            protected_outcomes=("control", "stability", "tech legality"),
        ),
        PerformanceOutcome(
            outcome_id="average_race_pace",
            label="Average race pace",
            measured_by=("eligible stint lap times",),
            protected_outcomes=("falloff", "traffic behavior"),
        ),
        PerformanceOutcome(
            outcome_id="long_run_falloff",
            label="Long-run falloff",
            measured_by=("qualified lap-to-lap pace migration",),
            protected_outcomes=("tire state", "driver corrections"),
        ),
        PerformanceOutcome(
            outcome_id="traffic_robustness",
            label="Traffic robustness",
            measured_by=("context-qualified traffic laps",),
            protected_outcomes=("control", "exit security"),
        ),
        PerformanceOutcome(
            outcome_id="tire_conservation",
            label="Tire conservation",
            measured_by=("long-run pace and tire-state development",),
            protected_outcomes=("peak pace", "stability"),
        ),
        PerformanceOutcome(
            outcome_id="driver_confidence",
            label="Driver confidence",
            measured_by=("repeatability", "correction workload"),
            protected_outcomes=("control",),
        ),
        PerformanceOutcome(
            outcome_id="repeatability",
            label="Repeatability",
            measured_by=("independent eligible lap dispersion",),
            protected_outcomes=("context integrity",),
        ),
        PerformanceOutcome(
            outcome_id="fuel_efficiency",
            label="Fuel efficiency",
            measured_by=("fuel-normalized elapsed time",),
            protected_outcomes=("pace", "power delivery"),
        ),
    )


def objective_envelope(objective: EngineeringObjective) -> PerformanceObjectiveEnvelope:
    primary = {
        EngineeringObjective.QUALIFYING_PEAK: ("peak_eligible_lap",),
        EngineeringObjective.RACE_LONG_RUN: (
            "average_race_pace",
            "long_run_falloff",
            "repeatability",
        ),
        EngineeringObjective.TIRE_CONSERVATION: (
            "tire_conservation",
            "long_run_falloff",
        ),
        EngineeringObjective.DRIVER_CONFIDENCE: ("driver_confidence", "repeatability"),
        EngineeringObjective.TRAFFIC_ROBUSTNESS: (
            "traffic_robustness",
            "average_race_pace",
        ),
        EngineeringObjective.SUPERSPEEDWAY_STABILITY: (
            "repeatability",
            "traffic_robustness",
        ),
        EngineeringObjective.FUEL_STRATEGY: ("fuel_efficiency", "average_race_pace"),
    }[objective]
    protected = {
        EngineeringObjective.QUALIFYING_PEAK: ("control", "stability", "tech legality"),
        EngineeringObjective.RACE_LONG_RUN: (
            "falloff",
            "tire state",
            "driver corrections",
            "traffic behavior",
            "exit security",
        ),
        EngineeringObjective.TIRE_CONSERVATION: (
            "control",
            "repeatability",
            "exit security",
        ),
        EngineeringObjective.DRIVER_CONFIDENCE: (
            "stability",
            "control",
            "repeatability",
        ),
        EngineeringObjective.TRAFFIC_ROBUSTNESS: (
            "control",
            "line flexibility",
            "exit security",
        ),
        EngineeringObjective.SUPERSPEEDWAY_STABILITY: (
            "platform consistency",
            "control",
            "traffic context",
        ),
        EngineeringObjective.FUEL_STRATEGY: (
            "power delivery",
            "pace",
            "temperature margin",
        ),
    }[objective]
    return PerformanceObjectiveEnvelope(
        objective_id=objective.value,
        primary_outcomes=primary,
        protected_outcomes=protected,
        countereffect_limits=tuple(f"P19 must protect {item}." for item in protected),
        measurement_requirements=(
            "eligible laps",
            "physical-position elapsed time",
            "objective-qualified context",
        ),
        policy_note="Objective selection changes Keep/Undo policy only; the measured time basis is unchanged and P19 remains final authority.",
    )


def _lap_time_key(lap: Any) -> tuple[float, int]:
    value = _finite(getattr(lap, "lap_time", None))
    return (value if value is not None and value > 0 else math.inf, lap.lap_number)


def _qualified(overview: Any) -> tuple[Any, ...]:
    if overview is None or engineering_blockers_for(
        overview.engineering_blockers,
        EngineeringBlockTarget.PERFORMANCE,
        EngineeringBlockTarget.COMPARISON,
    ):
        return ()
    return tuple(sorted(eligible_laps(overview.laps), key=_lap_time_key))


def _compatibility_assessment(
    baseline_run_id: str,
    test_run_id: str,
) -> tuple[bool, tuple[str, ...]]:
    """Mirror Compare's canonical full manifest-identity gate, fail closed."""
    try:
        baseline = (
            read_telemetry_manifest(baseline_run_id).get("compatibility_identity")
            or {}
        )
        test = (
            read_telemetry_manifest(test_run_id).get("compatibility_identity") or {}
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        return False, (
            "manifest compatibility identity is unavailable: "
            f"{type(exc).__name__}: {exc}",
        )
    missing = [
        label
        for key, label in _COMPATIBILITY_FIELDS.items()
        if baseline.get(key) is None or test.get(key) is None
    ]
    mismatches = [
        label
        for key, label in _COMPATIBILITY_FIELDS.items()
        if baseline.get(key) is not None
        and test.get(key) is not None
        and str(baseline.get(key)) != str(test.get(key))
    ]
    for key, label in _OPTIONAL_COMPATIBILITY_FIELDS.items():
        baseline_value = baseline.get(key)
        test_value = test.get(key)
        if (baseline_value is None) != (test_value is None):
            missing.append(label)
        elif baseline_value is not None and str(baseline_value) != str(test_value):
            mismatches.append(label)
    reasons = tuple(
        (
            *(f"missing {label}" for label in missing),
            *(f"mismatched {label}" for label in mismatches),
        )
    )
    return not reasons, reasons


def _pair(
    run_id: str,
    scope_run_ids: Sequence[str],
    repository: RaceLabRepository,
    overview: Any,
) -> tuple[Any | None, Any | None, Any | None, str, tuple[str, ...]]:
    current = _qualified(overview)
    if not current:
        return (
            None,
            None,
            None,
            "unavailable",
            ("No eligible current-run lap is available.",),
        )
    source = current[0]
    ordered = tuple(scope_run_ids)
    if run_id in ordered and ordered.index(run_id) > 0:
        reference_run_id = ordered[ordered.index(run_id) - 1]
        reference_overview = repository.get_overview(reference_run_id)
        reference = _qualified(reference_overview)
        compatible, compatibility_reasons = _compatibility_assessment(
            reference_run_id, run_id
        )
        if reference and compatible:
            return source, reference[0], reference_overview, "compatible", ()
        compatibility_blocker = (
            "Prior run is not compatible under the canonical manifest identity gate: "
            + ", ".join(compatibility_reasons)
            + "."
            if compatibility_reasons
            else "Prior run has no eligible reference lap."
        )
    if len(current) >= 2:
        return (
            current[1],
            current[0],
            overview,
            "same_run",
            (
                (
                    compatibility_blocker
                    if "compatibility_blocker" in locals()
                    else "No compatible prior run exists."
                ),
                "P32 uses a within-run eligible-lap comparison.",
            ),
        )
    return (
        source,
        None,
        None,
        "unavailable",
        (
            *(
                (compatibility_blocker,)
                if "compatibility_blocker" in locals()
                else ()
            ),
            "A second eligible same-scope lap or compatible prior run is required for time attribution.",
        ),
    )


def _rows(
    run_id: str, lap_number: int
) -> tuple[list[dict[str, Any]], str | None]:
    """Read one verified lap, degrading data-domain failures to typed debt.

    ``TelemetryArtifactIdentityError`` deliberately is not caught here.  An
    immutable evidence-owner/hash failure is a hard integrity error, whereas a
    missing, unreadable, or malformed lap is ordinary evidence unavailability.
    """

    try:
        rows = read_telemetry_rows(run_id, lap=lap_number, columns=list(_COLUMNS))
        lap_numbers = [
            int(row.get("lap", row.get("lap_number", -1))) for row in rows
        ]
    except (FileNotFoundError, OSError, TypeError, ValueError, OverflowError) as exc:
        return [], (
            f"Telemetry lap {lap_number} for run {run_id} is unavailable: "
            f"{type(exc).__name__}: {exc}"
        )
    if len(rows) < 2:
        return [], (
            f"Telemetry lap {lap_number} for run {run_id} has fewer than two samples."
        )
    if any(value != lap_number for value in lap_numbers):
        return [], (
            f"Telemetry lap {lap_number} for run {run_id} contains mixed lap identities."
        )
    return rows, None


def _traffic_exposure(rows: Sequence[dict[str, Any]]) -> float | None:
    # Keep P32 on the app's canonical asymmetric time-gap proximity screen.
    # That helper requires speed plus both distance channels on every sample and
    # returns ``None`` for partial coverage, so missing context fails closed.
    return proximity_time_gap_exposure_fraction(rows)


def _traffic_exposure_window(
    rows: Sequence[dict[str, Any]], start_pct: float, end_pct: float
) -> float | None:
    return _traffic_exposure(
        tuple(
            row
            for row in rows
            if (pct := _finite(row.get("lap_dist_pct_100"))) is not None
            and start_pct <= pct <= end_pct
        )
    )


def _aligned_source_window(
    alignment: TimeAlignmentResult, start_pct: float, end_pct: float
) -> tuple[float, float] | None:
    positions = [
        point.aligned_test_pct
        for point in alignment.alignment
        if start_pct <= point.lap_pct <= end_pct
        and not point.is_gap
        and point.aligned_test_pct is not None
    ]
    return (min(positions), max(positions)) if positions else None


def _track_demand(
    rows: Sequence[dict[str, Any]],
    alignment: TimeAlignmentResult | None,
    opportunity_ids: tuple[str, ...],
    *,
    eligible_lap_count: int = 0,
) -> TrackDemandProfile:
    # This builder receives one qualified source lap.  The overview's eligible
    # lap count is not longitudinal tire-state evidence and cannot make tire
    # development observable here.
    _ = eligible_lap_count
    count = len(rows)
    throttle = [_finite(row.get("throttle_pct")) for row in rows]
    brake = [_finite(row.get("brake_pct")) for row in rows]
    steering = [_finite(row.get("steering_deg")) for row in rows]
    lat_accel = [_finite(row.get("lat_accel")) for row in rows]
    long_accel = [_finite(row.get("long_accel")) for row in rows]
    speeds = [_finite(row.get("speed_mph")) for row in rows]
    if not any(value is not None for value in speeds):
        speeds = [
            value * 2.2369362920544 if value is not None else None
            for value in (_finite(row.get("speed_mps")) for row in rows)
        ]

    def fraction(states: Iterable[bool]) -> float | None:
        values = list(states)
        return sum(values) / len(values) if values else None

    full = fraction(value >= 95 for value in throttle if value is not None)
    braking = fraction(value >= 2 for value in brake if value is not None)
    cornering = fraction(
        abs(angle) >= 3 or abs(lat) >= 0.2
        for angle, lat in zip(steering, lat_accel)
        if angle is not None and lat is not None
    )
    combined = fraction(
        abs(lat) >= 0.2 and abs(long) >= 0.2
        for lat, long in zip(lat_accel, long_accel)
        if lat is not None and long is not None
    )
    corner_durations: list[float] = []
    if alignment:
        for effect in alignment.phase_effects:
            if effect.phase not in _CORNER_PHASES:
                continue
            start_index = nearest_sorted_index(alignment.grid_pct, effect.start_pct)
            end_index = nearest_sorted_index(alignment.grid_pct, effect.end_pct)
            start_time = alignment.baseline_elapsed_s[start_index]
            end_time = alignment.baseline_elapsed_s[end_index]
            if (
                start_time is not None
                and end_time is not None
                and end_time >= start_time
            ):
                corner_durations.append(end_time - start_time)
    carry_lengths = (
        tuple(
            round(effect.end_pct - effect.start_pct, 3)
            for effect in alignment.phase_effects
            if effect.phase == "following_straight_carry"
        )
        if alignment
        else ()
    )
    high_speed = sorted(value for value in speeds if value is not None)
    load_bands = ()
    if high_speed:
        load_bands = tuple(
            round(high_speed[int((len(high_speed) - 1) * pct)], 1)
            for pct in (0.5, 0.75, 0.9)
        )
    vertical_g: list[float | None] = [
        _finite(row.get("vert_accel_g")) for row in rows
    ]
    if not any(value is not None for value in vertical_g):
        vertical_g = [
            value / 9.80665 if value is not None else None
            for row in rows
            for value in (_finite(row.get("vert_accel")),)
        ]
    # The accelerometer carries gravity, banking, and sustained load.  Use a
    # short physical-position rolling median so only transient departure from
    # the local load state contributes; the normal/banked baseline never does.
    residuals: list[float | None] = []
    radius = 7
    for index, value in enumerate(vertical_g):
        neighborhood = [
            candidate
            for candidate in vertical_g[
                max(0, index - radius) : min(len(vertical_g), index + radius + 1)
            ]
            if candidate is not None
        ]
        residuals.append(
            abs(value - median(neighborhood))
            if value is not None and neighborhood
            else None
        )
    measured_residuals = [value for value in residuals if value is not None]
    residual_center = median(measured_residuals) if measured_residuals else None
    residual_mad = (
        median(abs(value - residual_center) for value in measured_residuals)
        if residual_center is not None
        else None
    )
    vertical_threshold = (
        max(0.35, residual_center + 6.0 * residual_mad)
        if residual_center is not None and residual_mad is not None
        else None
    )
    shock_activity_by_row: list[float | None] = []
    for row in rows:
        shock_values = [
            abs(value)
            for corner in ("lf", "rf", "lr", "rr")
            if (value := _finite(row.get(f"{corner}_shock_vel_in_s"))) is not None
        ]
        shock_activity_by_row.append(max(shock_values) if shock_values else None)
    measured_shock = [value for value in shock_activity_by_row if value is not None]
    shock_center = median(measured_shock) if measured_shock else None
    shock_mad = (
        median(abs(value - shock_center) for value in measured_shock)
        if shock_center is not None
        else None
    )
    shock_threshold = (
        max(4.0, shock_center + 8.0 * shock_mad)
        if shock_center is not None and shock_mad is not None
        else None
    )
    disturbance_states: list[bool] = []
    for index, row in enumerate(rows):
        vertical_deviation = residuals[index]
        shock_activity = shock_activity_by_row[index]
        if vertical_deviation is not None or shock_activity is not None:
            disturbance_states.append(
                bool(
                    (
                        vertical_deviation is not None
                        and vertical_threshold is not None
                        and vertical_deviation >= vertical_threshold
                    )
                    or (
                        shock_activity is not None
                        and shock_threshold is not None
                        and shock_activity >= shock_threshold
                    )
                )
            )
    disturbance = fraction(disturbance_states)
    shifts: list[str] = []
    for left, right in zip(rows, rows[1:]):
        left_gear = _finite(left.get("gear"))
        right_gear = _finite(right.get("gear"))
        pct = _finite(right.get("lap_dist_pct_100"))
        if None not in (left_gear, right_gear, pct) and left_gear != right_gear:
            shifts.append(f"{pct:.1f}% gear {int(left_gear)}-{int(right_gear)}")
    usable_speeds = [value for value in speeds if value is not None]
    blockers: list[str] = []
    if count < 2:
        blockers.append("Track demand requires a qualified telemetry lap.")
    if not usable_speeds:
        blockers.append("Speed range is unavailable.")
    blockers.append(
        "Limiter zones are unavailable without a reviewed direct limiter-status signal."
    )
    if count:
        blockers.append(
            "Tire-state development is unavailable from one inspected lap; "
            "a qualified multi-lap tire-state analysis is required."
        )
    traffic_exposure = _traffic_exposure(rows)
    if count and traffic_exposure is None:
        blockers.append(
            "Nearby-car exposure is unavailable because speed/ahead/behind "
            "coverage is incomplete."
        )
    return TrackDemandProfile(
        full_throttle_fraction=round(full, 4) if full is not None else None,
        braking_fraction=round(braking, 4) if braking is not None else None,
        cornering_fraction=round(cornering, 4) if cornering is not None else None,
        speed_min_mph=round(min(usable_speeds), 3) if usable_speeds else None,
        speed_max_mph=round(max(usable_speeds), 3) if usable_speeds else None,
        median_corner_duration_s=round(median(corner_durations), 3)
        if corner_durations
        else None,
        following_straight_carry_lengths_pct=carry_lengths,
        combined_acceleration_fraction=round(combined, 4)
        if combined is not None
        else None,
        platform_load_speed_bands_mph=load_bands,
        disturbance_exposure_fraction=round(disturbance, 4)
        if disturbance is not None
        else None,
        traffic_exposure_fraction=round(traffic_exposure, 4)
        if traffic_exposure is not None
        else None,
        tire_state_development="short_run" if count else "unavailable",
        shift_zones=tuple(shifts[:12]),
        limiter_zones=(),
        shift_limiter_zones=(),
        dominant_measured_opportunity_ids=opportunity_ids[:3],
        source_channels=_unique(
            channel
            for channel in _COLUMNS
            if any(row.get(channel) is not None for row in rows)
        ),
        blockers=tuple(blockers),
    )


def _aligned_channels(
    reference_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    alignment: TimeAlignmentResult,
) -> tuple[dict[str, list[float | None]], dict[str, list[float | None]]]:
    reference = interpolate_run_to_grid(
        reference_rows, list(_STATE_CHANNELS), alignment.grid_pct
    )
    raw_source = interpolate_run_to_grid(
        source_rows, list(_STATE_CHANNELS), alignment.grid_pct
    )
    source: dict[str, list[float | None]] = {channel: [] for channel in _STATE_CHANNELS}
    for point in alignment.alignment:
        for channel in _STATE_CHANNELS:
            if point.aligned_test_pct is None or point.is_gap:
                source[channel].append(None)
            else:
                index = nearest_sorted_index(alignment.grid_pct, point.aligned_test_pct)
                source[channel].append(raw_source[channel][index])
    return reference, source


def _path_length_m(
    data: dict[str, list[float | None]], indices: Sequence[int]
) -> float | None:
    points = [
        (data["lat"][index], data["lon"][index])
        for index in indices
        if data["lat"][index] is not None and data["lon"][index] is not None
    ]
    if len(points) < 2:
        return None
    total = 0.0
    for (left_lat, left_lon), (right_lat, right_lon) in zip(points, points[1:]):
        assert None not in (left_lat, left_lon, right_lat, right_lon)
        lat_scale = 111_132.0
        lon_scale = 111_320.0 * math.cos(math.radians((left_lat + right_lat) / 2))
        total += math.hypot(
            (right_lat - left_lat) * lat_scale, (right_lon - left_lon) * lon_scale
        )
    return total


def _line_separation_m(
    reference: dict[str, list[float | None]],
    source: dict[str, list[float | None]],
    indices: Sequence[int],
) -> float | None:
    separations: list[float] = []
    for index in indices:
        reference_lat = reference["lat"][index]
        reference_lon = reference["lon"][index]
        source_lat = source["lat"][index]
        source_lon = source["lon"][index]
        if None in (reference_lat, reference_lon, source_lat, source_lon):
            continue
        assert reference_lat is not None
        assert reference_lon is not None
        assert source_lat is not None
        assert source_lon is not None
        lat_scale = 111_132.0
        lon_scale = 111_320.0 * math.cos(
            math.radians((reference_lat + source_lat) / 2)
        )
        separations.append(
            math.hypot(
                (source_lat - reference_lat) * lat_scale,
                (source_lon - reference_lon) * lon_scale,
            )
        )
    return median(separations) if separations else None


def _driver_demand_coverage(
    rows: Sequence[dict[str, Any]], start_pct: float, end_pct: float
) -> float | None:
    scoped = [
        row
        for row in rows
        if (pct := _finite(row.get("lap_dist_pct_100"))) is not None
        and start_pct <= pct <= end_pct
    ]
    if not scoped:
        return None
    complete = sum(
        all(
            _finite(row.get(channel)) is not None
            for channel in ("throttle_pct", "brake_pct", "steering_deg")
        )
        for row in scoped
    )
    return complete / len(scoped)


def _phase_state(
    name: str,
    effects: Sequence[PhaseTimeEffect],
    alignment: TimeAlignmentResult,
    reference: dict[str, list[float | None]],
    source: dict[str, list[float | None]],
    reference_rows: Sequence[dict[str, Any]] = (),
    source_rows: Sequence[dict[str, Any]] = (),
) -> PerformancePhaseState | None:
    selected = [effect for effect in effects if effect.phase in _PHASE_GROUPS[name]]
    if not selected:
        return None
    start = min(effect.start_pct for effect in selected)
    end = max(effect.end_pct for effect in selected)
    indices = [
        index for index, pct in enumerate(alignment.grid_pct) if start <= pct <= end
    ]

    def delta(channel: str) -> float | None:
        values = [
            test - baseline
            for index in indices
            if (baseline := reference[channel][index]) is not None
            and (test := source[channel][index]) is not None
        ]
        return _median(values)

    elapsed_values = [
        effect.delta_s for effect in selected if effect.delta_s is not None
    ]
    reference_path = _path_length_m(reference, indices)
    source_path = _path_length_m(source, indices)
    path_delta = (
        source_path - reference_path
        if reference_path is not None and source_path is not None
        else None
    )
    line_separation = _line_separation_m(reference, source, indices)
    aligned_source_positions = [
        alignment.alignment[index].aligned_test_pct
        for index in indices
        if not alignment.alignment[index].is_gap
        and alignment.alignment[index].aligned_test_pct is not None
    ]
    source_start = min(aligned_source_positions) if aligned_source_positions else start
    source_end = max(aligned_source_positions) if aligned_source_positions else end
    reference_demand_coverage = _driver_demand_coverage(reference_rows, start, end)
    source_demand_coverage = _driver_demand_coverage(
        source_rows, source_start, source_end
    )
    values = {
        "elapsed_delta_s": sum(elapsed_values) if elapsed_values else None,
        "speed_delta_mph": delta("speed_mph"),
        "throttle_delta_pct": delta("throttle_pct"),
        "brake_delta_pct": delta("brake_pct"),
        "steering_delta_deg": delta("steering_deg"),
        "yaw_rate_delta": delta("yaw_rate"),
        "long_accel_delta": delta("long_accel"),
        "path_delta_m": path_delta,
        "line_separation_m": line_separation,
    }
    measured = any(value is not None for value in values.values())
    return PerformancePhaseState(
        phase=name,
        start_pct=start,
        end_pct=end,
        **{
            key: round(value, 6) if value is not None else None
            for key, value in values.items()
        },
        driver_demand_source_coverage=source_demand_coverage,
        driver_demand_reference_coverage=reference_demand_coverage,
        evidence_state="measured" if measured else "unavailable",
        source_channels=_unique(
            channel
            for channel, value in (
                ("session_time", values["elapsed_delta_s"]),
                ("speed_mph", values["speed_delta_mph"]),
                ("throttle_pct", values["throttle_delta_pct"]),
                ("brake_pct", values["brake_delta_pct"]),
                ("steering_deg", values["steering_delta_deg"]),
                ("yaw_rate", values["yaw_rate_delta"]),
                ("long_accel", values["long_accel_delta"]),
                ("lat/lon", values["path_delta_m"]),
                ("lat/lon", values["line_separation_m"]),
            )
            if value is not None
        ),
        blockers=() if measured else ("No co-observed phase values are available.",),
    )


def _separation(
    run_id: str,
    state: PerformancePhaseState,
    *,
    traffic: bool,
    context_unknown: bool = False,
) -> DriverVehicleSeparation:
    demand_values = (
        state.throttle_delta_pct,
        state.brake_delta_pct,
        state.steering_delta_deg,
    )
    demand_complete = all(value is not None for value in demand_values) and all(
        value is not None and value >= 1.0
        for value in (
            state.driver_demand_source_coverage,
            state.driver_demand_reference_coverage,
        )
    )
    demand_changed = any(
        value is not None and abs(value) > threshold
        for value, threshold in zip(demand_values, (5.0, 3.0, 2.0))
    )
    response_changed = any(
        value is not None and abs(value) > threshold
        for value, threshold in (
            (state.speed_delta_mph, 1.0),
            (state.yaw_rate_delta, 0.5),
            (state.long_accel_delta, 0.15),
        )
    )
    line_changed = (
        state.line_separation_m is not None and state.line_separation_m > 1.0
    ) or (
        state.line_separation_m is None
        and state.path_delta_m is not None
        and abs(state.path_delta_m) > 1.0
    )
    time_changed = (
        state.elapsed_delta_s is not None and abs(state.elapsed_delta_s) > 0.02
    )
    blockers: list[str] = []
    contradictions: list[str] = []
    support: list[str] = []
    if traffic:
        result = DriverVehicleResult.CONTEXT_CONTAMINATED
        blockers.append("Traffic exposure blocks driver/vehicle attribution.")
    elif context_unknown:
        result = DriverVehicleResult.CONTEXT_CONTAMINATED
        blockers.append(
            "Nearby-car context is unavailable for one or both phase windows."
        )
    elif line_changed:
        result = DriverVehicleResult.CONTEXT_CONTAMINATED
        blockers.append(
            "Measured path changed; driver-line attribution remains confounded."
        )
    elif not demand_complete:
        result = DriverVehicleResult.UNRESOLVED
        blockers.append(
            "Throttle, brake, and steering demand must all be co-observed with "
            "complete phase-window coverage on both laps before inputs can be "
            "classified as matched."
        )
    elif demand_changed and response_changed:
        result = DriverVehicleResult.MIXED_CHANGE
        contradictions.append("Driver demand and vehicle response changed together.")
    elif demand_changed:
        result = DriverVehicleResult.DRIVER_EXECUTION_CHANGED
        support.append(
            "Input demand changed before an isolated vehicle-response claim could be made."
        )
    elif response_changed:
        result = DriverVehicleResult.VEHICLE_RESPONSE_CHANGED_WITH_MATCHED_INPUTS
        support.append(
            "Vehicle response changed while phase-level driver demand stayed within deterministic matching bands."
        )
    else:
        result = DriverVehicleResult.UNRESOLVED
        blockers.append(
            "No demand/response change cleared the deterministic comparison bands."
        )
    return DriverVehicleSeparation(
        separation_id=f"p32d-{canonical_json_sha256([run_id, state.phase, state.start_pct, state.end_pct])[:20]}",
        phase=state.phase,
        driver_demand_changed=demand_changed if demand_complete else None,
        vehicle_response_changed=response_changed,
        line_changed=line_changed,
        context_changed=True if traffic else None if context_unknown else False,
        time_changed=time_changed,
        result=result,
        support=tuple(support),
        contradictions=tuple(contradictions),
        blockers=tuple(blockers),
    )


def _region_for(
    effect: PhaseTimeEffect, segments: Sequence[Any]
) -> tuple[str, str | None]:
    midpoint = (effect.start_pct + effect.end_pct) / 2
    matching = [
        segment
        for segment in segments
        if segment.pct_start <= midpoint <= segment.pct_end
    ]
    if not matching:
        return f"{effect.start_pct:.1f}-{effect.end_pct:.1f}%", None
    selected = min(matching, key=lambda segment: segment.pct_end - segment.pct_start)
    label = selected.segment_name
    turn = label if label.casefold().startswith(("turn", "t")) else None
    return label, turn


def _origin(
    effect: PhaseTimeEffect,
    entry: float | None,
    exit_value: float | None,
    threshold: float,
) -> TimeOriginKind:
    local = effect.delta_s
    if local is None or entry is None or exit_value is None:
        return TimeOriginKind.UNAVAILABLE
    entry_sign = 1 if entry > threshold else -1 if entry < -threshold else 0
    local_sign = 1 if local > threshold else -1 if local < -threshold else 0
    exit_sign = 1 if exit_value > threshold else -1 if exit_value < -threshold else 0
    if entry_sign < 0 and local_sign > 0:
        return TimeOriginKind.SURRENDERED
    if entry_sign > 0 and local_sign < 0:
        return TimeOriginKind.RECOVERED
    if entry_sign != 0 and local_sign == entry_sign:
        return TimeOriginKind.AMPLIFIED
    if entry_sign != 0 and local_sign == 0:
        return TimeOriginKind.CARRIED_IN
    if entry_sign == 0 and exit_sign != 0:
        return TimeOriginKind.LOCAL_GENERATION
    return TimeOriginKind.UNAVAILABLE


def _adjacent_following_effect(
    effect: PhaseTimeEffect,
    effects: Sequence[PhaseTimeEffect],
) -> PhaseTimeEffect | None:
    """Return only the physically adjacent following straight, including S/F wrap."""
    ordered = sorted(effects, key=lambda item: (item.start_pct, item.end_pct))
    try:
        effect_index = next(index for index, item in enumerate(ordered) if item is effect)
    except StopIteration:
        return None
    if effect_index + 1 < len(ordered):
        next_effect = ordered[effect_index + 1]
        if (
            next_effect.phase in {"following_straight_carry", "straight"}
            and -1e-6 <= next_effect.start_pct - effect.end_pct <= 0.4
        ):
            return next_effect
    if effect.end_pct >= 99.6:
        first = ordered[0] if ordered else None
        if (
            first is not None
            and first is not effect
            and first.phase in {"following_straight_carry", "straight"}
            and first.start_pct <= 0.4
        ):
            return first
    return None


def _contiguous_persistence_distance(
    alignment: TimeAlignmentResult,
    *,
    end_index: int,
    end_pct: float,
    threshold: float,
    baseline_value: float = 0.0,
) -> float | None:
    """Measure one uninterrupted deficit; stop at first recovery or gap."""
    exit_value = alignment.cumulative_delta_s[end_index]
    if exit_value is None:
        return None
    contribution = exit_value - baseline_value
    if abs(contribution) <= threshold:
        return None
    sign = 1.0 if contribution > 0 else -1.0
    last_pct = end_pct
    for index in range(end_index + 1, len(alignment.grid_pct)):
        value = alignment.cumulative_delta_s[index]
        if value is None or sign * (value - baseline_value) <= threshold:
            break
        last_pct = alignment.grid_pct[index]
    return max(0.0, last_pct - end_pct)


def _opportunities(
    run_id: str,
    source_lap: int,
    reference_lap: int,
    alignment: TimeAlignmentResult,
    segments: Sequence[Any],
    bundle: RunIntelligenceBundle,
    p26: Any | None,
    traffic: bool,
    *,
    source_rows: Sequence[dict[str, Any]] = (),
    reference_rows: Sequence[dict[str, Any]] = (),
    source_traffic_fraction: float | None = None,
    reference_traffic_fraction: float | None = None,
    traffic_context_unknown: bool = False,
    current_setup_id: str | None = None,
) -> tuple[LapTimeOpportunity, ...]:
    noise_values = (
        alignment.noise.bootstrap_low_s,
        alignment.noise.bootstrap_high_s,
    )
    threshold = max(
        0.02,
        abs(noise_values[1] - noise_values[0]) / 2
        if None not in noise_values
        else 0.05,
    )
    signatures = tuple(
        getattr(bundle.report.opportunity_signature, "signatures", ()) or ()
    )
    leading_components = set(getattr(p26, "leading_component_ids", ()))
    opportunities: list[LapTimeOpportunity] = []
    for effect in alignment.phase_effects:
        start_index = nearest_sorted_index(alignment.grid_pct, effect.start_pct)
        end_index = nearest_sorted_index(alignment.grid_pct, effect.end_pct)
        entry = alignment.cumulative_delta_s[start_index]
        exit_value = alignment.cumulative_delta_s[end_index]
        origin = _origin(effect, entry, exit_value, threshold)
        if origin is TimeOriginKind.UNAVAILABLE:
            continue
        region, turn = _region_for(effect, segments)
        repeated = next(
            (
                signature
                for signature in signatures
                if signature.phase == effect.phase
                and abs(effect.start_pct - signature.lap_pct_start) <= 0.2
                and abs(effect.end_pct - signature.lap_pct_end) <= 0.2
                and getattr(signature, "run_id", None) == run_id
                and current_setup_id is not None
                and getattr(signature, "setup_id", None) == current_setup_id
                and effect.delta_s is not None
                and (getattr(signature, "median_opportunity_s", 0.0) or 0.0)
                * effect.delta_s
                > 0.0
            ),
            None,
        )
        mechanisms = list(_PHASE_MECHANISMS.get(effect.phase, ("stability_workload",)))
        contradictions: list[str] = []
        source_scope = _aligned_source_window(
            alignment, effect.start_pct, effect.end_pct
        )
        source_window_traffic = (
            _traffic_exposure_window(source_rows, *source_scope)
            if source_scope is not None
            else None
        )
        reference_window_traffic = _traffic_exposure_window(
            reference_rows, effect.start_pct, effect.end_pct
        )
        window_context_materialized = bool(source_rows or reference_rows)
        opportunity_traffic = (
            any(
                value is not None and value > 0.0
                for value in (source_window_traffic, reference_window_traffic)
            )
            if window_context_materialized
            else traffic
        )
        opportunity_context_unknown = (
            any(
                value is None
                for value in (source_window_traffic, reference_window_traffic)
            )
            if window_context_materialized
            else traffic_context_unknown
        )
        if (
            effect.phase in {"straight", "following_straight_carry"}
            and origin is TimeOriginKind.CARRIED_IN
        ):
            mechanisms = ["exit_carry"]
            contradictions.append(
                "The straight deficit is inherited; it is not a powertrain diagnosis."
            )
        if opportunity_traffic:
            contradictions.append(
                "Traffic exposure blocks vehicle or component attribution."
            )
        elif opportunity_context_unknown:
            contradictions.append(
                "Nearby-car context is unavailable for one or both comparison laps; attribution is blocked."
            )
        components = (
            _unique(
                component
                for mechanism in mechanisms
                for component in _MECHANISM_COMPONENTS[mechanism]
                if not leading_components or component in leading_components
            )
            if p26 is not None
            and not opportunity_traffic
            and not opportunity_context_unknown
            else ()
        )
        if not components:
            contradictions.append(
                "P26 component context is unavailable or no runtime component candidate matches this measured time window."
            )
        contradictions.append(
            "Measured time consequence does not establish component cause or authorize setup."
        )
        persistence = _contiguous_persistence_distance(
            alignment,
            end_index=end_index,
            end_pct=effect.end_pct,
            threshold=threshold,
            baseline_value=(
                0.0 if origin is TimeOriginKind.CARRIED_IN else entry or 0.0
            ),
        )
        following_effect = _adjacent_following_effect(effect, alignment.phase_effects)
        following = following_effect.delta_s if following_effect is not None else None
        if (
            effect.end_pct >= 99.6
            and following_effect is not None
            and following_effect.start_pct <= 0.4
            and following is not None
            and exit_value is not None
            and abs(following) > threshold
            and following * exit_value > 0
        ):
            persistence = max(
                persistence or 0.0,
                following_effect.end_pct - following_effect.start_pct,
            )
        attribution_state = (
            "blocked_by_traffic"
            if opportunity_traffic
            else "blocked_by_context"
            if opportunity_context_unknown
            else "candidate_only"
        )
        opportunities.append(
            LapTimeOpportunity(
                opportunity_id=f"p32o-{canonical_json_sha256([run_id, source_lap, reference_lap, effect.phase, effect.start_pct, effect.end_pct])[:20]}",
                start_pct=effect.start_pct,
                end_pct=effect.end_pct,
                track_region=region,
                turn=turn,
                phase=effect.phase,
                local_delta_s=effect.delta_s,
                cumulative_delta_at_entry_s=entry,
                cumulative_delta_at_exit_s=exit_value,
                origin_kind=origin,
                persistence_distance_pct=round(max(0.0, persistence), 3)
                if persistence is not None
                else None,
                following_phase_effect_s=following,
                following_phase_start_pct=(
                    following_effect.start_pct if following_effect is not None else None
                ),
                following_phase_end_pct=(
                    following_effect.end_pct if following_effect is not None else None
                ),
                repeatability="repeatable" if repeated else "observed_once",
                noise_basis=(
                    f"same-run signature {repeated.signature_id}; empirical noise {repeated.empirical_noise_s:.4f} s"
                    if repeated
                    else f"pair observation; deterministic floor {threshold:.4f} s"
                ),
                source_laps=(source_lap, reference_lap),
                source_channels=tuple(effect.source_channels),
                driver_execution_state="requires typed phase separation",
                vehicle_response_state="candidate only until matched-input separation",
                context_state=(
                    "traffic_contaminated"
                    if opportunity_traffic
                    else "nearby_context_unavailable"
                    if opportunity_context_unknown
                    else "qualified_pair"
                ),
                attribution_state=attribution_state,
                source_traffic_exposure_fraction=source_window_traffic
                if source_window_traffic is not None
                else source_traffic_fraction,
                reference_traffic_exposure_fraction=reference_window_traffic
                if reference_window_traffic is not None
                else reference_traffic_fraction,
                mechanism_candidates=tuple(mechanisms),
                component_candidates=components,
                contradictions=_unique(contradictions),
            )
        )
    return tuple(
        sorted(
            opportunities,
            key=lambda item: (
                0 if (item.local_delta_s or 0.0) > 0 else 1,
                -(item.local_delta_s or 0.0)
                if (item.local_delta_s or 0.0) > 0
                else item.local_delta_s or 0.0,
                item.start_pct,
            ),
        )
    )


def _corner_chains(
    run_id: str,
    source_lap: int,
    reference_lap: int,
    alignment: TimeAlignmentResult,
    reference: dict[str, list[float | None]],
    source: dict[str, list[float | None]],
    reference_rows: Sequence[dict[str, Any]],
    source_rows: Sequence[dict[str, Any]],
    segments: Sequence[Any],
    contradiction: str,
) -> tuple[CornerPerformanceChain, ...]:
    centers = [
        effect
        for effect in alignment.phase_effects
        if effect.phase in _PHASE_GROUPS["center"]
    ]
    if not centers:
        fallback = [
            effect
            for effect in alignment.phase_effects
            if effect.phase in _CORNER_PHASES | {"bump_curb"}
            and effect.delta_s is not None
        ]
        if fallback:
            # Some flat-out ovals never produce a discrete speed trough. Keep
            # the connected chain available around the strongest measured
            # corner episode without pretending that its center was observed.
            centers = [max(fallback, key=lambda effect: abs(effect.delta_s or 0.0))]
    chains: list[CornerPerformanceChain] = []
    for center in centers:
        nearby = [
            effect
            for effect in alignment.phase_effects
            if effect.end_pct >= max(0.0, center.start_pct - 20)
            and effect.start_pct <= min(100.0, center.end_pct + 25)
        ]
        states = {
            name: _phase_state(
                name,
                nearby,
                alignment,
                reference,
                source,
                reference_rows,
                source_rows,
            )
            for name in _PHASE_GROUPS
        }
        separation_items: list[DriverVehicleSeparation] = []
        for state in states.values():
            if state is None:
                continue
            source_scope = _aligned_source_window(
                alignment, state.start_pct, state.end_pct
            )
            exposures = (
                _traffic_exposure_window(source_rows, *source_scope)
                if source_scope is not None
                else None,
                _traffic_exposure_window(
                    reference_rows, state.start_pct, state.end_pct
                ),
            )
            separation_items.append(
                _separation(
                    run_id,
                    state,
                    traffic=any(
                        value is not None and value > 0.0 for value in exposures
                    ),
                    context_unknown=any(value is None for value in exposures),
                )
            )
        separations = tuple(separation_items)
        region, turn = _region_for(center, segments)
        local = sum(
            state.elapsed_delta_s
            for name, state in states.items()
            if name in {"braking", "entry", "center", "exit"}
            and state is not None
            and state.elapsed_delta_s is not None
        )
        carry = states["carry"]
        chains.append(
            CornerPerformanceChain(
                chain_id=f"p32c-{canonical_json_sha256([run_id, source_lap, reference_lap, center.start_pct, center.end_pct])[:20]}",
                track_region=region,
                turn=turn,
                lap_numbers=(source_lap,),
                reference_lap_numbers=(reference_lap,),
                approach_state=states["approach"],
                braking_state=states["braking"],
                entry_state=states["entry"],
                center_state=states["center"],
                exit_state=states["exit"],
                carry_state=carry,
                local_time_effect_s=round(local, 6),
                downstream_time_effect_s=carry.elapsed_delta_s if carry else None,
                driver_vehicle_separation=separations,
                context=_unique(
                    item
                    for separation in separations
                    for item in (
                        "traffic exposed"
                        if separation.context_changed is True
                        else "nearby-car context unavailable"
                        if separation.context_changed is None
                        else "qualified lap pair",
                    )
                ),
                contradictions=_unique(
                    (
                        contradiction,
                        "Minimum speed alone does not represent the center phase.",
                    )
                ),
            )
        )
    return tuple(chains)


def _component_influences(
    p26: Any | None,
    opportunities: Sequence[LapTimeOpportunity],
) -> tuple[ComponentPerformanceInfluence, ...]:
    if p26 is None:
        return ()
    mechanisms_by_component: dict[str, list[str]] = {}
    opportunity_artifacts: dict[str, list[str]] = {}
    for opportunity in opportunities:
        for component in opportunity.component_candidates:
            mechanisms_by_component.setdefault(component, []).extend(
                opportunity.mechanism_candidates
            )
            opportunity_artifacts.setdefault(component, []).append(
                opportunity.opportunity_id
            )
    states = {state.component_id: state for state in p26.component_states}
    influences: list[ComponentPerformanceInfluence] = []
    for component_id, mechanisms in mechanisms_by_component.items():
        state = states.get(component_id)
        if state is None:
            continue
        history = [
            item
            for item in state.controlled_history
            if item.exact_context and item.policy_verdict != "invalid"
        ]
        if history:
            support_state = "controlled_response_observed"
            authority = "controlled_history"
        elif state.current_response_state == "observed":
            support_state = "response_supported"
            authority = "observation_only"
        else:
            support_state = "mechanically_relevant"
            authority = "knowledge_only"
        expected = _unique(
            node.label
            for node in p26.runtime_graph.nodes
            if node.component_id == component_id and node.kind.value == "vehicle_state"
        ) or ("declared component response",)
        measurable = _unique(
            (
                *state.available_live_channel_ids,
                *(
                    certificate.quantity_id
                    for certificate in state.quantity_observability
                ),
                "phase elapsed time",
            )
        )
        contradiction = (
            "Exact Undo history outranks generic mechanical relevance."
            if any(item.policy_verdict == "undo" for item in history)
            else "Mechanical relevance is not component cause or setup authority."
        )
        influences.append(
            ComponentPerformanceInfluence(
                influence_id=f"p32i-{canonical_json_sha256([component_id, sorted(set(mechanisms)), support_state])[:20]}",
                component_id=component_id,
                performance_mechanism_ids=_unique(mechanisms),
                expected_state_ids=expected,
                measurable_through=measurable,
                runtime_support_state=support_state,
                source_artifact_ids=_unique(
                    (
                        *opportunity_artifacts.get(component_id, ()),
                        *state.supporting_artifact_ids,
                    )
                ),
                contradictions=(contradiction,),
                authority=authority,
            )
        )
    return tuple(influences)


def _response_records(p26: Any | None) -> tuple[PerformanceResponseRecord, ...]:
    if p26 is None:
        return ()
    records: list[PerformanceResponseRecord] = []
    seen: set[tuple[str, str]] = set()
    for state in p26.component_states:
        for history in state.controlled_history:
            if not history.exact_context or history.policy_verdict == "invalid":
                continue
            identity = (history.workflow_id, state.component_id)
            if identity in seen:
                continue
            seen.add(identity)
            records.append(
                PerformanceResponseRecord(
                    record_id=f"p32r-{canonical_json_sha256(identity)[:20]}",
                    workflow_id=history.workflow_id,
                    context_run_ids=_unique(
                        (history.source_run_id, *history.stage_run_ids)
                    ),
                    control=history.control_key,
                    component=state.component_id,
                    expected_state=history.metric,
                    observed_state=history.mechanism_state,
                    time_origin=(
                        history.time_origin_phase or "not_materialized_in_legacy_record"
                    ),
                    time_origin_pct=history.time_origin_pct,
                    phase_effect=history.phase,
                    phase_effect_s=history.actual_effect_s,
                    downstream_carry=(
                        "measured following-straight carry"
                        if history.downstream_carry_effect_s is not None
                        else "not_materialized_in_legacy_record"
                    ),
                    downstream_carry_s=history.downstream_carry_effect_s,
                    performance_result=history.control_response,
                    countereffects=history.countereffects,
                    mechanism_assessment=history.mechanism_state,
                    control_response_assessment=history.control_response,
                    policy_verdict=history.policy_verdict,
                    exact_context=history.exact_context,
                )
            )
    return tuple(records)


def _next_move(bundle: RunIntelligenceBundle) -> str:
    action = bundle.report.briefing.action
    return (
        action.instruction
        or action.title
        or "Hold the current setup and complete the P19 measurement plan."
    )


def _projection_hash(payload: dict[str, Any]) -> str:
    return canonical_json_sha256(payload)


def build_performance_intelligence(
    run_id: str,
    *,
    session_id: str,
    scope_run_ids: Sequence[str],
    objective: EngineeringObjective,
    bundle: RunIntelligenceBundle,
    p20: Any,
    p26: Any | None,
    overview: Any,
    repository: RaceLabRepository,
) -> PerformanceIntelligenceProjection:
    """Build one immutable P32 view from the already-owned P19/P20/P26 workspace."""
    database = (
        Path(repository.db_path) if repository.db_path is not None else default_db_path()
    ).resolve()
    try:
        stat = database.stat()
        repository_identity = f"{database}|{stat.st_dev}|{stat.st_ino}"
    except OSError:
        repository_identity = str(database)
    cache_key = canonical_json_sha256(
        {
            "repository": repository_identity,
            "run_id": run_id,
            "session_id": session_id,
            "scope_run_ids": tuple(scope_run_ids),
            "objective": objective.value,
            "reasoning": canonical_json_sha256(bundle.report.reasoning_snapshot),
            "p20": p20.state_revision,
            "p26": getattr(p26, "knowledge_graph_sha256", _P26_UNAVAILABLE_SHA256),
            "setup": getattr(p26, "setup_snapshot_sha256", None),
        }
    )
    with _PROJECTION_CACHE_LOCK:
        cached = _PROJECTION_CACHE.get(cache_key)
        if cached is not None:
            return cached
    (
        source_lap,
        reference_lap,
        reference_overview,
        comparison_compatibility,
        pair_blockers,
    ) = _pair(run_id, scope_run_ids, repository, overview)
    source_rows, source_read_blocker = (
        _rows(run_id, source_lap.lap_number) if source_lap else ([], None)
    )
    reference_run_id = (
        reference_overview.run_id if reference_overview is not None else None
    )
    reference_rows, reference_read_blocker = (
        _rows(reference_run_id, reference_lap.lap_number)
        if reference_run_id and reference_lap
        else ([], None)
    )
    alignment: TimeAlignmentResult | None = None
    blockers = list(pair_blockers)
    blockers.extend(
        item
        for item in (source_read_blocker, reference_read_blocker)
        if item is not None
    )
    if source_rows and reference_rows:
        try:
            alignment = analyze_time_alignment(
                reference_rows,
                source_rows,
                start_pct=0.0,
                end_pct=100.0,
                step_pct=0.2,
            )
        except (TypeError, ValueError, OverflowError, ArithmeticError) as exc:
            blockers.append(
                "Measured lap-time alignment is unavailable: "
                f"{type(exc).__name__}: {exc}"
            )
        else:
            blockers.extend(alignment.warnings)
    elif source_lap is not None:
        blockers.append(
            "Measured lap-time opportunity is unavailable without a qualified reference lap."
        )

    setup_id = overview.setup_snapshot.setup_id
    reference_setup_id = (
        reference_overview.setup_snapshot.setup_id
        if reference_overview is not None
        and reference_overview.setup_snapshot is not None
        else None
    )
    alignment_identity = canonical_json_sha256(
        {
            "run_id": run_id,
            "reference_run_id": reference_run_id,
            "source_lap": source_lap.lap_number if source_lap else None,
            "reference_lap": reference_lap.lap_number if reference_lap else None,
            "setup_id": setup_id,
            "reference_setup_id": reference_setup_id,
            "time_engine": "analyze_time_alignment@0.2pct",
        }
    )
    segments = (
        repository.list_segments(run_id, source_lap.lap_number)
        if source_lap is not None
        else []
    )
    traffic_fraction = _traffic_exposure(source_rows)
    reference_traffic_fraction = _traffic_exposure(reference_rows)
    traffic = any(
        value is not None and value > 0.0
        for value in (traffic_fraction, reference_traffic_fraction)
    )
    traffic_context_unknown = any(
        value is None for value in (traffic_fraction, reference_traffic_fraction)
    )
    opportunities: tuple[LapTimeOpportunity, ...] = ()
    chains: tuple[CornerPerformanceChain, ...] = ()
    if alignment is not None and source_lap is not None and reference_lap is not None:
        opportunities = _opportunities(
            run_id,
            source_lap.lap_number,
            reference_lap.lap_number,
            alignment,
            segments,
            bundle,
            p26,
            traffic,
            source_rows=source_rows,
            reference_rows=reference_rows,
            source_traffic_fraction=traffic_fraction,
            reference_traffic_fraction=reference_traffic_fraction,
            traffic_context_unknown=traffic_context_unknown,
            current_setup_id=setup_id,
        )
        reference_data, source_data = _aligned_channels(
            reference_rows, source_rows, alignment
        )
        strongest = (
            getattr(p26, "strongest_contradiction", None)
            or "No component attribution is established by measured time alone."
        )
        chains = _corner_chains(
            run_id,
            source_lap.lap_number,
            reference_lap.lap_number,
            alignment,
            reference_data,
            source_data,
            reference_rows,
            source_rows,
            segments,
            strongest,
        )
    leading = next(
        (item for item in opportunities if (item.local_delta_s or 0.0) > 0.0),
        None,
    )
    if leading is None:
        leading = next(
            (item for item in opportunities if (item.local_delta_s or 0.0) < 0.0),
            None,
        )
    traffic_contradiction = None
    if leading is not None and leading.attribution_state == "blocked_by_traffic":
        source_window = leading.source_traffic_exposure_fraction
        reference_window = leading.reference_traffic_exposure_fraction
        traffic_contradiction = (
            "Traffic exposure covered the comparison window "
            f"(source {source_window:.1%}, reference {reference_window:.1%})."
            if source_window is not None and reference_window is not None
            else "Traffic exposure covered the comparison window."
        )
    context_contradiction = (
        "Nearby-car context is unavailable for one or both comparison laps."
        if leading is not None
        and leading.attribution_state == "blocked_by_context"
        else None
    )
    strongest_contradiction = (
        traffic_contradiction
        or context_contradiction
        or getattr(p26, "strongest_contradiction", None)
        or (blockers[0] if blockers else "Measured time does not establish component cause.")
    )
    phase_totals = tuple(
        (effect.phase, effect.delta_s)
        for effect in (alignment.phase_effects if alignment else ())
        if effect.delta_s is not None
    )
    opportunity_map = LapTimeOpportunityMap(
        run_id=run_id,
        reference_run_id=reference_run_id,
        setup_id=setup_id,
        reference_setup_id=reference_setup_id,
        physical_alignment_identity=alignment_identity,
        opportunities=opportunities,
        phase_totals_s=phase_totals,
        total_measured_delta_s=alignment.selected_effect_s if alignment else None,
        coverage=alignment.coverage_fraction if alignment else 0.0,
        noise_basis=(
            "eligible lap pair plus same-run repeatability signatures"
            if alignment
            else "unavailable without a qualified reference"
        ),
        context_blockers=_unique(blockers),
        theoretical_composite_s=(
            sum(max(0.0, item.local_delta_s or 0.0) for item in opportunities)
            if opportunities
            else None
        ),
    )
    influences = _component_influences(p26, opportunities)
    records = _response_records(p26)
    separation = next(
        (
            item
            for chain in chains
            for item in chain.driver_vehicle_separation
            if leading is not None and item.phase in leading.phase
        ),
        None,
    )
    driver_text = {
        DriverVehicleResult.DRIVER_EXECUTION_CHANGED: "Driver demand changed before an isolated car-response claim.",
        DriverVehicleResult.VEHICLE_RESPONSE_CHANGED_WITH_MATCHED_INPUTS: "Phase-level inputs are comparable while vehicle response changed.",
        DriverVehicleResult.MIXED_CHANGE: "Driver demand and vehicle response changed together.",
        DriverVehicleResult.CONTEXT_CONTAMINATED: "Line or traffic context blocks driver/car separation.",
        DriverVehicleResult.UNRESOLVED: "Driver/car separation remains unresolved.",
    }.get(separation.result if separation else DriverVehicleResult.UNRESOLVED)
    systems_text = (
        "P26 component context is unavailable; measured time/origin/carry remain available without component attribution."
        if p26 is None
        else (
            ", ".join(item.component_id.replace("_", " ") for item in influences[:3])
            + " remain mechanically relevant; none is established as cause."
            if influences
            else "No P26 component family is supported for attribution in this scope."
        )
    )
    history_text = (
        f"{len(records)} exact controlled performance records are attached; P19 verdicts outrank generic knowledge."
        if records
        else "No exact controlled performance response record is attached."
    )
    if leading:
        signed_effect = leading.local_delta_s or 0.0
        direction = "loss" if signed_effect > 0 else "gain"
        comparative = "slower" if signed_effect > 0 else "faster"
        if leading.attribution_state.startswith("blocked_by_"):
            what = (
                f"Observed {abs(signed_effect):.3f} s {comparative} through "
                f"{leading.track_region} {leading.phase.replace('_', ' ')} in the measured pair."
            )
        elif signed_effect > 0:
            what = f"{leading.track_region} {leading.phase.replace('_', ' ')} costs {signed_effect:.3f} s in the measured pair."
        else:
            what = f"{leading.track_region} {leading.phase.replace('_', ' ')} gains {abs(signed_effect):.3f} s in the measured pair."
        start = (
            f"The {'deficit' if signed_effect > 0 else 'gain'} is classified as "
            f"{leading.origin_kind.value.replace('_', ' ')} at {leading.start_pct:.1f}%."
        )
        carry = (
            f"It remains above the time floor for {leading.persistence_distance_pct:.1f}% of a lap downstream."
            if leading.persistence_distance_pct is not None
            else "No qualified downstream persistence is established."
        )
        blocked_attribution = leading.attribution_state.startswith("blocked_by_")
        if blocked_attribution:
            driver_text = "Driver attribution is blocked by comparison context."
            car_text = "Vehicle-response attribution is blocked by comparison context."
            systems_text = "Component attribution is withheld while comparison context is blocked."
        else:
            car_text = leading.vehicle_response_state
        attribution = {
            "blocked_by_traffic": "Attribution blocked by traffic context.",
            "blocked_by_context": "Attribution blocked by unavailable nearby-car context.",
            "candidate_only": "Attribution remains candidate-only; measured time does not establish cause.",
        }[leading.attribution_state]
        source_context = (
            f"Source lap {source_lap.lap_number} traffic exposure in the window: "
            f"{leading.source_traffic_exposure_fraction:.1%}."
            if source_lap is not None
            and leading.source_traffic_exposure_fraction is not None
            else f"Source lap {source_lap.lap_number if source_lap else 'unavailable'} nearby-car context unavailable."
        )
        reference_context = (
            f"Reference lap {reference_lap.lap_number} traffic exposure in the window: "
            f"{leading.reference_traffic_exposure_fraction:.1%}."
            if reference_lap is not None
            and leading.reference_traffic_exposure_fraction is not None
            else f"Reference lap {reference_lap.lap_number if reference_lap else 'unavailable'} nearby-car context unavailable."
        )
        comparison_window = (
            f"{leading.start_pct:.1f}-{leading.end_pct:.1f}% | {leading.track_region} | "
            f"{leading.phase.replace('_', ' ')}."
        )
        node_ids = _unique(
            (
                leading.opportunity_id,
                separation.separation_id
                if separation
                else "p32.driver-vehicle.unresolved",
                *(item.influence_id for item in influences),
                *(item.record_id for item in records),
                "p19.next-move",
            )
        )
        edges: list[PerformanceExplanationEdge] = []
        if separation:
            edges.append(
                PerformanceExplanationEdge(
                    source_id=separation.separation_id,
                    target_id=leading.opportunity_id,
                    kind="co_observed_with",
                )
            )
        for influence in influences:
            edges.append(
                PerformanceExplanationEdge(
                    source_id=influence.influence_id,
                    target_id=leading.opportunity_id,
                    kind="expected_to_influence",
                )
            )
        for record in records:
            edges.append(
                PerformanceExplanationEdge(
                    source_id=record.record_id,
                    target_id=leading.opportunity_id,
                    kind="controlled_response_observed",
                )
            )
        edges.append(
            PerformanceExplanationEdge(
                source_id=leading.opportunity_id,
                target_id="p19.next-move",
                kind="measured_time_consequence",
            )
        )
    else:
        what = "No qualified repeatable time-loss opportunity is available."
        start = "Time-loss origin is unavailable without a qualified aligned lap pair."
        carry = "Downstream carry is unavailable."
        car_text = "Vehicle response attribution is withheld."
        node_ids = ("p32.opportunity.unavailable", "p19.next-move")
        edges = []
        direction = "unavailable"
        signed_effect = None
        attribution = "Attribution unavailable without a qualified measured difference."
        source_context = "Source context unavailable."
        reference_context = "Reference context unavailable."
        comparison_window = "Comparison window unavailable."
    next_move = _next_move(bundle)
    speed_story = SpeedStory(
        what_costs_time=what,
        where_it_starts=start,
        what_carries=carry,
        driver=driver_text,
        car=car_text,
        systems=systems_text,
        history=history_text,
        strongest_contradiction=strongest_contradiction,
        next=next_move,
        observed_difference_s=signed_effect,
        observed_direction=direction,
        attribution_state=leading.attribution_state if leading else "unavailable",
        attribution=attribution,
        source_context=source_context,
        reference_context=reference_context,
        comparison_window=comparison_window,
    )
    explanation = PerformanceExplanationChain(
        chain_id=f"p32x-{canonical_json_sha256([alignment_identity, node_ids])[:20]}",
        node_ids=node_ids,
        edges=tuple(edges),
        branched=len(influences) > 1,
        strongest_contradiction=strongest_contradiction,
        p19_next_move=next_move,
    )
    basis = RunPerformanceBasis(
        run_id=run_id,
        reference_run_id=reference_run_id,
        setup_id=setup_id,
        reference_setup_id=reference_setup_id,
        source_lap_numbers=(source_lap.lap_number,) if source_lap else (),
        reference_lap_numbers=(reference_lap.lap_number,) if reference_lap else (),
        physical_alignment_identity=alignment_identity,
        qualified_phase_segments=len(alignment.phase_effects) if alignment else 0,
        sample_count=len(source_rows) + len(reference_rows),
        source_channels=_unique(
            channel
            for channel in _COLUMNS
            if any(
                row.get(channel) is not None for row in (*source_rows, *reference_rows)
            )
        ),
        time_basis=alignment.distance_basis if alignment else "unavailable",
        path_basis="measured_lat_lon"
        if any(
            row.get("lat") is not None and row.get("lon") is not None
            for row in source_rows
        )
        else "unavailable",
        coverage=alignment.coverage_fraction if alignment else 0.0,
        comparison_compatibility=comparison_compatibility,
        context_blockers=_unique(blockers),
    )
    payload = {
        "schema_version": "p32.performance-intelligence.v1",
        "run_id": run_id,
        "session_id": session_id,
        "objective_id": objective.value,
        "knowledge_version": _KNOWLEDGE_VERSION,
        "principles": [
            item.model_dump(mode="json") for item in performance_principles()
        ],
        "mechanisms": [
            item.model_dump(mode="json") for item in performance_mechanisms()
        ],
        "outcomes": [item.model_dump(mode="json") for item in performance_outcomes()],
        "objective_envelope": objective_envelope(objective).model_dump(mode="json"),
        "basis": basis.model_dump(mode="json"),
        "opportunity_map": opportunity_map.model_dump(mode="json"),
        "corner_chains": [item.model_dump(mode="json") for item in chains],
        "track_demand": _track_demand(
            source_rows,
            alignment,
            tuple(item.opportunity_id for item in opportunities),
            eligible_lap_count=len(_qualified(overview)),
        ).model_dump(mode="json"),
        "component_influences": [item.model_dump(mode="json") for item in influences],
        "explanation_chain": explanation.model_dump(mode="json"),
        "response_records": [item.model_dump(mode="json") for item in records],
        "speed_story": speed_story.model_dump(mode="json"),
        "p19_reasoning_snapshot_sha256": canonical_json_sha256(
            bundle.report.reasoning_snapshot
        ),
        "p20_state_revision": p20.state_revision,
        "p26_knowledge_graph_sha256": getattr(
            p26, "knowledge_graph_sha256", _P26_UNAVAILABLE_SHA256
        ),
        "component_context_state": "available" if p26 is not None else "unavailable",
        "component_context_blockers": []
        if p26 is not None
        else ["P26 Vehicle Systems projection is unavailable for this workspace."],
        "blockers": list(_unique(blockers)),
    }
    projection = PerformanceIntelligenceProjection(
        projection_sha256=_projection_hash(payload),
        **payload,
    )
    with _PROJECTION_CACHE_LOCK:
        _PROJECTION_CACHE[cache_key] = projection
        while len(_PROJECTION_CACHE) > 24:
            _PROJECTION_CACHE.pop(next(iter(_PROJECTION_CACHE)))
    return projection


__all__ = [
    "build_performance_intelligence",
    "objective_envelope",
    "performance_mechanisms",
    "performance_outcomes",
    "performance_principles",
]
