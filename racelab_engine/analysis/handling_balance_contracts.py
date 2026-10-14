"""Evidence contract for the automatic handling-balance assessment.

This is the NEW producer's own qualification contract. The legacy phase-
engineering balance proxy keeps its original truth contract unchanged; this
system never reinterprets it and never asserts what CORNER_ROTATION_CONTRACT
forbids.

Scientific ceiling for this producer:

- The steering/yaw comparison uses an actual-path kinematic reference
  (speed x actual-path curvature). Actual-path curvature is NOT the driver's
  intended path, so a response deficit is reported as a rotation-response
  signature, never as a measured understeer gradient.
- The sideslip-rate proxy (lat_accel / speed - yaw_rate) is a planar body
  kinematics approximation. It ignores banking; on banked ovals it can only
  act as a contradiction check, never as primary classification evidence.
- No output may authorize, direct, or size a setup change. No Keep/Undo/
  Retest. No causal claim.
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
                "reference envelope: deficit, excess, mixed, transient anomaly, "
                "steering-response anomaly, or no significant imbalance qualified."
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
                "only when the qualified signature, phase, and repetition evidence "
                "support the mapping; the association remains telemetry-observed and "
                "never becomes driver testimony or setup authority."
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
    }),
    minimum_repetitions=2,
    high_confidence_repetitions=5,
    confidence_caps=ConfidenceCaps(absolute_maximum=0.7),
)


__all__ = ["HANDLING_BALANCE_CONTRACT"]
