"""P34 immutable contracts for earned investigation adaptation.

P34 compares a frozen deterministic Crew investigation decision with a
memory-informed shadow decision.  These contracts intentionally contain no
setup target, P19 cause rank, Keep/Undo/Retest verdict, or mechanism diagnosis.
Current evidence and P19 remain the only truth and setup authorities.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.engineering_learning import validate_memory_prose


PolicyKind = Literal[
    "deterministic_baseline",
    "memory_informed_shadow",
    "limited_attention",
]
ActivationState = Literal["shadow_only", "limited_attention"]
CounterfactualState = Literal[
    "pending",
    "directly_observed",
    "counterfactual_observable",
    "counterfactual_unobservable",
    "invalid",
]
DecisionKind = Literal[
    "inspect_tool",
    "ask_driver",
    "surface_prior",
    "observe_only",
    "no_call",
]
PriorityTier = Literal[
    "identity_integrity",
    "context_qualification",
    "driver_car_confounders",
    "strongest_contradiction",
    "unresolved_p19_mechanisms",
    "component_family_separation",
    "exact_history",
    "measurement_debt",
    "terminal",
]
PhysicalProblemFamily = Literal[
    "braking",
    "entry",
    "center",
    "exit",
    "straight",
    "long_run",
    "mixed",
    "unresolved",
]
ProblemOrientation = Literal["driver", "vehicle", "combined", "unresolved"]
TrackClass = Literal[
    "short_track",
    "intermediate",
    "superspeedway",
    "road_course",
    "unknown",
]
TerminalInvestigationDecision = Literal[
    "driver_focus",
    "driver_question",
    "measurement_mission",
    "controlled_test",
    "observe_only",
    "no_call",
    "blocked",
    "stale",
    "abandoned",
]
NegativeTransferKind = Literal[
    "wrong_context_history",
    "driver_drift_misapplied",
    "dead_end_promoted",
    "useful_current_evidence_delayed",
    "strongest_contradiction_delayed",
    "extra_tool_steps",
    "extra_laps",
    "extra_driver_questions",
    "premature_terminal_decision",
]
P34_PHYSICAL_SCOPE_MISMATCH_DIMENSIONS = frozenset(
    {
        "track",
        "track_configuration",
        "package_type",
        "phase",
        "physical_region",
        "speed_load_band",
        "objective",
    }
)


class P34Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


def _unique(values: tuple[str, ...], label: str) -> None:
    if any(not value for value in values) or len(values) != len(set(values)):
        raise ValueError(f"P34 {label} identities must be non-empty and unique")


def _content_digest(payload: dict[str, Any], *identity_fields: str) -> str:
    return canonical_json_sha256(
        {key: value for key, value in payload.items() if key not in identity_fields}
    )


def investigation_adaptation_source_snapshot_sha256(
    *,
    run_id: str,
    session_id: str,
    workspace_revision: str,
    authority_revision: str,
    current_truth_sha256: str,
    p19_snapshot_sha256: str,
    p20_projection_sha256: str,
    p26_projection_sha256: str,
    p32_projection_sha256: str,
) -> str:
    """Hash the producer-owned Crew snapshot shared by both P34 planners."""

    return canonical_json_sha256(
        {
            "schema": "p34.investigation-adaptation-source-snapshot.v1",
            "run_id": run_id,
            "session_id": session_id,
            "workspace_revision": workspace_revision,
            "authority_revision": authority_revision,
            "current_truth_sha256": current_truth_sha256,
            "p19_snapshot_sha256": p19_snapshot_sha256,
            "p20_projection_sha256": p20_projection_sha256,
            "p26_projection_sha256": p26_projection_sha256,
            "p32_projection_sha256": p32_projection_sha256,
        }
    )


def canonical_context_subgroups(
    *,
    context_transfer_class: str,
    problem_orientation: ProblemOrientation,
    problem_family: PhysicalProblemFamily,
    objective: str,
    track_class: TrackClass,
    driver_drift_state: str,
    build_review_state: str,
) -> tuple[str, ...]:
    """Derive the frozen subgroup registry from typed, mutually exclusive facts."""

    values = [
        (
            f"{context_transfer_class}_context_history"
            if context_transfer_class in {"exact", "compatible"}
            else "weak_history"
        ),
        {
            "driver": "driver_first",
            "vehicle": "vehicle_response",
            "combined": "mixed_problem",
            "unresolved": "mixed_problem",
        }[problem_orientation],
    ]
    if problem_family in {"braking", "entry", "center", "exit", "straight", "long_run"}:
        values.append(problem_family)
    objective_subgroup = {
        "qualifying_peak": "qualifying_objective",
        "race_long_run": "race_long_run_objective",
        "driver_confidence": "driver_confidence_objective",
    }.get(objective)
    if objective_subgroup is not None:
        values.append(objective_subgroup)
    if track_class != "unknown":
        values.append(track_class)
    values.append(
        "stable_driver_fingerprint"
        if driver_drift_state == "stable"
        else "driver_drift_detected"
        if driver_drift_state == "material_drift"
        else "driver_state_unknown"
    )
    values.append(build_review_state)
    return tuple(dict.fromkeys(values))


class SafeReorderGroup(P34Model):
    group_id: str = Field(pattern=r"^[a-z][a-z0-9_.:-]*$")
    priority_tier: PriorityTier
    ordered_action_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def group_is_ordered_and_unique(self) -> Self:
        _unique(self.ordered_action_ids, "safe-reorder action")
        return self


class InvestigationPolicy(P34Model):
    schema_version: Literal["p34.investigation-policy.v1"] = (
        "p34.investigation-policy.v1"
    )
    policy_id: str = Field(pattern=r"^p34pol_[0-9a-f]{24}$")
    policy_version: str = Field(min_length=1)
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    kind: PolicyKind
    allowed_tool_ids: tuple[str, ...] = Field(min_length=1)
    hard_precedence_rules: tuple[PriorityTier, ...] = Field(min_length=1)
    safe_reorder_groups: tuple[SafeReorderGroup, ...] = ()
    maximum_reorder_distance: int = Field(ge=0, le=1)
    learning_source_schema: Literal[
        "none", "p33.engineering-experience.v1"
    ]
    authority_ceiling: Literal["attention_only"] = "attention_only"
    created_at: datetime
    code_version: str = Field(min_length=1)
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    p19_truth_unchanged: Literal[True] = True
    p19_authority_unchanged: Literal[True] = True
    setup_authorized: Literal[False] = False
    online_self_modifying: Literal[False] = False

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.setdefault("schema_version", "p34.investigation-policy.v1")
        body.pop("policy_id", None)
        body.pop("policy_sha256", None)
        draft = cls.model_construct(
            **body,
            policy_id="p34pol_" + "0" * 24,
            policy_sha256="0" * 64,
        ).model_dump(mode="json")
        digest = _content_digest(draft, "policy_id", "policy_sha256")
        return cls.model_validate(
            {
                **draft,
                "policy_id": f"p34pol_{digest[:24]}",
                "policy_sha256": digest,
            }
        )

    @model_validator(mode="after")
    def policy_is_bounded_and_content_addressed(self) -> Self:
        _unique(self.allowed_tool_ids, "allowed tool")
        _unique(tuple(self.hard_precedence_rules), "precedence rule")
        _unique(tuple(item.group_id for item in self.safe_reorder_groups), "reorder group")
        grouped_actions: set[str] = set()
        for group in self.safe_reorder_groups:
            if not set(group.ordered_action_ids).issubset(self.allowed_tool_ids):
                raise ValueError("P34 reorder actions must be allowed policy tools")
            if grouped_actions.intersection(group.ordered_action_ids):
                raise ValueError("P34 an action cannot belong to two reorder groups")
            grouped_actions.update(group.ordered_action_ids)
        if self.kind == "deterministic_baseline":
            if self.learning_source_schema != "none" or self.maximum_reorder_distance:
                raise ValueError("P34 baseline policy cannot consume or reorder memory")
        elif self.learning_source_schema != "p33.engineering-experience.v1":
            raise ValueError("P34 memory policies require the qualified P33 schema")
        dumped = self.model_dump(mode="json")
        expected = _content_digest(dumped, "policy_id", "policy_sha256")
        if self.policy_sha256 != expected or self.policy_id != f"p34pol_{expected[:24]}":
            raise ValueError("P34 investigation policy identity is corrupt")
        return self


class InvestigationDecision(P34Model):
    decision_kind: DecisionKind
    action_id: str = Field(min_length=1)
    priority_tier: PriorityTier
    safe_reorder_group: str | None = Field(default=None, min_length=1)
    baseline_ordinal: int = Field(ge=1)
    selected_ordinal: int = Field(ge=1)
    reason: str = Field(min_length=1)
    mandatory_check_ids: tuple[str, ...] = ()
    source_memory_record_ids: tuple[str, ...] = ()
    setup_authorized: Literal[False] = False
    terminal_policy_authorized: Literal[False] = False

    @property
    def executable_identity(self) -> tuple[object, ...]:
        """Identity of the next executable attention choice, excluding prose."""

        return (
            self.decision_kind,
            self.action_id,
            self.priority_tier,
            self.safe_reorder_group,
            self.selected_ordinal,
        )

    @model_validator(mode="after")
    def decision_is_attention_only(self) -> Self:
        _unique(self.mandatory_check_ids, "mandatory-check")
        _unique(self.source_memory_record_ids, "decision memory")
        validate_memory_prose(self.reason, label="P34 decision reason")
        if any(
            len(record_id) != 29
            or not record_id.startswith("p33x_")
            or any(character not in "0123456789abcdef" for character in record_id[5:])
            for record_id in self.source_memory_record_ids
        ):
            raise ValueError("P34 memory provenance requires exact P33 experience IDs")
        if self.decision_kind != "inspect_tool" and self.safe_reorder_group is not None:
            raise ValueError(
                "P34 v1 freezes learned reordering to tool inspections; driver questions "
                "and prior surfaces require a new protocol version"
            )
        if self.source_memory_record_ids and self.safe_reorder_group is None:
            raise ValueError("P34 memory-backed decisions require a safe reorder group")
        return self


class P19CauseState(P34Model):
    cause_id: str = Field(min_length=1)
    state: Literal["likely", "possible", "ruled_out", "unresolved"]


class NegativeControlConditionEvidence(P34Model):
    """Frozen P33 facts that make one negative-control label auditable.

    The condition is deliberately not inferred from a caller-provided pass
    boolean.  It is a mutually exclusive classification of the exact P33
    projection that was visible before the paired decision was frozen.
    """

    condition: Literal[
        "no_relevant_history",
        "incompatible_history",
        "corrupt_history",
        "generic_component_knowledge_only",
        "same_words_different_physical_scope",
        "material_driver_drift",
        "future_memory_record",
    ]
    p33_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p33_state: Literal["available", "insufficient_history", "blocked"]
    context_transfer_record_ids: tuple[str, ...] = ()
    context_transfer_levels: tuple[
        Literal["exact", "compatible", "weak", "blocked"], ...
    ] = ()
    useful_prior_experience_ids: tuple[str, ...] = ()
    component_history_experience_ids: tuple[str, ...] = ()
    physical_scope_mismatch_dimensions: tuple[str, ...] = ()
    recurrence_class: Literal[
        "new_problem",
        "possible_recurrence",
        "strong_recurrence",
        "exact_context_recurrence",
    ]
    corruption_blocker_sha256s: tuple[str, ...] = ()
    future_memory_record_ids: tuple[str, ...] = ()
    future_memory_record_completed_ats: tuple[datetime, ...] = ()
    driver_drift_state: Literal["stable", "material_drift", "unknown"]

    @model_validator(mode="after")
    def condition_is_proven_by_typed_pre_outcome_facts(self) -> Self:
        for values, label in (
            (self.context_transfer_record_ids, "negative-control transfer record"),
            (self.useful_prior_experience_ids, "negative-control useful prior"),
            (
                self.component_history_experience_ids,
                "negative-control component history",
            ),
            (
                self.physical_scope_mismatch_dimensions,
                "negative-control physical mismatch",
            ),
            (self.corruption_blocker_sha256s, "negative-control corruption blocker"),
            (self.future_memory_record_ids, "negative-control future memory"),
        ):
            _unique(values, label)
        if len(self.context_transfer_record_ids) != len(
            self.context_transfer_levels
        ):
            raise ValueError(
                "P34 negative-control transfers require aligned IDs and levels"
            )
        if len(self.future_memory_record_ids) != len(
            self.future_memory_record_completed_ats
        ) or any(
            item.tzinfo is None for item in self.future_memory_record_completed_ats
        ):
            raise ValueError(
                "P34 future-memory proof requires aligned timezone-aware completion times"
            )
        for record_id in (
            *self.context_transfer_record_ids,
            *self.useful_prior_experience_ids,
            *self.component_history_experience_ids,
            *self.future_memory_record_ids,
        ):
            if (
                len(record_id) != 29
                or not record_id.startswith("p33x_")
                or any(
                    character not in "0123456789abcdef"
                    for character in record_id[5:]
                )
            ):
                raise ValueError(
                    "P34 negative-control evidence requires exact P33 experience IDs"
                )
        if any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in self.corruption_blocker_sha256s
        ):
            raise ValueError(
                "P34 corruption evidence requires content-addressed blocker facts"
            )
        condition_is_exact = {
            "no_relevant_history": (
                self.p33_state in {"available", "insufficient_history"}
                and not self.context_transfer_record_ids
                and not self.useful_prior_experience_ids
                and not self.component_history_experience_ids
                and self.recurrence_class == "new_problem"
                and not self.future_memory_record_ids
            ),
            "incompatible_history": (
                self.p33_state != "blocked"
                and "blocked" in self.context_transfer_levels
                and not self.corruption_blocker_sha256s
                and not self.future_memory_record_ids
                and self.driver_drift_state == "stable"
            ),
            "corrupt_history": (
                self.p33_state == "blocked"
                and bool(self.corruption_blocker_sha256s)
                and not self.future_memory_record_ids
            ),
            "generic_component_knowledge_only": (
                self.p33_state == "available"
                and "weak" in self.context_transfer_levels
                and bool(self.component_history_experience_ids)
                and not self.useful_prior_experience_ids
                and not self.physical_scope_mismatch_dimensions
                and not self.future_memory_record_ids
            ),
            "same_words_different_physical_scope": (
                self.p33_state == "available"
                and "weak" in self.context_transfer_levels
                and bool(self.physical_scope_mismatch_dimensions)
                and self.recurrence_class != "new_problem"
                and not self.future_memory_record_ids
            ),
            "material_driver_drift": (
                self.driver_drift_state == "material_drift"
                and not self.future_memory_record_ids
            ),
            "future_memory_record": bool(self.future_memory_record_ids),
        }[self.condition]
        if not condition_is_exact:
            raise ValueError(
                "P34 negative-control label is not proven by its frozen typed facts"
            )
        return self


class PairedInvestigationDecision(P34Model):
    schema_version: Literal["p34.paired-investigation-decision.v1"] = (
        "p34.paired-investigation-decision.v1"
    )
    pair_id: str = Field(pattern=r"^p34pair_[0-9a-f]{24}$")
    pair_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    investigation_id: str = Field(min_length=1)
    investigation_opened_at: datetime
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    step_number: int = Field(ge=0)
    baseline_policy_id: str = Field(pattern=r"^p34pol_[0-9a-f]{24}$")
    baseline_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    memory_policy_id: str = Field(pattern=r"^p34pol_[0-9a-f]{24}$")
    memory_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    activation_protocol_id: str = Field(pattern=r"^p34proto_[0-9a-f]{24}$")
    activation_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    activation_state: ActivationState
    activation_decision_id: str | None = Field(
        default=None, pattern=r"^p34act_[0-9a-f]{24}$"
    )
    activation_decision_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    production_policy_kind: Literal[
        "deterministic_baseline", "limited_attention"
    ]
    baseline_decision: InvestigationDecision
    memory_decision: InvestigationDecision
    production_decision: InvestigationDecision
    available_tool_ids: tuple[str, ...]
    eligible_tool_ids: tuple[str, ...]
    completed_tool_ids: tuple[str, ...] = ()
    available_artifact_ids: tuple[str, ...] = ()
    qualified_available_artifact_ids: tuple[str, ...] = ()
    qualified_available_artifact_evidence_states: tuple[
        Literal["measured", "calculated", "controlled_test_effect"], ...
    ] = ()
    qualified_available_artifact_provenance_sha256s: tuple[str, ...] = ()
    current_evidence_pinned_tool_ids: tuple[str, ...] = ()
    current_truth_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p19_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p20_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p26_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p32_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_p19_cause_ids: tuple[str, ...] = ()
    current_p19_cause_states: tuple[P19CauseState, ...] = ()
    current_contradiction_ids: tuple[str, ...] = ()
    strongest_contradiction_id: str | None = Field(default=None, min_length=1)
    current_objective: str = Field(min_length=1)
    p33_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p33_history_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    p33_ledger_head_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    p33_context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p33_problem_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    track: str = Field(min_length=1)
    track_configuration: str = Field(min_length=1)
    package_type: str = Field(min_length=1)
    iracing_build: str = Field(min_length=1)
    problem_family: PhysicalProblemFamily
    problem_orientation: ProblemOrientation
    track_class: TrackClass
    phase: str = Field(min_length=1)
    context_subgroup_keys: tuple[str, ...] = Field(min_length=1)
    build_review_state: Literal[
        "same_build", "reviewed_compatible_build", "future_unreviewed_build"
    ]
    driver_drift_state: Literal["stable", "material_drift", "unknown"]
    negative_control_condition: Literal[
        "no_relevant_history",
        "incompatible_history",
        "corrupt_history",
        "generic_component_knowledge_only",
        "same_words_different_physical_scope",
        "material_driver_drift",
        "future_memory_record",
    ] | None = None
    negative_control_evidence: NegativeControlConditionEvidence | None = None
    future_memory_record_ids: tuple[str, ...] = ()
    memory_records_consulted: tuple[str, ...] = ()
    context_transfer_class: Literal["none", "exact", "compatible", "weak", "blocked"]
    decision_frozen_at: datetime
    outcome_exposed: Literal[False] = False
    p19_rank_unchanged: Literal[True] = True
    p19_authority_unchanged: Literal[True] = True
    p19_terminal_action_unchanged: Literal[True] = True
    setup_authorized: Literal[False] = False

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.setdefault("schema_version", "p34.paired-investigation-decision.v1")
        body.pop("pair_id", None)
        body.pop("pair_sha256", None)
        draft = cls.model_construct(
            **body,
            pair_id="p34pair_" + "0" * 24,
            pair_sha256="0" * 64,
        ).model_dump(mode="json")
        digest = _content_digest(draft, "pair_id", "pair_sha256")
        return cls.model_validate(
            {**draft, "pair_id": f"p34pair_{digest[:24]}", "pair_sha256": digest}
        )

    @model_validator(mode="after")
    def pair_is_frozen_before_outcome_and_preserves_authority(self) -> Self:
        for values, label in (
            (self.available_tool_ids, "available tool"),
            (self.eligible_tool_ids, "eligible tool"),
            (self.completed_tool_ids, "completed tool"),
            (self.available_artifact_ids, "available artifact"),
            (
                self.qualified_available_artifact_ids,
                "qualified available artifact",
            ),
            (self.current_evidence_pinned_tool_ids, "current-evidence pinned tool"),
            (self.current_p19_cause_ids, "current P19 cause"),
            (self.current_contradiction_ids, "current contradiction"),
            (self.memory_records_consulted, "consulted memory"),
            (self.future_memory_record_ids, "future memory"),
            (self.context_subgroup_keys, "context subgroup"),
        ):
            _unique(values, label)
        if not set(self.eligible_tool_ids).issubset(self.available_tool_ids):
            raise ValueError("P34 eligible tools must come from the frozen tool catalog")
        if not set(self.completed_tool_ids).issubset(self.available_tool_ids):
            raise ValueError("P34 completed tools must come from the frozen tool catalog")
        if set(self.eligible_tool_ids).intersection(self.completed_tool_ids):
            raise ValueError("P34 completed tools cannot remain eligible")
        if not set(self.current_evidence_pinned_tool_ids).issubset(
            self.eligible_tool_ids
        ):
            raise ValueError("P34 current-evidence pins must be exact eligible tools")
        expected_pin = (
            (self.baseline_decision.action_id,)
            if self.current_evidence_pinned_tool_ids
            and self.baseline_decision.decision_kind == "inspect_tool"
            else ()
        )
        if self.current_evidence_pinned_tool_ids != expected_pin:
            raise ValueError("P34 may pin only the exact deterministic baseline tool")
        if self.current_evidence_pinned_tool_ids and not (
            self.qualified_available_artifact_ids
        ):
            raise ValueError("P34 current-evidence pins require qualified artifacts")
        qualified_count = len(self.qualified_available_artifact_ids)
        if (
            len(self.qualified_available_artifact_evidence_states)
            != qualified_count
            or len(self.qualified_available_artifact_provenance_sha256s)
            != qualified_count
        ):
            raise ValueError(
                "P34 qualified available artifacts require aligned state and provenance"
            )
        if not set(self.qualified_available_artifact_ids).issubset(
            self.available_artifact_ids
        ):
            raise ValueError(
                "P34 qualified available artifacts must exist in the frozen evidence index"
            )
        if any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in self.qualified_available_artifact_provenance_sha256s
        ):
            raise ValueError(
                "P34 qualified available artifacts require exact provenance digests"
            )
        if tuple(item.cause_id for item in self.current_p19_cause_states) != (
            self.current_p19_cause_ids
        ):
            raise ValueError("P34 P19 cause states must align with frozen cause rank")
        if self.activation_state == "shadow_only":
            if (
                self.production_policy_kind != "deterministic_baseline"
                or self.production_decision != self.baseline_decision
                or self.activation_decision_id is not None
                or self.activation_decision_sha256 is not None
            ):
                raise ValueError("P34 shadow policy cannot control production")
        elif (
            self.production_policy_kind != "limited_attention"
            or self.production_decision != self.memory_decision
            or self.activation_decision_id is None
            or self.activation_decision_sha256 is None
        ):
            raise ValueError(
                "P34 limited attention requires its exact earned activation artifact"
            )
        if self.investigation_opened_at > self.decision_frozen_at:
            raise ValueError("P34 pair cannot predate its immutable investigation opening")
        if self.baseline_decision.source_memory_record_ids:
            raise ValueError("P34 baseline decision cannot consume P33 memory")
        if (
            self.baseline_decision.selected_ordinal
            != self.baseline_decision.baseline_ordinal
        ):
            raise ValueError("P34 baseline decision must preserve its canonical ordinal")
        for decision in (self.baseline_decision, self.memory_decision):
            if (
                decision.decision_kind == "inspect_tool"
                and decision.action_id not in self.eligible_tool_ids
            ):
                raise ValueError("P34 selected tools must be eligible at freeze time")
        if self.memory_records_consulted != self.memory_decision.source_memory_record_ids:
            raise ValueError("P34 pair must bind the exact memory used by its decision")
        if any(
            len(record_id) != 29
            or not record_id.startswith("p33x_")
            or any(character not in "0123456789abcdef" for character in record_id[5:])
            for record_id in self.future_memory_record_ids
        ):
            raise ValueError("P34 future-memory controls require exact P33 experience IDs")
        if set(self.future_memory_record_ids).intersection(
            self.memory_records_consulted
        ):
            raise ValueError("P34 future memory cannot be consulted before its freeze")
        if (
            self.memory_records_consulted or self.future_memory_record_ids
        ) and self.p33_ledger_head_sha256 is None:
            raise ValueError(
                "P34 referenced P33 records require the exact frozen ledger head"
            )
        decisions_differ = (
            self.memory_decision.executable_identity
            != self.baseline_decision.executable_identity
        )
        baseline_is_pinned = (
            self.baseline_decision.decision_kind == "inspect_tool"
            and self.baseline_decision.action_id
            in self.current_evidence_pinned_tool_ids
        )
        if baseline_is_pinned and (
            decisions_differ
            or self.memory_records_consulted
            or self.context_transfer_class != "blocked"
        ):
            raise ValueError(
                "P34 exact current evidence pins baseline and blocks learned attention"
            )
        if self.baseline_decision.decision_kind == "inspect_tool":
            eligible_shape_is_exact = bool(
                self.memory_decision.decision_kind == "inspect_tool"
                and self.eligible_tool_ids
                and self.eligible_tool_ids[0]
                == self.baseline_decision.action_id
                and len(self.eligible_tool_ids) <= 2
                and (
                    not decisions_differ
                    or len(self.eligible_tool_ids) == 2
                    and self.eligible_tool_ids[1]
                    == self.memory_decision.action_id
                )
            )
        else:
            eligible_shape_is_exact = not self.eligible_tool_ids
        if not eligible_shape_is_exact:
            raise ValueError(
                "P34 eligible tools must equal baseline plus the immediate live candidate"
            )
        if self.context_transfer_class in {"none", "weak", "blocked"} and (
            decisions_differ or self.memory_records_consulted
        ):
            raise ValueError("P34 unsafe or absent transfer must fall back exactly to baseline")
        if self.build_review_state == "future_unreviewed_build" and (
            self.context_transfer_class != "blocked" or decisions_differ
        ):
            raise ValueError("P34 future/unreviewed build history must remain blocked")
        if self.driver_drift_state != "stable" and decisions_differ:
            raise ValueError("P34 driver drift or uncertainty blocks learned reordering")
        if decisions_differ:
            if not self.memory_records_consulted:
                raise ValueError(
                    "P34 learned reordering requires exact qualified P33 provenance"
                )
            if (
                self.memory_decision.safe_reorder_group is None
                or self.memory_decision.safe_reorder_group
                != self.baseline_decision.safe_reorder_group
                or self.memory_decision.priority_tier != self.baseline_decision.priority_tier
            ):
                raise ValueError("P34 memory may reorder only inside one safe tier")
            if abs(
                self.memory_decision.selected_ordinal
                - self.memory_decision.baseline_ordinal
            ) > 1:
                raise ValueError("P34 memory may move at most one safe position")
        elif abs(
            self.memory_decision.selected_ordinal
            - self.memory_decision.baseline_ordinal
        ) > 1:
            raise ValueError("P34 memory metadata cannot bypass the reorder ceiling")
        if self.baseline_decision.mandatory_check_ids != self.memory_decision.mandatory_check_ids:
            raise ValueError("P34 memory cannot change mandatory checks")
        expected_strongest = (
            self.current_contradiction_ids[0]
            if self.current_contradiction_ids
            else None
        )
        if self.strongest_contradiction_id != expected_strongest:
            raise ValueError(
                "P34 strongest contradiction must equal canonical current rank one"
            )
        expected_subgroups = canonical_context_subgroups(
            context_transfer_class=self.context_transfer_class,
            problem_orientation=self.problem_orientation,
            problem_family=self.problem_family,
            objective=self.current_objective,
            track_class=self.track_class,
            driver_drift_state=self.driver_drift_state,
            build_review_state=self.build_review_state,
        )
        if self.context_subgroup_keys != expected_subgroups:
            raise ValueError("P34 subgroup keys must be derived from exact typed context")
        condition = self.negative_control_condition
        if condition is not None:
            if (
                self.negative_control_evidence is None
                or self.negative_control_evidence.condition != condition
                or self.negative_control_evidence.p33_projection_sha256
                != self.p33_projection_sha256
                or self.negative_control_evidence.future_memory_record_ids
                != self.future_memory_record_ids
                or self.negative_control_evidence.driver_drift_state
                != self.driver_drift_state
                or any(
                    completed_at < self.decision_frozen_at
                    for completed_at in self.negative_control_evidence.future_memory_record_completed_ats
                )
            ):
                raise ValueError(
                    "P34 negative-control condition requires its exact frozen P33 proof"
                )
            if decisions_differ or self.memory_records_consulted:
                raise ValueError("P34 negative controls require exact baseline fallback")
            condition_is_typed = {
                "no_relevant_history": self.context_transfer_class == "none",
                "incompatible_history": (
                    self.context_transfer_class == "blocked"
                    and self.driver_drift_state == "stable"
                    and self.build_review_state != "future_unreviewed_build"
                ),
                "corrupt_history": self.context_transfer_class == "blocked",
                "generic_component_knowledge_only": (
                    self.context_transfer_class == "weak"
                    and self.problem_orientation == "vehicle"
                ),
                "same_words_different_physical_scope": (
                    self.context_transfer_class == "weak"
                    and self.problem_orientation in {"combined", "unresolved"}
                ),
                "material_driver_drift": self.driver_drift_state == "material_drift",
                "future_memory_record": bool(self.future_memory_record_ids),
            }[condition]
            if not condition_is_typed:
                raise ValueError("P34 negative-control condition contradicts typed context")
        elif self.future_memory_record_ids or self.negative_control_evidence is not None:
            raise ValueError(
                "P34 negative-control evidence requires its exact condition"
            )
        dumped = self.model_dump(mode="json")
        expected = _content_digest(dumped, "pair_id", "pair_sha256")
        if self.pair_sha256 != expected or self.pair_id != f"p34pair_{expected[:24]}":
            raise ValueError("P34 paired-decision identity is corrupt")
        return self


class InvestigationOutcomeCertificate(P34Model):
    schema_version: Literal["p34.investigation-outcome.v1"] = (
        "p34.investigation-outcome.v1"
    )
    certificate_id: str = Field(pattern=r"^p34out_[0-9a-f]{24}$")
    certificate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    activation_protocol_id: str = Field(pattern=r"^p34proto_[0-9a-f]{24}$")
    activation_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_frozen_at: datetime
    pair_id: str = Field(pattern=r"^p34pair_[0-9a-f]{24}$")
    pair_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    investigation_id: str = Field(min_length=1)
    investigation_opened_at: datetime
    starting_workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    ending_workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_p19_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    terminal_crew_decision: TerminalInvestigationDecision
    tool_request_event_ids: tuple[str, ...] = ()
    tool_result_event_ids: tuple[str, ...] = ()
    tools_actually_requested: tuple[str, ...] = ()
    tool_results_received: tuple[str, ...] = ()
    qualified_artifact_ids: tuple[str, ...] = ()
    qualified_artifact_evidence_states: tuple[
        Literal[
            "measured",
            "calculated",
            "estimated_proxy",
            "observed_correlation",
            "controlled_test_effect",
        ],
        ...,
    ] = ()
    driver_question_ids: tuple[str, ...] = ()
    driver_answer_event_ids: tuple[str, ...] = ()
    consumption_metrics_state: Literal["observed", "unavailable"]
    lap_ids_consumed: tuple[str, ...] | None = None
    measurement_mission_ids: tuple[str, ...] | None = None
    consumption_metric_blockers: tuple[str, ...] = ()
    elapsed_wall_seconds: FiniteFloat = Field(ge=0)
    investigation_steps: int = Field(ge=0)
    useful_discriminator_id: str | None = Field(default=None, min_length=1)
    dead_end_tool_ids: tuple[str, ...] = ()
    repeated_no_finding_tool_ids: tuple[str, ...] = ()
    causes_separated: tuple[str, ...] = ()
    causes_left_unresolved: tuple[str, ...] = ()
    final_p19_cause_states: tuple[P19CauseState, ...] = ()
    strongest_contradiction_id: str | None = Field(default=None, min_length=1)
    strongest_contradiction_handled: bool
    completed_mandatory_check_ids: tuple[str, ...] = ()
    created_workflow_ids: tuple[str, ...] = Field(default=(), max_length=1)
    workflow_created: bool
    workflow_scored: bool
    p19_outcome: Literal["keep", "undo", "retest", "no_call", "blocked"] | None = None
    outcome_validity: Literal["qualified", "blocked", "invalid"]
    prospective: bool
    synthetic: bool = False
    blockers: tuple[str, ...] = ()
    certified_at: datetime
    setup_authorized: Literal[False] = False

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.setdefault("schema_version", "p34.investigation-outcome.v1")
        body.pop("certificate_id", None)
        body.pop("certificate_sha256", None)
        draft = cls.model_construct(
            **body,
            certificate_id="p34out_" + "0" * 24,
            certificate_sha256="0" * 64,
        ).model_dump(mode="json")
        digest = _content_digest(draft, "certificate_id", "certificate_sha256")
        return cls.model_validate(
            {
                **draft,
                "certificate_id": f"p34out_{digest[:24]}",
                "certificate_sha256": digest,
            }
        )

    @model_validator(mode="after")
    def certificate_is_event_bound_not_setup_authority(self) -> Self:
        for values, label in (
            (self.tool_request_event_ids, "tool request event"),
            (self.tool_result_event_ids, "tool result event"),
            (self.qualified_artifact_ids, "qualified artifact"),
            (self.driver_question_ids, "driver question"),
            (self.driver_answer_event_ids, "driver answer event"),
            (self.dead_end_tool_ids, "dead-end tool"),
            (self.repeated_no_finding_tool_ids, "repeated no-finding tool"),
            (self.causes_separated, "separated cause"),
            (self.causes_left_unresolved, "unresolved cause"),
            (self.completed_mandatory_check_ids, "completed mandatory check"),
            (self.created_workflow_ids, "created workflow"),
        ):
            _unique(values, label)
        if self.lap_ids_consumed is not None:
            _unique(self.lap_ids_consumed, "consumed lap")
        if self.measurement_mission_ids is not None:
            _unique(self.measurement_mission_ids, "measurement mission")
        _unique(self.consumption_metric_blockers, "consumption metric blocker")
        if len(self.tool_request_event_ids) != len(self.tools_actually_requested):
            raise ValueError("P34 requested tools require one ordered request event each")
        if self.investigation_opened_at > self.decision_frozen_at:
            raise ValueError("P34 outcome cannot predate its investigation opening")
        if len(self.tool_result_event_ids) != len(self.tool_results_received):
            raise ValueError("P34 tool results require one ordered result event each")
        if len(self.qualified_artifact_ids) != len(
            self.qualified_artifact_evidence_states
        ):
            raise ValueError("P34 qualified artifacts require exact evidence states")
        if self.consumption_metrics_state == "observed":
            if (
                self.lap_ids_consumed is None
                or self.measurement_mission_ids is None
                or self.consumption_metric_blockers
            ):
                raise ValueError(
                    "P34 observed consumption requires complete lap/mission lineage"
                )
        elif (
            self.lap_ids_consumed is not None
            or self.measurement_mission_ids is not None
            or not self.consumption_metric_blockers
        ):
            raise ValueError(
                "P34 unavailable consumption must remain null with blockers"
            )
        _unique(
            tuple(item.cause_id for item in self.final_p19_cause_states),
            "final P19 cause state",
        )
        if not set(self.tool_results_received).issubset(self.tools_actually_requested):
            raise ValueError("P34 tool results must correspond to requested tools")
        if not set(self.dead_end_tool_ids).issubset(self.tool_results_received):
            raise ValueError("P34 dead ends require a received tool result")
        if not set(self.repeated_no_finding_tool_ids).issubset(
            self.tool_results_received
        ):
            raise ValueError("P34 repeated no-findings require received tool results")
        if self.useful_discriminator_id is not None and (
            self.useful_discriminator_id not in self.tool_results_received
        ):
            raise ValueError("P34 useful discriminator requires a received result")
        if self.workflow_scored and not self.workflow_created:
            raise ValueError("P34 cannot score a workflow that was not created")
        if self.workflow_created != bool(self.created_workflow_ids):
            raise ValueError("P34 workflow-created state requires exact workflow IDs")
        if self.outcome_validity == "qualified" and self.blockers:
            raise ValueError("P34 qualified outcomes cannot retain blockers")
        if self.outcome_validity != "qualified" and not self.blockers:
            raise ValueError("P34 withheld outcomes require explicit blockers")
        dumped = self.model_dump(mode="json")
        expected = _content_digest(dumped, "certificate_id", "certificate_sha256")
        if (
            self.certificate_sha256 != expected
            or self.certificate_id != f"p34out_{expected[:24]}"
        ):
            raise ValueError("P34 outcome certificate identity is corrupt")
        return self


class InvestigationOutcomeFollowup(P34Model):
    """Later immutable P19 observation; never mutates its earlier certificate."""

    schema_version: Literal["p34.investigation-outcome-followup.v1"] = (
        "p34.investigation-outcome-followup.v1"
    )
    followup_id: str = Field(pattern=r"^p34follow_[0-9a-f]{24}$")
    followup_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    activation_protocol_id: str = Field(pattern=r"^p34proto_[0-9a-f]{24}$")
    activation_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    investigation_id: str = Field(min_length=1)
    certificate_id: str = Field(pattern=r"^p34out_[0-9a-f]{24}$")
    certificate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_p19_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_p19_outcome: Literal["keep", "undo", "retest", "no_call", "blocked"]
    source_workflow_id: str | None = Field(default=None, min_length=1)
    source_workflow_revision_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    source_event_ids: tuple[str, ...] = ()
    source_artifact_ids: tuple[str, ...] = ()
    observed_at: datetime
    setup_authorized: Literal[False] = False

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.setdefault("schema_version", "p34.investigation-outcome-followup.v1")
        body.pop("followup_id", None)
        body.pop("followup_sha256", None)
        draft = cls.model_construct(
            **body,
            followup_id="p34follow_" + "0" * 24,
            followup_sha256="0" * 64,
        ).model_dump(mode="json")
        digest = _content_digest(draft, "followup_id", "followup_sha256")
        return cls.model_validate(
            {
                **draft,
                "followup_id": f"p34follow_{digest[:24]}",
                "followup_sha256": digest,
            }
        )

    @model_validator(mode="after")
    def followup_is_content_addressed(self) -> Self:
        _unique(self.source_event_ids, "follow-up event")
        _unique(self.source_artifact_ids, "follow-up artifact")
        if (self.source_workflow_id is None) != (
            self.source_workflow_revision_sha256 is None
        ):
            raise ValueError("P34 follow-up workflow identity requires its revision")
        if self.observed_p19_outcome in {"keep", "undo", "retest"} and (
            self.source_workflow_id is None
        ):
            raise ValueError("P34 controlled P19 follow-up requires its workflow")
        dumped = self.model_dump(mode="json")
        expected = _content_digest(dumped, "followup_id", "followup_sha256")
        if (
            self.followup_sha256 != expected
            or self.followup_id != f"p34follow_{expected[:24]}"
        ):
            raise ValueError("P34 outcome follow-up identity is corrupt")
        return self


class P19CauseChange(P34Model):
    cause_id: str = Field(min_length=1)
    before_state: str = Field(min_length=1)
    after_state: str = Field(min_length=1)

    @model_validator(mode="after")
    def state_really_changed(self) -> Self:
        if self.before_state == self.after_state:
            raise ValueError("P34 cause change requires a real state transition")
        return self


class DiscriminatorOutcome(P34Model):
    schema_version: Literal["p34.discriminator-outcome.v1"] = (
        "p34.discriminator-outcome.v1"
    )
    outcome_id: str = Field(pattern=r"^p34disc_[0-9a-f]{24}$")
    outcome_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    activation_protocol_id: str = Field(pattern=r"^p34proto_[0-9a-f]{24}$")
    activation_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    investigation_id: str = Field(min_length=1)
    prediction_pair_id: str = Field(pattern=r"^p34pair_[0-9a-f]{24}$")
    prediction_pair_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_pair_id: str = Field(pattern=r"^p34pair_[0-9a-f]{24}$")
    source_pair_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_authority_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_id: str = Field(min_length=1)
    request_event_id: str = Field(min_length=1)
    request_sequence: int = Field(ge=1)
    request_recorded_at: datetime
    result_event_id: str = Field(min_length=1)
    result_sequence: int = Field(ge=1)
    result_recorded_at: datetime
    transition_sequence: int = Field(ge=1)
    lineage_event_ids: tuple[str, ...] = Field(min_length=1)
    artifact_ids: tuple[str, ...]
    qualified_evidence_states: tuple[
        Literal[
            "measured",
            "calculated",
            "estimated_proxy",
            "observed_correlation",
            "controlled_test_effect",
        ],
        ...,
    ]
    before_p19_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    after_p19_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relevant_ambiguity_ids: tuple[str, ...]
    cause_changes: tuple[P19CauseChange, ...] = ()
    resolved_blocker_ids: tuple[str, ...] = ()
    blocker_resolved: bool
    artifact_available_before_transition: bool
    exact_workspace_match: bool
    causally_relevant_transition: bool
    credit_state: Literal["earned", "rejected", "unobservable"]
    credit_reason: str = Field(min_length=1)
    evaluated_at: datetime

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.setdefault("schema_version", "p34.discriminator-outcome.v1")
        body.pop("outcome_id", None)
        body.pop("outcome_sha256", None)
        draft = cls.model_construct(
            **body,
            outcome_id="p34disc_" + "0" * 24,
            outcome_sha256="0" * 64,
        ).model_dump(mode="json")
        digest = _content_digest(draft, "outcome_id", "outcome_sha256")
        return cls.model_validate(
            {
                **draft,
                "outcome_id": f"p34disc_{digest[:24]}",
                "outcome_sha256": digest,
            }
        )

    @model_validator(mode="after")
    def credit_requires_ordered_qualified_evidence(self) -> Self:
        _unique(self.lineage_event_ids, "discriminator lineage event")
        _unique(self.artifact_ids, "discriminator artifact")
        _unique(self.relevant_ambiguity_ids, "relevant ambiguity")
        _unique(self.resolved_blocker_ids, "resolved blocker")
        _unique(tuple(item.cause_id for item in self.cause_changes), "changed cause")
        if len(self.artifact_ids) != len(self.qualified_evidence_states):
            raise ValueError("P34 discriminator artifacts require paired evidence states")
        credit_evidence_states = {
            "measured",
            "calculated",
            "controlled_test_effect",
        }
        evidence_is_credit_qualified = bool(self.qualified_evidence_states) and all(
            state in credit_evidence_states for state in self.qualified_evidence_states
        )
        validate_memory_prose(
            self.credit_reason,
            label="P34 discriminator credit reason",
        )
        if (
            self.request_event_id not in self.lineage_event_ids
            or self.result_event_id not in self.lineage_event_ids
        ):
            raise ValueError(
                "P34 discriminator lineage must contain its request and result events"
            )
        if not (
            self.request_recorded_at <= self.result_recorded_at <= self.evaluated_at
        ):
            raise ValueError("P34 discriminator event timestamps are not ordered")
        relevant_change = bool(
            set(item.cause_id for item in self.cause_changes)
            .intersection(self.relevant_ambiguity_ids)
        ) or bool(self.resolved_blocker_ids)
        earned = (
            bool(self.artifact_ids)
            and evidence_is_credit_qualified
            and self.request_sequence < self.result_sequence <= self.transition_sequence
            and self.before_p19_snapshot_sha256 != self.after_p19_snapshot_sha256
            and self.artifact_available_before_transition
            and self.exact_workspace_match
            and self.causally_relevant_transition
            and relevant_change
        )
        if self.blocker_resolved != bool(self.resolved_blocker_ids):
            raise ValueError("P34 resolved blocker state requires exact blocker identities")
        if self.credit_state == "earned" and not earned:
            raise ValueError("P34 discriminator credit lacks ordered qualified evidence")
        if self.credit_state != "earned" and earned:
            raise ValueError("P34 qualified discriminator transition must earn credit")
        dumped = self.model_dump(mode="json")
        expected = _content_digest(dumped, "outcome_id", "outcome_sha256")
        if self.outcome_sha256 != expected or self.outcome_id != f"p34disc_{expected[:24]}":
            raise ValueError("P34 discriminator outcome identity is corrupt")
        return self


class InvestigationNegativeTransfer(P34Model):
    schema_version: Literal["p34.negative-transfer.v1"] = (
        "p34.negative-transfer.v1"
    )
    transfer_id: str = Field(pattern=r"^p34neg_[0-9a-f]{24}$")
    transfer_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    activation_protocol_id: str = Field(pattern=r"^p34proto_[0-9a-f]{24}$")
    activation_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    investigation_id: str = Field(min_length=1)
    pair_id: str = Field(pattern=r"^p34pair_[0-9a-f]{24}$")
    comparison_id: str = Field(pattern=r"^p34cmp_[0-9a-f]{24}$")
    comparison_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    kinds: tuple[NegativeTransferKind, ...] = Field(min_length=1)
    attributable_to_memory_attention: Literal[True] = True
    baseline_tool_steps: int = Field(ge=0)
    memory_tool_steps: int | None = Field(default=None, ge=0)
    baseline_useful_discriminator_step: int | None = Field(default=None, ge=1)
    memory_useful_discriminator_step: int | None = Field(default=None, ge=1)
    consumption_metrics_observed: bool
    baseline_laps: int | None = Field(default=None, ge=0)
    memory_laps: int | None = Field(default=None, ge=0)
    baseline_questions: int = Field(ge=0)
    memory_questions: int | None = Field(default=None, ge=0)
    material_efficiency_degradation_pct: FiniteFloat = Field(ge=0)
    evidence_artifact_ids: tuple[str, ...] = Field(min_length=1)
    detected_at: datetime
    setup_authorized: Literal[False] = False

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.setdefault("schema_version", "p34.negative-transfer.v1")
        body.pop("transfer_id", None)
        body.pop("transfer_sha256", None)
        draft = cls.model_construct(
            **body,
            transfer_id="p34neg_" + "0" * 24,
            transfer_sha256="0" * 64,
        ).model_dump(mode="json")
        digest = _content_digest(draft, "transfer_id", "transfer_sha256")
        return cls.model_validate(
            {
                **draft,
                "transfer_id": f"p34neg_{digest[:24]}",
                "transfer_sha256": digest,
            }
        )

    @model_validator(mode="after")
    def transfer_is_attributable_and_content_addressed(self) -> Self:
        _unique(tuple(self.kinds), "negative-transfer kind")
        _unique(self.evidence_artifact_ids, "negative-transfer evidence")
        if self.consumption_metrics_observed != (
            self.baseline_laps is not None and self.memory_laps is not None
        ):
            raise ValueError("P34 negative-transfer lap consumption is unresolved")
        if (self.baseline_useful_discriminator_step is None) != (
            self.memory_useful_discriminator_step is None
        ):
            raise ValueError(
                "P34 negative transfer requires both discriminator positions or neither"
            )
        discriminator_delay = bool(
            self.baseline_useful_discriminator_step is not None
            and self.memory_useful_discriminator_step is not None
            and self.memory_useful_discriminator_step
            > self.baseline_useful_discriminator_step
        )
        if "dead_end_promoted" in self.kinds and not discriminator_delay:
            raise ValueError(
                "P34 promoted dead end requires an observed discriminator delay"
            )
        if not any(
            (
                self.memory_tool_steps is not None
                and self.memory_tool_steps > self.baseline_tool_steps,
                self.consumption_metrics_observed
                and int(self.memory_laps) > int(self.baseline_laps),
                self.memory_questions is not None
                and self.memory_questions > self.baseline_questions,
                self.material_efficiency_degradation_pct > 0,
                discriminator_delay,
                "premature_terminal_decision" in self.kinds,
                "wrong_context_history" in self.kinds,
                "driver_drift_misapplied" in self.kinds,
                "strongest_contradiction_delayed" in self.kinds,
                "useful_current_evidence_delayed" in self.kinds,
            )
        ):
            raise ValueError("P34 negative transfer requires material attributable harm")
        dumped = self.model_dump(mode="json")
        expected = _content_digest(dumped, "transfer_id", "transfer_sha256")
        if self.transfer_sha256 != expected or self.transfer_id != f"p34neg_{expected[:24]}":
            raise ValueError("P34 negative-transfer identity is corrupt")
        return self


class P34SafetyResults(P34Model):
    authority_violations: int = Field(ge=0)
    p19_action_mismatches: int = Field(ge=0)
    stale_workspace_actions: int = Field(ge=0)
    mandatory_check_violations: int = Field(ge=0)
    hidden_contradiction_failures: int = Field(ge=0)
    incompatible_history_transfers: int = Field(ge=0)
    driver_memory_mechanical_diagnoses: int = Field(ge=0)
    memory_only_terminal_actions: int = Field(ge=0)

    @property
    def passed(self) -> bool:
        return not any(self.model_dump().values())


class P34EfficiencyResults(P34Model):
    median_tool_step_difference: FiniteFloat
    relative_tool_step_reduction: FiniteFloat
    median_elapsed_seconds_difference: FiniteFloat
    median_lap_difference: FiniteFloat | None
    median_question_difference: FiniteFloat
    median_measurement_mission_difference: FiniteFloat | None
    lap_consumption_observation_count: int = Field(ge=0)
    measurement_mission_observation_count: int = Field(ge=0)
    dead_end_reduction_rate: FiniteFloat
    repeated_no_finding_reduction_rate: FiniteFloat
    earlier_useful_discriminator_rate: FiniteFloat = Field(ge=0, le=1)
    unresolved_abandoned_rate_change: FiniteFloat


class P34QualityResults(P34Model):
    useful_discriminator_hit_rate: FiniteFloat = Field(ge=0, le=1)
    strongest_contradiction_inspection_rate: FiniteFloat = Field(ge=0, le=1)
    recurrence_match_correctness_rate: FiniteFloat = Field(ge=0, le=1)
    context_transfer_correctness_rate: FiniteFloat = Field(ge=0, le=1)
    driver_car_separation_correctness_rate: FiniteFloat = Field(ge=0, le=1)
    eventual_p19_resolution_rate: FiniteFloat = Field(ge=0, le=1)
    no_call_stability_rate: FiniteFloat = Field(ge=0, le=1)


class P34SubgroupResult(P34Model):
    subgroup_key: str = Field(min_length=1)
    independent_investigations: int = Field(ge=0)
    authority_violations: int = Field(ge=0)
    mandatory_check_violations: int = Field(ge=0)
    material_efficiency_degradation_pct: FiniteFloat = Field(ge=0)
    passed: bool
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def subgroup_cannot_hide_failure(self) -> Self:
        should_pass = (
            self.independent_investigations > 0
            and self.authority_violations == 0
            and self.mandatory_check_violations == 0
            and self.material_efficiency_degradation_pct <= 20
            and not self.blockers
        )
        if self.passed != should_pass:
            raise ValueError("P34 subgroup pass state is inconsistent")
        return self


class PairedInvestigationComparison(P34Model):
    """One honest outcome comparison at the investigation independence unit."""

    schema_version: Literal["p34.paired-investigation-comparison.v1"] = (
        "p34.paired-investigation-comparison.v1"
    )
    comparison_id: str = Field(pattern=r"^p34cmp_[0-9a-f]{24}$")
    comparison_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    investigation_id: str = Field(min_length=1)
    pair_id: str = Field(pattern=r"^p34pair_[0-9a-f]{24}$")
    pair_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    activation_protocol_id: str = Field(pattern=r"^p34proto_[0-9a-f]{24}$")
    activation_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    certificate_id: str = Field(pattern=r"^p34out_[0-9a-f]{24}$")
    certificate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    discriminator_outcome_id: str | None = Field(
        default=None, pattern=r"^p34disc_[0-9a-f]{24}$"
    )
    discriminator_outcome_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    outcome_followup_id: str | None = Field(
        default=None, pattern=r"^p34follow_[0-9a-f]{24}$"
    )
    outcome_followup_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    counterfactual_source_certificate_id: str | None = Field(
        default=None, pattern=r"^p34out_[0-9a-f]{24}$"
    )
    counterfactual_source_certificate_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    independently_observed_artifact_ids: tuple[str, ...] = ()
    decision_frozen_at: datetime
    observability: CounterfactualState
    context_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    problem_family: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    context_transfer_class: Literal["none", "exact", "compatible", "weak", "blocked"]
    subgroup_keys: tuple[str, ...] = Field(min_length=1)
    baseline_tool_steps: int = Field(ge=0)
    memory_path_metrics_observed: bool
    bounded_reorder_observed: bool = False
    bounded_discriminator_step_advance: Literal[0, 1] = 0
    bounded_discriminator_step_delay: Literal[0, 1] = 0
    bounded_dead_end_promoted: bool = False
    memory_tool_steps: int | None = Field(default=None, ge=0)
    baseline_elapsed_seconds: FiniteFloat = Field(ge=0)
    memory_elapsed_seconds: FiniteFloat | None = Field(default=None, ge=0)
    baseline_consumption_metrics_observed: bool
    memory_consumption_metrics_observed: bool
    baseline_laps: int | None = Field(default=None, ge=0)
    memory_laps: int | None = Field(default=None, ge=0)
    baseline_questions: int = Field(ge=0)
    memory_questions: int | None = Field(default=None, ge=0)
    baseline_dead_ends: int = Field(ge=0)
    memory_dead_ends: int | None = Field(default=None, ge=0)
    baseline_measurement_missions: int | None = Field(default=None, ge=0)
    memory_measurement_missions: int | None = Field(default=None, ge=0)
    baseline_repeated_no_findings: int = Field(ge=0)
    memory_repeated_no_findings: int | None = Field(default=None, ge=0)
    baseline_useful_discriminator_step: int | None = Field(default=None, ge=1)
    memory_useful_discriminator_step: int | None = Field(default=None, ge=1)
    baseline_unresolved_or_abandoned: bool
    memory_unresolved_or_abandoned: bool | None
    useful_discriminator_hit: bool
    strongest_contradiction_handled: bool
    recurrence_match_correct: bool | None
    context_transfer_correct: bool | None
    driver_car_separation_correct: bool | None
    eventual_p19_resolution: bool | None
    no_call_stable: bool | None
    authority_violations: int = Field(ge=0)
    p19_action_mismatches: int = Field(ge=0)
    stale_workspace_actions: int = Field(ge=0)
    mandatory_check_violations: int = Field(ge=0)
    hidden_contradiction_failures: int = Field(ge=0)
    incompatible_history_transfers: int = Field(ge=0)
    driver_memory_mechanical_diagnoses: int = Field(ge=0)
    memory_only_terminal_actions: int = Field(ge=0)
    prospective: bool
    synthetic: bool
    qualified: bool
    blockers: tuple[str, ...] = ()
    compared_at: datetime
    setup_authorized: Literal[False] = False

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.setdefault(
            "schema_version", "p34.paired-investigation-comparison.v1"
        )
        body.pop("comparison_id", None)
        body.pop("comparison_sha256", None)
        draft = cls.model_construct(
            **body,
            comparison_id="p34cmp_" + "0" * 24,
            comparison_sha256="0" * 64,
        ).model_dump(mode="json")
        digest = _content_digest(draft, "comparison_id", "comparison_sha256")
        return cls.model_validate(
            {
                **draft,
                "comparison_id": f"p34cmp_{digest[:24]}",
                "comparison_sha256": digest,
            }
        )

    @model_validator(mode="after")
    def comparison_never_fabricates_a_counterfactual(self) -> Self:
        _unique(self.subgroup_keys, "comparison subgroup")
        _unique(
            self.independently_observed_artifact_ids,
            "independently observed artifact",
        )
        for left, right, label in (
            (
                self.discriminator_outcome_id,
                self.discriminator_outcome_sha256,
                "discriminator outcome",
            ),
            (
                self.outcome_followup_id,
                self.outcome_followup_sha256,
                "outcome follow-up",
            ),
            (
                self.counterfactual_source_certificate_id,
                self.counterfactual_source_certificate_sha256,
                "counterfactual certificate",
            ),
        ):
            if (left is None) != (right is None):
                raise ValueError(f"P34 {label} identity requires ID and digest")
        memory_metrics = (
            self.memory_tool_steps,
            self.memory_elapsed_seconds,
            self.memory_questions,
            self.memory_dead_ends,
            self.memory_repeated_no_findings,
            self.memory_unresolved_or_abandoned,
        )
        baseline_consumption_complete = (
            self.baseline_laps is not None
            and self.baseline_measurement_missions is not None
        )
        memory_consumption_complete = (
            self.memory_laps is not None
            and self.memory_measurement_missions is not None
        )
        if self.baseline_consumption_metrics_observed != baseline_consumption_complete:
            raise ValueError("P34 baseline consumption must be complete or withheld")
        if self.memory_consumption_metrics_observed != memory_consumption_complete:
            raise ValueError("P34 memory consumption must be complete or withheld")
        if self.observability in {"pending", "counterfactual_unobservable", "invalid"}:
            if any(value is not None for value in memory_metrics) or (
                self.memory_useful_discriminator_step is not None
            ) or self.memory_path_metrics_observed or self.memory_consumption_metrics_observed:
                raise ValueError("P34 unobservable comparison cannot invent memory outcomes")
            if (
                self.context_transfer_correct is not None
                or self.driver_car_separation_correct is not None
            ):
                raise ValueError(
                    "P34 unobservable comparison cannot claim learned-path correctness"
                )
        elif self.memory_path_metrics_observed != all(
            value is not None for value in memory_metrics
        ):
            raise ValueError("P34 memory path metrics must be complete or wholly withheld")
        if self.bounded_reorder_observed:
            if (
                self.observability != "counterfactual_observable"
                or (
                    self.bounded_discriminator_step_advance
                    + self.bounded_discriminator_step_delay
                    != 1
                )
                or (
                    self.bounded_discriminator_step_advance
                    and self.bounded_discriminator_step_delay
                )
                or not self.useful_discriminator_hit
            ):
                raise ValueError(
                    "P34 bounded reorder requires one observed useful position effect"
                )
        elif (
            self.bounded_discriminator_step_advance
            or self.bounded_discriminator_step_delay
            or self.bounded_dead_end_promoted
        ):
            raise ValueError("P34 unobserved reorder cannot claim localized improvement")
        if (
            self.bounded_dead_end_promoted
            and not self.bounded_discriminator_step_delay
        ):
            raise ValueError("P34 promoted dead end requires one bounded observed cost")
        if (
            self.observability == "counterfactual_observable"
            and self.memory_path_metrics_observed
            and self.counterfactual_source_certificate_id is None
        ):
            raise ValueError(
                "P34 counterfactual efficiency requires an independent outcome certificate"
            )
        if self.observability == "directly_observed" and (
            not self.memory_path_metrics_observed
            or
            self.memory_tool_steps != self.baseline_tool_steps
            or self.memory_elapsed_seconds != self.baseline_elapsed_seconds
            or self.memory_consumption_metrics_observed
            != self.baseline_consumption_metrics_observed
            or self.memory_laps != self.baseline_laps
            or self.memory_questions != self.baseline_questions
            or self.memory_dead_ends != self.baseline_dead_ends
            or self.memory_measurement_missions
            != self.baseline_measurement_missions
            or self.memory_repeated_no_findings
            != self.baseline_repeated_no_findings
            or self.memory_useful_discriminator_step
            != self.baseline_useful_discriminator_step
            or self.memory_unresolved_or_abandoned
            != self.baseline_unresolved_or_abandoned
        ):
            raise ValueError("P34 directly observed action must preserve actual metrics")
        if self.qualified and (self.synthetic or self.blockers or self.observability == "invalid"):
            raise ValueError("P34 synthetic, blocked, or invalid cases cannot qualify")
        if not self.qualified and not self.blockers:
            raise ValueError("P34 withheld comparisons require explicit blockers")
        dumped = self.model_dump(mode="json")
        expected = _content_digest(dumped, "comparison_id", "comparison_sha256")
        if (
            self.comparison_sha256 != expected
            or self.comparison_id != f"p34cmp_{expected[:24]}"
        ):
            raise ValueError("P34 paired comparison identity is corrupt")
        return self


class P34NegativeControlResult(P34Model):
    schema_version: Literal["p34.negative-control-result.v1"] = (
        "p34.negative-control-result.v1"
    )
    result_id: str = Field(pattern=r"^p34ctrl_[0-9a-f]{24}$")
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_id: str = Field(pattern=r"^p34proto_[0-9a-f]{24}$")
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_id: str = Field(min_length=1)
    investigation_id: str = Field(min_length=1)
    pair_id: str = Field(pattern=r"^p34pair_[0-9a-f]{24}$")
    pair_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_exact_fallback: Literal[True] = True
    observed_exact_fallback: bool
    passed: bool
    source_artifact_ids: tuple[str, ...] = Field(min_length=1)
    synthetic: Literal[False] = False
    blockers: tuple[str, ...] = ()
    evaluated_at: datetime

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.setdefault("schema_version", "p34.negative-control-result.v1")
        body.pop("result_id", None)
        body.pop("result_sha256", None)
        draft = cls.model_construct(
            **body,
            result_id="p34ctrl_" + "0" * 24,
            result_sha256="0" * 64,
        ).model_dump(mode="json")
        digest = _content_digest(draft, "result_id", "result_sha256")
        return cls.model_validate(
            {
                **draft,
                "result_id": f"p34ctrl_{digest[:24]}",
                "result_sha256": digest,
            }
        )

    @model_validator(mode="after")
    def control_is_real_and_content_addressed(self) -> Self:
        _unique(self.source_artifact_ids, "negative-control artifact")
        if self.passed != (self.observed_exact_fallback and not self.blockers):
            raise ValueError("P34 negative-control result is inconsistent")
        dumped = self.model_dump(mode="json")
        expected = _content_digest(dumped, "result_id", "result_sha256")
        if self.result_sha256 != expected or self.result_id != f"p34ctrl_{expected[:24]}":
            raise ValueError("P34 negative-control result identity is corrupt")
        return self


class P34InvestigationActivationProtocol(P34Model):
    schema_version: Literal["p34.activation-protocol.v1"] = (
        "p34.activation-protocol.v1"
    )
    protocol_id: str = Field(pattern=r"^p34proto_[0-9a-f]{24}$")
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_version: str = Field(min_length=1)
    frozen_at: datetime
    prospective_boundary: datetime
    candidate_capability: Literal["limited_attention"] = "limited_attention"
    baseline_policy_id: str = Field(pattern=r"^p34pol_[0-9a-f]{24}$")
    baseline_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    memory_policy_id: str = Field(pattern=r"^p34pol_[0-9a-f]{24}$")
    memory_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    activated_policy_id: str = Field(pattern=r"^p34pol_[0-9a-f]{24}$")
    activated_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    independence_unit: Literal["investigation"] = "investigation"
    eligibility_rules: tuple[str, ...] = Field(min_length=1)
    exclusions: tuple[str, ...] = Field(min_length=1)
    metrics: tuple[str, ...] = Field(min_length=1)
    required_subgroups: tuple[str, ...] = Field(min_length=1)
    negative_control_ids: tuple[str, ...] = Field(min_length=1)
    drift_rules: tuple[str, ...] = Field(min_length=1)
    rollback_rules: tuple[str, ...] = Field(min_length=1)
    minimum_historical_investigations: int = Field(ge=20)
    minimum_prospective_investigations: int = Field(ge=12)
    minimum_contexts: int = Field(ge=3)
    minimum_problem_families: int = Field(ge=4)
    minimum_objectives: int = Field(ge=2)
    minimum_exact_recurrence_cases: int = Field(ge=5)
    minimum_compatible_recurrence_cases: int = Field(ge=5)
    minimum_tool_step_reduction: FiniteFloat = Field(ge=1)
    minimum_relative_tool_step_reduction: FiniteFloat = Field(ge=0.15, le=1)
    minimum_earlier_discriminator_rate: FiniteFloat = Field(ge=0.60, le=1)
    minimum_dead_end_reduction_rate: FiniteFloat = Field(ge=0.15, le=1)
    maximum_unresolved_rate_worsening: FiniteFloat = Field(ge=0, le=0.05)
    maximum_negative_transfer_rate: FiniteFloat = Field(ge=0, le=0.10)
    maximum_subgroup_efficiency_degradation_pct: FiniteFloat = Field(ge=0, le=20)
    maximum_reorder_distance: Literal[1] = 1
    authority_ceiling: Literal["limited_attention"] = "limited_attention"
    synthetic_cases_count_toward_activation: Literal[False] = False
    historical_only_activation_allowed: Literal[False] = False
    manual_override_allowed: Literal[False] = False
    p19_authority_unchanged: Literal[True] = True

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.setdefault("schema_version", "p34.activation-protocol.v1")
        body.pop("protocol_id", None)
        body.pop("protocol_sha256", None)
        draft = cls.model_construct(
            **body,
            protocol_id="p34proto_" + "0" * 24,
            protocol_sha256="0" * 64,
        ).model_dump(mode="json")
        digest = _content_digest(draft, "protocol_id", "protocol_sha256")
        return cls.model_validate(
            {
                **draft,
                "protocol_id": f"p34proto_{digest[:24]}",
                "protocol_sha256": digest,
            }
        )

    @model_validator(mode="after")
    def protocol_is_preregistered_and_content_addressed(self) -> Self:
        for values, label in (
            (self.eligibility_rules, "eligibility rule"),
            (self.exclusions, "exclusion"),
            (self.metrics, "metric"),
            (self.required_subgroups, "required subgroup"),
            (self.negative_control_ids, "negative control"),
            (self.drift_rules, "drift rule"),
            (self.rollback_rules, "rollback rule"),
        ):
            _unique(values, label)
        if self.prospective_boundary != self.frozen_at:
            raise ValueError("P34 prospective evidence begins exactly after protocol freeze")
        dumped = self.model_dump(mode="json")
        expected = _content_digest(dumped, "protocol_id", "protocol_sha256")
        if (
            self.protocol_sha256 != expected
            or self.protocol_id != f"p34proto_{expected[:24]}"
        ):
            raise ValueError("P34 activation protocol identity is corrupt")
        return self


class InvestigationPolicyEvaluation(P34Model):
    schema_version: Literal["p34.policy-evaluation.v1"] = (
        "p34.policy-evaluation.v1"
    )
    evaluation_id: str = Field(pattern=r"^p34eval_[0-9a-f]{24}$")
    evaluation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_id: str = Field(pattern=r"^p34proto_[0-9a-f]{24}$")
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registry_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ledger_record_count: int = Field(ge=0)
    ledger_head_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    baseline_policy_id: str = Field(pattern=r"^p34pol_[0-9a-f]{24}$")
    memory_policy_id: str = Field(pattern=r"^p34pol_[0-9a-f]{24}$")
    independent_investigation_count: int = Field(ge=0)
    historical_count: int = Field(ge=0)
    prospective_count: int = Field(ge=0)
    context_count: int = Field(ge=0)
    problem_family_count: int = Field(ge=0)
    objective_count: int = Field(ge=0)
    exact_recurrence_count: int = Field(ge=0)
    compatible_recurrence_count: int = Field(ge=0)
    paired_observable_comparisons: int = Field(ge=0)
    unobservable_comparisons: int = Field(ge=0)
    invalid_comparisons: int = Field(ge=0)
    safety: P34SafetyResults
    efficiency: P34EfficiencyResults
    quality: P34QualityResults
    negative_transfer_count: int = Field(ge=0)
    negative_transfer_rate: FiniteFloat = Field(ge=0, le=1)
    negative_control_results: dict[str, bool]
    subgroup_results: tuple[P34SubgroupResult, ...]
    drift_results: dict[str, int]
    blockers: tuple[str, ...]
    decision: Literal["no_activation_earned", "limited_attention_earned"]
    evaluated_at: datetime

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.setdefault("schema_version", "p34.policy-evaluation.v1")
        body.pop("evaluation_id", None)
        body.pop("evaluation_sha256", None)
        draft = cls.model_construct(
            **body,
            evaluation_id="p34eval_" + "0" * 24,
            evaluation_sha256="0" * 64,
        ).model_dump(mode="json")
        digest = _content_digest(draft, "evaluation_id", "evaluation_sha256")
        return cls.model_validate(
            {
                **draft,
                "evaluation_id": f"p34eval_{digest[:24]}",
                "evaluation_sha256": digest,
            }
        )

    @model_validator(mode="after")
    def evaluation_counts_independent_investigations_only(self) -> Self:
        if (self.ledger_record_count == 0) != (self.ledger_head_sha256 is None):
            raise ValueError("P34 evaluation ledger boundary is inconsistent")
        if self.historical_count + self.prospective_count != self.independent_investigation_count:
            raise ValueError("P34 historical/prospective counts must partition investigations")
        if (
            self.paired_observable_comparisons + self.unobservable_comparisons
            > self.independent_investigation_count
        ):
            raise ValueError("P34 comparison counts cannot exceed independent investigations")
        expected_rate = (
            self.negative_transfer_count / self.paired_observable_comparisons
            if self.paired_observable_comparisons
            else 0.0
        )
        if abs(float(self.negative_transfer_rate) - expected_rate) > 1e-9:
            raise ValueError("P34 negative-transfer rate is inconsistent")
        if self.decision == "limited_attention_earned" and self.blockers:
            raise ValueError("P34 activation cannot retain blockers")
        if self.decision == "no_activation_earned" and not self.blockers:
            raise ValueError("P34 locked evaluation requires explicit blockers")
        dumped = self.model_dump(mode="json")
        expected = _content_digest(dumped, "evaluation_id", "evaluation_sha256")
        if (
            self.evaluation_sha256 != expected
            or self.evaluation_id != f"p34eval_{expected[:24]}"
        ):
            raise ValueError("P34 policy evaluation identity is corrupt")
        return self


class P34ActivationDecision(P34Model):
    schema_version: Literal["p34.activation-decision.v1"] = (
        "p34.activation-decision.v1"
    )
    decision_id: str = Field(pattern=r"^p34act_[0-9a-f]{24}$")
    decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_id: str = Field(pattern=r"^p34proto_[0-9a-f]{24}$")
    protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_id: str = Field(pattern=r"^p34eval_[0-9a-f]{24}$")
    evaluation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    activated_policy_id: str = Field(pattern=r"^p34pol_[0-9a-f]{24}$")
    activated_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    state: ActivationState
    production_policy_kind: PolicyKind
    blockers: tuple[str, ...]
    recovery_debt: tuple[str, ...] = ()
    supersedes_decision_id: str | None = Field(
        default=None, pattern=r"^p34act_[0-9a-f]{24}$"
    )
    supersedes_decision_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    rollback_applied: bool = False
    decided_at: datetime
    manual_override_used: Literal[False] = False
    setup_authorized: Literal[False] = False

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.setdefault("schema_version", "p34.activation-decision.v1")
        body.pop("decision_id", None)
        body.pop("decision_sha256", None)
        draft = cls.model_construct(
            **body,
            decision_id="p34act_" + "0" * 24,
            decision_sha256="0" * 64,
        ).model_dump(mode="json")
        digest = _content_digest(draft, "decision_id", "decision_sha256")
        return cls.model_validate(
            {
                **draft,
                "decision_id": f"p34act_{digest[:24]}",
                "decision_sha256": digest,
            }
        )

    @model_validator(mode="after")
    def activation_is_limited_or_baseline(self) -> Self:
        if (self.supersedes_decision_id is None) != (
            self.supersedes_decision_sha256 is None
        ):
            raise ValueError("P34 superseded activation requires ID and digest")
        if self.state == "shadow_only":
            if (
                self.production_policy_kind != "deterministic_baseline"
                or not self.blockers
                or self.recovery_debt != self.blockers
                or self.rollback_applied
                != (self.supersedes_decision_id is not None)
            ):
                raise ValueError("P34 shadow state must retain baseline and blockers")
        elif (
            self.production_policy_kind != "limited_attention"
            or self.blockers
            or self.recovery_debt
            or self.supersedes_decision_id is not None
            or self.rollback_applied
        ):
            raise ValueError("P34 limited attention requires a blocker-free earned decision")
        dumped = self.model_dump(mode="json")
        expected = _content_digest(dumped, "decision_id", "decision_sha256")
        if self.decision_sha256 != expected or self.decision_id != f"p34act_{expected[:24]}":
            raise ValueError("P34 activation decision identity is corrupt")
        return self


class InvestigationImprovementReadiness(P34Model):
    production_policy: Literal["deterministic_baseline", "limited_attention"]
    memory_policy_state: ActivationState
    activation_decision: Literal[
        "no_activation_earned", "limited_attention_earned"
    ]
    evaluation_decision: Literal[
        "no_activation_earned", "limited_attention_earned"
    ]
    effective_activation_decision_id: str | None = Field(
        default=None, pattern=r"^p34act_[0-9a-f]{24}$"
    )
    effective_activation_decision_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    qualified_historical_investigations: int = Field(ge=0)
    qualified_prospective_investigations: int = Field(ge=0)
    observable_comparisons: int = Field(ge=0)
    unobservable_comparisons: int = Field(ge=0)
    historical_deficit: int = Field(ge=0)
    prospective_deficit: int = Field(ge=0)
    exact_recurrence_deficit: int = Field(ge=0)
    compatible_recurrence_deficit: int = Field(ge=0)
    context_deficit: int = Field(ge=0)
    problem_family_deficit: int = Field(ge=0)
    objective_deficit: int = Field(ge=0)
    safety_gate_passed: bool
    negative_controls_passed: bool
    subgroup_gate_passed: bool
    blockers: tuple[str, ...]
    remaining_collection_missions: tuple[str, ...]
    authority_ceiling: Literal["attention_only"] = "attention_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def readiness_cannot_activate_from_debt(self) -> Self:
        for statement in (*self.blockers, *self.remaining_collection_missions):
            validate_memory_prose(statement, label="P34 readiness statement")
        if (self.effective_activation_decision_id is None) != (
            self.effective_activation_decision_sha256 is None
        ):
            raise ValueError("P34 readiness activation identity must be complete")
        if self.memory_policy_state == "shadow_only":
            if (
                self.production_policy != "deterministic_baseline"
                or self.activation_decision != "no_activation_earned"
                or self.effective_activation_decision_id is not None
                or not self.blockers
            ):
                raise ValueError("P34 shadow readiness requires an explicit locked decision")
        elif (
            self.production_policy != "limited_attention"
            or
            self.activation_decision != "limited_attention_earned"
            or self.effective_activation_decision_id is None
            or not self.safety_gate_passed
        ):
            raise ValueError(
                "P34 limited attention requires an exact effective artifact and safe ledger"
            )
        return self


class InvestigationAdaptationContext(P34Model):
    """Independent current-workspace mirror for public pair verification."""

    schema_version: Literal["p34.investigation-adaptation-context.v1"] = (
        "p34.investigation-adaptation-context.v1"
    )
    context_binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_truth_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p19_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p20_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p26_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p32_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p33_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p33_context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    p33_problem_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    qualified_available_artifact_ids: tuple[str, ...] = ()
    qualified_available_artifact_evidence_states: tuple[
        Literal["measured", "calculated", "controlled_test_effect"], ...
    ] = ()
    qualified_available_artifact_provenance_sha256s: tuple[str, ...] = ()
    current_evidence_pinned_tool_ids: tuple[str, ...] = ()
    track: str = Field(min_length=1)
    track_configuration: str = Field(min_length=1)
    package_type: str = Field(min_length=1)
    iracing_build: str = Field(min_length=1)
    problem_family: PhysicalProblemFamily
    problem_orientation: ProblemOrientation
    track_class: TrackClass
    phase: str = Field(min_length=1)
    current_objective: str = Field(min_length=1)
    build_review_state: Literal[
        "same_build", "reviewed_compatible_build", "future_unreviewed_build"
    ]
    driver_drift_state: Literal["stable", "material_drift", "unknown"]
    context_subgroup_keys: tuple[str, ...] = Field(min_length=1)
    negative_control_condition: Literal[
        "no_relevant_history",
        "incompatible_history",
        "corrupt_history",
        "generic_component_knowledge_only",
        "same_words_different_physical_scope",
        "material_driver_drift",
        "future_memory_record",
    ] | None = None
    negative_control_evidence_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.setdefault(
            "schema_version", "p34.investigation-adaptation-context.v1"
        )
        body.pop("context_binding_sha256", None)
        draft = cls.model_construct(
            **body,
            context_binding_sha256="0" * 64,
        ).model_dump(mode="json")
        digest = _content_digest(draft, "context_binding_sha256")
        return cls.model_validate(
            {**draft, "context_binding_sha256": digest}
        )

    @model_validator(mode="after")
    def current_context_is_content_addressed(self) -> Self:
        _unique(self.context_subgroup_keys, "adaptation-context subgroup")
        _unique(
            self.qualified_available_artifact_ids,
            "adaptation-context qualified artifact",
        )
        _unique(
            self.current_evidence_pinned_tool_ids,
            "adaptation-context current-evidence pinned tool",
        )
        qualified_count = len(self.qualified_available_artifact_ids)
        if (
            len(self.qualified_available_artifact_evidence_states)
            != qualified_count
            or len(self.qualified_available_artifact_provenance_sha256s)
            != qualified_count
            or any(
                len(value) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in value
                )
                for value in self.qualified_available_artifact_provenance_sha256s
            )
        ):
            raise ValueError(
                "P34 current context requires aligned qualified artifact provenance"
            )
        if (self.negative_control_condition is None) != (
            self.negative_control_evidence_sha256 is None
        ):
            raise ValueError(
                "P34 current context requires condition and proof digest together"
            )
        dumped = self.model_dump(mode="json")
        expected = _content_digest(dumped, "context_binding_sha256")
        if self.context_binding_sha256 != expected:
            raise ValueError("P34 adaptation context identity is corrupt")
        return self


class InvestigationImprovementProjection(P34Model):
    """Bounded Learning Mode projection; never the production decision source."""

    schema_version: Literal["p34.investigation-improvement-projection.v1"] = (
        "p34.investigation-improvement-projection.v1"
    )
    projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    state: Literal["available", "unavailable"]
    production_policy: Literal["deterministic_baseline", "limited_attention"]
    memory_policy_state: ActivationState
    current_pair: PairedInvestigationDecision | None
    current_context: InvestigationAdaptationContext | None
    current_pair_status: Literal["pending"] | None
    latest_completed_pair: PairedInvestigationDecision | None
    latest_completed_comparison: PairedInvestigationComparison | None
    latest_outcome_status: CounterfactualState | None
    decisions_differ: bool
    difference_explanation: str = Field(min_length=1)
    memory_evidence_record_ids: tuple[str, ...] = ()
    context_transfer_class: Literal[
        "none", "exact", "compatible", "weak", "blocked"
    ]
    readiness: InvestigationImprovementReadiness
    safety_blockers: tuple[str, ...]
    p19_authority_unchanged: Literal[True] = True
    setup_authorized: Literal[False] = False

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = dict(values)
        body.setdefault(
            "schema_version", "p34.investigation-improvement-projection.v1"
        )
        body.pop("projection_sha256", None)
        draft = cls.model_construct(
            **body,
            projection_sha256="0" * 64,
        ).model_dump(mode="json")
        digest = _content_digest(draft, "projection_sha256")
        return cls.model_validate({**draft, "projection_sha256": digest})

    @model_validator(mode="after")
    def projection_matches_pair_semantics(self) -> Self:
        _unique(self.memory_evidence_record_ids, "projection memory evidence")
        validate_memory_prose(
            self.difference_explanation,
            label="P34 projection explanation",
        )
        for statement in self.safety_blockers:
            validate_memory_prose(statement, label="P34 safety blocker")
        if (self.current_pair is None) != (self.current_pair_status is None):
            raise ValueError("P34 current pair status must be pending or absent")
        if (self.current_pair is None) != (self.current_context is None):
            raise ValueError("P34 current pair requires an independent current context")
        if (self.latest_completed_pair is None) != (
            self.latest_completed_comparison is None
        ) or (self.latest_completed_comparison is None) != (
            self.latest_outcome_status is None
        ):
            raise ValueError(
                "P34 latest completed pair, comparison, and status are all-or-none"
            )
        if self.state == "available":
            if self.current_pair is None and self.latest_completed_comparison is None:
                raise ValueError(
                    "P34 available projection requires a current pair or completed comparison"
                )
        if self.current_pair is not None:
            pair = self.current_pair
            context = self.current_context
            if (
                context is None
                or pair.run_id != self.run_id
                or pair.session_id != self.session_id
                or pair.workspace_revision != self.workspace_revision
            ):
                raise ValueError("P34 projection scope does not match its frozen pair")
            evidence_sha256 = (
                canonical_json_sha256(
                    pair.negative_control_evidence.model_dump(mode="json")
                )
                if pair.negative_control_evidence is not None
                else None
            )
            if (
                context.run_id != pair.run_id
                or context.session_id != pair.session_id
                or context.workspace_revision != pair.workspace_revision
                or context.current_truth_sha256 != pair.current_truth_sha256
                or context.p19_snapshot_sha256 != pair.p19_snapshot_sha256
                or context.p20_projection_sha256 != pair.p20_projection_sha256
                or context.p26_projection_sha256 != pair.p26_projection_sha256
                or context.p32_projection_sha256 != pair.p32_projection_sha256
                or context.p33_projection_sha256 != pair.p33_projection_sha256
                or context.p33_context_sha256 != pair.p33_context_sha256
                or context.p33_problem_sha256 != pair.p33_problem_sha256
                or context.qualified_available_artifact_ids
                != pair.qualified_available_artifact_ids
                or context.qualified_available_artifact_evidence_states
                != pair.qualified_available_artifact_evidence_states
                or context.qualified_available_artifact_provenance_sha256s
                != pair.qualified_available_artifact_provenance_sha256s
                or context.current_evidence_pinned_tool_ids
                != pair.current_evidence_pinned_tool_ids
                or context.track != pair.track
                or context.track_configuration != pair.track_configuration
                or context.package_type != pair.package_type
                or context.iracing_build != pair.iracing_build
                or context.problem_family != pair.problem_family
                or context.problem_orientation != pair.problem_orientation
                or context.track_class != pair.track_class
                or context.phase != pair.phase
                or context.current_objective != pair.current_objective
                or context.build_review_state != pair.build_review_state
                or context.driver_drift_state != pair.driver_drift_state
                or context.context_subgroup_keys != pair.context_subgroup_keys
                or context.negative_control_condition
                != pair.negative_control_condition
                or context.negative_control_evidence_sha256 != evidence_sha256
            ):
                raise ValueError(
                    "P34 current context does not independently bind the pair"
                )
        surfaced_pair = self.current_pair or self.latest_completed_pair
        if surfaced_pair is not None:
            if self.decisions_differ != (
                surfaced_pair.baseline_decision.executable_identity
                != surfaced_pair.memory_decision.executable_identity
            ):
                raise ValueError("P34 surfaced-pair difference flag is inconsistent")
            if self.memory_evidence_record_ids != surfaced_pair.memory_records_consulted:
                raise ValueError("P34 surfaced pair must expose exact P33 records")
            if self.context_transfer_class != surfaced_pair.context_transfer_class:
                raise ValueError("P34 projection transfer must match its surfaced pair")
        if self.latest_completed_comparison is not None:
            completed_pair = self.latest_completed_pair
            comparison = self.latest_completed_comparison
            if (
                completed_pair is None
                or comparison.pair_id != completed_pair.pair_id
                or comparison.pair_sha256 != completed_pair.pair_sha256
                or comparison.investigation_id != completed_pair.investigation_id
                or self.latest_outcome_status != comparison.observability
            ):
                raise ValueError("P34 latest comparison must bind its exact parent pair")
        if self.state == "unavailable" and (
            self.current_pair is not None
            or self.current_context is not None
            or self.current_pair_status is not None
            or self.latest_completed_pair is not None
            or self.latest_completed_comparison is not None
            or self.latest_outcome_status is not None
            or self.decisions_differ
            or self.memory_evidence_record_ids
            or not self.safety_blockers
        ):
            raise ValueError("P34 unavailable projection must fail closed without a pair")
        expected_policy = (
            "deterministic_baseline"
            if self.memory_policy_state == "shadow_only"
            else "limited_attention"
        )
        if self.production_policy != expected_policy:
            raise ValueError("P34 projection activation state does not match production")
        if self.current_pair is not None and (
            self.current_pair.activation_state != self.memory_policy_state
            or self.current_pair.production_policy_kind != self.production_policy
        ):
            raise ValueError("P34 projection production policy must match its pair")
        if (
            self.readiness.memory_policy_state != self.memory_policy_state
            or self.readiness.production_policy != self.production_policy
        ):
            raise ValueError("P34 projection policy state must match readiness")
        dumped = self.model_dump(mode="json")
        expected = _content_digest(dumped, "projection_sha256")
        if self.projection_sha256 != expected:
            raise ValueError("P34 improvement projection identity is corrupt")
        return self


__all__ = [
    "ActivationState",
    "CounterfactualState",
    "DecisionKind",
    "DiscriminatorOutcome",
    "InvestigationDecision",
    "InvestigationAdaptationContext",
    "InvestigationImprovementReadiness",
    "InvestigationImprovementProjection",
    "InvestigationNegativeTransfer",
    "InvestigationOutcomeCertificate",
    "InvestigationOutcomeFollowup",
    "InvestigationPolicy",
    "InvestigationPolicyEvaluation",
    "NegativeControlConditionEvidence",
    "NegativeTransferKind",
    "P19CauseChange",
    "P19CauseState",
    "P34ActivationDecision",
    "P34EfficiencyResults",
    "P34InvestigationActivationProtocol",
    "P34NegativeControlResult",
    "P34Model",
    "P34_PHYSICAL_SCOPE_MISMATCH_DIMENSIONS",
    "P34SafetyResults",
    "P34QualityResults",
    "P34SubgroupResult",
    "PairedInvestigationComparison",
    "PairedInvestigationDecision",
    "PolicyKind",
    "PhysicalProblemFamily",
    "PriorityTier",
    "SafeReorderGroup",
    "TerminalInvestigationDecision",
    "TrackClass",
    "ProblemOrientation",
    "canonical_context_subgroups",
    "investigation_adaptation_source_snapshot_sha256",
]
