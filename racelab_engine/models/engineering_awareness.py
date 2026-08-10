"""Non-authoritative contracts for P20 engineering state awareness.

These models preserve exact scope, provenance, and independent trust axes.  They
cannot carry a setup target, a Keep/Undo verdict, or any other intervention
authority; P19 remains the sole owner of canonical reasoning and setup policy.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap_engineering_context import ChannelUpdateSemantic
from racelab_engine.models.observation_intelligence import MechanismKind


_USABLE_STATE_EVIDENCE = frozenset(
    {
        EvidenceState.MEASURED,
        EvidenceState.CALCULATED,
        EvidenceState.ESTIMATED_PROXY,
        EvidenceState.OBSERVED_CORRELATION,
        EvidenceState.CONTROLLED_TEST_EFFECT,
    }
)


class AwarenessModel(BaseModel):
    """Strict, immutable base for durable state-awareness data."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ChannelRole(str, Enum):
    """Known reasoning roles for telemetry channels.

    There is deliberately no ``unknown`` member.  Callers must retain an absent
    role as ``None`` instead of assigning an unsupported semantic role.
    """

    MEASUREMENT = "measurement"
    CONTEXT = "context"
    CONTROL_STATE = "control_state"
    CONTROL_REQUEST = "control_request"
    INTEGRITY = "integrity"
    PHASE_LOCATOR = "phase_locator"
    POSITION_LOCATOR = "position_locator"
    SETUP_SNAPSHOT = "setup_snapshot"
    PIT_SNAPSHOT = "pit_snapshot"
    CONTINUOUS_STATE = "continuous_state"
    SUB_TICK_MEASUREMENT = "sub_tick_measurement"
    DERIVED_INPUT = "derived_input"
    COMPATIBILITY_IDENTITY = "compatibility_identity"


class MetricProvenance(AwarenessModel):
    producer_id: str = Field(min_length=1)
    source_module: str = Field(min_length=1)
    source_contract_ids: tuple[str, ...] = ()
    reference_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def provenance_values_are_unique(self) -> MetricProvenance:
        _require_unique(self.source_contract_ids, "source contract")
        _require_unique(self.reference_ids, "reference")
        return self


class DerivedMetricContract(AwarenessModel):
    """Fail-closed semantic envelope for one derived engineering metric."""

    metric_key: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    label: str = Field(min_length=1)
    evidence_state: Literal[
        EvidenceState.CALCULATED,
        EvidenceState.ESTIMATED_PROXY,
        EvidenceState.OBSERVED_CORRELATION,
    ]
    required_channels: tuple[str, ...] = Field(min_length=1)
    preferred_channels: tuple[str, ...] = ()
    allowed_channel_semantics: tuple[ChannelUpdateSemantic, ...] = Field(min_length=1)
    required_vehicle_profile_fields: tuple[str, ...] = ()
    valid_phases: tuple[str, ...] = Field(min_length=1)
    hard_blockers: tuple[str, ...] = Field(min_length=1)
    minimum_sample_coverage: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)
    minimum_repetitions: int = Field(ge=1)
    allowed_outputs: tuple[str, ...] = Field(min_length=1)
    forbidden_claims: tuple[str, ...] = Field(min_length=1)
    authority_ceiling: Literal["observation_only"] = "observation_only"
    description: str = Field(min_length=1)
    provenance: MetricProvenance

    @model_validator(mode="after")
    def contract_is_canonical_and_non_authoritative(self) -> DerivedMetricContract:
        for values, label in (
            (self.required_channels, "required channel"),
            (self.preferred_channels, "preferred channel"),
            (self.allowed_channel_semantics, "channel semantic"),
            (self.required_vehicle_profile_fields, "vehicle-profile field"),
            (self.valid_phases, "phase"),
            (self.hard_blockers, "hard blocker"),
            (self.allowed_outputs, "allowed output"),
            (self.forbidden_claims, "forbidden claim"),
        ):
            _require_unique(values, label)
        overlap = set(self.required_channels) & set(self.preferred_channels)
        if overlap:
            raise ValueError(
                f"channels cannot be both required and preferred: {sorted(overlap)}"
            )
        unavailable = {
            ChannelUpdateSemantic.MISSING,
            ChannelUpdateSemantic.UNHEALTHY,
        }
        if unavailable & set(self.allowed_channel_semantics):
            raise ValueError(
                "missing or unhealthy telemetry cannot be an allowed input semantic"
            )
        if set(self.allowed_outputs) & set(self.forbidden_claims):
            raise ValueError("a metric output cannot also be a forbidden claim")
        return self


class AnalyzerVersion(AwarenessModel):
    analyzer_id: str = Field(min_length=1)
    version: str = Field(min_length=1)


class FrameChannelSemantic(AwarenessModel):
    channel: str = Field(min_length=1)
    role: ChannelRole | None = None
    update_semantic: ChannelUpdateSemantic


class ChannelCoverage(AwarenessModel):
    channel: str = Field(min_length=1)
    sample_coverage: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


class StateEvidenceReference(AwarenessModel):
    """Exact-scope evidence reference; prose alone is never sufficient provenance."""

    evidence_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    lap_number: int = Field(ge=0)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_peak: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    evidence_state: EvidenceState
    source_channels: tuple[str, ...] = Field(min_length=1)
    summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def reference_is_exact_and_evidence_bearing(self) -> StateEvidenceReference:
        if not self.lap_pct_start <= self.lap_pct_peak <= self.lap_pct_end:
            raise ValueError("evidence peak must be inside its physical window")
        if self.evidence_state not in _USABLE_STATE_EVIDENCE:
            raise ValueError("state evidence references require usable evidence")
        _require_unique(self.source_channels, "source channel")
        return self


class SubsystemStateReference(AwarenessModel):
    artifact_id: str = Field(min_length=1)
    producer_id: str = Field(min_length=1)
    mechanism: MechanismKind
    run_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    lap_number: int = Field(ge=0)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_peak: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def subsystem_window_is_exact(self) -> SubsystemStateReference:
        if not self.lap_pct_start <= self.lap_pct_peak <= self.lap_pct_end:
            raise ValueError("subsystem peak must be inside its physical window")
        return self


class EngineeringStateFrame(AwarenessModel):
    """One exact, immutable physical/time state window with no setup authority."""

    frame_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    lap_number: int = Field(ge=0)
    setup_id: str = Field(min_length=1)
    context_id: str = Field(min_length=1)
    independence_cluster_id: str = Field(min_length=1)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_peak: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    session_time_start: float = Field(ge=0.0, allow_inf_nan=False)
    session_time_end: float = Field(ge=0.0, allow_inf_nan=False)
    phase: str = Field(min_length=1)
    source_artifact_ids: tuple[str, ...] = Field(min_length=1)
    source_event_ids: tuple[str, ...] = ()
    source_channels: tuple[str, ...] = Field(min_length=1)
    channel_semantics: tuple[FrameChannelSemantic, ...] = Field(min_length=1)
    coverage_by_channel: tuple[ChannelCoverage, ...] = Field(min_length=1)
    vehicle_profile_id: str | None = None
    vehicle_profile_hash: str | None = None
    analyzer_versions: tuple[AnalyzerVersion, ...] = Field(min_length=1)
    driver: SubsystemStateReference | None = None
    braking: SubsystemStateReference | None = None
    rotation: SubsystemStateReference | None = None
    tires: SubsystemStateReference | None = None
    dampers: SubsystemStateReference | None = None
    platform: SubsystemStateReference | None = None
    resistance: SubsystemStateReference | None = None
    powertrain: SubsystemStateReference | None = None
    stint: SubsystemStateReference | None = None
    integrity: SubsystemStateReference | None = None
    evidence_states: tuple[EvidenceState, ...] = Field(min_length=1)
    blocker_reasons: tuple[str, ...] = ()
    supporting_evidence: tuple[StateEvidenceReference, ...] = Field(min_length=1)
    contradicting_evidence: tuple[StateEvidenceReference, ...] = ()
    spans_material_control_mutation: Literal[False] = False
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def state_frame_has_one_exact_scope(self) -> EngineeringStateFrame:
        if not self.lap_pct_start <= self.lap_pct_peak <= self.lap_pct_end:
            raise ValueError("frame peak must be inside its physical window")
        if self.session_time_end < self.session_time_start:
            raise ValueError("frame session-time window must be ordered")
        for values, label in (
            (self.source_artifact_ids, "source artifact"),
            (self.source_event_ids, "source event"),
            (self.source_channels, "source channel"),
            (self.evidence_states, "evidence state"),
        ):
            _require_unique(values, label)
        if any(state not in _USABLE_STATE_EVIDENCE for state in self.evidence_states):
            raise ValueError("state frames require usable evidence states")
        if (self.vehicle_profile_id is None) != (self.vehicle_profile_hash is None):
            raise ValueError(
                "vehicle profile identity and hash must be present together"
            )

        semantic_channels = [item.channel for item in self.channel_semantics]
        coverage_channels = [item.channel for item in self.coverage_by_channel]
        analyzer_ids = [item.analyzer_id for item in self.analyzer_versions]
        _require_unique(semantic_channels, "channel semantic")
        _require_unique(coverage_channels, "channel coverage")
        _require_unique(analyzer_ids, "analyzer")
        source_channel_set = set(self.source_channels)
        if set(semantic_channels) != source_channel_set:
            raise ValueError(
                "channel semantics must cover every and only source channel"
            )
        if set(coverage_channels) != source_channel_set:
            raise ValueError(
                "channel coverage must cover every and only source channel"
            )

        evidence_references = (*self.supporting_evidence, *self.contradicting_evidence)
        evidence_ids = [reference.evidence_id for reference in evidence_references]
        _require_unique(evidence_ids, "evidence reference")
        for reference in evidence_references:
            _validate_reference_scope(reference, self)
            if reference.artifact_id not in self.source_artifact_ids:
                raise ValueError(
                    "frame evidence artifacts must be declared as frame sources"
                )
            if not set(reference.source_channels) <= source_channel_set:
                raise ValueError(
                    "frame evidence channels must be declared as frame sources"
                )
        expected_mechanisms = {
            "driver": MechanismKind.DRIVER_EXECUTION,
            "braking": MechanismKind.BRAKING_RESPONSE,
            "rotation": MechanismKind.CORNER_ROTATION,
            "tires": MechanismKind.TIRE_STATE,
            "dampers": MechanismKind.DAMPER_RESPONSE,
            "platform": MechanismKind.PLATFORM_RESPONSE,
            "resistance": MechanismKind.RESISTANCE_SCRUB_LIKE,
            "powertrain": MechanismKind.POWERTRAIN_RESPONSE,
            "stint": MechanismKind.STINT_TREND,
            "integrity": MechanismKind.SIM_INTEGRITY,
        }
        for field_name, mechanism in expected_mechanisms.items():
            reference = getattr(self, field_name)
            if reference is None:
                continue
            if reference.mechanism is not mechanism:
                raise ValueError(f"{field_name} reference has the wrong mechanism kind")
            _validate_subsystem_scope(reference, self)
            if reference.artifact_id not in self.source_artifact_ids:
                raise ValueError(
                    "subsystem artifacts must be declared as frame sources"
                )
        return self


class TemporalRelationship(str, Enum):
    PRECEDES = "precedes"
    RESPONDS_AFTER = "responds_after"
    CO_OCCURS_WITH = "co_occurs_with"
    PERSISTS_INTO = "persists_into"
    RECOVERS_AFTER = "recovers_after"


class StateTransition(AwarenessModel):
    transition_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    context_id: str = Field(min_length=1)
    from_frame_id: str = Field(min_length=1)
    to_frame_id: str = Field(min_length=1)
    relationship: TemporalRelationship
    onset_time: float = Field(ge=0.0, allow_inf_nan=False)
    peak_time: float = Field(ge=0.0, allow_inf_nan=False)
    recovery_time: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    onset_lap_pct: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    peak_lap_pct: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    observed_lag_ms: float = Field(ge=0.0, allow_inf_nan=False)
    source_artifact_ids: tuple[str, ...] = Field(min_length=1)
    source_channels: tuple[str, ...] = Field(min_length=1)
    evidence_state: EvidenceState
    supporting_evidence: tuple[StateEvidenceReference, ...] = Field(min_length=1)
    contradicting_evidence: tuple[StateEvidenceReference, ...] = ()
    blockers: tuple[str, ...] = ()
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def transition_is_temporal_not_causal(self) -> StateTransition:
        if self.from_frame_id == self.to_frame_id:
            raise ValueError("state transitions require two distinct frames")
        if self.peak_time < self.onset_time:
            raise ValueError("transition peak cannot precede onset")
        if self.recovery_time is not None and self.recovery_time < self.peak_time:
            raise ValueError("transition recovery cannot precede its peak")
        if self.peak_lap_pct < self.onset_lap_pct:
            raise ValueError("transition peak position cannot precede onset position")
        if self.evidence_state not in _USABLE_STATE_EVIDENCE:
            raise ValueError("state transitions require usable evidence")
        _require_unique(self.source_artifact_ids, "source artifact")
        _require_unique(self.source_channels, "source channel")
        for reference in (*self.supporting_evidence, *self.contradicting_evidence):
            if reference.run_id != self.run_id or reference.setup_id != self.setup_id:
                raise ValueError(
                    "transition evidence must match run and setup identity"
                )
        return self


class EpisodeRepeatability(AwarenessModel):
    repetition_count: int = Field(ge=1)
    distinct_lap_count: int = Field(ge=1)
    independent_cluster_count: int = Field(ge=1)
    basis: str = Field(min_length=1)

    @model_validator(mode="after")
    def repeatability_counts_are_bounded(self) -> EpisodeRepeatability:
        if self.distinct_lap_count > self.repetition_count:
            raise ValueError("distinct laps cannot exceed repetitions")
        if self.independent_cluster_count > self.distinct_lap_count:
            raise ValueError("independent clusters cannot exceed distinct laps")
        return self


class MechanismEpisode(AwarenessModel):
    """Ordered temporal state evidence with observation-only authority."""

    episode_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    context_id: str = Field(min_length=1)
    lap_scope: tuple[int, ...] = Field(min_length=1)
    phase: str = Field(min_length=1)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_peak: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    state_frame_ids: tuple[str, ...] = Field(min_length=2)
    transition_ids: tuple[str, ...] = Field(min_length=1)
    supporting_mechanism_kinds: tuple[MechanismKind, ...] = Field(min_length=1)
    contradicting_mechanism_kinds: tuple[MechanismKind, ...] = ()
    supporting_artifact_ids: tuple[str, ...] = Field(min_length=1)
    contradicting_artifact_ids: tuple[str, ...] = ()
    independence_cluster_ids: tuple[str, ...] = Field(min_length=1)
    repeatability: EpisodeRepeatability
    time_effect_s: float | None = Field(default=None, allow_inf_nan=False)
    context_blockers: tuple[str, ...] = ()
    mind_change_requirements: tuple[str, ...] = Field(min_length=1)
    measurement_requirements: tuple[str, ...] = Field(min_length=1)
    signature_keys: tuple[str, ...] = ()
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def episode_is_exact_and_non_authoritative(self) -> MechanismEpisode:
        if not self.lap_pct_start <= self.lap_pct_peak <= self.lap_pct_end:
            raise ValueError("episode peak must be inside its physical window")
        if tuple(sorted(self.lap_scope)) != self.lap_scope:
            raise ValueError("episode lap scope must be ordered chronologically")
        for values, label in (
            (self.lap_scope, "lap"),
            (self.state_frame_ids, "state frame"),
            (self.transition_ids, "transition"),
            (self.supporting_mechanism_kinds, "supporting mechanism"),
            (self.contradicting_mechanism_kinds, "contradicting mechanism"),
            (self.supporting_artifact_ids, "supporting artifact"),
            (self.contradicting_artifact_ids, "contradicting artifact"),
            (self.independence_cluster_ids, "independence cluster"),
            (self.mind_change_requirements, "mind-change requirement"),
            (self.measurement_requirements, "measurement requirement"),
            (self.signature_keys, "mechanism signature"),
        ):
            _require_unique(values, label)
        if set(self.supporting_mechanism_kinds) & set(
            self.contradicting_mechanism_kinds
        ):
            raise ValueError(
                "a mechanism cannot both support and contradict one episode"
            )
        if self.repeatability.independent_cluster_count != len(
            self.independence_cluster_ids
        ):
            raise ValueError(
                "episode repeatability must match exact independence clusters"
            )
        return self


class MechanismSignatureDefinition(AwarenessModel):
    """Inspectable expected/contradicting pattern contract, never a probability."""

    signature_key: str = Field(min_length=1)
    signature_version: str = Field(min_length=1)
    label: str = Field(min_length=1)
    valid_phases: tuple[str, ...] = Field(min_length=1)
    required_mechanism_kinds: tuple[MechanismKind, ...] = Field(min_length=1)
    expected_patterns: tuple[str, ...] = Field(min_length=1)
    contradiction_patterns: tuple[str, ...] = Field(min_length=1)
    mind_change_requirements: tuple[str, ...] = Field(min_length=1)
    measurement_requirements: tuple[str, ...] = Field(min_length=1)
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def definition_is_deterministic_and_non_authoritative(
        self,
    ) -> MechanismSignatureDefinition:
        for values, label in (
            (self.valid_phases, "valid phase"),
            (self.required_mechanism_kinds, "required mechanism"),
            (self.expected_patterns, "expected pattern"),
            (self.contradiction_patterns, "contradiction pattern"),
            (self.mind_change_requirements, "mind-change requirement"),
            (self.measurement_requirements, "measurement requirement"),
        ):
            _require_unique(values, label)
        return self


class StateDriftMetric(AwarenessModel):
    metric_key: Literal[
        "center_steering_demand",
        "yaw_response_delay",
        "rf_slip_exposure",
        "rr_slip_exposure",
        "throttle_pickup",
        "chassis_response",
        "platform_clearance",
        "surface_temperature_response",
        "running_pressure",
        "fuel_normalized_phase_time",
        "driver_control_workload",
    ]
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1)
    source_artifact_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def metric_sources_are_exact(self) -> StateDriftMetric:
        _require_unique(self.source_artifact_ids, "drift metric source artifact")
        return self


class StateDriftEntry(AwarenessModel):
    entry_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    context_id: str = Field(min_length=1)
    independence_cluster_id: str = Field(min_length=1)
    lap_number: int = Field(ge=0)
    phase: str = Field(min_length=1)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    metrics: tuple[StateDriftMetric, ...] = Field(min_length=1)
    eligible: Literal[True] = True
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def drift_entry_is_one_exact_window(self) -> StateDriftEntry:
        if self.lap_pct_end < self.lap_pct_start:
            raise ValueError("state-drift physical window must be ordered")
        _require_unique([metric.metric_key for metric in self.metrics], "drift metric")
        return self


class StateDriftFinding(AwarenessModel):
    finding_id: str = Field(min_length=1)
    metric_key: str = Field(min_length=1)
    from_lap_number: int = Field(ge=0)
    to_lap_number: int = Field(ge=0)
    observed_delta: float = Field(allow_inf_nan=False)
    empirical_noise_floor: float = Field(ge=0.0, allow_inf_nan=False)
    persistence_lap_count: int = Field(ge=2)
    relationship: Literal["state_shift_observed"] = "state_shift_observed"
    source_entry_ids: tuple[str, ...] = Field(min_length=3)
    source_artifact_ids: tuple[str, ...] = Field(min_length=1)
    evidence_state: Literal[EvidenceState.OBSERVED_CORRELATION] = (
        EvidenceState.OBSERVED_CORRELATION
    )
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def drift_finding_is_persistent_not_causal(self) -> StateDriftFinding:
        if self.to_lap_number <= self.from_lap_number:
            raise ValueError("state drift must move forward across eligible laps")
        if abs(self.observed_delta) <= self.empirical_noise_floor:
            raise ValueError("state drift must exceed same-context empirical noise")
        _require_unique(self.source_entry_ids, "drift source entry")
        _require_unique(self.source_artifact_ids, "drift source artifact")
        return self


class StateDriftLedger(AwarenessModel):
    ledger_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    status: Literal["ready", "no_finding", "blocked"]
    entries: tuple[StateDriftEntry, ...] = ()
    findings: tuple[StateDriftFinding, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    formal_change_point_authority: Literal[False] = False
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def ledger_is_clean_stint_only(self) -> StateDriftLedger:
        if self.status == "blocked" and (self.findings or not self.blocker_reasons):
            raise ValueError("blocked drift ledgers require blockers and no findings")
        if self.status == "ready" and (not self.findings or self.blocker_reasons):
            raise ValueError("ready drift ledgers require findings and no blockers")
        if self.status == "no_finding" and (self.findings or self.blocker_reasons):
            raise ValueError(
                "no-finding drift ledgers cannot carry findings or blockers"
            )
        if any(
            entry.run_id != self.run_id or entry.setup_id != self.setup_id
            for entry in self.entries
        ):
            raise ValueError("state-drift entries must match exact run and setup")
        laps = [entry.lap_number for entry in self.entries]
        if laps != sorted(laps) or len(laps) != len(set(laps)):
            raise ValueError("state-drift entries require unique chronological laps")
        return self


class TrustState(str, Enum):
    TRUSTED = "trusted"
    LIMITED = "limited"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"


class TrustAxis(AwarenessModel):
    state: TrustState
    basis: str = Field(min_length=1)
    blockers: tuple[str, ...] = ()
    source_artifact_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def trust_state_preserves_blockers(self) -> TrustAxis:
        _require_unique(self.blockers, "trust blocker")
        _require_unique(self.source_artifact_ids, "source artifact")
        if self.state is TrustState.TRUSTED and self.blockers:
            raise ValueError("trusted axes cannot hide blockers")
        if self.state in {
            TrustState.LIMITED,
            TrustState.BLOCKED,
            TrustState.UNAVAILABLE,
        }:
            if not self.blockers:
                raise ValueError(
                    "limited, blocked, and unavailable axes require blockers"
                )
        return self


class TrustBudget(AwarenessModel):
    """Independent trust axes; intentionally has no averaged confidence field."""

    data_health: TrustAxis
    alignment_quality: TrustAxis
    context_comparability: TrustAxis
    driver_repeatability: TrustAxis
    mechanism_separation: TrustAxis
    controlled_response_validity: TrustAxis
    policy_countereffect_risk: TrustAxis
    history_completeness: TrustAxis


def _require_unique(values: tuple[object, ...] | list[object], label: str) -> None:
    if any(value == "" for value in values) or len(values) != len(set(values)):
        raise ValueError(f"{label} values must be non-empty and unique")


def _validate_reference_scope(
    reference: StateEvidenceReference,
    frame: EngineeringStateFrame,
) -> None:
    if (
        reference.run_id != frame.run_id
        or reference.setup_id != frame.setup_id
        or reference.lap_number != frame.lap_number
        or reference.lap_pct_start < frame.lap_pct_start
        or reference.lap_pct_end > frame.lap_pct_end
    ):
        raise ValueError(
            "frame evidence must remain inside the exact run/setup/lap window"
        )


def _validate_subsystem_scope(
    reference: SubsystemStateReference,
    frame: EngineeringStateFrame,
) -> None:
    if (
        reference.run_id != frame.run_id
        or reference.setup_id != frame.setup_id
        or reference.lap_number != frame.lap_number
        or reference.lap_pct_start < frame.lap_pct_start
        or reference.lap_pct_end > frame.lap_pct_end
    ):
        raise ValueError(
            "subsystem references must remain inside the exact frame scope"
        )


__all__ = [
    "AnalyzerVersion",
    "ChannelCoverage",
    "ChannelRole",
    "DerivedMetricContract",
    "EngineeringStateFrame",
    "EpisodeRepeatability",
    "FrameChannelSemantic",
    "MechanismEpisode",
    "MechanismSignatureDefinition",
    "MetricProvenance",
    "StateEvidenceReference",
    "StateDriftEntry",
    "StateDriftFinding",
    "StateDriftLedger",
    "StateDriftMetric",
    "StateTransition",
    "SubsystemStateReference",
    "TemporalRelationship",
    "TrustAxis",
    "TrustBudget",
    "TrustState",
]
