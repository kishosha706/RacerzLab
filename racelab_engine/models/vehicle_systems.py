"""Typed, non-authoritative vehicle-systems intelligence contracts.

P26 describes sourced engineering expectations and projects P19/P20 evidence onto
components.  These models deliberately cannot authorize a setup change.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.models.evidence import EvidenceState


class VehicleSystemsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class VehicleSystemsNodeKind(str, Enum):
    COMPONENT = "component"
    ENGINEERING_AREA = "engineering_area"
    CONTROL = "control"
    COMPONENT_PROPERTY = "component_property"
    VEHICLE_STATE = "vehicle_state"
    OBSERVATION = "observation"
    SYMPTOM = "symptom"
    OUTCOME = "outcome"
    CONTEXT = "context"


class VehicleSystemsEdgeKind(str, Enum):
    COMPONENT_HAS_ENGINEERING_AREA = "component_has_engineering_area"
    ENGINEERING_AREA_HAS_CONTROL = "engineering_area_has_control"
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

    @model_validator(mode="after")
    def applicability_is_closed_and_unambiguous(self) -> BuildApplicability:
        for values in (self.car_paths, self.car_versions, self.track_package_types):
            if any(not value for value in values) or len(values) != len(set(values)):
                raise ValueError("build applicability identities must be non-empty and unique")
        if (self.iracing_build_min is None) != (self.iracing_build_max is None):
            raise ValueError("build applicability requires a closed min/max range")
        if self.iracing_build_min is not None:
            build_pattern = re.compile(r"^\d{4}\.\d{2}\.\d{2}\.\d{2}$")
            if not build_pattern.fullmatch(self.iracing_build_min) or not build_pattern.fullmatch(
                self.iracing_build_max or ""
            ):
                raise ValueError("iRacing build bounds require exact four-part identities")
        return self


class VehicleSystemsRuntimeIdentity(VehicleSystemsModel):
    run_id: str = Field(min_length=1)
    car_path: str = Field(min_length=1)
    car_version: str = Field(min_length=1)
    iracing_build_version: str = Field(min_length=1)
    track_configuration_name: str = Field(min_length=1)
    source_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    telemetry_cache_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    compatibility_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    available_telemetry_channels: tuple[str, ...] = Field(min_length=1)
    source: Literal["verified_telemetry_artifact"] = "verified_telemetry_artifact"

    @model_validator(mode="after")
    def telemetry_channels_are_canonical_and_unique(self) -> VehicleSystemsRuntimeIdentity:
        if (
            any(not channel or channel.strip() != channel for channel in self.available_telemetry_channels)
            or len(self.available_telemetry_channels) != len(set(self.available_telemetry_channels))
        ):
            raise ValueError("available telemetry channel identities must be canonical and unique")
        return self


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
    def interaction_is_scoped_and_sourced(self) -> ComponentInteraction:
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
    def definition_is_complete_and_non_authoritative(self) -> ComponentDefinition:
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
    description: str | None = None
    component_id: str | None = None
    engineering_area_mode: Literal[
        "static_setup", "live_telemetry", "derived_proxy", "mixed"
    ] | None = None
    source_ids: tuple[str, ...] = Field(min_length=1)
    authority: Literal["knowledge_only", "observation_only", "controlled_history"]

    @model_validator(mode="after")
    def node_sources_are_unique(self) -> VehicleSystemsNode:
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("vehicle-system node sources must be unique")
        if (self.kind is VehicleSystemsNodeKind.ENGINEERING_AREA) != (
            self.engineering_area_mode is not None
        ):
            raise ValueError("engineering-area mode belongs only to engineering-area nodes")
        return self


class VehicleSystemsEdge(VehicleSystemsModel):
    edge_id: str = Field(min_length=1)
    source_node_id: str = Field(min_length=1)
    target_node_id: str = Field(min_length=1)
    kind: VehicleSystemsEdgeKind
    direction: Literal["increase", "decrease", "bidirectional", "observed"] | None = None
    interaction_type: str | None = None
    source_ids: tuple[str, ...] = Field(min_length=1)
    authority: Literal["engineering_expectation_only", "observation_only", "controlled_history"]

    @model_validator(mode="after")
    def edge_sources_are_unique(self) -> VehicleSystemsEdge:
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("vehicle-system edge sources must be unique")
        return self


_ALLOWED_EDGE_ENDPOINTS = {
    VehicleSystemsEdgeKind.COMPONENT_HAS_ENGINEERING_AREA: ({VehicleSystemsNodeKind.COMPONENT}, {VehicleSystemsNodeKind.ENGINEERING_AREA}),
    VehicleSystemsEdgeKind.ENGINEERING_AREA_HAS_CONTROL: ({VehicleSystemsNodeKind.ENGINEERING_AREA}, {VehicleSystemsNodeKind.CONTROL}),
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


def _validate_typed_edges(
    nodes: tuple[VehicleSystemsNode, ...],
    edges: tuple[VehicleSystemsEdge, ...],
) -> None:
    node_kinds = {item.node_id: item.kind for item in nodes}
    for edge in edges:
        if edge.source_node_id not in node_kinds or edge.target_node_id not in node_kinds:
            raise ValueError("vehicle-system graph edges cannot be orphaned")
        source_kinds, target_kinds = _ALLOWED_EDGE_ENDPOINTS[edge.kind]
        if (
            node_kinds[edge.source_node_id] not in source_kinds
            or node_kinds[edge.target_node_id] not in target_kinds
        ):
            raise ValueError(f"invalid endpoints for {edge.kind.value}")


class VehicleSystemsGraph(VehicleSystemsModel):
    schema_version: Literal["p26.vehicle-systems.v3"] = "p26.vehicle-systems.v3"
    graph_version: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    components: tuple[ComponentDefinition, ...] = Field(min_length=1)
    interactions: tuple[ComponentInteraction, ...] = ()
    nodes: tuple[VehicleSystemsNode, ...] = Field(min_length=1)
    edges: tuple[VehicleSystemsEdge, ...] = Field(min_length=1)
    source_ids: tuple[str, ...] = Field(min_length=1)
    immutable: Literal[True] = True
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def graph_is_closed_and_typed(self) -> VehicleSystemsGraph:
        component_ids = [item.component_id for item in self.components]
        node_ids = [item.node_id for item in self.nodes]
        edge_ids = [item.edge_id for item in self.edges]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("vehicle-system component identities must be unique")
        if len(node_ids) != len(set(node_ids)) or len(edge_ids) != len(set(edge_ids)):
            raise ValueError("vehicle-system graph identities must be unique")
        _validate_typed_edges(self.nodes, self.edges)
        known_components = set(component_ids)
        interaction_ids = [item.interaction_id for item in self.interactions]
        if len(interaction_ids) != len(set(interaction_ids)):
            raise ValueError("component interaction identities must be unique")
        if any(
            node.component_id is not None and node.component_id not in known_components
            for node in self.nodes
        ):
            raise ValueError("vehicle-system nodes cannot reference unknown components")
        if any(
            interaction.source_component_id not in known_components
            or interaction.target_component_id not in known_components
            for interaction in self.interactions
        ):
            raise ValueError("component interactions cannot reference unknown components")
        runtime_kinds = {
            VehicleSystemsEdgeKind.OBSERVATION_SUPPORTS_STATE,
            VehicleSystemsEdgeKind.OBSERVATION_CONTRADICTS_STATE,
            VehicleSystemsEdgeKind.CONTROLLED_TEST_OBSERVED_RESPONSE,
            VehicleSystemsEdgeKind.POLICY_REJECTED_DUE_TO_COUNTEREFFECT,
        }
        if any(edge.kind in runtime_kinds for edge in self.edges):
            raise ValueError("static vehicle-system graphs cannot contain runtime evidence edges")
        if not self.graph_version.endswith(f":{self.content_sha256[:12]}"):
            raise ValueError("vehicle-system graph version must bind its exact content hash")
        declared_sources = set(self.source_ids)
        used_sources = {
            source_id
            for item in (*self.components, *self.interactions, *self.nodes, *self.edges)
            for source_id in item.source_ids
        }
        if declared_sources != used_sources:
            raise ValueError("vehicle-system source registry must exactly cover graph provenance")
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
    def factor_represents_one_physical_property(self) -> SetupExperimentFactor:
        controls = (*self.primary_controls, *self.coordinated_controls)
        if len(controls) != len(set(controls)):
            raise ValueError("experiment-factor controls must be unique")
        return self


class ComponentControlledHistory(VehicleSystemsModel):
    workflow_id: str = Field(min_length=1)
    source_run_id: str = Field(min_length=1)
    stage_run_ids: tuple[str, ...] = ()
    eligible_lap_ids: tuple[str, ...] = ()
    control_key: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    mechanism_state: str = Field(min_length=1)
    control_response: str = Field(min_length=1)
    policy_verdict: Literal["keep", "undo", "retest", "invalid"]
    countereffects: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    diagnostic_validity: Literal["mechanism_diagnostic", "control_response_only"]
    exact_context: bool

    @model_validator(mode="after")
    def history_scope_is_unique_and_fail_closed(self) -> ComponentControlledHistory:
        for values in (self.stage_run_ids, self.eligible_lap_ids):
            if any(not value for value in values) or len(values) != len(set(values)):
                raise ValueError("controlled-history scope identities must be non-empty and unique")
        if self.policy_verdict == "invalid" and self.exact_context:
            raise ValueError("invalid controlled history cannot claim exact-context authority")
        if self.exact_context and (
            not self.stage_run_ids
            or not self.eligible_lap_ids
            or self.metric == "unscoped"
            or self.phase == "unscoped"
        ):
            raise ValueError("exact controlled history requires complete persisted experiment scope")
        return self


class QuantityObservabilityCertificate(VehicleSystemsModel):
    quantity_id: str = Field(min_length=1)
    required_channels: tuple[str, ...] = Field(min_length=1)
    available_channels: tuple[str, ...] = ()
    missing_channels: tuple[str, ...] = ()
    health_basis: Literal["qualified_producer", "manifest_presence_only", "missing"]
    minimum_coobserved_coverage: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    coobserved_coverage: float | None = Field(default=None, ge=0.0, le=1.0, allow_inf_nan=False)
    state: Literal["observed", "screenable", "unavailable"]
    producer_artifact_ids: tuple[str, ...] = ()
    supported_derived_outputs: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def quantity_truth_is_consistent(self) -> QuantityObservabilityCertificate:
        required = set(self.required_channels)
        if set(self.available_channels) | set(self.missing_channels) != required:
            raise ValueError("quantity certificate must partition every required channel")
        if set(self.available_channels) & set(self.missing_channels):
            raise ValueError("quantity certificate channel partitions cannot overlap")
        if self.state == "observed" and (
            self.health_basis != "qualified_producer"
            or self.coobserved_coverage is None
            or self.coobserved_coverage < self.minimum_coobserved_coverage
            or not self.producer_artifact_ids
        ):
            raise ValueError("observed quantities require qualified co-observed producer evidence")
        if self.state == "screenable" and (
            self.missing_channels or self.health_basis != "manifest_presence_only"
        ):
            raise ValueError("screenable quantities require manifest presence without qualified evidence")
        if self.state == "unavailable" and not self.blocker_reasons:
            raise ValueError("unavailable quantities require exact blockers")
        return self


class ComponentObservationScope(VehicleSystemsModel):
    artifact_id: str = Field(min_length=1)
    observation_id: str = Field(min_length=1)
    lap_number: int = Field(ge=0)
    phase: str = Field(min_length=1)
    lap_pct_start: float = Field(ge=0.0, le=100.0)
    lap_pct_end: float = Field(ge=0.0, le=100.0)

    @model_validator(mode="after")
    def physical_window_is_ordered(self) -> ComponentObservationScope:
        if self.lap_pct_end < self.lap_pct_start:
            raise ValueError("component observation windows must be ordered")
        return self


class ComponentAwarenessState(VehicleSystemsModel):
    component_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    observation_scopes: tuple[ComponentObservationScope, ...] = ()
    current_settings: tuple[str, ...] = ()
    present_setting_keys: tuple[str, ...] = ()
    missing_setting_keys: tuple[str, ...] = ()
    current_setting_provenance: tuple[str, ...] = ()
    observability_states: tuple[ComponentObservabilityState, ...] = Field(min_length=1)
    quantity_observability: tuple[QuantityObservabilityCertificate, ...] = ()
    current_response_state: Literal["observed", "not_observed", "unavailable"]
    relevance: ComponentRelevance
    supporting_artifact_ids: tuple[str, ...] = ()
    supporting_citation_ids: tuple[str, ...] = ()
    contradicting_citation_ids: tuple[str, ...] = ()
    supporting_cause_ids: tuple[str, ...] = ()
    contradicting_cause_ids: tuple[str, ...] = ()
    confounders: tuple[str, ...] = ()
    unavailable_quantities: tuple[str, ...] = Field(default=("not declared",), min_length=1)
    measurement_requirements: tuple[str, ...] = Field(default=("exact evidence required",), min_length=1)
    coupled_component_ids: tuple[str, ...] = ()
    interaction_summaries: tuple[str, ...] = ()
    controlled_history: tuple[ComponentControlledHistory, ...] = ()
    blocked_control_keys: tuple[str, ...] = ()
    testable_control_keys: tuple[str, ...] = ()
    authorized_control_key: str | None = None
    available_live_channel_ids: tuple[str, ...] = ()
    live_response_blocker_reasons: tuple[str, ...] = ()
    next_discriminator: str = Field(min_length=1)
    current_testability: Literal["measurement_only", "policy_blocked", "p19_authorized"]
    authority_state: Literal["knowledge_only", "observation_only", "controlled_history", "p19_authorized"]
    evidence_states: tuple[EvidenceState, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    setup_authorized: bool = False

    @model_validator(mode="after")
    def awareness_cannot_create_authority(self) -> ComponentAwarenessState:
        if self.setup_authorized != (self.authority_state == "p19_authorized"):
            raise ValueError("component awareness may only mirror P19 setup authority")
        if self.current_testability == "p19_authorized" and not self.setup_authorized:
            raise ValueError("component testability cannot manufacture setup authority")
        if ComponentObservabilityState.UNAVAILABLE in self.observability_states and len(self.observability_states) > 1:
            raise ValueError("unavailable observability cannot be mixed with usable states")
        identity_sequences = (
            self.supporting_artifact_ids,
            self.supporting_citation_ids,
            self.contradicting_citation_ids,
            self.supporting_cause_ids,
            self.contradicting_cause_ids,
            self.coupled_component_ids,
            self.blocked_control_keys,
            self.testable_control_keys,
            self.available_live_channel_ids,
        )
        if any(len(values) != len(set(values)) for values in identity_sequences):
            raise ValueError("component-awareness evidence identities must be unique")
        response_observed = self.current_response_state == "observed"
        if response_observed != (
            ComponentObservabilityState.CURRENT_RESPONSE_OBSERVED
            in self.observability_states
        ):
            raise ValueError("observed component response requires matching observability state")
        if response_observed and not self.supporting_artifact_ids:
            raise ValueError("observed component response requires a producer artifact")
        if response_observed != bool(self.observation_scopes):
            raise ValueError("observed component response requires every producer scope")
        scope_ids = [scope.observation_id for scope in self.observation_scopes]
        if len(scope_ids) != len(set(scope_ids)):
            raise ValueError("component observation scope identities must be unique")
        if {scope.artifact_id for scope in self.observation_scopes} != set(
            self.supporting_artifact_ids
        ):
            raise ValueError("component observation scopes must cover supporting artifacts")
        if self.current_settings and not self.current_setting_provenance:
            raise ValueError("captured component settings require setup provenance")
        response_known = any(
            history.exact_context
            and history.control_response in {"matched", "missed"}
            and history.policy_verdict != "invalid"
            for history in self.controlled_history
        )
        if response_known != (
            ComponentObservabilityState.CONTROLLED_RESPONSE_KNOWN
            in self.observability_states
        ):
            raise ValueError("controlled response observability must match usable history")
        policy_known = any(
            history.exact_context
            and history.policy_verdict in {"keep", "undo", "retest"}
            for history in self.controlled_history
        )
        if policy_known != (
            ComponentObservabilityState.EXACT_CONTEXT_POLICY_KNOWN
            in self.observability_states
        ):
            raise ValueError("controlled policy observability must match usable history")
        live_observable = ComponentObservabilityState.LIVE_RESPONSE_OBSERVABLE in self.observability_states
        if self.quantity_observability:
            if live_observable != any(item.state == "observed" for item in self.quantity_observability):
                raise ValueError("live observability requires a qualified quantity certificate")
            certificate_channels = {
                channel for item in self.quantity_observability for channel in item.available_channels
            }
            if certificate_channels != set(self.available_live_channel_ids):
                raise ValueError("available live channels must match quantity certificates")
        elif live_observable != bool(self.available_live_channel_ids):
            raise ValueError("legacy live observability must be backed by current manifest channels")
        if set(self.blocked_control_keys) & set(self.testable_control_keys):
            raise ValueError("one control cannot be both blocked and testable")
        if self.authorized_control_key is not None:
            if not self.setup_authorized or self.authorized_control_key not in self.testable_control_keys:
                raise ValueError("P19 authorization must name one currently testable control")
        elif self.setup_authorized:
            raise ValueError("P19-authorized components require the exact control identity")
        return self


class VehicleSystemsRuntimeGraph(VehicleSystemsModel):
    schema_version: Literal["p26.runtime-graph.v3"] = "p26.runtime-graph.v3"
    reasoning_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    nodes: tuple[VehicleSystemsNode, ...] = ()
    edges: tuple[VehicleSystemsEdge, ...] = ()
    authority: Literal["observation_and_controlled_history_only"] = (
        "observation_and_controlled_history_only"
    )
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def runtime_graph_is_closed_and_non_authoritative(self) -> VehicleSystemsRuntimeGraph:
        node_ids = [item.node_id for item in self.nodes]
        edge_ids = [item.edge_id for item in self.edges]
        if len(node_ids) != len(set(node_ids)) or len(edge_ids) != len(set(edge_ids)):
            raise ValueError("runtime vehicle-system graph identities must be unique")
        _validate_typed_edges(self.nodes, self.edges)
        runtime_kinds = {
            VehicleSystemsEdgeKind.OBSERVATION_SUPPORTS_STATE,
            VehicleSystemsEdgeKind.OBSERVATION_CONTRADICTS_STATE,
            VehicleSystemsEdgeKind.CONTROLLED_TEST_OBSERVED_RESPONSE,
            VehicleSystemsEdgeKind.POLICY_REJECTED_DUE_TO_COUNTEREFFECT,
        }
        if any(edge.kind not in runtime_kinds for edge in self.edges):
            raise ValueError("runtime vehicle-system graph contains a static expectation edge")
        if any(node.authority == "knowledge_only" for node in self.nodes) or any(
            edge.authority == "engineering_expectation_only" for edge in self.edges
        ):
            raise ValueError("runtime vehicle-system graph cannot manufacture knowledge authority")
        return self


class VehicleSystemsProjection(VehicleSystemsModel):
    schema_version: Literal["p26.component-awareness.v4"] = "p26.component-awareness.v4"
    run_id: str = Field(min_length=1)
    session_id: str | None = None
    graph_version: str = Field(min_length=1)
    knowledge_graph_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reasoning_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    setup_id: str | None = None
    setup_snapshot_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    runtime_identity: VehicleSystemsRuntimeIdentity
    leading_system: str
    leading_component_ids: tuple[str, ...] = ()
    next_discriminator: str
    strongest_contradiction: str
    knowledge_debt: tuple[str, ...] = ()
    component_states: tuple[ComponentAwarenessState, ...] = Field(min_length=1)
    experiment_factors: tuple[SetupExperimentFactor, ...] = Field(min_length=1)
    runtime_graph: VehicleSystemsRuntimeGraph
    authority: Literal["p19_projection_only"] = "p19_projection_only"
    setup_authorized: bool = False

    @model_validator(mode="after")
    def projection_only_mirrors_component_authority(self) -> VehicleSystemsProjection:
        authorized = [state for state in self.component_states if state.setup_authorized]
        if self.setup_authorized != bool(authorized) or len(authorized) > 1:
            raise ValueError("vehicle systems may mirror at most one P19-authorized component")
        if self.runtime_identity.run_id != self.run_id:
            raise ValueError("vehicle-system runtime identity must match projection run")
        if (self.setup_id is None) != (self.setup_snapshot_sha256 is None):
            raise ValueError("vehicle-system setup identity and hash must be supplied together")
        state_ids = [state.component_id for state in self.component_states]
        if len(state_ids) != len(set(state_ids)):
            raise ValueError("vehicle-system component states must be unique")
        if any(state.run_id != self.run_id for state in self.component_states):
            raise ValueError("vehicle-system component states must match projection run")
        if not set(self.leading_component_ids) <= set(state_ids):
            raise ValueError("leading vehicle-system components must exist in the projection")
        if self.reasoning_snapshot_sha256 != self.runtime_graph.reasoning_snapshot_sha256:
            raise ValueError("vehicle-system runtime graph must match the reasoning snapshot")
        if not self.graph_version.endswith(f":{self.knowledge_graph_sha256[:12]}"):
            raise ValueError("vehicle-system graph version must bind its exact knowledge content")
        if any(factor.component_id not in set(state_ids) for factor in self.experiment_factors):
            raise ValueError("vehicle-system experiment factors must reference known components")
        return self


class ComponentInspectionResponse(VehicleSystemsModel):
    run_id: str = Field(min_length=1)
    session_id: str | None = None
    graph_version: str = Field(min_length=1)
    knowledge_graph_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reasoning_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    setup_id: str | None = None
    setup_snapshot_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    runtime_identity: VehicleSystemsRuntimeIdentity
    component_id: str = Field(min_length=1)
    definition: ComponentDefinition
    state: ComponentAwarenessState
    interactions: tuple[ComponentInteraction, ...] = ()
    controls: tuple[str, ...] = ()
    authority: Literal["p19_projection_only"] = "p19_projection_only"

    @model_validator(mode="after")
    def inspection_scope_matches_definition(self) -> ComponentInspectionResponse:
        if self.runtime_identity.run_id != self.run_id or self.state.run_id != self.run_id:
            raise ValueError("component inspection evidence must match its run")
        if self.component_id != self.state.component_id or self.component_id != self.definition.component_id:
            raise ValueError("component inspection state must match its definition")
        if (self.setup_id is None) != (self.setup_snapshot_sha256 is None):
            raise ValueError("component inspection setup identity and hash must be paired")
        if not self.graph_version.endswith(f":{self.knowledge_graph_sha256[:12]}"):
            raise ValueError("component inspection must bind its exact knowledge graph")
        if tuple(self.controls) != self.definition.setup_keys:
            raise ValueError("component inspection controls must match its definition")
        return self


class ControlMechanismTraceResponse(VehicleSystemsModel):
    run_id: str = Field(min_length=1)
    control_key: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    graph_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_identity: VehicleSystemsRuntimeIdentity
    authority: Literal["engineering_expectation_only"] = "engineering_expectation_only"
    setup_authorized: Literal[False] = False
    nodes: tuple[VehicleSystemsNode, ...] = Field(min_length=1)
    edges: tuple[VehicleSystemsEdge, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def trace_is_static_and_control_scoped(self) -> ControlMechanismTraceResponse:
        if self.runtime_identity.run_id != self.run_id:
            raise ValueError("control trace runtime identity must match its run")
        if not self.graph_version.endswith(f":{self.graph_content_sha256[:12]}"):
            raise ValueError("control trace must bind its exact knowledge graph")
        if not any(edge.source_node_id == f"control:{self.control_key}" for edge in self.edges):
            raise ValueError("control trace must start from its requested control")
        if any(edge.authority != "engineering_expectation_only" for edge in self.edges):
            raise ValueError("control traces may contain engineering expectations only")
        if any(node.authority != "knowledge_only" for node in self.nodes):
            raise ValueError("control traces may contain knowledge nodes only")
        _validate_typed_edges(self.nodes, self.edges)
        return self


__all__ = [
    "BuildApplicability",
    "ComponentAwarenessState",
    "ComponentControlledHistory",
    "ComponentDefinition",
    "ComponentInspectionResponse",
    "ComponentInteraction",
    "ComponentObservabilityContract",
    "ComponentObservabilityState",
    "ComponentObservationScope",
    "QuantityObservabilityCertificate",
    "ComponentRelevance",
    "ControlMechanismTraceResponse",
    "SetupExperimentFactor",
    "VehicleSystemsEdge",
    "VehicleSystemsEdgeKind",
    "VehicleSystemsGraph",
    "VehicleSystemsNode",
    "VehicleSystemsNodeKind",
    "VehicleSystemsProjection",
    "VehicleSystemsRuntimeGraph",
    "VehicleSystemsRuntimeIdentity",
]
