"""Evidence contracts for phase-aware driver, rotation, and platform systems."""

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
        description="both inputs are eligible complete flying laps",
        measurement_needed="Record complete flying laps that pass the canonical eligibility gate.",
    ),
    OperatingCondition(
        key="physical_alignment",
        description="local comparison coverage is physically aligned without extrapolation",
        measurement_needed="Record complete position coverage with timing and geometric alignment evidence.",
    ),
    OperatingCondition(
        key="phase_coverage",
        description="each reported effect has sustained phase coverage",
        measurement_needed="Record continuous driver, motion, and lap-position channels through the target phase.",
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
        description="more than one mapped control or an unmapped garage value changed",
        measurement_needed="Restore baseline and repeat with no more than one mapped setup change.",
    ),
)


DRIVER_LINE_CONTRACT = AnalysisEvidenceContract(
    key="driver_input_racing_line_efficiency",
    purpose="Measure phase-specific driver execution and block setup attribution when execution changes materially.",
    required_channels=frozenset({
        "lap_dist_pct_100", "session_time", "speed_mps", "throttle_pct",
        "brake_pct", "steering_deg", "geometric_curvature_1_per_m", "lat", "lon",
    }),
    preferred_channels=frozenset({"yaw_rate", "lat_accel", "lap_dist_ft", "curvature_1_per_m"}),
    operating_conditions=_CONDITIONS,
    hard_blockers=_BLOCKERS,
    allowed_outputs=(
        AllowedOutput(
            key="driver_phase_metrics",
            description="Calculated line, steering, correction, commitment, release, coast, and minimum-speed metrics.",
            evidence_state=EvidenceState.CALCULATED,
            source_channels=frozenset({
                "lap_dist_pct_100", "session_time", "speed_mps", "throttle_pct",
                "brake_pct", "steering_deg", "geometric_curvature_1_per_m",
                "curvature_1_per_m", "lat", "lon",
            }),
        ),
        AllowedOutput(
            key="driver_execution_similarity",
            description="Observed execution similarity at matched physical positions and phases.",
            evidence_state=EvidenceState.OBSERVED_CORRELATION,
            source_channels=frozenset({
                "lap_dist_pct_100", "throttle_pct", "brake_pct", "steering_deg", "lat", "lon",
            }),
        ),
    ),
    forbidden_outputs=frozenset({"setup_caused_driver_gain", "measured_driver_skill"}),
    minimum_repetitions=1,
    high_confidence_repetitions=3,
    confidence_caps=ConfidenceCaps(absolute_maximum=0.9),
)


CORNER_ROTATION_CONTRACT = AnalysisEvidenceContract(
    key="corner_balance_rotation",
    purpose="Describe sustained phase-specific rotation response without one-sample loose/tight labels.",
    required_channels=frozenset({
        "lap_dist_pct_100", "speed_mps", "yaw_rate", "steering_deg",
        "lat_accel", "geometric_curvature_1_per_m",
    }),
    preferred_channels=frozenset({"lat", "lon", "throttle_pct", "brake_pct", "curvature_1_per_m"}),
    operating_conditions=_CONDITIONS,
    hard_blockers=_BLOCKERS,
    allowed_outputs=(
        AllowedOutput(
            key="rotation_phase_metrics",
            description="Calculated expected yaw, sustained yaw error, steering efficiency, and correction demand.",
            evidence_state=EvidenceState.CALCULATED,
            source_channels=frozenset({
                "lap_dist_pct_100", "speed_mps", "yaw_rate", "steering_deg",
                "lat_accel", "geometric_curvature_1_per_m", "curvature_1_per_m", "lat", "lon",
            }),
        ),
        AllowedOutput(
            key="balance_signature_proxy",
            description="Phase-local rotation and sideslip-rate proxy requiring controlled confirmation.",
            evidence_state=EvidenceState.ESTIMATED_PROXY,
            source_channels=frozenset({
                "speed_mps", "yaw_rate", "steering_deg", "lat_accel",
                "geometric_curvature_1_per_m", "curvature_1_per_m", "lat", "lon",
            }),
        ),
    ),
    forbidden_outputs=frozenset({"measured_understeer_gradient", "measured_sideslip_angle", "one_sample_loose_tight"}),
    confidence_caps=ConfidenceCaps(absolute_maximum=0.85),
)


AERO_PLATFORM_WINDOW_CONTRACT = AnalysisEvidenceContract(
    key="aero_platform_operating_window",
    purpose="Measure speed-conditioned platform behavior and risk proxies without claiming measured aerodynamic load.",
    required_channels=frozenset({
        "lap_dist_pct_100", "session_time", "speed_mph", "cfs_ride_height_in",
        "front_avg_rh_in", "rear_avg_rh_in", "center_rake_fs_in", "side_rake_in",
    }),
    preferred_channels=frozenset({
        "dynamic_pressure_psf", "cfs_risk_score", "lf_ride_height_in",
        "rf_ride_height_in", "lr_ride_height_in", "rr_ride_height_in",
        "throttle_pct", "brake_pct", "long_accel",
    }),
    operating_conditions=_CONDITIONS,
    hard_blockers=_BLOCKERS,
    allowed_outputs=(
        AllowedOutput(
            key="platform_operating_metrics",
            description="Calculated distributions, speed bands, hysteresis, settling, consistency, and asymmetry.",
            evidence_state=EvidenceState.CALCULATED,
            source_channels=frozenset({
                "lap_dist_pct_100", "session_time", "speed_mph", "cfs_ride_height_in",
                "front_avg_rh_in", "rear_avg_rh_in", "center_rake_fs_in", "side_rake_in",
                "dynamic_pressure_psf",
            }),
        ),
        AllowedOutput(
            key="platform_risk_proxy",
            description="Proxy tradeoff between observed time and platform/tech-risk indicators.",
            evidence_state=EvidenceState.ESTIMATED_PROXY,
            source_channels=frozenset({"speed_mph", "cfs_ride_height_in", "center_rake_fs_in", "side_rake_in"}),
        ),
    ),
    forbidden_outputs=frozenset({"measured_downforce", "exact_aero_load", "exact_tech_legality"}),
    confidence_caps=ConfidenceCaps(absolute_maximum=0.85),
)


__all__ = ["AERO_PLATFORM_WINDOW_CONTRACT", "CORNER_ROTATION_CONTRACT", "DRIVER_LINE_CONTRACT"]
