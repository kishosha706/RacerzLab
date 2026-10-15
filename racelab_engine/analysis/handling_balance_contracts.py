"""Evidence contract for the automatic handling-balance assessment.

This is the NEW producer's own qualification contract. The legacy phase-
engineering balance proxy keeps its original truth contract unchanged; this
system never reinterprets it and never asserts what CORNER_ROTATION_CONTRACT
forbids.

Scientific ceiling for this producer (physics audit 2026-10-13):

- Planar kinematics: course angle = heading + sideslip, so
  speed x path-curvature - yaw_rate = d(sideslip)/dt. The kinematic residual
  is therefore a sideslip-RATE proxy: it is zero in steady-state cornering no
  matter how unbalanced the car is, and it moves during transients without
  implying imbalance. The residual is a diagnostic only. It can never, by
  itself, establish a tight/loose-family symptom.
- A deficit/excess signature may carry a canonical symptom ONLY when a second,
  independent strand corroborates it under comparable conditions: steering
  demand per achieved path curvature, compared against the run-local
  reference at matched speeds. The residual (speed, curvature, yaw) and the
  demand strand (steering, curvature, speed) test different relationships;
  a sideslip-rate proxy derived from the same kinematic identity (for example
  lat_accel / speed - yaw_rate) is NOT independent and must never count as
  corroboration.
- Dependence audit: the two strands share measured path curvature and the
  same run-local reference lap group. They are complementary, NOT
  statistically independent evidence. Corroboration qualifies the symptom
  mapping; it can never inflate independent evidence-unit counts, and the
  corroborated confidence carries an explicit discount.
- Actual-path curvature is NOT the driver's intended path. Every comparison
  is run-local (leave-one-out lap reference); a car-wide uniform balance
  offset cannot be separated from that reference and is reported as
  unavailable, never invented.
- No output may authorize, direct, or size a setup change. No Keep/Undo/
  Retest. No causal claim. No DriverIntent.
"""

from __future__ import annotations

from racelab_engine.analysis.evidence_contracts import (
    AllowedOutput,
    AnalysisEvidenceContract,
    ConfidenceCaps,
    HardBlocker,
    OperatingCondition,
)
from racelab_engine.models.evidence import EvidenceState


_CONDITIONS = (
    OperatingCondition(
        key="eligible_laps",
        description="at least two eligible complete flying laps from the same run and setup",
        measurement_needed="Record multiple complete flying laps that pass the canonical eligibility gate.",
    ),
    OperatingCondition(
        key="physical_alignment",
        description="every lap is compared at matched physical track positions",
        measurement_needed="Record laps with complete lap-position coverage and continuous timing.",
    ),
    OperatingCondition(
        key="phase_coverage",
        description="each reported phase has sustained coverage across the eligible lap group",
        measurement_needed="Record continuous steering, yaw, lateral, and position channels through the target phase.",
    ),
    OperatingCondition(
        key="steering_demand",
        description="the phase contains sustained steering demand above the response floor",
        measurement_needed="The classification only applies to phases where the driver is actually asking the car to rotate.",
    ),
    OperatingCondition(
        key="independent_response_corroboration",
        description=(
            "a deficit/excess signature may carry a canonical symptom only when "
            "steering demand per achieved path curvature independently "
            "corroborates the kinematic residual under comparable speeds; the "
            "kinematic residual alone (a planar sideslip-rate proxy) never "
            "establishes a tight/loose-family symptom"
        ),
        measurement_needed=(
            "Repeat comparable-speed laps so the steering-demand-to-response "
            "strand can be compared against the run-local reference "
            "independently of the sideslip-rate residual."
        ),
    ),
)

_BLOCKERS = (
    HardBlocker(
        key="junk_lap_context",
        description="junk-lap, pit, reset, wreck, caution, or partial-lap context is present",
        measurement_needed="Repeat on complete flying laps without invalid context.",
    ),
    HardBlocker(
        key="sample_integrity_failure",
        description="sample gaps, timing discontinuities, or an unclear simulator integrity certificate can explain the result",
        measurement_needed="Repeat with continuous telemetry and a simulator integrity certificate that is clear for analysis.",
    ),
    HardBlocker(
        key="unisolated_setup_change",
        description="the lap group spans a setup change, so a handling signature cannot be attributed to one configuration",
        measurement_needed="Compare laps from one unchanged setup only.",
    ),
)


HANDLING_BALANCE_CONTRACT = AnalysisEvidenceContract(
    key="automatic_handling_balance",
    purpose=(
        "Describe repeatable phase-local rotation-response signatures without "
        "asserting measured understeer, oversteer, neutral balance, or setup causation."
    ),
    required_channels=frozenset({
        "lap_dist_pct_100", "session_time", "speed_mps", "yaw_rate",
        "steering_rad", "lat_accel", "lap",
    }),
    preferred_channels=frozenset({
        "lat", "lon", "curvature_1_per_m", "velocity_y", "throttle_pct",
        "brake_pct", "steering_wheel_torque_nm",
    }),
    operating_conditions=_CONDITIONS,
    hard_blockers=_BLOCKERS,
    allowed_outputs=(
        AllowedOutput(
            key="handling_phase_observations",
            description=(
                "Phase-local steering demand, path-kinematic expected yaw, signed "
                "rotation-response deficit, steering efficiency, correction demand, "
                "and transient development, aggregated over the eligible lap group."
            ),
            evidence_state=EvidenceState.CALCULATED,
            source_channels=frozenset({
                "lap_dist_pct_100", "session_time", "speed_mps", "yaw_rate",
                "steering_rad", "lat_accel", "lap",
            }),
        ),
        AllowedOutput(
            key="handling_balance_signature",
            description=(
                "A rotation-response signature qualified against the run-local "
                "reference envelope: corroborated deficit, corroborated excess, "
                "kinematic residual observation, steering-demand anomaly, mixed, "
                "transient anomaly, steering-response anomaly, or no significant "
                "imbalance qualified. Deficit/excess require two aligned "
                "independent strands; residual-only and demand-only signatures "
                "remain diagnostics without a canonical symptom."
            ),
            evidence_state=EvidenceState.OBSERVED_CORRELATION,
            source_channels=frozenset({
                "lap_dist_pct_100", "speed_mps", "yaw_rate", "steering_rad",
                "lat_accel", "lap",
            }),
        ),
        AllowedOutput(
            key="handling_canonical_symptom",
            description=(
                "A canonical symptom association (tight_center, loose_exit, ...) "
                "only when a corroborated deficit/excess signature qualifies: "
                "the kinematic residual and the steering-demand-to-response "
                "strand must both exceed the run-local reference envelope and "
                "align under comparable speeds. The association remains "
                "telemetry-observed and never becomes driver testimony or "
                "setup authority."
            ),
            evidence_state=EvidenceState.OBSERVED_CORRELATION,
            source_channels=frozenset({
                "lap_dist_pct_100", "speed_mps", "yaw_rate", "steering_rad",
                "lat_accel", "lap",
            }),
        ),
    ),
    forbidden_outputs=frozenset({
        "measured_understeer_gradient",
        "measured_sideslip_angle",
        "one_sample_loose_tight",
        "global_tight_loose_verdict",
        "setup_authorized_tight_loose",
        "neutral_balance_claimed",
        "single_strand_tight_loose",
        "sideslip_rate_self_corroboration",
    }),
    minimum_repetitions=2,
    high_confidence_repetitions=5,
    confidence_caps=ConfidenceCaps(absolute_maximum=0.7),
)


__all__ = ["HANDLING_BALANCE_CONTRACT"]
