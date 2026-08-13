"""Fail-closed evidence contracts for telemetry analysis.

An evidence contract describes what an analysis is allowed to conclude and the
context that must be established first.  It deliberately separates channel
availability from conclusion eligibility: a signal being present never proves
that the surrounding lap, test, or comparison is valid.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator
from racelab_engine.models.evidence import EvidenceState


class ContractModel(BaseModel):
    """Strict, immutable base for durable analysis-contract data."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class OperatingCondition(ContractModel):
    """A fact that must be established before an analysis is trusted."""

    key: str = Field(min_length=1)
    description: str = Field(min_length=1)
    measurement_needed: str = Field(min_length=1)
    required: bool = True


class HardBlocker(ContractModel):
    """A disqualifying fact whose absence normally must be observed."""

    key: str = Field(min_length=1)
    description: str = Field(min_length=1)
    measurement_needed: str = Field(min_length=1)
    require_observed_clearance: bool = True


class OutputDependencyContract(ContractModel):
    """Co-observation needed to calculate one multi-channel output."""

    required_channels: frozenset[str] = Field(min_length=1)
    minimum_pairwise_coverage: float = Field(default=0.7, gt=0.0, le=1.0)
    minimum_coobserved_samples: int = Field(default=3, ge=1)
    maximum_gap_s: float | None = Field(default=None, gt=0.0)
    contiguous_episode_required: bool = True
    physical_position_required: bool = True
    missing_output: str = "unavailable"


class AllowedOutput(ContractModel):
    """An output a contract may authorize, including its evidence identity."""

    key: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence_state: EvidenceState
    source_channels: frozenset[str] = Field(min_length=1)
    dependency_contract: OutputDependencyContract | None = None

    @model_validator(mode="after")
    def require_usable_evidence_state(self) -> AllowedOutput:
        if self.evidence_state in {
            EvidenceState.UNAVAILABLE,
            EvidenceState.BLOCKED_BY_CONTEXT,
        }:
            raise ValueError("allowed outputs must describe evidence the analysis can emit")
        return self


class ConfidenceCaps(ContractModel):
    """Maximum confidence under common evidence limitations."""

    absolute_maximum: float = Field(default=0.95, ge=0.0, le=1.0)
    minimum_repetitions_only: float = Field(default=0.70, ge=0.0, le=1.0)
    missing_preferred_channels: float = Field(default=0.65, ge=0.0, le=1.0)
    unmet_preferred_condition: float = Field(default=0.55, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def caps_cannot_exceed_absolute_maximum(self) -> ConfidenceCaps:
        conditional_caps = (
            self.minimum_repetitions_only,
            self.missing_preferred_channels,
            self.unmet_preferred_condition,
        )
        if any(cap > self.absolute_maximum for cap in conditional_caps):
            raise ValueError("conditional confidence caps cannot exceed absolute_maximum")
        return self


class AnalysisEvidenceContract(ContractModel):
    """Reusable, serializable eligibility policy for one analysis."""

    key: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    purpose: str = Field(min_length=1)
    required_channels: frozenset[str] = Field(min_length=1)
    preferred_channels: frozenset[str] = frozenset()
    operating_conditions: tuple[OperatingCondition, ...] = ()
    hard_blockers: tuple[HardBlocker, ...] = ()
    allowed_outputs: tuple[AllowedOutput, ...] = Field(min_length=1)
    forbidden_outputs: frozenset[str] = frozenset()
    minimum_repetitions: int = Field(default=1, ge=1)
    high_confidence_repetitions: int = Field(default=3, ge=1)
    confidence_caps: ConfidenceCaps = ConfidenceCaps()

    @model_validator(mode="after")
    def validate_contract(self) -> AnalysisEvidenceContract:
        overlap = self.required_channels & self.preferred_channels
        if overlap:
            raise ValueError(f"channels cannot be both required and preferred: {sorted(overlap)}")
        if self.high_confidence_repetitions < self.minimum_repetitions:
            raise ValueError("high_confidence_repetitions must meet minimum_repetitions")

        condition_keys = [condition.key for condition in self.operating_conditions]
        blocker_keys = [blocker.key for blocker in self.hard_blockers]
        output_keys = [output.key for output in self.allowed_outputs]
        for label, keys in (
            ("operating condition", condition_keys),
            ("hard blocker", blocker_keys),
            ("allowed output", output_keys),
        ):
            if len(keys) != len(set(keys)):
                raise ValueError(f"duplicate {label} key")

        output_overlap = set(output_keys) & self.forbidden_outputs
        if output_overlap:
            raise ValueError(
                f"outputs cannot be both allowed and forbidden: {sorted(output_overlap)}"
            )
        declared_channels = self.required_channels | self.preferred_channels
        undeclared_sources = {
            channel
            for output in self.allowed_outputs
            for channel in output.source_channels
            if channel not in declared_channels
        }
        if undeclared_sources:
            raise ValueError(
                f"output source channels must be declared by the contract: {sorted(undeclared_sources)}"
            )
        return self


class EvidenceEvaluationInput(ContractModel):
    """Observed facts supplied to the contract evaluator."""

    usable_channels: frozenset[str]
    condition_results: dict[str, bool | None] = Field(default_factory=dict)
    blocker_results: dict[str, bool | None] = Field(default_factory=dict)
    repetitions: int = Field(default=0, ge=0)
    requested_outputs: frozenset[str] = frozenset()


class EvidenceBlocker(ContractModel):
    code: str
    key: str
    message: str
    measurement_needed: str | None = None
    resolvable: bool = True


class NeededMeasurement(ContractModel):
    key: str
    instruction: str


class ConfidenceLimit(ContractModel):
    code: str
    message: str
    cap: float = Field(ge=0.0, le=1.0)


class EvidenceEvaluation(ContractModel):
    contract_key: str
    contract_version: int
    eligible: bool
    confidence_cap: float = Field(ge=0.0, le=1.0)
    confidence_limits: tuple[ConfidenceLimit, ...]
    blockers: tuple[EvidenceBlocker, ...]
    needed_measurements: tuple[NeededMeasurement, ...]
    authorized_outputs: tuple[AllowedOutput, ...]
    denied_outputs: frozenset[str]


class EvidenceConclusion(ContractModel):
    """A conclusion with structural provenance, not wording-only caveats."""

    output_key: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    evidence_state: EvidenceState
    source_channels: frozenset[str] = frozenset()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_sources_or_blockers(self) -> EvidenceConclusion:
        blocked_states = {
            EvidenceState.UNAVAILABLE,
            EvidenceState.BLOCKED_BY_CONTEXT,
        }
        if self.evidence_state in blocked_states:
            if not self.blocker_reasons:
                raise ValueError("blocked or unavailable conclusions require blocker_reasons")
        elif not self.source_channels:
            raise ValueError("evidence-bearing conclusions require source_channels")
        return self


def _unique_measurements(
    measurements: list[NeededMeasurement],
) -> tuple[NeededMeasurement, ...]:
    unique: dict[str, NeededMeasurement] = {}
    for measurement in measurements:
        unique.setdefault(measurement.key, measurement)
    return tuple(unique.values())


def evaluate_evidence_contract(
    contract: AnalysisEvidenceContract,
    evidence: EvidenceEvaluationInput,
) -> EvidenceEvaluation:
    """Evaluate an analysis contract conservatively and explain every failure.

    Required context and blocker clearance fail closed: an omitted/unknown fact
    blocks the analysis instead of being interpreted as safe.
    """

    blockers: list[EvidenceBlocker] = []
    measurements: list[NeededMeasurement] = []
    limits: list[ConfidenceLimit] = []
    denied_outputs: set[str] = set()

    missing_required = sorted(contract.required_channels - evidence.usable_channels)
    for channel in missing_required:
        instruction = f"Record a healthy, varying {channel} channel for the target window."
        blockers.append(
            EvidenceBlocker(
                code="missing_required_channel",
                key=channel,
                message=f"Required channel {channel} is unavailable or unhealthy.",
                measurement_needed=instruction,
            )
        )
        measurements.append(NeededMeasurement(key=channel, instruction=instruction))

    missing_preferred = sorted(contract.preferred_channels - evidence.usable_channels)
    if missing_preferred:
        limits.append(
            ConfidenceLimit(
                code="missing_preferred_channels",
                message=f"Preferred channels missing: {', '.join(missing_preferred)}.",
                cap=contract.confidence_caps.missing_preferred_channels,
            )
        )

    for condition in contract.operating_conditions:
        result = evidence.condition_results.get(condition.key)
        if result is True:
            continue
        if not condition.required:
            limits.append(
                ConfidenceLimit(
                    code="unmet_preferred_condition",
                    message=f"Preferred context not established: {condition.description}",
                    cap=contract.confidence_caps.unmet_preferred_condition,
                )
            )
            measurements.append(
                NeededMeasurement(
                    key=condition.key,
                    instruction=condition.measurement_needed,
                )
            )
            continue
        message = (
            f"Required context failed: {condition.description}"
            if result is False
            else f"Required context is unknown: {condition.description}"
        )
        blockers.append(
            EvidenceBlocker(
                code="operating_condition_failed" if result is False else "operating_condition_unknown",
                key=condition.key,
                message=message,
                measurement_needed=condition.measurement_needed,
            )
        )
        measurements.append(
            NeededMeasurement(key=condition.key, instruction=condition.measurement_needed)
        )

    for blocker in contract.hard_blockers:
        result = evidence.blocker_results.get(blocker.key)
        if result is False:
            continue
        if result is None and not blocker.require_observed_clearance:
            continue
        message = (
            f"Hard blocker active: {blocker.description}"
            if result is True
            else f"Hard blocker clearance is unknown: {blocker.description}"
        )
        blockers.append(
            EvidenceBlocker(
                code="hard_blocker_active" if result is True else "hard_blocker_unknown",
                key=blocker.key,
                message=message,
                measurement_needed=blocker.measurement_needed,
            )
        )
        measurements.append(
            NeededMeasurement(key=blocker.key, instruction=blocker.measurement_needed)
        )

    if evidence.repetitions < contract.minimum_repetitions:
        needed = contract.minimum_repetitions - evidence.repetitions
        instruction = (
            f"Record {needed} more eligible repetition{'s' if needed != 1 else ''} "
            f"under the same controlled conditions."
        )
        blockers.append(
            EvidenceBlocker(
                code="insufficient_repetitions",
                key="repetitions",
                message=(
                    f"Only {evidence.repetitions} eligible repetitions are available; "
                    f"{contract.minimum_repetitions} are required."
                ),
                measurement_needed=instruction,
            )
        )
        measurements.append(NeededMeasurement(key="repetitions", instruction=instruction))
    elif evidence.repetitions < contract.high_confidence_repetitions:
        limits.append(
            ConfidenceLimit(
                code="minimum_repetitions_only",
                message=(
                    f"Only {evidence.repetitions} eligible repetitions are available; "
                    f"{contract.high_confidence_repetitions} are needed for high confidence."
                ),
                cap=contract.confidence_caps.minimum_repetitions_only,
            )
        )

    allowed_by_key = {output.key: output for output in contract.allowed_outputs}
    requested = evidence.requested_outputs or frozenset(allowed_by_key)
    for output_key in sorted(requested):
        if output_key in contract.forbidden_outputs:
            denied_outputs.add(output_key)
            blockers.append(
                EvidenceBlocker(
                    code="forbidden_output",
                    key=output_key,
                    message=f"The {contract.key} contract forbids output {output_key}.",
                    measurement_needed=None,
                    resolvable=False,
                )
            )
        elif output_key not in allowed_by_key:
            denied_outputs.add(output_key)
            blockers.append(
                EvidenceBlocker(
                    code="undeclared_output",
                    key=output_key,
                    message=f"Output {output_key} is not declared by the {contract.key} contract.",
                    measurement_needed=None,
                    resolvable=False,
                )
            )
        else:
            missing_sources = sorted(
                allowed_by_key[output_key].source_channels - evidence.usable_channels
            )
            if missing_sources:
                denied_outputs.add(output_key)
                instruction = (
                    "Record healthy output-source channels: " + ", ".join(missing_sources) + "."
                )
                blockers.append(
                    EvidenceBlocker(
                        code="missing_output_source_channel",
                        key=output_key,
                        message=(
                            f"Output {output_key} is missing usable source channels: "
                            f"{', '.join(missing_sources)}."
                        ),
                        measurement_needed=instruction,
                    )
                )
                measurements.append(
                    NeededMeasurement(key=output_key, instruction=instruction)
                )

    eligible = not blockers
    authorized = (
        tuple(allowed_by_key[key] for key in sorted(requested) if key in allowed_by_key)
        if eligible
        else ()
    )
    confidence_cap = min(
        [contract.confidence_caps.absolute_maximum, *(limit.cap for limit in limits)]
    )
    return EvidenceEvaluation(
        contract_key=contract.key,
        contract_version=contract.version,
        eligible=eligible,
        confidence_cap=confidence_cap,
        confidence_limits=tuple(limits),
        blockers=tuple(blockers),
        needed_measurements=_unique_measurements(measurements),
        authorized_outputs=authorized,
        denied_outputs=frozenset(denied_outputs),
    )


RELATIVE_HIGH_SPEED_RESISTANCE_CONTRACT = AnalysisEvidenceContract(
    key="relative_high_speed_resistance",
    purpose=(
        "Compare repeatable high-speed loss between tightly matched windows without "
        "claiming an absolute aerodynamic force or coefficient."
    ),
    required_channels=frozenset(
        {
            "lap_dist_pct",
            "speed_mph",
            "speed_rate_mph_s",
            "throttle_pct",
            "brake_pct",
            "rpm",
            "gear",
            "abs_steering_deg",
            "air_density",
            "car_distance_ahead_m",
            "car_distance_behind_m",
        }
    ),
    preferred_channels=frozenset(
        {
            "air_temp",
            "track_temp",
            "wind_vel",
            "wind_dir",
            "fuel_level",
            "lf_tire_distance_m",
            "rf_tire_distance_m",
            "lr_tire_distance_m",
            "rr_tire_distance_m",
            "lap_dist_m",
            "alt",
            "long_accel",
            "lf_slip_ratio",
            "rf_slip_ratio",
            "lr_slip_ratio",
            "rr_slip_ratio",
            "lf_brake_line_pressure_bar",
            "rf_brake_line_pressure_bar",
            "lr_brake_line_pressure_bar",
            "rr_brake_line_pressure_bar",
        }
    ),
    operating_conditions=(
        OperatingCondition(
            key="complete_flying_lap_coverage",
            description="both comparison windows come from eligible complete flying laps",
            measurement_needed="Record complete flying laps without pit, reset, wreck, slowdown, or cooldown fragments.",
        ),
        OperatingCondition(
            key="matched_track_position",
            description="samples are aligned at matched physical track positions",
            measurement_needed="Capture complete lap-position coverage and align the windows by track position.",
        ),
        OperatingCondition(
            key="matched_operating_point",
            description="speed, RPM, gear, throttle, brake, and steering demand are tightly matched",
            measurement_needed="Repeat the target zone at matched speed, RPM, gear, throttle, brake, and steering demand.",
        ),
        OperatingCondition(
            key="matched_fuel_tire_weather_context",
            description="fuel, tire age, and weather are comparable",
            measurement_needed="Repeat with recorded and matched fuel, tire distance, air temperature, track temperature, and wind context.",
        ),
        OperatingCondition(
            key="matched_measured_grade_context",
            description="measured altitude-versus-distance grade shape agrees at common track positions",
            measurement_needed="Record healthy Alt and LapDist channels through the complete comparison window.",
            required=False,
        ),
    ),
    hard_blockers=(
        HardBlocker(
            key="junk_lap_context",
            description="a junk-lap, partial-lap, pit, reset, caution, wreck, or invalid-speed condition is present",
            measurement_needed="Record a complete flying lap that passes the canonical lap-eligibility gate.",
        ),
        HardBlocker(
            key="sample_or_sim_integrity_failure",
            description="sample continuity, timing, or simulator integrity could explain the difference",
            measurement_needed="Record a run with continuous timestamps and healthy simulator/telemetry integrity.",
        ),
        HardBlocker(
            key="unisolated_setup_change",
            description="more than one unrelated setup control changed",
            measurement_needed="Restore baseline and repeat with one small setup change only.",
        ),
        HardBlocker(
            key="nearby_car_context_uncertain",
            description="nearby-car proximity context is too uncertain for a resistance conclusion",
            measurement_needed="Repeat the zone with stable, well-recorded nearby-car distance context; do not infer aerodynamic force from proximity.",
        ),
    ),
    allowed_outputs=(
        AllowedOutput(
            key="relative_speed_loss_delta",
            description="Calculated speed-loss difference at matched track positions.",
            evidence_state=EvidenceState.CALCULATED,
            source_channels=frozenset({"lap_dist_pct", "speed_mph", "speed_rate_mph_s"}),
        ),
        AllowedOutput(
            key="relative_resistance_direction",
            description="Observed direction of repeatable high-speed resistance-like behavior.",
            evidence_state=EvidenceState.OBSERVED_CORRELATION,
            source_channels=frozenset(
                {
                    "speed_mph",
                    "speed_rate_mph_s",
                    "throttle_pct",
                    "brake_pct",
                    "rpm",
                    "gear",
                    "abs_steering_deg",
                }
            ),
        ),
        AllowedOutput(
            key="resistance_cause_hypothesis",
            description="A proxy-ranked cause bucket that requires a controlled confirmation test.",
            evidence_state=EvidenceState.ESTIMATED_PROXY,
            source_channels=frozenset(
                {
                    "speed_rate_mph_s", "throttle_pct", "brake_pct", "rpm", "gear",
                    "lf_slip_ratio", "rf_slip_ratio", "lr_slip_ratio", "rr_slip_ratio",
                    "lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar",
                    "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar",
                }
            ),
        ),
        AllowedOutput(
            key="measured_grade_context",
            description="Calculated grade-shape match from measured altitude and distance at common track positions.",
            evidence_state=EvidenceState.CALCULATED,
            source_channels=frozenset({"lap_dist_pct", "lap_dist_m", "alt"}),
        ),
    ),
    forbidden_outputs=frozenset(
        {
            "measured_cda",
            "exact_drag_force",
            "exact_aerodynamic_drag_force",
            "exact_horsepower_loss",
        }
    ),
    minimum_repetitions=2,
    high_confidence_repetitions=4,
)


RUN_OBSERVATION_CONTRACT = AnalysisEvidenceContract(
    key="run_observation",
    purpose=(
        "Qualify one located engineering observation for later mechanism reasoning. "
        "This contract cannot authorize a setup change, Keep/Undo decision, or stop-testing policy."
    ),
    required_channels=frozenset({"lap_dist_pct", "speed_mph"}),
    preferred_channels=frozenset({"throttle_pct", "brake_pct", "abs_steering_deg", "rpm"}),
    operating_conditions=(
        OperatingCondition(
            key="complete_flying_lap_coverage",
            description="the source event belongs to a complete eligible flying lap",
            measurement_needed="Record a complete flying lap that passes the canonical eligibility gate.",
        ),
        OperatingCondition(
            key="setup_snapshot_captured",
            description="the current setup snapshot is captured",
            measurement_needed="Capture the current garage setup before the test run.",
        ),
        OperatingCondition(
            key="event_linked",
            description="the proposed test links to a located telemetry event",
            measurement_needed="Repeat the symptom with lap-position and event telemetry recorded.",
        ),
    ),
    hard_blockers=(
        HardBlocker(
            key="junk_lap_context",
            description="junk-lap context is present",
            measurement_needed="Record a complete flying lap without pit, reset, caution, wreck, slowdown, or sampling faults.",
        ),
        HardBlocker(
            key="sample_or_sim_integrity_failure",
            description="telemetry timing or simulator integrity failed",
            measurement_needed="Record continuous telemetry at a credible sample rate.",
        ),
        HardBlocker(
            key="short_run_sensitive_claim",
            description="a short run is being used for a strong tire-degradation or cooling conclusion",
            measurement_needed="Record a representative longer stint before drawing degradation or cooling conclusions.",
        ),
        HardBlocker(
            key="missing_data_substitution",
            description="missing telemetry was substituted with a numeric zero",
            measurement_needed="Record the missing source channel; do not infer zero from unavailable data.",
        ),
    ),
    allowed_outputs=(
        AllowedOutput(
            key="located_engineering_observation",
            description=(
                "A setup-bound, track-position-located observation that may feed later "
                "mechanism qualification but carries no setup authority."
            ),
            evidence_state=EvidenceState.OBSERVED_CORRELATION,
            source_channels=frozenset({"lap_dist_pct", "speed_mph"}),
        ),
    ),
    forbidden_outputs=frozenset(
        {
            "exact_drag_force",
            "measured_cda",
            "exact_horsepower_loss",
            "strong_tire_degradation_claim",
            "strong_cooling_claim",
        }
    ),
    minimum_repetitions=1,
    high_confidence_repetitions=3,
)


__all__ = [
    "AllowedOutput",
    "AnalysisEvidenceContract",
    "ConfidenceCaps",
    "ConfidenceLimit",
    "EvidenceBlocker",
    "EvidenceConclusion",
    "EvidenceEvaluation",
    "EvidenceEvaluationInput",
    "EvidenceState",
    "HardBlocker",
    "NeededMeasurement",
    "OperatingCondition",
    "RELATIVE_HIGH_SPEED_RESISTANCE_CONTRACT",
    "RUN_OBSERVATION_CONTRACT",
    "evaluate_evidence_contract",
]
