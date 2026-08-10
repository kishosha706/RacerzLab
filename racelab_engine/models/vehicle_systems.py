"""Typed, non-authoritative vehicle-systems intelligence contracts.

P26 describes sourced engineering expectations and projects P19/P20 evidence onto
components.  These models deliberately cannot authorize a setup change.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.models.evidence import EvidenceState


class VehicleSystemsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class VehicleSystemsNodeKind(str, Enum):
    COMPONENT = "component"
    CONTROL = "control"
    COMPONENT_PROPERTY = "component_property"
    VEHICLE_STATE = "vehicle_state"
    OBSERVATION = "observation"
    SYMPTOM = "symptom"
    OUTCOME = "outcome"
    CONTEXT = "context"


class VehicleSystemsEdgeKind(str, Enum):
    CONTROL_ADJUSTS_PROPERTY = "control_adjusts_property"
    PROPERTY_EXPECTED_TO_INFLUENCE_STATE = "property_expected_to_influence_state"
    STATE_MAY_PRESENT_AS_SYMPTOM = "state_may_present_as_symptom"
    STATE_OBSERVABLE_BY = "state_observable_by"
    COMPONENT_COUPLES_WITH_COMPONENT = "component_couples_with_component"
    CONTROL_REQUIRES_INVARIANT = "control_requires_invariant"
    CONTROL_HAS_COUNTEREFFECT = "control_has_countereffect"
    OBSERVATION_SUPPORTS_STATE = "observation_supports_state"
    OBSERVATION_CONTRADICTS_STATE = "observation_contradicts_state"
    CONTROLLED_TEST_OBSERVED_RESPONSE = "controlled_test_observed_response"
    POLICY_REJECTED_DUE_TO_COUNTEREFFECT = "policy_rejected_due_to_countereffect"


class ComponentObservabilityState(str, Enum):
    DEFINITION_KNOWN = "definition_known"
    SETUP_CAPTURED = "setup_captured"
    LIVE_RESPONSE_OBSERVABLE = "live_response_observable"
    CURRENT_RESPONSE_OBSERVED = "current_response_observed"
    MECHANISM_SUPPORTED = "mechanism_supported"
    CONTROLLED_RESPONSE_KNOWN = "controlled_response_known"
    EXACT_CONTEXT_POLICY_KNOWN = "exact_context_policy_known"
    UNAVAILABLE = "unavailable"


class ComponentRelevance(str, Enum):
    IRRELEVANT = "irrelevant"
    CANDIDATE = "candidate"
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    BLOCKED = "blocked"
    TESTED = "tested"


class BuildApplicability(VehicleSystemsModel):
    car_family: str = Field(min_length=1)
    car_paths: tuple[str, ...] = ()
    car_versions: tuple[str, ...] = ()
    iracing_build_min: str | None = None
    iracing_build_max: str | None = None
    track_package_types: tuple[str, ...] = ()
    source_version: str = Field(min_length=1)


class ComponentObservabilityContract(VehicleSystemsModel):
    static_setting_channels: tuple[str, ...] = ()
    live_telemetry_channels: tuple[str, ...] = ()
    derived_metrics: tuple[str, ...] = ()
    indirect_proxies: tuple[str, ...] = ()
    unavailable_quantities: tuple[str, ...] = Field(min_length=1)
    interpretation_blockers: tuple[str, ...] = Field(min_length=1)


class ComponentInteraction(VehicleSystemsModel):
    interaction_id: str = Field(min_length=1)
    source_component_id: str = Field(min_length=1)
    target_component_id: str = Field(min_length=1)
    interaction_type: Literal[
        "mechanically_coupled",
        "garage_autocompensated",
        "requires_manual_recheck",
        "setup_only_relationship",
        "telemetry_observable",
        "unknown_for_build",
    ]
    description: str = Field(min_length=1)
    applicability: BuildApplicability
    source_ids: tuple[str, ...] = Field(min_length=1)
    authority: Literal["engineering_expectation_only"] = "engineering_expectation_only"

    @model_validator(mode="after")
    def interaction_is_scoped_and_sourced(self) -> "ComponentInteraction":
        if self.source_component_id == self.target_component_id:
            raise ValueError("component interactions require two components")
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("component interaction sources must be unique")
        return self


class ComponentDefinition(VehicleSystemsModel):
    component_id: str = Field(min_length=1)
    system_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    physical_location: str = Field(min_length=1)
    physical_role: str = Field(min_length=1)
    applicability: BuildApplicability
    adjustable_property_ids: tuple[str, ...] = Field(min_length=1)
    operating_phases: tuple[str, ...] = Field(min_length=1)
    speed_load_relevance: str = Field(min_length=1)
    setup_keys: tuple[str, ...] = ()
    coordinated_control_groups: tuple[tuple[str, ...], ...] = ()
    observability: ComponentObservabilityContract
    coupled_component_ids: tuple[str, ...] = ()
    compensating_control_keys: tuple[str, ...] = ()
    invariants: tuple[str, ...] = ()
    expected_state_ids: tuple[str, ...] = Field(min_length=1)
    symptom_ids: tuple[str, ...] = Field(min_length=1)
    performance_targets: tuple[str, ...] = Field(min_length=1)
    countereffects: tuple[str, ...] = Field(min_length=1)
    supporting_signatures: tuple[str, ...] = Field(min_length=1)
    contradicting_signatures: tuple[str, ...] = Field(min_length=1)
    confounders: tuple[str, ...] = Field(min_length=1)
    measurement_requirements: tuple[str, ...] = Field(min_length=1)
    rollback_conditions: tuple[str, ...] = Field(min_length=1)
    source_ids: tuple[str, ...] = Field(min_length=1)
    evidence_authority_ceiling: Literal["hypothesis_only"] = "hypothesis_only"

    @model_validator(mode="after")
    def definition_is_complete_and_non_authoritative(self) -> "ComponentDefinition":
        sequences = (
            self.adjustable_property_ids,
            self.operating_phases,
            self.setup_keys,
            self.coupled_component_ids,
            self.expected_state_ids,
            self.symptom_ids,
            self.performance_targets,
            self.source_ids,
        )
        if any(len(values) != len(set(values)) for values in sequences):
            raise ValueError("component definition identities must be unique")
        return self


class VehicleSystemsNode(VehicleSystemsModel):
    node_id: str = Field(min_length=1)
    kind: VehicleSystemsNodeKind
    label: str = Field(min_length=1)
    component_id: str | None = None
    source_ids: tuple[str, ...] = Field(min_length=1)
    authority: Literal["knowledge_only", "observation_only", "controlled_history"]


class VehicleSystemsEdge(VehicleSystemsModel):
    edge_id: str = Field(min_length=1)
    source_node_id: str = Field(min_length=1)
    target_node_id: str = Field(min_length=1)
    kind: VehicleSystemsEdgeKind
    direction: Literal["increase", "decrease", "bidirectional", "observed"] | None = None
    interaction_type: str | None = None
    source_ids: tuple[str, ...] = Field(min_length=1)
    authority: Literal["engineering_expectation_only", "observation_only", "controlled_history"]


class VehicleSystemsGraph(VehicleSystemsModel):
    schema_version: Literal["p26.vehicle-systems.v1"] = "p26.vehicle-systems.v1"
    graph_version: str = Field(min_length=1)
    components: tuple[ComponentDefinition, ...] = Field(min_length=1)
    interactions: tuple[ComponentInteraction, ...] = ()
    nodes: tuple[VehicleSystemsNode, ...] = Field(min_length=1)
    edges: tuple[VehicleSystemsEdge, ...] = Field(min_length=1)
    source_ids: tuple[str, ...] = Field(min_length=1)
    immutable: Literal[True] = True
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def graph_is_closed_and_typed(self) -> "VehicleSystemsGraph":
        component_ids = [item.component_id for item in self.components]
        node_ids = [item.node_id for item in self.nodes]
        edge_ids = [item.edge_id for item in self.edges]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("vehicle-system component identities must be unique")
        if len(node_ids) != len(set(node_ids)) or len(edge_ids) != len(set(edge_ids)):
            raise ValueError("vehicle-system graph identities must be unique")
        node_kinds = {item.node_id: item.kind for item in self.nodes}
        allowed = {
            VehicleSystemsEdgeKind.CONTROL_ADJUSTS_PROPERTY: ({VehicleSystemsNodeKind.CONTROL}, {VehicleSystemsNodeKind.COMPONENT_PROPERTY}),
            VehicleSystemsEdgeKind.PROPERTY_EXPECTED_TO_INFLUENCE_STATE: ({VehicleSystemsNodeKind.COMPONENT_PROPERTY}, {VehicleSystemsNodeKind.VEHICLE_STATE}),
            VehicleSystemsEdgeKind.STATE_MAY_PRESENT_AS_SYMPTOM: ({VehicleSystemsNodeKind.VEHICLE_STATE}, {VehicleSystemsNodeKind.SYMPTOM}),
            VehicleSystemsEdgeKind.STATE_OBSERVABLE_BY: ({VehicleSystemsNodeKind.VEHICLE_STATE}, {VehicleSystemsNodeKind.OBSERVATION}),
            VehicleSystemsEdgeKind.COMPONENT_COUPLES_WITH_COMPONENT: ({VehicleSystemsNodeKind.COMPONENT}, {VehicleSystemsNodeKind.COMPONENT}),
            VehicleSystemsEdgeKind.CONTROL_REQUIRES_INVARIANT: ({VehicleSystemsNodeKind.CONTROL}, {VehicleSystemsNodeKind.CONTEXT}),
            VehicleSystemsEdgeKind.CONTROL_HAS_COUNTEREFFECT: ({VehicleSystemsNodeKind.CONTROL}, {VehicleSystemsNodeKind.OUTCOME}),
            VehicleSystemsEdgeKind.OBSERVATION_SUPPORTS_STATE: ({VehicleSystemsNodeKind.OBSERVATION}, {VehicleSystemsNodeKind.VEHICLE_STATE}),
            VehicleSystemsEdgeKind.OBSERVATION_CONTRADICTS_STATE: ({VehicleSystemsNodeKind.OBSERVATION}, {VehicleSystemsNodeKind.VEHICLE_STATE}),
            VehicleSystemsEdgeKind.CONTROLLED_TEST_OBSERVED_RESPONSE: ({VehicleSystemsNodeKind.CONTROL}, {VehicleSystemsNodeKind.OUTCOME}),
            VehicleSystemsEdgeKind.POLICY_REJECTED_DUE_TO_COUNTEREFFECT: ({VehicleSystemsNodeKind.OUTCOME}, {VehicleSystemsNodeKind.OUTCOME}),
        }
        for edge in self.edges:
            if edge.source_node_id not in node_kinds or edge.target_node_id not in node_kinds:
                raise ValueError("vehicle-system graph edges cannot be orphaned")
            source_kinds, target_kinds = allowed[edge.kind]
            if node_kinds[edge.source_node_id] not in source_kinds or node_kinds[edge.target_node_id] not in target_kinds:
                raise ValueError(f"invalid endpoints for {edge.kind.value}")
        known_components = set(component_ids)
        if any(
            interaction.source_component_id not in known_components
            or interaction.target_component_id not in known_components
            for interaction in self.interactions
        ):
            raise ValueError("component interactions cannot reference unknown components")
        return self


class SetupExperimentFactor(VehicleSystemsModel):
    factor_id: str = Field(min_length=1)
    component_id: str = Field(min_length=1)
    physical_property_id: str = Field(min_length=1)
    primary_controls: tuple[str, ...] = Field(min_length=1)
    coordinated_controls: tuple[str, ...] = ()
    automatic_sim_compensations: tuple[str, ...] = ()
    required_manual_compensations: tuple[str, ...] = ()
    invariants_to_hold: tuple[str, ...] = Field(min_length=1)
    preconditions: tuple[str, ...] = Field(min_length=1)
    expected_component_response: tuple[str, ...] = Field(min_length=1)
    expected_vehicle_response: tuple[str, ...] = Field(min_length=1)
    countereffects: tuple[str, ...] = Field(min_length=1)
    success_metrics: tuple[str, ...] = Field(min_length=1)
    rollback_rule: str = Field(min_length=1)
    source_ids: tuple[str, ...] = Field(min_length=1)
    authority: Literal["experiment_definition_only"] = "experiment_definition_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def factor_represents_one_physical_property(self) -> "SetupExperimentFactor":
        controls = (*self.primary_controls, *self.coordinated_controls)
        if len(controls) != len(set(controls)):
            raise ValueError("experiment-factor controls must be unique")
        return self


class ComponentControlledHistory(VehicleSystemsModel):
    workflow_id: str = Field(min_length=1)
    control_key: str = Field(min_length=1)
    mechanism_state: str = Field(min_length=1)
    control_response: str = Field(min_length=1)
    policy_verdict: Literal["keep", "undo", "retest", "invalid"]
    countereffects: tuple[str, ...] = ()
    exact_context: Literal[True] = True


class ComponentAwarenessState(VehicleSystemsModel):
    component_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    lap_number: int | None = Field(default=None, ge=0)
    phase: str | None = None
    lap_pct_start: float | None = Field(default=None, ge=0.0, le=100.0)
    lap_pct_end: float | None = Field(default=None, ge=0.0, le=100.0)
    current_settings: tuple[str, ...] = ()
    current_setting_provenance: tuple[str, ...] = ()
    observability_states: tuple[ComponentObservabilityState, ...] = Field(min_length=1)
    current_response_state: Literal["observed", "not_observed", "unavailable"]
    relevance: ComponentRelevance
    supporting_artifact_ids: tuple[str, ...] = ()
    contradicting_artifact_ids: tuple[str, ...] = ()
    confounders: tuple[str, ...] = ()
    coupled_component_ids: tuple[str, ...] = ()
    controlled_history: tuple[ComponentControlledHistory, ...] = ()
    current_testability: Literal["measurement_only", "policy_blocked", "p19_authorized"]
    legal_adjacent_options: tuple[str, ...] = ()
    authority_state: Literal["knowledge_only", "observation_only", "controlled_history", "p19_authorized"]
    evidence_states: tuple[EvidenceState, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    setup_authorized: bool = False

    @model_validator(mode="after")
    def awareness_cannot_create_authority(self) -> "ComponentAwarenessState":
        if self.setup_authorized != (self.authority_state == "p19_authorized"):
            raise ValueError("component awareness may only mirror P19 setup authority")
        if self.current_testability == "p19_authorized" and not self.setup_authorized:
            raise ValueError("component testability cannot manufacture setup authority")
        if ComponentObservabilityState.UNAVAILABLE in self.observability_states and len(self.observability_states) > 1:
            raise ValueError("unavailable observability cannot be mixed with usable states")
        return self


class VehicleSystemsProjection(VehicleSystemsModel):
    schema_version: Literal["p26.component-awareness.v1"] = "p26.component-awareness.v1"
    run_id: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    leading_system: str
    next_discriminator: str
    component_states: tuple[ComponentAwarenessState, ...] = Field(min_length=1)
    experiment_factors: tuple[SetupExperimentFactor, ...] = Field(min_length=1)
    authority: Literal["p19_projection_only"] = "p19_projection_only"
    setup_authorized: bool = False

    @model_validator(mode="after")
    def projection_only_mirrors_component_authority(self) -> "VehicleSystemsProjection":
        authorized = [state for state in self.component_states if state.setup_authorized]
        if self.setup_authorized != bool(authorized) or len(authorized) > 1:
            raise ValueError("vehicle systems may mirror at most one P19-authorized component")
        return self


__all__ = [
    "BuildApplicability",
    "ComponentAwarenessState",
    "ComponentControlledHistory",
    "ComponentDefinition",
    "ComponentInteraction",
    "ComponentObservabilityContract",
    "ComponentObservabilityState",
    "ComponentRelevance",
    "SetupExperimentFactor",
    "VehicleSystemsEdge",
    "VehicleSystemsEdgeKind",
    "VehicleSystemsGraph",
    "VehicleSystemsNode",
    "VehicleSystemsNodeKind",
    "VehicleSystemsProjection",
]
