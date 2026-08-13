"""Evidence contracts for the P3 engineering systems."""

from __future__ import annotations

from racelab_engine.analysis.evidence_contracts import (
    AllowedOutput,
    AnalysisEvidenceContract,
    HardBlocker,
    OperatingCondition,
    OutputDependencyContract,
)
from racelab_engine.models.evidence import EvidenceState


def _conditions() -> tuple[OperatingCondition, ...]:
    return (
        OperatingCondition(
            key="eligible_lap",
            description="analysis rows belong to complete eligible flying laps",
            measurement_needed="Record complete flying laps that pass the canonical eligibility gate.",
        ),
        OperatingCondition(
            key="phase_scoped",
            description="the conclusion is scoped to an identified engineering phase",
            measurement_needed="Record lap-position, brake, throttle, steering, yaw, and acceleration channels.",
        ),
        OperatingCondition(
            key="track_position_available",
            description="samples carry physical lap-position coverage",
            measurement_needed="Record complete LapDistPct coverage and compare by track position.",
        ),
    )


def _blockers() -> tuple[HardBlocker, ...]:
    return (
        HardBlocker(
            key="junk_lap_context",
            description="junk-lap or partial-lap context is present",
            measurement_needed="Repeat on a complete eligible flying lap.",
        ),
        HardBlocker(
            key="sim_integrity_uncertain",
            description="simulator or sample integrity could explain the signal",
            measurement_needed="Record continuous SessionTick/SessionTime plus healthy simulator-performance channels.",
        ),
    )


BRAKING_EFFICIENCY_CONTRACT = AnalysisEvidenceContract(
    key="braking_efficiency_dynamic_balance",
    purpose="Measure phase-specific braking response while separating pedal technique from setup-bias evidence.",
    required_channels=frozenset({
        "lap_dist_pct", "session_time", "brake_pct",
        "lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar",
        "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar",
        "lf_speed", "rf_speed", "lr_speed", "rr_speed",
        "long_accel", "yaw_rate", "abs_steering_deg",
    }),
    preferred_channels=frozenset({
        "brake_01", "brake_abs_active", "brake_abs_cut_01",
        "lf_slip_ratio", "rf_slip_ratio", "lr_slip_ratio", "rr_slip_ratio",
        "lf_pressure", "rf_pressure", "lr_pressure", "rr_pressure",
    }),
    operating_conditions=_conditions(),
    hard_blockers=_blockers(),
    allowed_outputs=(
        AllowedOutput(
            key="braking_phase_metrics",
            description="Calculated pressure, balance, ABS, lock-timing, and deceleration-efficiency metrics.",
            evidence_state=EvidenceState.CALCULATED,
            source_channels=frozenset({
                "lap_dist_pct", "session_time", "brake_pct",
                "lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar",
                "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar",
                "lf_speed", "rf_speed", "lr_speed", "rr_speed", "long_accel",
            }),
            dependency_contract=OutputDependencyContract(
                required_channels=frozenset({
                    "session_time", "lap_dist_pct", "long_accel",
                    "lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar",
                    "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar",
                }),
                minimum_pairwise_coverage=0.7,
                minimum_coobserved_samples=3,
                maximum_gap_s=0.25,
            ),
        ),
        AllowedOutput(
            key="braking_cause_hypothesis",
            description="Proxy separation of setup-bias and pedal-technique evidence.",
            evidence_state=EvidenceState.ESTIMATED_PROXY,
            source_channels=frozenset({
                "brake_pct", "yaw_rate", "abs_steering_deg",
                "lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar",
                "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar",
            }),
        ),
    ),
    forbidden_outputs=frozenset({"friction_coefficient", "measured_mu", "exact_brake_force"}),
)


TIRE_STATE_CONTRACT = AnalysisEvidenceContract(
    key="tire_state_energy",
    purpose="Describe per-corner tire state and evidence-supported thermal origin without universal pressure rules.",
    required_channels=frozenset({
        "lap_dist_pct", "brake_pct", "throttle_pct",
        "lf_pressure", "rf_pressure", "lr_pressure", "rr_pressure",
        "lf_temp_inner", "lf_temp_middle", "lf_temp_outer",
        "rf_temp_inner", "rf_temp_middle", "rf_temp_outer",
        "lr_temp_inner", "lr_temp_middle", "lr_temp_outer",
        "rr_temp_inner", "rr_temp_middle", "rr_temp_outer",
        "lf_wear_inner", "lf_wear_middle", "lf_wear_outer",
        "rf_wear_inner", "rf_wear_middle", "rf_wear_outer",
        "lr_wear_inner", "lr_wear_middle", "lr_wear_outer",
        "rr_wear_inner", "rr_wear_middle", "rr_wear_outer",
        "lf_tire_distance_m", "rf_tire_distance_m", "lr_tire_distance_m", "rr_tire_distance_m",
        "lf_slip_ratio", "rf_slip_ratio", "lr_slip_ratio", "rr_slip_ratio",
    }),
    preferred_channels=frozenset({
        "lf_cold_pressure", "rf_cold_pressure", "lr_cold_pressure", "rr_cold_pressure",
        "lf_carcass_temp_m", "rf_carcass_temp_m", "lr_carcass_temp_m", "rr_carcass_temp_m",
        "lat_accel", "long_accel", "vert_accel_g",
    }),
    operating_conditions=_conditions(),
    hard_blockers=_blockers(),
    allowed_outputs=(
        AllowedOutput(
            key="tire_state_vector",
            description="Measured and calculated per-corner pressure, temperature, wear, distance, and slip state.",
            evidence_state=EvidenceState.CALCULATED,
            source_channels=frozenset({
                "lap_dist_pct", "lf_pressure", "rf_pressure", "lr_pressure", "rr_pressure",
                "lf_temp_inner", "lf_temp_middle", "lf_temp_outer",
                "rf_temp_inner", "rf_temp_middle", "rf_temp_outer",
                "lr_temp_inner", "lr_temp_middle", "lr_temp_outer",
                "rr_temp_inner", "rr_temp_middle", "rr_temp_outer",
            }),
            dependency_contract=OutputDependencyContract(
                required_channels=frozenset({
                    "lap_dist_pct", "lf_pressure", "rf_pressure", "lr_pressure", "rr_pressure",
                    "lf_temp_inner", "lf_temp_middle", "lf_temp_outer",
                    "rf_temp_inner", "rf_temp_middle", "rf_temp_outer",
                    "lr_temp_inner", "lr_temp_middle", "lr_temp_outer",
                    "rr_temp_inner", "rr_temp_middle", "rr_temp_outer",
                }),
                minimum_pairwise_coverage=0.7,
                minimum_coobserved_samples=3,
                maximum_gap_s=0.25,
            ),
        ),
        AllowedOutput(
            key="tire_energy_cause_hypothesis",
            description="Proxy classification of plausible thermal/usage origin requiring repeated confirmation.",
            evidence_state=EvidenceState.ESTIMATED_PROXY,
            source_channels=frozenset({
                "brake_pct", "throttle_pct", "lf_slip_ratio", "rf_slip_ratio",
                "lr_slip_ratio", "rr_slip_ratio", "lf_tire_distance_m",
                "rf_tire_distance_m", "lr_tire_distance_m", "rr_tire_distance_m",
            }),
        ),
    ),
    forbidden_outputs=frozenset({"universal_hot_pressure_rule", "measured_tire_energy", "measured_tire_load"}),
)


DAMPER_RESPONSE_CONTRACT = AnalysisEvidenceContract(
    key="damper_suspension_response",
    purpose="Measure shaft motion by phase and regime without claiming damper force.",
    required_channels=frozenset({
        "lap_dist_pct", "session_time",
        "lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s",
        "lf_shock_defl_in", "rf_shock_defl_in", "lr_shock_defl_in", "rr_shock_defl_in",
    }),
    preferred_channels=frozenset({"vert_accel_g", "speed_mph", "brake_pct", "throttle_pct", "steering_deg"}),
    operating_conditions=_conditions(),
    hard_blockers=_blockers(),
    allowed_outputs=(
        AllowedOutput(
            key="damper_response_metrics",
            description="Calculated histograms, regime occupancy, response timing, coherence, and spectral metrics.",
            evidence_state=EvidenceState.CALCULATED,
            source_channels=frozenset({
                "lap_dist_pct", "session_time", "lf_shock_vel_in_s", "rf_shock_vel_in_s",
                "lr_shock_vel_in_s", "rr_shock_vel_in_s", "lf_shock_defl_in",
                "rf_shock_defl_in", "lr_shock_defl_in", "rr_shock_defl_in",
            }),
        ),
        AllowedOutput(
            key="damper_regime_observation",
            description="Observed shaft-velocity regime occupancy with no damper-setting direction or target.",
            evidence_state=EvidenceState.NEEDS_CONFIRMATION,
            source_channels=frozenset({
                "lap_dist_pct", "lf_shock_vel_in_s", "rf_shock_vel_in_s",
                "lr_shock_vel_in_s", "rr_shock_vel_in_s",
            }),
        ),
    ),
    forbidden_outputs=frozenset({"measured_damper_force", "exact_damping_coefficient"}),
)


SIM_INTEGRITY_CONTRACT = AnalysisEvidenceContract(
    key="simulator_data_integrity",
    purpose="Certify whether simulator performance or telemetry continuity can support controlled attribution.",
    required_channels=frozenset({"session_tick", "session_time"}),
    preferred_channels=frozenset({
        "frame_rate", "cpu_usage_foreground", "cpu_usage_background", "gpu_usage",
        "memory_page_faults_per_s", "memory_soft_page_faults_per_s",
        "channel_latency_s", "channel_average_latency_s", "channel_quality",
    }),
    operating_conditions=(
        OperatingCondition(
            key="continuous_clock_window",
            description="session ticks and timestamps are monotonic and continuous",
            measurement_needed="Record continuous SessionTick and SessionTime channels.",
        ),
        OperatingCondition(
            key="credible_sample_rate",
            description="the observed telemetry rate matches the declared rate",
            measurement_needed="Record the declared telemetry rate plus continuous ticks/timestamps.",
        ),
    ),
    hard_blockers=(
        HardBlocker(
            key="integrity_failure",
            description="dropped ticks, clock reversals, or severe simulator-performance faults are present",
            measurement_needed="Repeat after simulator and telemetry performance are stable.",
        ),
    ),
    allowed_outputs=(
        AllowedOutput(
            key="sim_integrity_certificate",
            description="Calculated integrity certificate and confidence gate.",
            evidence_state=EvidenceState.CALCULATED,
            source_channels=frozenset({"session_tick", "session_time"}),
        ),
    ),
)


POWERTRAIN_GEARING_CONTRACT = AnalysisEvidenceContract(
    key="powertrain_gearing",
    purpose="Measure repeatable RPM, shift, and acceleration behavior without proposing a gearing direction.",
    required_channels=frozenset({
        "lap_dist_pct", "session_time", "speed_mph", "rpm", "gear", "throttle_pct", "long_accel",
    }),
    preferred_channels=frozenset({
        "fuel_level", "water_temp", "oil_temp", "engine_warnings", "shift_indicator_pct",
    }),
    operating_conditions=_conditions(),
    hard_blockers=_blockers(),
    allowed_outputs=(
        AllowedOutput(
            key="powertrain_phase_metrics",
            description="Calculated RPM occupancy, shift loss, speed/RPM, and acceleration-by-RPM metrics.",
            evidence_state=EvidenceState.CALCULATED,
            source_channels=frozenset({
                "lap_dist_pct", "session_time", "speed_mph", "rpm", "gear", "throttle_pct", "long_accel",
            }),
        ),
        AllowedOutput(
            key="gearing_discriminator_observation",
            description="An observed limiter/headroom discriminator with no gearing direction or target.",
            evidence_state=EvidenceState.NEEDS_CONFIRMATION,
            source_channels=frozenset({"speed_mph", "rpm", "gear", "throttle_pct", "long_accel"}),
        ),
        AllowedOutput(
            key="powertrain_context_diagnostics",
            description="Measured temperature, fuel-load proxy, warning-state, and matched-gear diagnostics.",
            evidence_state=EvidenceState.CALCULATED,
            source_channels=frozenset({
                "lap_dist_pct", "rpm", "gear", "throttle_pct", "fuel_level",
                "water_temp", "oil_temp", "engine_warnings",
            }),
        ),
    ),
    forbidden_outputs=frozenset({"measured_engine_power", "exact_drivetrain_loss"}),
    minimum_repetitions=2,
)


STINT_STRATEGY_CONTRACT = AnalysisEvidenceContract(
    key="stint_tire_strategy",
    purpose="Estimate fuel and long-run trends from canonical eligible history without extrapolating short runs.",
    required_channels=frozenset({"lap_dist_pct", "fuel_level"}),
    preferred_channels=frozenset({
        "session_time", "lap_completed",
        "lf_tire_distance_m", "rf_tire_distance_m", "lr_tire_distance_m", "rr_tire_distance_m",
        "lf_pressure", "rf_pressure", "lr_pressure", "rr_pressure",
        "lf_temp_middle", "rf_temp_middle", "lr_temp_middle", "rr_temp_middle",
        "lf_wear_inner", "lf_wear_middle", "lf_wear_outer",
        "rf_wear_inner", "rf_wear_middle", "rf_wear_outer",
        "lr_wear_inner", "lr_wear_middle", "lr_wear_outer",
        "rr_wear_inner", "rr_wear_middle", "rr_wear_outer",
        "player_tire_compound", "tire_sets_used", "left_tire_sets_used",
        "right_tire_sets_used", "front_tire_sets_used", "rear_tire_sets_used",
        "tire_sets_available", "left_tire_sets_available", "right_tire_sets_available",
        "front_tire_sets_available", "rear_tire_sets_available",
        "session_time_remaining_s", "session_laps_remaining",
        "session_laps_remaining_legacy", "session_time_total_s", "session_laps_total",
        "session_state", "session_flags", "pits_open", "pitstop_active",
        "player_in_pit_stall", "player_pit_service_status", "on_pit_road",
        "pit_repair_remaining_s", "pit_optional_repair_remaining_s",
        "pending_pit_service_flags", "pending_pit_fuel_add",
        "repair_required", "repair_time_s",
        "car_distance_ahead_m", "car_distance_behind_m", "speed_mps",
    }),
    operating_conditions=(
        OperatingCondition(
            key="eligible_history",
            description="the stint history contains canonical eligible laps only",
            measurement_needed="Record consecutive complete flying laps without pits, cautions, resets, or incidents.",
        ),
        OperatingCondition(
            key="fuel_trace_available",
            description="fuel is recorded across lap boundaries",
            measurement_needed="Record FuelLevel continuously for at least three eligible laps.",
        ),
    ),
    hard_blockers=(
        HardBlocker(
            key="sim_integrity_uncertain",
            description="simulator or sample integrity could distort stint trends",
            measurement_needed="Record a continuous stint with healthy simulator/data integrity.",
        ),
    ),
    allowed_outputs=(
        AllowedOutput(
            key="fuel_strategy_metrics",
            description="Calculated burn, range, and pit-window context.",
            evidence_state=EvidenceState.CALCULATED,
            source_channels=frozenset({"lap_dist_pct", "fuel_level"}),
        ),
        AllowedOutput(
            key="stint_degradation_hypothesis",
            description="Observed long-run pace and tire-state trend requiring adequate stint length.",
            evidence_state=EvidenceState.OBSERVED_CORRELATION,
            source_channels=frozenset({"lap_dist_pct", "fuel_level"}),
        ),
        AllowedOutput(
            key="tire_life_curve",
            description="Observed per-corner remaining-wear curve over canonical continuous laps.",
            evidence_state=EvidenceState.OBSERVED_CORRELATION,
            source_channels=frozenset({
                "lap_dist_pct", "lf_tire_distance_m", "rf_tire_distance_m",
                "lr_tire_distance_m", "rr_tire_distance_m", "lf_wear_inner",
                "lf_wear_middle", "lf_wear_outer", "rf_wear_inner",
                "rf_wear_middle", "rf_wear_outer", "lr_wear_inner",
                "lr_wear_middle", "lr_wear_outer", "rr_wear_inner",
                "rr_wear_middle", "rr_wear_outer",
            }),
        ),
        AllowedOutput(
            key="fuel_exhaustion_service_bound",
            description="Observed active-stint fuel exhaustion/service bound without claiming race-strategy optimality.",
            evidence_state=EvidenceState.CALCULATED,
            source_channels=frozenset({"lap_dist_pct", "fuel_level"}),
        ),
        AllowedOutput(
            key="pit_window_recommendation",
            description="Production race pit-service recommendation using server-derived horizon, pit-rule state, and measured pit loss.",
            evidence_state=EvidenceState.CALCULATED,
            source_channels=frozenset({
                "session_time", "lap_dist_pct", "lap_completed", "fuel_level", "on_pit_road",
                "pits_open", "session_state",
            }),
        ),
    ),
    forbidden_outputs=frozenset({"guaranteed_pit_window", "short_run_tire_degradation"}),
    minimum_repetitions=3,
    high_confidence_repetitions=15,
)


__all__ = [
    "BRAKING_EFFICIENCY_CONTRACT", "DAMPER_RESPONSE_CONTRACT",
    "POWERTRAIN_GEARING_CONTRACT", "SIM_INTEGRITY_CONTRACT",
    "STINT_STRATEGY_CONTRACT", "TIRE_STATE_CONTRACT",
]
