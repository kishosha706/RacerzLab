"""P33 immutable engineering experience and attention-only learning contracts.

The models in this module deliberately contain no current setup action, learned
probability, or causal-authority field.  They preserve qualified historical facts
and project them into a bounded attention prior; P19 remains the only owner of
current cause rank, setup control, and terminal policy.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.evidence import EvidenceState


EngineeringObjectiveValue = Literal[
    "qualifying_peak",
    "race_long_run",
    "tire_conservation",
    "driver_confidence",
    "traffic_robustness",
    "superspeedway_stability",
    "fuel_strategy",
]
ContextTransferLevel = Literal["exact", "compatible", "weak", "blocked"]
LearningStrength = Literal[
    "single_case",
    "repeated_same_context",
    "repeated_multi_session",
    "controlled_repeated",
    "cross_context_supported",
    "conflicted",
    "insufficient",
]


class EngineeringLearningModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


def _unique(values: tuple[str, ...], label: str) -> None:
    if any(not value for value in values) or len(values) != len(set(values)):
        raise ValueError(f"P33 {label} identities must be non-empty and unique")


_UNSAFE_MEMORY_PROSE = (
    re.compile(r"\b(?:set|adjust|change)\s+[a-z][\w -]{0,48}\s+to\s+[-+]?\d", re.I),
    re.compile(
        r"\b(?:increase|decrease|raise|lower|add|remove)\s+[a-z][\w -]{0,48}\s+by\s+[-+]?\d",
        re.I,
    ),
    re.compile(r"\b(?:keep|undo)\s+(?:the|this)\s+(?:change|setup)\b", re.I),
    re.compile(
        r"\b(?:recommend|recommended|must|should)\s+(?:set|adjust|change|increase|decrease|raise|lower)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:caused?|due\s+to|because\s+of|responsible\s+for|proves?|"
        r"produc(?:e|ed|es|ing)|generat(?:e|ed|es|ing)|result(?:ed|s|ing)?\s+(?:in|from)|"
        r"creates?|drives?|drove|explains?|accounts?\s+for|stems?\s+from|comes?\s+from)\b"
        r"[^.!?\n]{0,64}\b(?:loss|gain|delta|time|problem|handling|instability|understeer|oversteer)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:loss|gain|delta|time|problem|handling|instability|understeer|oversteer)\b"
        r"[^.!?\n]{0,64}\b(?:caused?|due\s+to|because\s+of|responsible\s+for|"
        r"driven\s+by|explained\s+by|attributable\s+to|came\s+from|result(?:ed|s|ing)?\s+from)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:cross[ -]?weight|corner[ -]?weight|ballast|wedge|brake[ -]?bias|"
        r"ride[ -]?height|shock|damper|spring|tire[ -]?pressure|anti[ -]?roll[ -]?bar|"
        r"sway[ -]?bar|camber|caster|toe|track[ -]?bar|gear|final[ -]?drive|splitter|tape)\b"
        r"[^.!?\n]{0,64}[+-]?\d+(?:\.\d+)?\s*(?:%|psi|kpa|bar|lb/?in|n/?mm|clicks?|inches?|mm|degrees?)?",
        re.I,
    ),
    re.compile(
        r"(?:^|[.!?]\s+)(?:keep|undo|revert|rollback|roll back|stop testing|no more testing)(?:\s+it|\s+the change|\s+this change)?(?=[.!?]|$)",
        re.I,
    ),
)

_NEGATED_CAUSAL_MEMORY = re.compile(
    r"\b(?:does\s+not|do\s+not|did\s+not|cannot|can\s+not|is\s+not|are\s+not|"
    r"was\s+not|were\s+not)\s+"
    r"(?:caus(?:e|ed|es|ing)|produc(?:e|ed|es|ing)|generat(?:e|ed|es|ing)|"
    r"result(?:ed|s|ing)?\s+(?:in|from)|create(?:d|s|ing)?|drive|drives|drove|"
    r"explain(?:ed|s|ing)?|establish(?:ed|es|ing)?|prove(?:d|s|n|ing)?)\b"
    r"[^.!?\n]{0,64}\b(?:loss|gain|delta|time|problem|handling|instability|understeer|oversteer)\b",
    re.I,
)


def validate_memory_prose(value: str, *, label: str) -> str:
    """Reject advice/causal prose that an attention-only memory cannot own."""

    if value != " ".join(value.split()):
        raise ValueError(f"P33 {label} prose must use canonical whitespace")
    causal_scoped = _NEGATED_CAUSAL_MEMORY.sub("explicit non-causal boundary", value)
    if any(pattern.search(causal_scoped) for pattern in _UNSAFE_MEMORY_PROSE):
        raise ValueError(f"P33 {label} prose exceeds attention-only authority")
    return value


class EvidenceUnitCounts(EngineeringLearningModel):
    observation_count: int = Field(ge=0)
    independent_episode_count: int = Field(ge=0)
    independent_workflow_count: int = Field(ge=0)
    distinct_session_count: int = Field(ge=0)
    distinct_context_count: int = Field(ge=0)

    @model_validator(mode="after")
    def counts_are_physical_units(self) -> Self:
        if self.independent_episode_count > self.observation_count:
            raise ValueError("P33 episodes cannot exceed qualified observations")
        if self.independent_workflow_count > self.observation_count:
            raise ValueError("P33 workflows cannot exceed qualified observations")
        if self.distinct_session_count > self.observation_count:
            raise ValueError("P33 sessions cannot exceed qualified observations")
        if self.distinct_context_count > self.observation_count:
            raise ValueError("P33 contexts cannot exceed qualified observations")
        return self


class EngineeringExperienceContext(EngineeringLearningModel):
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    driver_id: str | None = Field(default=None, min_length=1)
    car_path: str = Field(min_length=1)
    car_version: str = Field(min_length=1)
    iracing_build: str = Field(min_length=1)
    track: str = Field(min_length=1)
    track_configuration: str = Field(min_length=1)
    package_type: str = Field(min_length=1)
    setup_family: str | None = Field(default=None, min_length=1)
    setup_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    objective: EngineeringObjectiveValue
    physical_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    phase: str = Field(min_length=1)
    physical_region: str = Field(min_length=1)
    speed_load_band: str
    fuel_state: str
    tire_state: str
    weather_state: str
    traffic_state: str
    driver_execution_state: str

    @model_validator(mode="after")
    def context_identity_is_canonical(self) -> Self:
        body = self.model_dump(
            mode="json", exclude={"context_sha256", "run_id", "session_id"}
        )
        if canonical_json_sha256(body) != self.context_sha256:
            raise ValueError("P33 engineering context identity is corrupt")
        return self

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.pop("context_sha256", None)
        normalized = cls.model_construct(**body, context_sha256="0" * 64).model_dump(
            mode="json"
        )
        normalized.pop("context_sha256", None)
        identity_body = {
            key: value
            for key, value in normalized.items()
            if key not in {"run_id", "session_id"}
        }
        return cls.model_validate(
            {
                **normalized,
                "context_sha256": canonical_json_sha256(identity_body),
            }
        )


class ProblemFingerprint(EngineeringLearningModel):
    problem_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    physical_episode_id: str | None = Field(default=None, min_length=1)
    performance_opportunity_id: str | None = Field(default=None, min_length=1)
    phase: str = Field(min_length=1)
    physical_region: str = Field(min_length=1)
    time_origin_class: str = Field(min_length=1)
    carry_behavior: str = Field(min_length=1)
    driver_demand_state: str = Field(min_length=1)
    vehicle_response_state: str = Field(min_length=1)
    p20_mechanism_families: tuple[str, ...] = ()
    p26_component_families: tuple[str, ...] = ()
    traffic_context_state: str = Field(min_length=1)
    tire_stint_state: str = Field(min_length=1)
    objective: EngineeringObjectiveValue
    source_artifact_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def fingerprint_is_canonical(self) -> Self:
        for values, label in (
            (self.p20_mechanism_families, "mechanism"),
            (self.p26_component_families, "component"),
            (self.source_artifact_ids, "problem-artifact"),
        ):
            _unique(values, label)
        body = self.model_dump(
            mode="json",
            exclude={
                "problem_sha256",
                "physical_episode_id",
                "performance_opportunity_id",
                "source_artifact_ids",
            },
        )
        if canonical_json_sha256(body) != self.problem_sha256:
            raise ValueError("P33 problem fingerprint identity is corrupt")
        return self

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.pop("problem_sha256", None)
        normalized = cls.model_construct(**body, problem_sha256="0" * 64).model_dump(
            mode="json"
        )
        normalized.pop("problem_sha256", None)
        identity_body = {
            key: value
            for key, value in normalized.items()
            if key
            not in {
                "physical_episode_id",
                "performance_opportunity_id",
                "source_artifact_ids",
            }
        }
        return cls.model_validate(
            {
                **normalized,
                "problem_sha256": canonical_json_sha256(identity_body),
            }
        )


class P19CauseMemory(EngineeringLearningModel):
    cause_id: str = Field(min_length=1)
    status: Literal["likely", "possible", "ruled_out", "unresolved"]
    ordinal_rank: int = Field(ge=1)
    mechanism_family: str | None = Field(default=None, min_length=1)


class P19ReasoningMemory(EngineeringLearningModel):
    reasoning_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    causes: tuple[P19CauseMemory, ...]
    measurement_plan_kind: str = Field(min_length=1)
    discriminator_ids: tuple[str, ...] = ()
    authority_level: Literal[
        "observation", "measurement", "controlled_setup", "blocked"
    ]
    setup_authorized: bool

    @model_validator(mode="after")
    def preserves_exact_p19_state(self) -> Self:
        cause_ids = tuple(item.cause_id for item in self.causes)
        _unique(cause_ids, "P19 cause")
        # P19 uses competition ranking: independent causes in the same evidence
        # tier intentionally share an ordinal rank.  P33 preserves those ties;
        # inventing a unique order here would silently acquire cause authority.
        _unique(self.discriminator_ids, "discriminator")
        if self.setup_authorized != (self.authority_level == "controlled_setup"):
            raise ValueError("P33 must preserve the exact P19 authority state")
        return self


DriverMetric = Literal[
    "brake_onset_consistency",
    "brake_release_timing_consistency",
    "steering_onset_consistency",
    "steering_workload",
    "correction_frequency",
    "throttle_pickup_timing",
    "throttle_realization",
    "line_repeatability",
    "phase_time_repeatability",
    "short_run_long_run_behavior",
    "traffic_execution",
    "controlled_test_execution_consistency",
    "driver_vehicle_separation",
]


class DriverFingerprintContribution(EngineeringLearningModel):
    contribution_id: str = Field(min_length=1)
    metric: DriverMetric
    tendency: Literal[
        "repeatable_tendency",
        "context_dependent_tendency",
        "insufficient_history",
        "changed_behavior",
    ]
    statement: str = Field(min_length=1)
    physical_episode_ids: tuple[str, ...] = ()
    source_artifact_ids: tuple[str, ...] = Field(min_length=1)
    source_lap_count: int = Field(ge=0)
    authority: Literal["driver_context_only"] = "driver_context_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def driver_fact_is_not_diagnosis(self) -> Self:
        _unique(self.physical_episode_ids, "driver episode")
        _unique(self.source_artifact_ids, "driver artifact")
        validate_memory_prose(self.statement, label="driver")
        return self


class PerformanceResponseFact(EngineeringLearningModel):
    performance_opportunity_id: str | None = Field(default=None, min_length=1)
    observed_delta_s: FiniteFloat | None = None
    observed_direction: Literal["loss", "gain", "unavailable"]
    attribution_state: Literal[
        "candidate_only",
        "blocked_by_traffic",
        "blocked_by_context",
        "unavailable",
    ]
    time_origin: str = Field(min_length=1)
    phase_effect_s: FiniteFloat | None = None
    carry_effect_s: FiniteFloat | None = None
    recovery_surrender: str = Field(min_length=1)
    source_response_record_id: str | None = Field(default=None, min_length=1)
    source_artifact_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def blocked_attribution_stays_observational(self) -> Self:
        _unique(self.source_artifact_ids, "performance artifact")
        if self.observed_delta_s is None and self.observed_direction != "unavailable":
            raise ValueError("P33 signed direction requires a measured delta")
        if self.observed_delta_s is not None:
            expected = (
                "gain"
                if self.observed_delta_s < 0
                else "loss"
                if self.observed_delta_s > 0
                else "unavailable"
            )
            if self.observed_direction != expected:
                raise ValueError("P33 performance response sign is inconsistent")
        if (self.observed_delta_s is None) != (self.attribution_state == "unavailable"):
            raise ValueError(
                "P33 unavailable attribution must match unavailable performance"
            )
        return self


class CarResponseFact(EngineeringLearningModel):
    response_id: str = Field(min_length=1)
    component: str = Field(pattern=r"^[a-z][a-z0-9_.:-]*$")
    control: str = Field(pattern=r"^[a-z][a-z0-9_.:-]*$")
    direction: Literal["increase", "decrease", "unchanged", "unknown"]
    magnitude_class: Literal["adjacent", "small", "medium", "large", "unknown"]
    expected_vehicle_response: str = Field(min_length=1)
    observed_vehicle_response: str = Field(min_length=1)
    p32_time_origin: str = Field(min_length=1)
    phase_time_effect_s: FiniteFloat | None = None
    carry_effect_s: FiniteFloat | None = None
    recovery_surrender: str = Field(min_length=1)
    countereffects: tuple[str, ...] = ()
    p19_mechanism_assessment: Literal[
        "supported", "weakened", "unchanged", "inconclusive", "invalid"
    ]
    control_response_assessment: Literal[
        "matched", "missed", "inconclusive", "unavailable", "invalid"
    ]
    policy_verdict: Literal["keep", "undo", "retest", "invalid"]
    source_workflow_id: str = Field(min_length=1)
    source_response_record_id: str | None = Field(default=None, min_length=1)
    source_artifact_ids: tuple[str, ...] = ()
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def undo_keeps_three_axes_separate(self) -> Self:
        _unique(self.countereffects, "countereffect")
        _unique(self.source_artifact_ids, "car-response artifact")
        for label, statement in (
            ("expected car response", self.expected_vehicle_response),
            ("observed car response", self.observed_vehicle_response),
            ("car recovery", self.recovery_surrender),
            *(("car countereffect", item) for item in self.countereffects),
        ):
            validate_memory_prose(statement, label=label)
        if self.policy_verdict == "undo" and not self.countereffects:
            raise ValueError("P33 Undo history must preserve its countereffect")
        if self.policy_verdict == "invalid" and any(
            value is not None
            for value in (self.phase_time_effect_s, self.carry_effect_s)
        ):
            raise ValueError("invalid P33 response history cannot publish time effects")
        return self


class InvestigationPathFact(EngineeringLearningModel):
    investigation_id: str = Field(min_length=1)
    started_at: datetime
    completed_at: datetime
    initial_cause_ids: tuple[str, ...] = ()
    tools_inspected: tuple[str, ...] = ()
    driver_question_ids: tuple[str, ...] = ()
    driver_answers: tuple[str, ...] = ()
    requested_measurement_ids: tuple[str, ...] = ()
    completed_measurement_ids: tuple[str, ...] = ()
    strongest_contradiction: str
    eliminated_cause_ids: tuple[str, ...] = ()
    unresolved_cause_ids: tuple[str, ...] = ()
    terminal_decision: Literal[
        "controlled_test",
        "retest",
        "no_call",
        "driver_focus",
        "measurement_only",
        "abandoned",
    ]
    workflow_ids: tuple[str, ...] = ()
    elapsed_seconds: FiniteFloat = Field(ge=0)
    laps_consumed: int = Field(ge=0)
    tool_steps_consumed: int = Field(ge=0)
    driver_questions_consumed: int = Field(ge=0)
    successful_discriminator_ids: tuple[str, ...] = ()
    source_artifact_ids: tuple[str, ...] = ()
    historical_retrieval_used: bool
    historical_match_confirmed: bool | None = None

    @model_validator(mode="after")
    def operational_counts_match_identities(self) -> Self:
        for values, label in (
            (self.initial_cause_ids, "initial cause"),
            (self.driver_question_ids, "driver question"),
            (self.requested_measurement_ids, "requested measurement"),
            (self.completed_measurement_ids, "completed measurement"),
            (self.eliminated_cause_ids, "eliminated cause"),
            (self.unresolved_cause_ids, "unresolved cause"),
            (self.workflow_ids, "investigation workflow"),
            (self.successful_discriminator_ids, "successful discriminator"),
            (self.source_artifact_ids, "investigation artifact"),
        ):
            _unique(values, label)
        if self.completed_at < self.started_at:
            raise ValueError("P33 investigation completion precedes its start")
        if self.tool_steps_consumed != len(self.tools_inspected):
            raise ValueError("P33 tool-step count must match the event sequence")
        if self.driver_questions_consumed != len(self.driver_question_ids):
            raise ValueError("P33 question count must match exact question IDs")
        if not set(self.completed_measurement_ids).issubset(
            self.requested_measurement_ids
        ):
            raise ValueError("P33 completed measurements must have been requested")
        if not set(self.successful_discriminator_ids).issubset(self.tools_inspected):
            raise ValueError("P33 successful discriminators must be inspected tools")
        if not set(self.successful_discriminator_ids).issubset(
            self.completed_measurement_ids
        ):
            raise ValueError(
                "P33 successful discriminators must be completed measurements"
            )
        validate_memory_prose(self.strongest_contradiction, label="contradiction")
        return self


class MindChangeFact(EngineeringLearningModel):
    mind_change_id: str = Field(min_length=1)
    before_reasoning: P19ReasoningMemory
    after_reasoning: P19ReasoningMemory
    new_artifact_ids: tuple[str, ...] = Field(min_length=1)
    new_evidence_states: tuple[str, ...] = Field(min_length=1)
    causes_promoted: tuple[str, ...] = ()
    causes_demoted: tuple[str, ...] = ()
    causes_ruled_out: tuple[str, ...] = ()
    measurement_discriminator_id: str | None = Field(default=None, min_length=1)
    evidence_discriminated: bool
    driver_question_involved: bool
    controlled_evidence_involved: bool
    context_gate_involved: bool

    @model_validator(mode="after")
    def mind_change_requires_a_real_transition(self) -> Self:
        for values, label in (
            (self.new_artifact_ids, "mind-change artifact"),
            (self.causes_promoted, "promoted cause"),
            (self.causes_demoted, "demoted cause"),
            (self.causes_ruled_out, "ruled cause"),
        ):
            _unique(values, label)
        if any(not state for state in self.new_evidence_states) or len(
            self.new_evidence_states
        ) != len(self.new_artifact_ids):
            raise ValueError(
                "P33 mind-change evidence states must pair with exact artifacts"
            )
        if (
            self.before_reasoning.reasoning_snapshot_sha256
            == self.after_reasoning.reasoning_snapshot_sha256
        ):
            raise ValueError("P33 mind-change history requires a changed P19 snapshot")
        if self.evidence_discriminated and self.measurement_discriminator_id is None:
            raise ValueError(
                "discriminating P33 evidence requires its discriminator identity"
            )
        return self


class DeadEndFact(EngineeringLearningModel):
    dead_end_id: str = Field(min_length=1)
    kind: Literal[
        "failed_investigation",
        "non_discriminating_measurement",
        "repeated_no_finding_tool",
        "repeated_undo_policy",
        "irrelevant_component_family",
        "context_invalidated_comparison",
    ]
    tool_id: str | None = Field(default=None, min_length=1)
    component_family: str | None = Field(default=None, min_length=1)
    control: str | None = Field(default=None, min_length=1)
    statement: str = Field(min_length=1)
    source_artifact_ids: tuple[str, ...] = ()
    source_workflow_ids: tuple[str, ...] = ()
    current_evidence_may_override: Literal[True] = True
    authority: Literal["attention_only"] = "attention_only"

    @model_validator(mode="after")
    def negative_knowledge_cannot_veto_physics(self) -> Self:
        _unique(self.source_artifact_ids, "dead-end artifact")
        _unique(self.source_workflow_ids, "dead-end workflow")
        validate_memory_prose(self.statement, label="dead-end")
        return self


class EngineeringSourceProvenance(EngineeringLearningModel):
    """One exact historical artifact bound to its run/setup/build reality."""

    provenance_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_id: str = Field(min_length=1)
    producer_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    setup_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    build_context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lap_numbers: tuple[int, ...] = ()
    lap_pct_start: FiniteFloat | None = Field(default=None, ge=0, le=100)
    lap_pct_end: FiniteFloat | None = Field(default=None, ge=0, le=100)
    phase: str | None = Field(default=None, min_length=1)
    source_channels: tuple[str, ...] = ()
    evidence_state: EvidenceState
    polarity: Literal["support", "contradiction", "neutral"]

    @model_validator(mode="after")
    def exact_source_identity_is_canonical(self) -> Self:
        if len(self.lap_numbers) != len(set(self.lap_numbers)) or any(
            lap < 0 for lap in self.lap_numbers
        ):
            raise ValueError(
                "P33 source lap identities must be non-negative and unique"
            )
        _unique(self.source_channels, "source channel")
        if (self.lap_pct_start is None) != (self.lap_pct_end is None):
            raise ValueError("P33 source physical windows require both bounds")
        if (
            self.lap_pct_start is not None
            and self.lap_pct_end is not None
            and self.lap_pct_end < self.lap_pct_start
        ):
            raise ValueError("P33 source physical window is reversed")
        body = self.model_dump(mode="json", exclude={"provenance_sha256"})
        if canonical_json_sha256(body) != self.provenance_sha256:
            raise ValueError("P33 source provenance identity is corrupt")
        return self

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.pop("provenance_sha256", None)
        body["evidence_state"] = EvidenceState(body["evidence_state"])
        normalized = cls.model_construct(**body, provenance_sha256="0" * 64).model_dump(
            mode="json"
        )
        normalized.pop("provenance_sha256", None)
        return cls.model_validate(
            {
                **normalized,
                "provenance_sha256": canonical_json_sha256(normalized),
            }
        )


class EngineeringExperienceRecord(EngineeringLearningModel):
    schema_version: Literal["p33.engineering-experience.v1"] = (
        "p33.engineering-experience.v1"
    )
    experience_id: str = Field(pattern=r"^p33x_[0-9a-f]{24}$")
    experience_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_kind: Literal["resolved_investigation", "controlled_workflow"]
    source_investigation_id: str | None = Field(default=None, min_length=1)
    source_workflow_id: str | None = Field(default=None, min_length=1)
    created_at: datetime
    context: EngineeringExperienceContext
    problem: ProblemFingerprint
    source_p19_reasoning_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_p32_projection_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    opening_reasoning: P19ReasoningMemory | None = None
    closing_reasoning: P19ReasoningMemory
    driver_contributions: tuple[DriverFingerprintContribution, ...] = ()
    car_response: CarResponseFact | None = None
    performance_response: PerformanceResponseFact | None = None
    investigation_outcome: InvestigationPathFact | None = None
    mind_change: MindChangeFact | None = None
    dead_ends: tuple[DeadEndFact, ...] = ()
    source_event_ids: tuple[str, ...] = ()
    source_response_record_ids: tuple[str, ...] = ()
    source_artifact_ids: tuple[str, ...] = ()
    source_provenance: tuple[EngineeringSourceProvenance, ...] = Field(min_length=1)
    raw_telemetry_included: Literal[False] = False

    @staticmethod
    def _source_identity(payload: dict[str, Any]) -> str:
        return canonical_json_sha256(
            {
                "schema_version": payload.get(
                    "schema_version", "p33.engineering-experience.v1"
                ),
                "source_kind": payload["source_kind"],
                "source_investigation_id": payload.get("source_investigation_id"),
                "source_workflow_id": payload.get("source_workflow_id"),
            }
        )

    @staticmethod
    def _content_body(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in payload.items()
            if key not in {"experience_id", "experience_sha256"}
        }

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.setdefault("schema_version", "p33.engineering-experience.v1")
        body.pop("experience_id", None)
        body.pop("experience_sha256", None)
        body["source_identity_sha256"] = cls._source_identity(body)
        draft = cls.model_construct(
            **body,
            experience_id="p33x_" + ("0" * 24),
            experience_sha256="0" * 64,
        )
        normalized = draft.model_dump(mode="json")
        digest = canonical_json_sha256(cls._content_body(normalized))
        return cls.model_validate(
            {
                **normalized,
                "experience_id": f"p33x_{digest[:24]}",
                "experience_sha256": digest,
            }
        )

    @model_validator(mode="after")
    def immutable_identity_and_source_are_exact(self) -> Self:
        for values, label in (
            (self.source_event_ids, "source event"),
            (self.source_response_record_ids, "source response"),
            (self.source_artifact_ids, "source artifact"),
            (
                tuple(item.provenance_sha256 for item in self.source_provenance),
                "source provenance",
            ),
        ):
            _unique(values, label)
        _unique(
            tuple(item.artifact_id for item in self.source_provenance),
            "source provenance artifact",
        )
        provenance_artifact_ids = {item.artifact_id for item in self.source_provenance}
        nested_artifact_ids = {
            *self.problem.source_artifact_ids,
            *(
                artifact_id
                for contribution in self.driver_contributions
                for artifact_id in contribution.source_artifact_ids
            ),
            *(
                self.car_response.source_artifact_ids
                if self.car_response is not None
                else ()
            ),
            *(
                self.performance_response.source_artifact_ids
                if self.performance_response is not None
                else ()
            ),
            *(
                self.investigation_outcome.source_artifact_ids
                if self.investigation_outcome is not None
                else ()
            ),
            *(
                self.mind_change.new_artifact_ids
                if self.mind_change is not None
                else ()
            ),
            *(
                artifact_id
                for dead_end in self.dead_ends
                for artifact_id in dead_end.source_artifact_ids
            ),
        }
        if not nested_artifact_ids.issubset(set(self.source_artifact_ids)):
            raise ValueError(
                "P33 nested facts must resolve through top-level source artifacts"
            )
        if not set(self.source_artifact_ids).issubset(provenance_artifact_ids):
            raise ValueError(
                "P33 source artifacts require exact run/setup/build provenance"
            )
        current_sources = tuple(
            item
            for item in self.source_provenance
            if item.run_id == self.context.run_id
        )
        if not current_sources or any(
            item.session_id != self.context.session_id
            or item.setup_snapshot_sha256 != self.context.setup_snapshot_sha256
            for item in current_sources
        ):
            raise ValueError(
                "P33 current source run/session/setup must resolve in exact provenance"
            )
        if (
            self.source_p19_reasoning_snapshot_sha256
            != self.closing_reasoning.reasoning_snapshot_sha256
        ):
            raise ValueError("P33 source P19 identity must equal closing reasoning")
        if self.mind_change is not None and (
            self.opening_reasoning is None
            or self.mind_change.before_reasoning != self.opening_reasoning
            or self.mind_change.after_reasoning != self.closing_reasoning
        ):
            raise ValueError(
                "P33 mind change must bind the exact opening and closing P19 state"
            )
        if self.mind_change is not None and self.investigation_outcome is not None:
            discriminator_id = self.mind_change.measurement_discriminator_id
            successful_ids = self.investigation_outcome.successful_discriminator_ids
            if self.mind_change.evidence_discriminated:
                if discriminator_id not in successful_ids:
                    raise ValueError(
                        "P33 discriminating mind change must bind a successful investigation discriminator"
                    )
            elif discriminator_id is not None:
                raise ValueError(
                    "P33 non-discriminating mind change cannot claim a measurement discriminator"
                )
        nested_response_ids = {
            *(
                (self.car_response.source_response_record_id,)
                if self.car_response is not None
                and self.car_response.source_response_record_id is not None
                else ()
            ),
            *(
                (self.performance_response.source_response_record_id,)
                if self.performance_response is not None
                and self.performance_response.source_response_record_id is not None
                else ()
            ),
        }
        if not nested_response_ids.issubset(set(self.source_response_record_ids)):
            raise ValueError(
                "P33 response facts must resolve through top-level response identities"
            )
        if (
            self.performance_response is not None
            and self.source_p32_projection_sha256 is None
        ):
            raise ValueError(
                "P33 performance history requires its exact P32 projection"
            )
        investigation_source = self.source_investigation_id is not None
        workflow_source = self.source_workflow_id is not None
        if self.source_kind == "resolved_investigation":
            if (
                not investigation_source
                or workflow_source
                or self.investigation_outcome is None
            ):
                raise ValueError(
                    "P33 investigation experience requires one investigation outcome"
                )
        elif (
            investigation_source
            or not workflow_source
            or self.investigation_outcome is not None
        ):
            raise ValueError("P33 workflow experience requires one workflow source")
        if self.car_response is not None and (
            self.source_workflow_id is not None
            and self.car_response.source_workflow_id != self.source_workflow_id
        ):
            raise ValueError("P33 car response must match its source workflow")
        dumped = self.model_dump(mode="json")
        expected_source = self._source_identity(dumped)
        expected_content = canonical_json_sha256(self._content_body(dumped))
        if expected_source != self.source_identity_sha256:
            raise ValueError("P33 source identity is corrupt")
        if expected_content != self.experience_sha256:
            raise ValueError("P33 experience content identity is corrupt")
        if self.experience_id != f"p33x_{expected_content[:24]}":
            raise ValueError("P33 experience ID does not match its content")
        return self


class ContextTransferAssessment(EngineeringLearningModel):
    experience_id: str = Field(pattern=r"^p33x_[0-9a-f]{24}$")
    level: ContextTransferLevel
    matching_dimensions: tuple[str, ...] = ()
    mismatched_dimensions: tuple[str, ...] = ()
    drift_reasons: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def transfer_is_explicit(self) -> Self:
        for values, label in (
            (self.matching_dimensions, "matching dimension"),
            (self.mismatched_dimensions, "mismatched dimension"),
            (self.drift_reasons, "drift reason"),
            (self.blocker_reasons, "transfer blocker"),
        ):
            _unique(values, label)
        if self.level == "exact" and (
            self.mismatched_dimensions or self.drift_reasons or self.blocker_reasons
        ):
            raise ValueError("exact P33 transfer cannot contain mismatch or drift")
        if self.level == "blocked" and not self.blocker_reasons:
            raise ValueError("blocked P33 transfer requires a blocker")
        return self


class LearningEvidenceReference(EngineeringLearningModel):
    reference_id: str = Field(pattern=r"^p33ref_[0-9a-f]{24}$")
    experience_id: str = Field(pattern=r"^p33x_[0-9a-f]{24}$")
    provenance: EngineeringSourceProvenance
    state: Literal["available", "unavailable"]
    blocker_reasons: tuple[str, ...] = ()
    authority: Literal["attention_only"] = "attention_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def historical_navigation_is_fail_closed(self) -> Self:
        _unique(self.blocker_reasons, "historical-source blocker")
        if self.state == "available" and self.blocker_reasons:
            raise ValueError("available P33 evidence cannot carry source blockers")
        if self.state == "unavailable" and not self.blocker_reasons:
            raise ValueError("unavailable P33 evidence requires a source blocker")
        expected = canonical_json_sha256(
            {
                "experience_id": self.experience_id,
                "provenance_sha256": self.provenance.provenance_sha256,
            }
        )
        if self.reference_id != f"p33ref_{expected[:24]}":
            raise ValueError("P33 learning evidence reference identity is corrupt")
        return self

    @classmethod
    def build(
        cls,
        *,
        experience_id: str,
        provenance: EngineeringSourceProvenance,
        state: Literal["available", "unavailable"],
        blocker_reasons: tuple[str, ...] = (),
    ) -> Self:
        digest = canonical_json_sha256(
            {
                "experience_id": experience_id,
                "provenance_sha256": provenance.provenance_sha256,
            }
        )
        return cls(
            reference_id=f"p33ref_{digest[:24]}",
            experience_id=experience_id,
            provenance=provenance,
            state=state,
            blocker_reasons=blocker_reasons,
        )


class RecurringProblemMatch(EngineeringLearningModel):
    recurrence_id: str = Field(min_length=1)
    classification: Literal[
        "new_problem",
        "possible_recurrence",
        "strong_recurrence",
        "exact_context_recurrence",
    ]
    problem_sha256s: tuple[str, ...] = Field(min_length=1)
    experience_ids: tuple[str, ...] = ()
    investigation_ids: tuple[str, ...] = ()
    statement: str = Field(min_length=1)
    useful_discriminator: str | None = Field(default=None, min_length=1)
    prior_dead_end: str | None = Field(default=None, min_length=1)
    strongest_contradiction: str
    transfer: ContextTransferAssessment | None = None
    counts: EvidenceUnitCounts
    strength: LearningStrength
    authority: Literal["attention_only"] = "attention_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def recurrence_uses_independent_cases(self) -> Self:
        for values, label in (
            (self.problem_sha256s, "problem fingerprint"),
            (self.experience_ids, "recurrence experience"),
            (self.investigation_ids, "recurrence investigation"),
        ):
            _unique(values, label)
        for label, value in (
            ("recurrence", self.statement),
            ("recurrence contradiction", self.strongest_contradiction),
            ("recurrence discriminator", self.useful_discriminator),
            ("recurrence dead end", self.prior_dead_end),
        ):
            if value is not None:
                validate_memory_prose(value, label=label)
        if self.classification == "new_problem" and self.experience_ids:
            raise ValueError("a new P33 problem cannot cite prior experiences")
        if self.classification in {
            "strong_recurrence",
            "exact_context_recurrence",
        } and (
            self.counts.independent_episode_count < 2
            and self.counts.independent_workflow_count < 2
        ):
            raise ValueError(
                "strong P33 recurrence requires two independent evidence units"
            )
        return self


class DriverPerformanceFingerprint(EngineeringLearningModel):
    fingerprint_id: str = Field(min_length=1)
    driver_id: str = Field(min_length=1)
    transfer_level: ContextTransferLevel
    state: Literal[
        "repeatable_tendency",
        "context_dependent_tendency",
        "insufficient_history",
        "changed_behavior",
    ]
    tendencies: tuple[DriverFingerprintContribution, ...] = ()
    counts: EvidenceUnitCounts
    source_experience_ids: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    authority: Literal["driver_context_only"] = "driver_context_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def driver_history_remains_context_only(self) -> Self:
        _unique(self.source_experience_ids, "driver experience")
        _unique(self.contradictions, "driver contradiction")
        if self.state == "insufficient_history" and self.tendencies:
            raise ValueError(
                "insufficient P33 driver history cannot publish a tendency"
            )
        if self.state in {"repeatable_tendency", "changed_behavior"} and (
            self.counts.independent_episode_count < 2
            and self.counts.independent_workflow_count < 2
        ):
            raise ValueError(
                "qualified P33 driver tendencies require two independent evidence units"
            )
        if any(item.tendency != self.state for item in self.tendencies):
            raise ValueError(
                "P33 driver contributions must match their fingerprint state"
            )
        return self


class CarResponseFingerprint(EngineeringLearningModel):
    fingerprint_id: str = Field(min_length=1)
    transfer_level: ContextTransferLevel
    response: CarResponseFact
    counts: EvidenceUnitCounts
    source_experience_ids: tuple[str, ...] = Field(min_length=1)
    source_workflow_ids: tuple[str, ...] = Field(min_length=1)
    contradictions: tuple[str, ...] = ()
    statement: str = Field(min_length=1)
    authority: Literal["controlled_history_only"] = "controlled_history_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def car_history_is_descriptive(self) -> Self:
        _unique(self.source_experience_ids, "car experience")
        _unique(self.source_workflow_ids, "car workflow")
        _unique(self.contradictions, "car contradiction")
        validate_memory_prose(self.statement, label="car response")
        if (
            self.counts.independent_workflow_count < 1
            or self.counts.independent_workflow_count != len(self.source_workflow_ids)
        ):
            raise ValueError(
                "P33 car response strength requires exact independent workflows"
            )
        return self


class InvestigationOutcomeRecord(EngineeringLearningModel):
    outcome_id: str = Field(min_length=1)
    experience_id: str = Field(pattern=r"^p33x_[0-9a-f]{24}$")
    transfer_level: ContextTransferLevel
    outcome: InvestigationPathFact
    counts: EvidenceUnitCounts
    useful: bool
    explanation: str = Field(min_length=1)
    authority: Literal["attention_only"] = "attention_only"

    @model_validator(mode="after")
    def effectiveness_is_operational_only(self) -> Self:
        validate_memory_prose(self.explanation, label="investigation effectiveness")
        return self


class MindChangeRecord(EngineeringLearningModel):
    experience_id: str = Field(pattern=r"^p33x_[0-9a-f]{24}$")
    transfer_level: ContextTransferLevel
    fact: MindChangeFact
    statement: str = Field(min_length=1)
    authority: Literal["attention_only"] = "attention_only"

    @model_validator(mode="after")
    def mind_change_is_a_retrieval_prior(self) -> Self:
        validate_memory_prose(self.statement, label="mind change")
        return self


class EngineeringDeadEndRecord(EngineeringLearningModel):
    experience_ids: tuple[str, ...] = Field(min_length=1)
    transfer_level: ContextTransferLevel
    fact: DeadEndFact
    counts: EvidenceUnitCounts
    may_deprioritize_within_band: bool
    may_veto_current_evidence: Literal[False] = False

    @model_validator(mode="after")
    def dead_end_is_bounded(self) -> Self:
        _unique(self.experience_ids, "dead-end experience")
        if self.may_deprioritize_within_band and (
            self.transfer_level not in {"exact", "compatible"}
            or (
                self.counts.independent_episode_count < 2
                and self.counts.independent_workflow_count < 2
            )
        ):
            raise ValueError(
                "P33 dead ends need repeated transferable evidence to change order"
            )
        return self


class AttentionOrderItem(EngineeringLearningModel):
    tool_id: str = Field(min_length=1)
    safety_band: str = Field(min_length=1)
    learned_rank_within_band: int = Field(ge=1)
    baseline_rank_within_band: int = Field(ge=1)
    reason: str = Field(min_length=1)
    transfer_level: Literal["exact", "compatible"]
    source_experience_ids: tuple[str, ...] = Field(min_length=1)
    investigation_count: int = Field(ge=2)
    session_count: int = Field(ge=1)
    independent_workflow_count: int = Field(ge=0)
    authority: Literal["attention_only"] = "attention_only"

    @model_validator(mode="after")
    def attention_reason_is_transparent(self) -> Self:
        _unique(self.source_experience_ids, "attention experience")
        validate_memory_prose(self.reason, label="attention")
        if len(self.source_experience_ids) < 2:
            raise ValueError(
                "P33 learned attention requires two independent prior experiences"
            )
        return self


class EngineeringLearningLedger(EngineeringLearningModel):
    investigations_opened: int = Field(ge=0)
    investigations_resolved: int = Field(ge=0)
    no_call_outcomes: int = Field(ge=0)
    driver_focus_outcomes: int = Field(ge=0)
    measurement_missions: int = Field(ge=0)
    controlled_tests: int = Field(ge=0)
    keep_outcomes: int = Field(ge=0)
    undo_outcomes: int = Field(ge=0)
    retest_outcomes: int = Field(ge=0)
    average_tool_steps_before_resolution: FiniteFloat | None = Field(default=None, ge=0)
    laps_consumed_before_resolution: int = Field(ge=0)
    questions_asked: int = Field(ge=0)
    repeated_dead_end_tools: tuple[str, ...] = ()
    successful_discriminators: tuple[str, ...] = ()
    recurring_problem_count: int = Field(ge=0)
    recurrence_resolved_faster_count: int = Field(ge=0)
    claims_lap_time_improvement: Literal[False] = False

    @model_validator(mode="after")
    def ledger_counts_are_operational(self) -> Self:
        _unique(self.repeated_dead_end_tools, "ledger dead-end tool")
        _unique(self.successful_discriminators, "ledger discriminator")
        if self.investigations_resolved > self.investigations_opened:
            raise ValueError(
                "P33 resolved investigations cannot exceed opened investigations"
            )
        return self


class PostRunLearningBrief(EngineeringLearningModel):
    state: Literal["available", "insufficient_history", "blocked"]
    what_we_learned: tuple[str, ...] = ()
    what_changed_our_mind: tuple[str, ...] = ()
    what_did_not_work: tuple[str, ...] = ()
    next_attention: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    authority: Literal["attention_only"] = "attention_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def brief_is_safe_and_stateful(self) -> Self:
        groups = (
            (self.what_we_learned, "brief learning"),
            (self.what_changed_our_mind, "brief mind change"),
            (self.what_did_not_work, "brief dead end"),
            (self.next_attention, "brief attention"),
            (self.blocker_reasons, "brief blocker"),
        )
        for values, label in groups:
            _unique(values, label)
            for value in values:
                validate_memory_prose(value, label=label)
        content = any(values for values, _ in groups[:-1])
        if self.state == "available" and not content:
            raise ValueError("available P33 brief requires a qualified fact")
        if self.state != "available" and (content or not self.blocker_reasons):
            raise ValueError("unavailable P33 brief requires blockers and no claims")
        return self


class CrewChiefLearningPrior(EngineeringLearningModel):
    schema_version: Literal["p33.engineering-learning.v1"] = (
        "p33.engineering-learning.v1"
    )
    projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    history_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    objective_id: EngineeringObjectiveValue
    selected_scope_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    p19_reasoning_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p32_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_problem_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    state: Literal["available", "insufficient_history", "blocked"]
    recurrence: RecurringProblemMatch
    useful_prior_investigations: tuple[InvestigationOutcomeRecord, ...] = ()
    known_dead_ends: tuple[EngineeringDeadEndRecord, ...] = ()
    driver_tendencies: tuple[DriverPerformanceFingerprint, ...] = ()
    car_response_history: tuple[CarResponseFingerprint, ...] = ()
    mind_change_history: tuple[MindChangeRecord, ...] = ()
    recommended_attention_order: tuple[AttentionOrderItem, ...] = ()
    context_transfers: tuple[ContextTransferAssessment, ...] = ()
    evidence_references: tuple[LearningEvidenceReference, ...] = ()
    context_transfer_level: ContextTransferLevel
    strength: LearningStrength
    counts: EvidenceUnitCounts
    ledger: EngineeringLearningLedger
    post_run_brief: PostRunLearningBrief
    blocker_reasons: tuple[str, ...] = ()
    authority: Literal["attention_only"] = "attention_only"
    setup_authorized: Literal[False] = False
    p19_rank_modified: Literal[False] = False

    @staticmethod
    def _projection_body(payload: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value for key, value in payload.items() if key != "projection_sha256"
        }

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.setdefault("schema_version", "p33.engineering-learning.v1")
        body.pop("projection_sha256", None)
        draft = cls.model_construct(**body, projection_sha256="0" * 64)
        normalized = draft.model_dump(mode="json")
        return cls.model_validate(
            {
                **normalized,
                "projection_sha256": canonical_json_sha256(
                    cls._projection_body(normalized)
                ),
            }
        )

    @model_validator(mode="after")
    def prior_is_one_attention_only_reality(self) -> Self:
        for values, label in (
            (
                tuple(item.outcome_id for item in self.useful_prior_investigations),
                "prior investigation",
            ),
            (
                tuple(item.fact.dead_end_id for item in self.known_dead_ends),
                "prior dead end",
            ),
            (
                tuple(item.fingerprint_id for item in self.driver_tendencies),
                "prior driver fingerprint",
            ),
            (
                tuple(item.fingerprint_id for item in self.car_response_history),
                "prior car fingerprint",
            ),
            (
                tuple(item.fact.mind_change_id for item in self.mind_change_history),
                "prior mind change",
            ),
            (
                tuple(item.tool_id for item in self.recommended_attention_order),
                "prior attention tool",
            ),
            (
                tuple(item.experience_id for item in self.context_transfers),
                "prior context transfer",
            ),
            (
                tuple(item.reference_id for item in self.evidence_references),
                "prior evidence reference",
            ),
            (self.blocker_reasons, "learning blocker"),
        ):
            _unique(values, label)
        surfaced_experience_ids = (
            {item.experience_id for item in self.useful_prior_investigations}
            | {
                experience_id
                for item in self.known_dead_ends
                for experience_id in item.experience_ids
            }
            | {
                experience_id
                for item in self.driver_tendencies
                for experience_id in item.source_experience_ids
            }
            | {
                experience_id
                for item in self.car_response_history
                for experience_id in item.source_experience_ids
            }
            | {item.experience_id for item in self.mind_change_history}
        )
        if any(
            item.experience_id not in surfaced_experience_ids
            for item in self.evidence_references
        ):
            raise ValueError("P33 evidence references must resolve to surfaced memory")
        memory_items = (
            len(self.useful_prior_investigations)
            + len(self.known_dead_ends)
            + len(self.driver_tendencies)
            + len(self.car_response_history)
            + len(self.mind_change_history)
        )
        if self.state == "available" and memory_items == 0:
            raise ValueError("available P33 prior requires qualified memory")
        if self.state == "insufficient_history" and (
            memory_items or self.recommended_attention_order or not self.blocker_reasons
        ):
            raise ValueError(
                "insufficient P33 history requires blockers and no learned reorder"
            )
        if self.state == "blocked" and (
            self.recommended_attention_order or not self.blocker_reasons
        ):
            raise ValueError("blocked P33 history cannot reorder tools")
        if (
            self.context_transfer_level in {"weak", "blocked"}
            and self.recommended_attention_order
        ):
            raise ValueError("weak or blocked P33 history cannot reorder tools")
        dumped = self.model_dump(mode="json")
        if (
            canonical_json_sha256(self._projection_body(dumped))
            != self.projection_sha256
        ):
            raise ValueError("P33 learning projection identity is corrupt")
        return self


__all__ = [
    "AttentionOrderItem",
    "CarResponseFact",
    "CarResponseFingerprint",
    "ContextTransferAssessment",
    "ContextTransferLevel",
    "CrewChiefLearningPrior",
    "DeadEndFact",
    "DriverFingerprintContribution",
    "DriverMetric",
    "DriverPerformanceFingerprint",
    "EngineeringDeadEndRecord",
    "EngineeringExperienceContext",
    "EngineeringExperienceRecord",
    "EngineeringSourceProvenance",
    "EngineeringLearningLedger",
    "EngineeringLearningModel",
    "EngineeringObjectiveValue",
    "EvidenceUnitCounts",
    "InvestigationOutcomeRecord",
    "InvestigationPathFact",
    "LearningEvidenceReference",
    "LearningStrength",
    "MindChangeFact",
    "MindChangeRecord",
    "P19CauseMemory",
    "P19ReasoningMemory",
    "PerformanceResponseFact",
    "PostRunLearningBrief",
    "ProblemFingerprint",
    "RecurringProblemMatch",
    "validate_memory_prose",
]
