"""P35 typed Next Gen oval vehicle-dynamics knowledge contracts.

The static graph describes reviewed physical relationships and the evidence that
would separate candidate mechanisms.  It is not a telemetry observer, a causal
ranker, or a setup authority.  Runtime assessments may cite existing P20/P32
observations, but P19 remains the sole terminal setup authority.
"""

from __future__ import annotations

import re
from collections import Counter
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.performance_intelligence import TimeOriginKind


_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_ID_PATTERN = r"^[a-z0-9][a-z0-9_.:-]*$"


class VehicleDynamicsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class DynamicResponseRegime(str, Enum):
    TRANSIENT = "transient"
    STEADY_STATE = "steady_state"
    BOTH = "both"


class VehicleDynamicsPhase(str, Enum):
    STRAIGHT = "straight"
    LIFT = "lift"
    BRAKE = "brake"
    TURN_IN = "turn_in"
    ENTRY = "entry"
    CENTER = "center"
    THROTTLE_PICKUP = "throttle_pickup"
    EXIT = "exit"
    FOLLOWING_STRAIGHT = "following_straight"
    TRANSITION = "transition"


class QuantitySemantics(str, Enum):
    MEASURED_NUMERIC = "measured_numeric"
    DERIVED_NUMERIC = "derived_numeric"
    RELATIVE_STATE = "relative_state"
    QUALITATIVE_PROXY = "qualitative_proxy"
    UNAVAILABLE = "unavailable"


class TireDemandLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    INCREASING = "increasing"
    DECREASING = "decreasing"
    THERMAL_MIGRATION = "thermal_migration"
    PRESSURE_MIGRATION = "pressure_migration"
    POSSIBLE_COMBINED_DEMAND_LIMITATION = "possible_combined_demand_limitation"


class VehicleDynamicsNodeKind(str, Enum):
    QUANTITY = "quantity"
    MECHANISM = "mechanism"
    LOAD_PATH = "load_path"
    TIRE_DEMAND_STATE = "tire_demand_state"
    CHASSIS_RESPONSE_STATE = "chassis_response_state"
    TRANSIENT_RESPONSE = "transient_response"
    STEADY_STATE_RESPONSE = "steady_state_response"
    COMPONENT_INFLUENCE = "component_influence"
    OBSERVATION_CONTRACT = "observation_contract"
    CONTEXT = "context"
    PHASE = "phase"
    COMPONENT_FAMILY = "component_family"
    PERFORMANCE_DIMENSION = "performance_dimension"


class VehicleDynamicsEdgeKind(str, Enum):
    PHYSICALLY_INFLUENCES = "physically_influences"
    COUPLES_WITH = "couples_with"
    CHANGES_DEMAND_ON = "changes_demand_on"
    EXPECTED_TO_AFFECT = "expected_to_affect"
    REQUIRES_MEASUREMENT_OF = "requires_measurement_of"
    CONFOUNDED_BY = "confounded_by"


class KnowledgeSourceTier(str, Enum):
    OFFICIAL_IRACING = "official_iracing_documentation"
    OFFICIAL_NASCAR = "official_nascar_technical_documentation"
    PEER_REVIEWED = "peer_reviewed_vehicle_dynamics_research"
    REVIEWED_SYNTHESIS = "reviewed_racerzlab_engineering_synthesis"


class DynamicsChainStageKind(str, Enum):
    DRIVER_INPUT = "driver_input"
    VEHICLE_DEMAND = "vehicle_demand"
    VEHICLE_RESPONSE = "vehicle_response"
    TIRE_PLATFORM_STATE = "tire_platform_state"
    TIME_CONSEQUENCE = "time_consequence"


class VehicleDynamicsInspectionToolId(str, Enum):
    INSPECT_TIRE_DEMAND = "inspect_tire_demand"
    INSPECT_LOAD_TRANSFER = "inspect_load_transfer"
    INSPECT_ROLL_RESPONSE = "inspect_roll_response"
    INSPECT_PITCH_RESPONSE = "inspect_pitch_response"
    INSPECT_PLATFORM_STATE = "inspect_platform_state"
    INSPECT_TRANSIENT_SETTLING = "inspect_transient_settling"
    INSPECT_STEADY_STATE_BALANCE = "inspect_steady_state_balance"
    INSPECT_BRAKE_VEHICLE_RESPONSE = "inspect_brake_vehicle_response"
    INSPECT_POWER_ON_RESPONSE = "inspect_power_on_response"
    INSPECT_DIFFERENTIAL_RESPONSE = "inspect_differential_response"
    INSPECT_ALIGNMENT_RESPONSE = "inspect_alignment_response"
    INSPECT_TIRE_STATE_MIGRATION = "inspect_tire_state_migration"
    INSPECT_TRAFFIC_PLATFORM_RESPONSE = "inspect_traffic_platform_response"
    INSPECT_GEAR_ACCELERATION_RESPONSE = "inspect_gear_acceleration_response"


class VehicleDynamicsApplicability(VehicleDynamicsModel):
    applicability_id: str = Field(pattern=_ID_PATTERN)
    car_family: Literal["nascar_cup_next_gen"] = "nascar_cup_next_gen"
    car_paths: tuple[str, ...] = Field(min_length=1)
    car_version_min: str = Field(min_length=1)
    car_version_max: str = Field(min_length=1)
    iracing_build_min: str = Field(pattern=r"^\d{4}\.\d{2}\.\d{2}\.\d{2}$")
    iracing_build_max: str = Field(pattern=r"^\d{4}\.\d{2}\.\d{2}\.\d{2}$")
    track_packages: tuple[
        Literal["oval", "short_oval", "intermediate_oval", "superspeedway_oval"], ...
    ] = Field(min_length=1)
    knowledge_version: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    review_required_after_build: Literal[True] = True

    @model_validator(mode="after")
    def applicability_is_closed(self) -> VehicleDynamicsApplicability:
        for values, label in (
            (self.car_paths, "car paths"),
            (self.track_packages, "track packages"),
        ):
            if len(values) != len(set(values)) or any(not value for value in values):
                raise ValueError(f"vehicle-dynamics {label} must be canonical and unique")
        if _version_key(self.car_version_max) < _version_key(self.car_version_min):
            raise ValueError("vehicle-dynamics car-version range is reversed")
        if _version_key(self.iracing_build_max) < _version_key(self.iracing_build_min):
            raise ValueError("vehicle-dynamics iRacing build range is reversed")
        return self

    def covers(
        self,
        *,
        car_path: str,
        car_version: str,
        iracing_build_version: str,
        track_package: str,
    ) -> bool:
        return (
            car_path in self.car_paths
            and _version_key(self.car_version_min)
            <= _version_key(car_version)
            <= _version_key(self.car_version_max)
            and _version_key(self.iracing_build_min)
            <= _version_key(iracing_build_version)
            <= _version_key(self.iracing_build_max)
            and track_package in self.track_packages
        )


class VehicleDynamicsSource(VehicleDynamicsModel):
    source_id: str = Field(pattern=_ID_PATTERN)
    tier: KnowledgeSourceTier
    publisher: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    publication_date: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"
    )
    reviewed_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    source_uri: str = Field(pattern=r"^(?:https://|repo://)")
    local_digest: str = Field(pattern=_SHA256_PATTERN)
    review_status: Literal["reviewed"] = "reviewed"


class ExternalIdentityNamespace(VehicleDynamicsModel):
    namespace_id: Literal[
        "telemetry_channel",
        "p20_mechanism",
        "p26_component_family",
        "p32_performance_mechanism",
    ]
    field_names: tuple[str, ...] = Field(min_length=1)
    owner: str = Field(min_length=1)
    registry_mode: Literal["runtime_manifest_bound", "closed_registry"]
    allowed_ids: tuple[str, ...] = ()
    policy: str = Field(min_length=1)

    @model_validator(mode="after")
    def external_namespace_is_explicit(self) -> ExternalIdentityNamespace:
        if len(self.field_names) != len(set(self.field_names)):
            raise ValueError("external namespace fields must be unique")
        if self.registry_mode == "closed_registry" and not self.allowed_ids:
            raise ValueError("closed external namespaces require allowed identities")
        if self.registry_mode == "runtime_manifest_bound" and self.allowed_ids:
            raise ValueError("runtime-manifest namespaces cannot embed a stale registry")
        if len(self.allowed_ids) != len(set(self.allowed_ids)):
            raise ValueError("external namespace identities must be unique")
        return self


class VehicleDynamicDefinition(VehicleDynamicsModel):
    definition_id: str = Field(pattern=_ID_PATTERN)
    label: str = Field(min_length=1)
    physical_meaning: str = Field(min_length=1)
    units: str | None = None
    created_by_ids: tuple[str, ...] = Field(min_length=1)
    affected_by_ids: tuple[str, ...] = Field(min_length=1)
    affects_ids: tuple[str, ...] = Field(min_length=1)
    required_measured_channels: tuple[str, ...] = ()
    derived_quantity_ids: tuple[str, ...] = ()
    valid_proxy_ids: tuple[str, ...] = ()
    unavailable_quantity_ids: tuple[str, ...] = Field(min_length=1)
    driver_confounders: tuple[str, ...] = Field(min_length=1)
    track_context_confounders: tuple[str, ...] = Field(min_length=1)
    relevant_phases: tuple[VehicleDynamicsPhase, ...] = Field(min_length=1)
    relevant_component_ids: tuple[str, ...] = Field(min_length=1)
    source_ids: tuple[str, ...] = Field(min_length=1)
    applicability: VehicleDynamicsApplicability
    forbidden_inferences: tuple[str, ...] = Field(min_length=1)
    authority_ceiling: Literal["knowledge_only"] = "knowledge_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def definition_is_canonical(self) -> VehicleDynamicDefinition:
        identity_sequences = (
            self.created_by_ids,
            self.affected_by_ids,
            self.affects_ids,
            self.required_measured_channels,
            self.derived_quantity_ids,
            self.valid_proxy_ids,
            self.unavailable_quantity_ids,
            self.driver_confounders,
            self.track_context_confounders,
            self.relevant_phases,
            self.relevant_component_ids,
            self.source_ids,
            self.forbidden_inferences,
        )
        if any(len(values) != len(set(values)) for values in identity_sequences):
            raise ValueError("vehicle-dynamics definition identities must be unique")
        return self


class VehicleDynamicQuantity(VehicleDynamicDefinition):
    semantics: QuantitySemantics
    runtime_publishable: bool
    exact_value_authorized: bool
    manifest_validity_required_channels: tuple[str, ...] = ()

    @model_validator(mode="after")
    def unavailable_quantity_cannot_publish(self) -> VehicleDynamicQuantity:
        if self.semantics is QuantitySemantics.UNAVAILABLE and (
            self.runtime_publishable or self.exact_value_authorized
        ):
            raise ValueError("unavailable vehicle quantities cannot publish runtime values")
        if self.semantics in {
            QuantitySemantics.RELATIVE_STATE,
            QuantitySemantics.QUALITATIVE_PROXY,
        } and self.exact_value_authorized:
            raise ValueError("relative/proxy quantities cannot authorize exact values")
        if (
            len(self.manifest_validity_required_channels)
            != len(set(self.manifest_validity_required_channels))
            or not set(self.manifest_validity_required_channels)
            <= set(self.required_measured_channels)
        ):
            raise ValueError(
                "manifest-validity channels must be unique required measurements"
            )
        return self


class VehicleDynamicMechanism(VehicleDynamicDefinition):
    response_regime: DynamicResponseRegime
    inspection_tool_id: VehicleDynamicsInspectionToolId
    allowed_time_origin_kinds: tuple[TimeOriginKind, ...] = Field(min_length=1)
    support_contract_ids: tuple[str, ...] = Field(min_length=1)
    contradiction_contract_ids: tuple[str, ...] = Field(min_length=1)
    discriminator_contract_ids: tuple[str, ...] = Field(min_length=1)
    p20_mechanism_ids: tuple[str, ...] = Field(min_length=1)
    p26_component_family_ids: tuple[str, ...] = Field(min_length=1)
    p32_performance_mechanism_ids: tuple[str, ...] = Field(min_length=1)
    expected_countereffects: tuple[str, ...] = Field(min_length=1)
    current_cause_authorized: Literal[False] = False
    component_cause_authorized: Literal[False] = False

    @model_validator(mode="after")
    def typed_bridge_ids_are_unique(self) -> VehicleDynamicMechanism:
        for values in (
            self.allowed_time_origin_kinds,
            self.support_contract_ids,
            self.contradiction_contract_ids,
            self.discriminator_contract_ids,
            self.p20_mechanism_ids,
            self.p26_component_family_ids,
            self.p32_performance_mechanism_ids,
        ):
            if len(values) != len(set(values)):
                raise ValueError("mechanism bridge identities must be unique")
        return self


class LoadPath(VehicleDynamicDefinition):
    sequence_index: int = Field(ge=0)
    input_quantity_ids: tuple[str, ...] = Field(min_length=1)
    output_quantity_ids: tuple[str, ...] = Field(min_length=1)
    demand_state_ids: tuple[str, ...] = Field(min_length=1)
    prior_load_path_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    next_load_path_id: str | None = Field(default=None, pattern=_ID_PATTERN)


class TireDemandState(VehicleDynamicDefinition):
    demand_level: TireDemandLevel
    demand_axes: tuple[
        Literal["vertical", "lateral", "longitudinal", "combined"], ...
    ] = Field(min_length=1)
    response_regime: DynamicResponseRegime
    exact_tire_force_authorized: Literal[False] = False
    exact_grip_limit_authorized: Literal[False] = False

    @model_validator(mode="after")
    def demand_axes_are_unique(self) -> TireDemandState:
        if len(self.demand_axes) != len(set(self.demand_axes)):
            raise ValueError("tire-demand axes must be unique")
        return self


class ChassisResponseState(VehicleDynamicDefinition):
    response_regime: DynamicResponseRegime
    response_axes: tuple[
        Literal["roll", "pitch", "yaw", "heave", "steering", "acceleration", "stability"],
        ...,
    ] = Field(min_length=1)


class TransientResponse(VehicleDynamicDefinition):
    response_regime: Literal[DynamicResponseRegime.TRANSIENT] = DynamicResponseRegime.TRANSIENT
    settling_evidence_required: Literal[True] = True


class SteadyStateResponse(VehicleDynamicDefinition):
    response_regime: Literal[DynamicResponseRegime.STEADY_STATE] = (
        DynamicResponseRegime.STEADY_STATE
    )
    sustained_window_required: Literal[True] = True


class ComponentInfluence(VehicleDynamicDefinition):
    component_id: str = Field(pattern=_ID_PATTERN)
    mechanism_ids: tuple[str, ...] = Field(min_length=1)
    countereffect_mechanism_ids: tuple[str, ...] = Field(min_length=1)
    influence_regime: DynamicResponseRegime
    candidate_mapping_only: Literal[True] = True
    exact_setup_value_fields: tuple[()] = ()


class MechanismInteraction(VehicleDynamicDefinition):
    source_mechanism_id: str = Field(pattern=_ID_PATTERN)
    target_mechanism_id: str = Field(pattern=_ID_PATTERN)
    edge_kind: Literal[
        VehicleDynamicsEdgeKind.PHYSICALLY_INFLUENCES,
        VehicleDynamicsEdgeKind.COUPLES_WITH,
        VehicleDynamicsEdgeKind.CHANGES_DEMAND_ON,
        VehicleDynamicsEdgeKind.EXPECTED_TO_AFFECT,
    ]
    interaction_regime: DynamicResponseRegime
    tradeoffs: tuple[str, ...] = Field(min_length=1)
    runtime_cause_edge_authorized: Literal[False] = False

    @model_validator(mode="after")
    def interaction_requires_two_mechanisms(self) -> MechanismInteraction:
        if self.source_mechanism_id == self.target_mechanism_id:
            raise ValueError("mechanism interactions require two different mechanisms")
        return self


class DynamicObservationContract(VehicleDynamicDefinition):
    inspection_tool_id: VehicleDynamicsInspectionToolId
    supports_mechanism_ids: tuple[str, ...] = ()
    contradicts_mechanism_ids: tuple[str, ...] = ()
    discriminates_mechanism_ids: tuple[str, ...] = Field(min_length=1)
    support_requirements: tuple[str, ...] = Field(min_length=1)
    contradiction_requirements: tuple[str, ...] = Field(min_length=1)
    discriminator_requirements: tuple[str, ...] = Field(min_length=1)
    required_evidence_layers: tuple[
        Literal[
            "driver_input",
            "vehicle_demand",
            "vehicle_response",
            "tire_platform_state",
            "time_consequence",
        ],
        ...,
    ] = Field(min_length=1)
    traffic_clean_required: bool = False
    transient_evidence_required: bool = False
    steady_state_evidence_required: bool = False
    p20_observation_remains_distinct: Literal[True] = True
    current_observation_authorized: Literal[False] = False

    @model_validator(mode="after")
    def contract_separates_candidates(self) -> DynamicObservationContract:
        if not (
            self.supports_mechanism_ids
            or self.contradicts_mechanism_ids
            or len(self.discriminates_mechanism_ids) > 1
        ):
            raise ValueError("observation contracts must separate candidate mechanisms")
        return self


class OvalTrackDemandModel(VehicleDynamicDefinition):
    geometry_inputs: tuple[
        Literal[
            "banking",
            "corner_radius",
            "curvature",
            "speed",
            "line",
            "transition_severity",
            "straight_length",
            "corner_duration",
        ],
        ...,
    ] = Field(min_length=8, max_length=8)
    empirical_outputs: tuple[str, ...] = Field(min_length=1)
    run_specific: Literal[True] = True
    exact_wheel_load_authorized: Literal[False] = False
    exact_tire_force_authorized: Literal[False] = False


class StaticLoadDistributionKnowledge(VehicleDynamicDefinition):
    static_quantity_ids: tuple[str, ...] = Field(min_length=1)
    prohibited_dynamic_equivalents: tuple[str, ...] = Field(min_length=1)
    universal_balance_direction_authorized: Literal[False] = False


class TireStateEvolution(VehicleDynamicDefinition):
    evolution_axes: tuple[
        Literal[
            "pressure_rise",
            "temperature_change",
            "wear",
            "slip_exposure",
            "steering_demand_growth",
            "balance_migration",
            "lap_time_falloff",
        ],
        ...,
    ] = Field(min_length=7, max_length=7)
    exact_context_required: Literal[True] = True
    universal_optimum_authorized: Literal[False] = False
    exact_grip_loss_authorized: Literal[False] = False


class DriverVehicleResponseChain(VehicleDynamicDefinition):
    driver_input_id: str = Field(pattern=_ID_PATTERN)
    vehicle_demand_id: str = Field(pattern=_ID_PATTERN)
    vehicle_response_id: str = Field(pattern=_ID_PATTERN)
    tire_platform_state_id: str = Field(pattern=_ID_PATTERN)
    performance_dimension_id: str = Field(pattern=_ID_PATTERN)
    p32_driver_vehicle_separation_required: Literal[True] = True


class ForbiddenVehicleControl(VehicleDynamicsModel):
    control_id: Literal["track_bar", "truck_arm_mount"]
    physical_reason: str = Field(min_length=1)
    source_ids: tuple[str, ...] = Field(min_length=1)
    applicability: VehicleDynamicsApplicability
    live_control_available: Literal[False] = False
    mechanism_candidate_authorized: Literal[False] = False
    setup_authorized: Literal[False] = False


class VehicleDynamicsGraphNode(VehicleDynamicsModel):
    node_id: str = Field(pattern=_ID_PATTERN)
    kind: VehicleDynamicsNodeKind
    label: str = Field(min_length=1)
    definition_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    source_ids: tuple[str, ...] = Field(min_length=1)
    authority: Literal["knowledge_only"] = "knowledge_only"


class VehicleDynamicsGraphEdge(VehicleDynamicsModel):
    edge_id: str = Field(pattern=_ID_PATTERN)
    source_node_id: str = Field(pattern=_ID_PATTERN)
    target_node_id: str = Field(pattern=_ID_PATTERN)
    kind: VehicleDynamicsEdgeKind
    source_ids: tuple[str, ...] = Field(min_length=1)
    authority: Literal["engineering_expectation_only"] = "engineering_expectation_only"
    runtime_cause_authorized: Literal[False] = False


class VehicleDynamicsKnowledgeGraph(VehicleDynamicsModel):
    schema_version: Literal["p35.vehicle-dynamics-knowledge.v1"] = (
        "p35.vehicle-dynamics-knowledge.v1"
    )
    graph_id: str = Field(pattern=r"^p35vdg_[0-9a-f]{24}$")
    graph_version: str = Field(pattern=r"^2026\.08\.next-gen-oval\.v1:[0-9a-f]{12}$")
    knowledge_version: str = Field(min_length=1)
    content_sha256: str = Field(pattern=_SHA256_PATTERN)
    applicability: VehicleDynamicsApplicability
    sources: tuple[VehicleDynamicsSource, ...] = Field(min_length=1)
    external_identity_namespaces: tuple[ExternalIdentityNamespace, ...] = Field(
        min_length=4, max_length=4
    )
    quantities: tuple[VehicleDynamicQuantity, ...] = Field(min_length=1)
    mechanisms: tuple[VehicleDynamicMechanism, ...] = Field(min_length=14)
    load_paths: tuple[LoadPath, ...] = Field(min_length=8)
    tire_demand_states: tuple[TireDemandState, ...] = Field(min_length=1)
    chassis_response_states: tuple[ChassisResponseState, ...] = Field(min_length=1)
    transient_responses: tuple[TransientResponse, ...] = Field(min_length=1)
    steady_state_responses: tuple[SteadyStateResponse, ...] = Field(min_length=1)
    component_influences: tuple[ComponentInfluence, ...] = Field(min_length=1)
    mechanism_interactions: tuple[MechanismInteraction, ...] = Field(min_length=1)
    observation_contracts: tuple[DynamicObservationContract, ...] = Field(min_length=1)
    oval_track_demand_model: OvalTrackDemandModel
    static_load_distribution: StaticLoadDistributionKnowledge
    tire_state_evolution: TireStateEvolution
    driver_response_chains: tuple[DriverVehicleResponseChain, ...] = Field(min_length=3)
    forbidden_controls: tuple[ForbiddenVehicleControl, ...] = Field(min_length=2, max_length=2)
    nodes: tuple[VehicleDynamicsGraphNode, ...] = Field(min_length=1)
    edges: tuple[VehicleDynamicsGraphEdge, ...] = Field(min_length=1)
    unavailable_quantity_ids: tuple[str, ...] = Field(min_length=1)
    authority: Literal["candidate_mechanism_knowledge_only"] = (
        "candidate_mechanism_knowledge_only"
    )
    setup_authorized: Literal[False] = False
    p19_terminal_authority: Literal[True] = True
    immutable: Literal[True] = True

    @model_validator(mode="after")
    def graph_is_closed_and_non_authoritative(
        self, info: ValidationInfo
    ) -> VehicleDynamicsKnowledgeGraph:
        collections: tuple[tuple[VehicleDynamicDefinition, ...], ...] = (
            self.quantities,
            self.mechanisms,
            self.load_paths,
            self.tire_demand_states,
            self.chassis_response_states,
            self.transient_responses,
            self.steady_state_responses,
            self.component_influences,
            self.mechanism_interactions,
            self.observation_contracts,
            (self.oval_track_demand_model,),
            (self.static_load_distribution,),
            (self.tire_state_evolution,),
            self.driver_response_chains,
        )
        definitions = tuple(item for collection in collections for item in collection)
        definition_ids = [item.definition_id for item in definitions]
        source_ids = [item.source_id for item in self.sources]
        node_ids = [item.node_id for item in self.nodes]
        edge_ids = [item.edge_id for item in self.edges]
        for values, label in (
            (definition_ids, "definition"),
            (source_ids, "source"),
            (node_ids, "node"),
            (edge_ids, "edge"),
            (list(self.unavailable_quantity_ids), "unavailable quantity"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"vehicle-dynamics {label} identities must be unique")
        declared_sources = set(source_ids)
        used_sources = {
            source_id
            for definition in definitions
            for source_id in definition.source_ids
        } | {
            source_id
            for item in (*self.forbidden_controls, *self.nodes, *self.edges)
            for source_id in item.source_ids
        }
        if used_sources != declared_sources:
            raise ValueError("vehicle-dynamics provenance must exactly match reviewed sources")
        if any(definition.applicability != self.applicability for definition in definitions):
            raise ValueError("every vehicle-dynamics definition must carry exact applicability")
        if any(item.applicability != self.applicability for item in self.forbidden_controls):
            raise ValueError("forbidden controls must carry exact graph applicability")
        definition_set = set(definition_ids)
        node_by_id = {item.node_id: item for item in self.nodes}
        if any(
            node.definition_id is not None and node.definition_id not in definition_set
            for node in self.nodes
        ):
            raise ValueError("vehicle-dynamics nodes cannot cite unknown definitions")
        definition_node_counts = Counter(
            node.definition_id for node in self.nodes if node.definition_id is not None
        )
        if set(definition_node_counts) != definition_set or any(
            count != 1 for count in definition_node_counts.values()
        ):
            raise ValueError("every vehicle-dynamics definition requires exactly one graph node")
        expected_node_kinds: dict[type[VehicleDynamicDefinition], VehicleDynamicsNodeKind] = {
            VehicleDynamicQuantity: VehicleDynamicsNodeKind.QUANTITY,
            VehicleDynamicMechanism: VehicleDynamicsNodeKind.MECHANISM,
            LoadPath: VehicleDynamicsNodeKind.LOAD_PATH,
            TireDemandState: VehicleDynamicsNodeKind.TIRE_DEMAND_STATE,
            ChassisResponseState: VehicleDynamicsNodeKind.CHASSIS_RESPONSE_STATE,
            TransientResponse: VehicleDynamicsNodeKind.TRANSIENT_RESPONSE,
            SteadyStateResponse: VehicleDynamicsNodeKind.STEADY_STATE_RESPONSE,
            ComponentInfluence: VehicleDynamicsNodeKind.COMPONENT_INFLUENCE,
            MechanismInteraction: VehicleDynamicsNodeKind.MECHANISM,
            DynamicObservationContract: VehicleDynamicsNodeKind.OBSERVATION_CONTRACT,
            OvalTrackDemandModel: VehicleDynamicsNodeKind.LOAD_PATH,
            StaticLoadDistributionKnowledge: VehicleDynamicsNodeKind.LOAD_PATH,
            TireStateEvolution: VehicleDynamicsNodeKind.TIRE_DEMAND_STATE,
            DriverVehicleResponseChain: VehicleDynamicsNodeKind.LOAD_PATH,
        }
        definitions_by_id = {item.definition_id: item for item in definitions}
        if any(
            node.definition_id is not None
            and node.kind is not expected_node_kinds[type(definitions_by_id[node.definition_id])]
            for node in self.nodes
        ):
            raise ValueError("vehicle-dynamics node kinds must match definition types")
        if any(
            edge.source_node_id not in node_by_id or edge.target_node_id not in node_by_id
            for edge in self.edges
        ):
            raise ValueError("vehicle-dynamics edges cannot be orphaned")
        if any(edge.source_node_id == edge.target_node_id for edge in self.edges):
            raise ValueError("vehicle-dynamics edges cannot be self-referential")
        if set(self.unavailable_quantity_ids) != {
            item.definition_id
            for item in self.quantities
            if item.semantics is QuantitySemantics.UNAVAILABLE
        }:
            raise ValueError("global unavailable physics must exactly match quantity contracts")
        required_unavailable = {
            "quantity:exact_tire_force",
            "quantity:exact_wheel_load",
            "quantity:exact_spring_force",
            "quantity:exact_damper_force",
            "quantity:exact_arb_torque",
            "quantity:exact_aerodynamic_downforce",
            "quantity:exact_aerodynamic_balance",
            "quantity:exact_aerodynamic_drag_force",
            "quantity:exact_drag_coefficient",
            "quantity:exact_differential_torque",
            "quantity:exact_contact_patch_distribution",
            "quantity:exact_friction_coefficient",
        }
        if not required_unavailable <= set(self.unavailable_quantity_ids):
            raise ValueError("vehicle-dynamics graph is missing mandatory unavailable physics")
        if {item.control_id for item in self.forbidden_controls} != {
            "track_bar",
            "truck_arm_mount",
        }:
            raise ValueError("Next Gen must explicitly prohibit track bar and truck arm controls")
        graph_without_forbidden = self.model_dump(
            mode="json",
            exclude={
                "forbidden_controls",
                "content_sha256",
                "graph_id",
                "graph_version",
            },
        )
        serialized = str(graph_without_forbidden).casefold()
        if re.search(r"track[_ -]?bar|truck[_ -]?arm", serialized):
            raise ValueError("legacy solid-axle controls cannot enter the Next Gen graph")
        mechanism_ids = {item.definition_id for item in self.mechanisms}
        observation_ids = {item.definition_id for item in self.observation_contracts}
        quantity_ids = {item.definition_id for item in self.quantities}
        required_brake_quantities = {
            "quantity:front_brake_line_pressure_state",
            "quantity:rear_brake_line_pressure_state",
            "quantity:relative_front_rear_brake_pressure_distribution",
            "quantity:wheel_lock_evidence_state",
            "quantity:abs_intervention_state",
        }
        if not required_brake_quantities <= quantity_ids:
            raise ValueError("vehicle-dynamics graph is missing typed brake response")
        abs_state = self.quantity("quantity:abs_intervention_state")
        if set(abs_state.manifest_validity_required_channels) != {
            "brake_abs_active",
            "brake_abs_cut_01",
        }:
            raise ValueError(
                "ABS evidence requires explicit runtime-manifest channel validity"
            )
        demand_state_ids = {item.definition_id for item in self.tire_demand_states}
        all_node_ids = set(node_by_id)
        component_ids = {
            node.node_id.removeprefix("component:")
            for node in self.nodes
            if node.kind is VehicleDynamicsNodeKind.COMPONENT_FAMILY
        }
        external_by_id = {
            item.namespace_id: item for item in self.external_identity_namespaces
        }
        if set(external_by_id) != {
            "telemetry_channel",
            "p20_mechanism",
            "p26_component_family",
            "p32_performance_mechanism",
        }:
            raise ValueError("vehicle-dynamics external identity policy is incomplete")
        p20_ids = set(external_by_id["p20_mechanism"].allowed_ids)
        p26_ids = set(external_by_id["p26_component_family"].allowed_ids)
        p32_ids = set(external_by_id["p32_performance_mechanism"].allowed_ids)
        for definition in definitions:
            graph_refs = {
                *definition.created_by_ids,
                *definition.affected_by_ids,
                *definition.affects_ids,
            }
            if graph_refs - all_node_ids:
                raise ValueError("vehicle-dynamics definitions cannot cite unknown graph identities")
            if set(definition.derived_quantity_ids) - quantity_ids:
                raise ValueError("derived vehicle quantities must cite known quantity definitions")
            if set(definition.valid_proxy_ids) - all_node_ids:
                raise ValueError("vehicle-dynamics proxies must cite known graph identities")
            if set(definition.unavailable_quantity_ids) - set(self.unavailable_quantity_ids):
                raise ValueError("definitions cannot cite undeclared unavailable physics")
            if set(definition.relevant_component_ids) - component_ids:
                raise ValueError("definitions cannot cite unknown P26 component families")
            if any(
                not re.fullmatch(r"[a-z0-9][a-z0-9_]*", channel)
                for channel in definition.required_measured_channels
            ):
                raise ValueError("telemetry references must use canonical manifest identities")
        for mechanism in self.mechanisms:
            if set(mechanism.p20_mechanism_ids) - p20_ids:
                raise ValueError("mechanisms cannot cite unknown P20 identities")
            if set(mechanism.p26_component_family_ids) - p26_ids:
                raise ValueError("mechanisms cannot cite unknown P26 component identities")
            if set(mechanism.p32_performance_mechanism_ids) - p32_ids:
                raise ValueError("mechanisms cannot cite unknown P32 performance identities")
            if not set(
                (*mechanism.support_contract_ids,
                 *mechanism.contradiction_contract_ids,
                 *mechanism.discriminator_contract_ids)
            ) <= observation_ids:
                raise ValueError("mechanisms cannot cite unknown observation contracts")
            for contract_id in mechanism.support_contract_ids:
                contract = next(
                    item for item in self.observation_contracts
                    if item.definition_id == contract_id
                )
                if mechanism.definition_id not in contract.supports_mechanism_ids:
                    raise ValueError("mechanism support mappings must be reciprocal")
            for contract_id in mechanism.contradiction_contract_ids:
                contract = next(
                    item for item in self.observation_contracts
                    if item.definition_id == contract_id
                )
                if mechanism.definition_id not in contract.contradicts_mechanism_ids:
                    raise ValueError("mechanism contradiction mappings must be reciprocal")
            for contract_id in mechanism.discriminator_contract_ids:
                contract = next(
                    item for item in self.observation_contracts
                    if item.definition_id == contract_id
                )
                if mechanism.definition_id not in contract.discriminates_mechanism_ids:
                    raise ValueError("mechanism discriminator mappings must be reciprocal")
        for contract in self.observation_contracts:
            if not set(
                (*contract.supports_mechanism_ids,
                 *contract.contradicts_mechanism_ids,
                 *contract.discriminates_mechanism_ids)
            ) <= mechanism_ids:
                raise ValueError("observation contracts cannot cite unknown mechanisms")
            if set(contract.supports_mechanism_ids) & set(contract.contradicts_mechanism_ids):
                raise ValueError("one observation contract cannot support and contradict a mechanism")
            directly_mapped = set(
                (*contract.supports_mechanism_ids, *contract.contradicts_mechanism_ids)
            )
            if any(
                self.mechanism(mechanism_id).inspection_tool_id
                is not contract.inspection_tool_id
                for mechanism_id in directly_mapped
            ):
                raise ValueError("observation contracts must use their mechanism inspection tool")
        if {item.inspection_tool_id for item in self.mechanisms} != set(
            VehicleDynamicsInspectionToolId
        ):
            raise ValueError("P35 mechanisms must cover every typed inspection tool")
        for interaction in self.mechanism_interactions:
            if {
                interaction.source_mechanism_id,
                interaction.target_mechanism_id,
            } - mechanism_ids:
                raise ValueError("mechanism interactions cannot cite unknown mechanisms")
        for influence in self.component_influences:
            if not set(
                (*influence.mechanism_ids, *influence.countereffect_mechanism_ids)
            ) <= mechanism_ids:
                raise ValueError("component influences cannot cite unknown mechanisms")
            mapped_mechanisms = tuple(
                self.mechanism(mechanism_id)
                for mechanism_id in influence.mechanism_ids
            )
            expected_phases = {
                phase
                for mechanism in mapped_mechanisms
                for phase in mechanism.relevant_phases
            }
            if set(influence.relevant_phases) != expected_phases:
                raise ValueError(
                    "component influence phases must equal its mechanism phase union"
                )
        sequence_indexes = [item.sequence_index for item in self.load_paths]
        if sorted(sequence_indexes) != list(range(len(self.load_paths))):
            raise ValueError("oval load paths require one contiguous canonical sequence")
        ordered_load_paths = sorted(self.load_paths, key=lambda item: item.sequence_index)
        for index, load_path in enumerate(ordered_load_paths):
            expected_prior = ordered_load_paths[index - 1].definition_id if index else None
            expected_next = (
                ordered_load_paths[index + 1].definition_id
                if index + 1 < len(ordered_load_paths)
                else None
            )
            if (
                load_path.prior_load_path_id != expected_prior
                or load_path.next_load_path_id != expected_next
            ):
                raise ValueError("oval load-path prior/next identities must be continuous")
            if not set((*load_path.input_quantity_ids, *load_path.output_quantity_ids)) <= quantity_ids:
                raise ValueError("oval load paths cannot cite unknown quantities")
            if not set(load_path.demand_state_ids) <= demand_state_ids:
                raise ValueError("oval load paths cannot cite unknown tire-demand states")
            if expected_next is not None:
                next_path = ordered_load_paths[index + 1]
                if not set(load_path.output_quantity_ids) & set(next_path.input_quantity_ids):
                    raise ValueError("adjacent oval load paths require a physical quantity handoff")
        for chain in self.driver_response_chains:
            if {
                chain.driver_input_id,
                chain.vehicle_demand_id,
                chain.vehicle_response_id,
                chain.tire_platform_state_id,
                chain.performance_dimension_id,
            } - all_node_ids:
                raise ValueError("driver-response chains cannot cite unknown graph nodes")
            expected_chain_kinds = (
                (chain.driver_input_id, VehicleDynamicsNodeKind.QUANTITY),
                (chain.vehicle_demand_id, VehicleDynamicsNodeKind.QUANTITY),
                (chain.vehicle_response_id, VehicleDynamicsNodeKind.CHASSIS_RESPONSE_STATE),
                (chain.tire_platform_state_id, VehicleDynamicsNodeKind.TIRE_DEMAND_STATE),
                (chain.performance_dimension_id, VehicleDynamicsNodeKind.PERFORMANCE_DIMENSION),
            )
            if any(node_by_id[node_id].kind is not kind for node_id, kind in expected_chain_kinds):
                raise ValueError("driver-response chain nodes must match canonical stage semantics")
        if set(self.static_load_distribution.static_quantity_ids) - quantity_ids:
            raise ValueError("static load distribution cannot cite unknown quantities")
        if set(self.static_load_distribution.prohibited_dynamic_equivalents) - quantity_ids:
            raise ValueError("static load locks cannot cite unknown dynamic quantities")
        if self.graph_version != f"2026.08.next-gen-oval.v1:{self.content_sha256[:12]}":
            raise ValueError("vehicle-dynamics graph version must bind exact content")
        if self.graph_id != f"p35vdg_{self.content_sha256[:24]}":
            raise ValueError("vehicle-dynamics graph ID must bind exact content")
        if not (info.context or {}).get("skip_content_hash"):
            expected = vehicle_dynamics_graph_hash(self)
            if self.content_sha256 != expected:
                raise ValueError("vehicle-dynamics content hash does not match canonical content")
        return self

    def quantity(self, quantity_id: str) -> VehicleDynamicQuantity:
        return _lookup(self.quantities, quantity_id, "quantity")

    def mechanism(self, mechanism_id: str) -> VehicleDynamicMechanism:
        return _lookup(self.mechanisms, mechanism_id, "mechanism")

    def observation_contract(self, contract_id: str) -> DynamicObservationContract:
        return _lookup(self.observation_contracts, contract_id, "observation contract")

    def component_candidates(self, component_id: str) -> tuple[VehicleDynamicMechanism, ...]:
        return tuple(
            item for item in self.mechanisms if component_id in item.p26_component_family_ids
        )


class VehicleDynamicsKnowledgeResolution(VehicleDynamicsModel):
    status: Literal["ready", "unavailable", "incompatible", "unreviewed_build"]
    graph: VehicleDynamicsKnowledgeGraph | None = None
    requested_car_path: str = Field(min_length=1)
    requested_car_version: str = Field(min_length=1)
    requested_iracing_build_version: str = Field(min_length=1)
    requested_track_package: str = Field(min_length=1)
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def resolution_fails_closed(self) -> VehicleDynamicsKnowledgeResolution:
        if self.status == "ready" and (self.graph is None or self.blocker_reasons):
            raise ValueError("ready vehicle-dynamics resolution requires one graph and no blockers")
        if self.status != "ready" and (self.graph is not None or not self.blocker_reasons):
            raise ValueError("blocked vehicle-dynamics resolution requires blockers and no graph")
        return self


class VehicleDynamicsRuntimeChannelAlternative(VehicleDynamicsModel):
    """One exact producer-channel spelling set for a reviewed requirement."""

    channel_id: str = Field(pattern=_ID_PATTERN)
    accepted_source_channel_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def source_channel_ids_are_closed(self) -> VehicleDynamicsRuntimeChannelAlternative:
        if any(not value for value in self.accepted_source_channel_ids) or len(
            self.accepted_source_channel_ids
        ) != len(set(self.accepted_source_channel_ids)):
            raise ValueError(
                "runtime-trust accepted source-channel identities must be non-empty and unique"
            )
        return self


class VehicleDynamicsRuntimeChannelRequirement(VehicleDynamicsModel):
    """A required any-of/minimum channel group, scoped to exact evidence layers."""

    requirement_id: str = Field(pattern=_ID_PATTERN)
    evidence_layer_ids: tuple[DynamicsChainStageKind, ...] = Field(min_length=1)
    alternatives: tuple[VehicleDynamicsRuntimeChannelAlternative, ...] = Field(
        min_length=1
    )
    minimum_alternatives: int = Field(ge=1)

    @model_validator(mode="after")
    def requirement_is_closed_and_satisfiable(
        self,
    ) -> VehicleDynamicsRuntimeChannelRequirement:
        canonical_layers = tuple(
            layer for layer in DynamicsChainStageKind if layer in self.evidence_layer_ids
        )
        if self.evidence_layer_ids != canonical_layers:
            raise ValueError(
                "runtime-trust channel requirement layers must be unique and canonical"
            )
        channel_ids = tuple(item.channel_id for item in self.alternatives)
        if len(channel_ids) != len(set(channel_ids)):
            raise ValueError(
                "runtime-trust channel requirement alternatives must be unique"
            )
        if self.minimum_alternatives > len(self.alternatives):
            raise ValueError(
                "runtime-trust channel requirement minimum exceeds its alternatives"
            )
        return self


class VehicleDynamicsRuntimeMechanismTrust(VehicleDynamicsModel):
    mechanism_id: str = Field(pattern=r"^mechanism:[a-z0-9_]+$")
    p20_mechanism_ids: tuple[str, ...] = Field(min_length=1)
    p32_performance_mechanism_ids: tuple[str, ...] = Field(min_length=1)
    allowed_time_origin_kinds: tuple[TimeOriginKind, ...] = Field(min_length=1)
    relevant_phases: tuple[VehicleDynamicsPhase, ...] = Field(min_length=1)
    response_regime: DynamicResponseRegime
    component_family_ids: tuple[str, ...] = Field(min_length=1)
    inspection_tool_id: VehicleDynamicsInspectionToolId
    support_observation_contract_ids: tuple[str, ...] = Field(min_length=1)
    contradiction_observation_contract_ids: tuple[str, ...] = Field(min_length=1)
    discriminator_observation_contract_ids: tuple[str, ...] = Field(min_length=1)
    support_required_evidence_layers: tuple[DynamicsChainStageKind, ...] = Field(
        min_length=1
    )
    support_required_channel_groups: tuple[
        VehicleDynamicsRuntimeChannelRequirement, ...
    ] = Field(min_length=1)
    focus_artifact_prefix: str = Field(min_length=1)

    @model_validator(mode="after")
    def runtime_relations_are_closed(self) -> VehicleDynamicsRuntimeMechanismTrust:
        for values in (
            self.p20_mechanism_ids,
            self.p32_performance_mechanism_ids,
            self.allowed_time_origin_kinds,
            self.relevant_phases,
            self.component_family_ids,
            self.support_observation_contract_ids,
            self.contradiction_observation_contract_ids,
            self.discriminator_observation_contract_ids,
            self.support_required_evidence_layers,
        ):
            if len(values) != len(set(values)):
                raise ValueError("runtime-trust mechanism relations must be unique")
        canonical_layers = tuple(
            layer
            for layer in DynamicsChainStageKind
            if layer in self.support_required_evidence_layers
        )
        if self.support_required_evidence_layers != canonical_layers:
            raise ValueError(
                "runtime-trust support evidence layers must use canonical order"
            )
        requirement_ids = tuple(
            item.requirement_id for item in self.support_required_channel_groups
        )
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError(
                "runtime-trust support channel requirements must be unique"
            )
        if any(
            not set(item.evidence_layer_ids)
            <= set(self.support_required_evidence_layers)
            for item in self.support_required_channel_groups
        ):
            raise ValueError(
                "runtime-trust channel requirements must use required evidence layers"
            )
        expected_prefix = (
            f"p35.focus.{self.inspection_tool_id.value.removeprefix('inspect_')}:"
        )
        if self.focus_artifact_prefix != expected_prefix:
            raise ValueError("runtime-trust focus prefix must bind the inspection tool")
        return self


class VehicleDynamicsRuntimeTrustManifest(VehicleDynamicsModel):
    schema_version: Literal["p35.vehicle-dynamics-runtime-trust.v1"] = (
        "p35.vehicle-dynamics-runtime-trust.v1"
    )
    runtime_trust_sha256: str = Field(pattern=_SHA256_PATTERN)
    graph_id: str = Field(pattern=r"^p35vdg_[0-9a-f]{24}$")
    graph_version: str = Field(pattern=r"^2026\.08\.next-gen-oval\.v1:[0-9a-f]{12}$")
    knowledge_version: str = Field(min_length=1)
    knowledge_graph_sha256: str = Field(pattern=_SHA256_PATTERN)
    mechanisms: tuple[VehicleDynamicsRuntimeMechanismTrust, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def manifest_is_graph_bound_and_content_addressed(
        self, info: ValidationInfo
    ) -> VehicleDynamicsRuntimeTrustManifest:
        if self.graph_id != f"p35vdg_{self.knowledge_graph_sha256[:24]}":
            raise ValueError("runtime-trust graph ID does not bind knowledge content")
        if not self.graph_version.endswith(f":{self.knowledge_graph_sha256[:12]}"):
            raise ValueError("runtime-trust graph version does not bind knowledge content")
        mechanism_ids = tuple(item.mechanism_id for item in self.mechanisms)
        if mechanism_ids != tuple(sorted(mechanism_ids)) or len(mechanism_ids) != len(
            set(mechanism_ids)
        ):
            raise ValueError(
                "runtime-trust mechanisms must be unique and canonically ordered"
            )
        if not (info.context or {}).get("skip_content_hash"):
            expected = vehicle_dynamics_runtime_trust_hash(self)
            if self.runtime_trust_sha256 != expected:
                raise ValueError("runtime-trust hash does not match canonical content")
        return self


class VehicleDynamicsChainStage(VehicleDynamicsModel):
    stage: DynamicsChainStageKind
    evidence_state: EvidenceState
    source_artifact_ids: tuple[str, ...] = ()
    source_channels: tuple[str, ...] = ()
    summary: str = Field(min_length=1)
    blocker_reasons: tuple[str, ...] = ()
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def stage_truth_matches_evidence(self) -> VehicleDynamicsChainStage:
        if len(self.source_artifact_ids) != len(set(self.source_artifact_ids)) or len(
            self.source_channels
        ) != len(set(self.source_channels)):
            raise ValueError("dynamics chain provenance identities must be unique")
        positive = self.evidence_state in {
            EvidenceState.MEASURED,
            EvidenceState.CALCULATED,
            EvidenceState.ESTIMATED_PROXY,
            EvidenceState.OBSERVED_CORRELATION,
            EvidenceState.CONTROLLED_TEST_EFFECT,
        }
        if positive and (not self.source_artifact_ids or not self.source_channels):
            raise ValueError("positive dynamics chain stages require artifacts and channels")
        if positive and self.blocker_reasons:
            raise ValueError("positive dynamics chain stages cannot carry blockers")
        if not positive and not self.blocker_reasons:
            raise ValueError("unavailable or blocked dynamics chain stages require blockers")
        return self


class PerformanceMechanismCandidate(VehicleDynamicsModel):
    mechanism_id: str = Field(pattern=_ID_PATTERN)
    p32_performance_mechanism_ids: tuple[str, ...] = Field(min_length=1)
    support_artifact_ids: tuple[str, ...] = ()
    contradiction_artifact_ids: tuple[str, ...] = ()
    discriminator_contract_ids: tuple[str, ...] = Field(min_length=1)
    component_family_ids: tuple[str, ...] = Field(min_length=1)
    blocker_reasons: tuple[str, ...] = ()
    relevance: Literal["candidate", "blocked"]
    authority: Literal["candidate_only"] = "candidate_only"
    component_cause_authorized: Literal[False] = False
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def candidate_is_noncausal(self) -> PerformanceMechanismCandidate:
        for values in (
            self.p32_performance_mechanism_ids,
            self.support_artifact_ids,
            self.contradiction_artifact_ids,
            self.discriminator_contract_ids,
            self.component_family_ids,
        ):
            if len(values) != len(set(values)):
                raise ValueError("P35 candidate identities must be unique")
        if self.relevance == "blocked" and not self.blocker_reasons:
            raise ValueError("blocked mechanism candidates require explicit blockers")
        if self.relevance == "candidate" and self.blocker_reasons:
            raise ValueError("unblocked mechanism candidates cannot carry blockers")
        if self.relevance == "candidate" and not self.support_artifact_ids:
            raise ValueError("mechanism candidates require positive supporting evidence")
        if self.relevance == "blocked" and self.support_artifact_ids:
            raise ValueError("blocked mechanism candidates cannot publish support evidence")
        if not self.contradiction_artifact_ids:
            raise ValueError(
                "mechanism candidates require contradiction or uncertainty evidence"
            )
        if set(self.support_artifact_ids) & set(self.contradiction_artifact_ids):
            raise ValueError("one artifact cannot both support and contradict a candidate")
        return self


class VehicleDynamicsFocusArtifact(VehicleDynamicsModel):
    artifact_id: str = Field(pattern=_ID_PATTERN)
    mechanism_id: str = Field(pattern=_ID_PATTERN)
    observation_contract_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    inspection_tool_id: VehicleDynamicsInspectionToolId
    stage: DynamicsChainStageKind
    evidence_state: EvidenceState
    source_artifact_ids: tuple[str, ...] = Field(min_length=1)
    source_channels: tuple[str, ...] = Field(min_length=1)
    lap_numbers: tuple[int, ...] = ()
    lap_pct_start: float | None = Field(default=None, ge=0.0, le=100.0)
    lap_pct_end: float | None = Field(default=None, ge=0.0, le=100.0)
    phase: str | None = Field(default=None, min_length=1)
    polarity: Literal["support", "contradiction", "uncertainty", "neutral"]
    summary: str = Field(min_length=1)
    blocker_reasons: tuple[str, ...] = ()
    authority: Literal["observation_only"] = "observation_only"

    @model_validator(mode="after")
    def focus_artifact_is_typed(self) -> VehicleDynamicsFocusArtifact:
        if len(self.source_artifact_ids) != len(set(self.source_artifact_ids)) or len(
            self.source_channels
        ) != len(set(self.source_channels)):
            raise ValueError("P35 focus provenance identities must be unique")
        expected_prefix = (
            f"p35.focus.{self.inspection_tool_id.value.removeprefix('inspect_')}:"
        )
        if not re.fullmatch(f"{re.escape(expected_prefix)}[0-9a-f]{{24}}", self.artifact_id):
            raise ValueError("P35 focus identity must bind its exact inspection tool")
        if self.evidence_state in {
            EvidenceState.UNAVAILABLE,
            EvidenceState.BLOCKED_BY_CONTEXT,
            EvidenceState.NEEDS_CONFIRMATION,
        } and not self.blocker_reasons:
            raise ValueError("blocked P35 focus artifacts require explicit blockers")
        if self.evidence_state not in {
            EvidenceState.UNAVAILABLE,
            EvidenceState.BLOCKED_BY_CONTEXT,
            EvidenceState.NEEDS_CONFIRMATION,
        } and self.blocker_reasons:
            raise ValueError("positive P35 focus artifacts cannot carry blockers")
        if len(self.lap_numbers) != len(set(self.lap_numbers)) or any(
            lap_number < 0 for lap_number in self.lap_numbers
        ):
            raise ValueError("P35 focus lap identities must be non-negative and unique")
        if (self.lap_pct_start is None) != (self.lap_pct_end is None):
            raise ValueError("P35 focus windows require both physical-position bounds")
        if (
            self.lap_pct_start is not None
            and self.lap_pct_end is not None
            and self.lap_pct_start > self.lap_pct_end
        ):
            raise ValueError("P35 focus physical-position window is reversed")
        positive = self.evidence_state not in {
            EvidenceState.UNAVAILABLE,
            EvidenceState.BLOCKED_BY_CONTEXT,
            EvidenceState.NEEDS_CONFIRMATION,
        }
        if positive and (
            not self.lap_numbers
            or self.lap_pct_start is None
            or self.lap_pct_end is None
            or self.phase is None
        ):
            raise ValueError("positive P35 focus artifacts require exact lap/window/phase scope")
        if self.polarity == "support" and not positive:
            raise ValueError("P35 support focus requires positive existing evidence")
        if self.polarity == "uncertainty" and positive:
            raise ValueError("P35 uncertainty focus must remain unavailable, blocked, or unconfirmed")
        return self


_PHASE_RESPONSE_CHANNELS = {
    "elapsed_time_delta_s": frozenset(
        {
            "session_time",
            "SessionTime",
            "lap_dist_pct_100",
            "lap_dist_pct",
            "speed_mph",
            "speed_mps",
            "Speed",
        }
    ),
    "speed_delta_mph": frozenset({"speed_mph", "Speed", "speed_mps"}),
    "throttle_demand_delta_pct": frozenset(
        {"Throttle", "throttle_pct", "throttle_01", "throttle"}
    ),
    "brake_demand_delta_pct": frozenset({"Brake", "brake_pct", "brake_01"}),
    "steering_wheel_demand_delta_deg": frozenset(
        {"SteeringWheelAngle", "steering_deg", "steering_rad"}
    ),
    "yaw_rate_response_delta_rad_s": frozenset({"YawRate", "yaw_rate"}),
    "longitudinal_accel_response_delta_mps2": frozenset(
        {"LongAccel", "long_accel", "long_accel_mps2"}
    ),
    "path_delta_m": frozenset(
        {"lat", "lon", "Lat", "Lon", "lap_dist_pct_100"}
    ),
    "line_separation_m": frozenset(
        {"lat", "lon", "Lat", "Lon", "lap_dist_pct_100"}
    ),
}
_PHASE_RESPONSE_UNITS = {
    "elapsed_time_delta_s": "s",
    "speed_delta_mph": "mph",
    "throttle_demand_delta_pct": "%",
    "brake_demand_delta_pct": "%",
    "steering_wheel_demand_delta_deg": "deg",
    "yaw_rate_response_delta_rad_s": "rad/s",
    "longitudinal_accel_response_delta_mps2": "m/s^2",
    "path_delta_m": "m",
    "line_separation_m": "m",
}
_PHASE_RESPONSE_SEMANTICS = {
    "elapsed_time_delta_s": "calculated_delta",
    "speed_delta_mph": "measured_delta",
    "throttle_demand_delta_pct": "measured_delta",
    "brake_demand_delta_pct": "measured_delta",
    "steering_wheel_demand_delta_deg": "measured_delta",
    "yaw_rate_response_delta_rad_s": "measured_delta",
    "longitudinal_accel_response_delta_mps2": "measured_delta",
    "path_delta_m": "calculated_delta",
    "line_separation_m": "calculated_delta",
}


def _p354_content_id(prefix: str, value: BaseModel, identity_field: str) -> str:
    digest = canonical_json_sha256(
        value.model_dump(mode="json", exclude={identity_field})
    )
    return f"{prefix}:{digest[:24]}"


class PhaseResponseMetric(VehicleDynamicsModel):
    """One producer-owned delta in an exact physical phase.

    Metrics retain their native meaning. Steering is explicitly steering-wheel
    demand, platform values remain relative, and no force-like proxy is allowed.
    """

    metric_id: str = Field(pattern=_ID_PATTERN)
    quantity: Literal[
        "elapsed_time_delta_s",
        "speed_delta_mph",
        "throttle_demand_delta_pct",
        "brake_demand_delta_pct",
        "steering_wheel_demand_delta_deg",
        "yaw_rate_response_delta_rad_s",
        "longitudinal_accel_response_delta_mps2",
        "path_delta_m",
        "line_separation_m",
    ]
    value: float = Field(allow_inf_nan=False)
    units: Literal["s", "mph", "%", "deg", "rad/s", "m/s^2", "m"]
    semantics: Literal["measured_delta", "calculated_delta"]
    source_channels: tuple[str, ...] = Field(min_length=1)
    force_like: Literal[False] = False
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def metric_provenance_matches_quantity(
        self, info: ValidationInfo
    ) -> PhaseResponseMetric:
        if len(self.source_channels) != len(set(self.source_channels)):
            raise ValueError("phase-response metric channels must be unique")
        if not set(self.source_channels) <= _PHASE_RESPONSE_CHANNELS[self.quantity]:
            raise ValueError(
                "phase-response metric channels must match the measured quantity"
            )
        if self.units != _PHASE_RESPONSE_UNITS[self.quantity]:
            raise ValueError("phase-response metric units do not match the quantity")
        if self.semantics != _PHASE_RESPONSE_SEMANTICS[self.quantity]:
            raise ValueError("phase-response metric semantics do not match the quantity")
        if not (info.context or {}).get("skip_content_hash") and self.metric_id != (
            _p354_content_id("p354.metric", self, "metric_id")
        ):
            raise ValueError("phase-response metric ID does not match canonical content")
        return self


class VehicleResponseObservation(VehicleDynamicsModel):
    """Immutable demand-to-response truth for one phase-resolved comparison."""

    observation_id: str = Field(pattern=r"^p354\.response:[0-9a-f]{24}$")
    opportunity_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(min_length=1)
    source_lap_numbers: tuple[int, ...] = Field(min_length=1)
    reference_lap_numbers: tuple[int, ...] = Field(min_length=1)
    phase: str = Field(min_length=1)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    onset_pct: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    onset_resolution: Literal["phase_boundary"] = "phase_boundary"
    response_regime: DynamicResponseRegime
    driver_demand_state: Literal["matched", "changed", "mixed", "unavailable"]
    vehicle_response_state: Literal["changed", "not_established", "unavailable"]
    line_state: Literal["matched", "changed", "unavailable"]
    context_state: Literal["qualified", "blocked", "unavailable"]
    persistence: Literal["phase_local", "carried_forward", "recovered", "unavailable"]
    metrics: tuple[PhaseResponseMetric, ...] = Field(min_length=1)
    source_artifact_ids: tuple[str, ...] = Field(min_length=1)
    source_channels: tuple[str, ...] = Field(min_length=1)
    blocker_reasons: tuple[str, ...] = ()
    evidence_state: Literal[
        EvidenceState.MEASURED,
        EvidenceState.BLOCKED_BY_CONTEXT,
        EvidenceState.NEEDS_CONFIRMATION,
    ]
    authority: Literal["observation_only"] = "observation_only"
    component_cause_authorized: Literal[False] = False
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def response_truth_is_exact_and_noncausal(
        self, info: ValidationInfo
    ) -> VehicleResponseObservation:
        if self.lap_pct_end < self.lap_pct_start:
            raise ValueError("phase-response physical window is reversed")
        if not self.lap_pct_start <= self.onset_pct <= self.lap_pct_end:
            raise ValueError("phase-response onset must stay inside its physical window")
        for values in (
            self.source_lap_numbers,
            self.reference_lap_numbers,
            self.source_artifact_ids,
            self.source_channels,
        ):
            if len(values) != len(set(values)):
                raise ValueError("phase-response provenance must be unique")
        if set(self.source_lap_numbers) & set(self.reference_lap_numbers):
            raise ValueError("source and reference response laps must be independent identities")
        metric_ids = tuple(item.metric_id for item in self.metrics)
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("phase-response metric identities must be unique")
        unsafe = {
            "front_slip_angle_deg",
            "rear_slip_angle_deg",
            "slip_angle_balance_deg",
            "ackermann_steering_error_deg",
            "ackermann_scrub_proxy",
            "wheel_power_proxy_w",
            "cda_coastdown_proxy_m2",
            "full_throttle_resistance_cda_proxy_m2",
            "platform_roll_deg_from_rh",
            "dynamic_pressure_pa",
            "dynamic_pressure_psf",
            "dynamic_pressure_lap_index",
            "dynamic_pressure_index",
            "aero_load_index",
            "aero_load_index_180mph",
        }
        if unsafe.intersection(self.source_channels):
            raise ValueError("research/display-only physics cannot support a phase response")
        metric_channels = tuple(
            dict.fromkeys(
                channel for metric in self.metrics for channel in metric.source_channels
            )
        )
        if self.source_channels != metric_channels:
            raise ValueError(
                "phase-response source channels must equal the metric provenance union"
            )
        if self.opportunity_id not in self.source_artifact_ids:
            raise ValueError("phase response must retain its P32 opportunity source")
        expected_evidence = {
            "qualified": EvidenceState.MEASURED,
            "blocked": EvidenceState.BLOCKED_BY_CONTEXT,
            "unavailable": EvidenceState.NEEDS_CONFIRMATION,
        }[self.context_state]
        if self.evidence_state is not expected_evidence:
            raise ValueError("phase-response evidence state must match context state")
        if self.context_state == "qualified" and self.blocker_reasons:
            raise ValueError("qualified phase response cannot carry blockers")
        if self.context_state != "qualified" and not self.blocker_reasons:
            raise ValueError("blocked phase response requires explicit blockers")
        if not (info.context or {}).get("skip_content_hash") and self.observation_id != (
            _p354_content_id("p354.response", self, "observation_id")
        ):
            raise ValueError("phase-response observation ID does not match canonical content")
        return self


class VehicleProblemSignature(VehicleDynamicsModel):
    """Physical problem statement before mechanism or component relevance."""

    signature_id: str = Field(pattern=r"^p354\.signature:[0-9a-f]{24}$")
    response_observation_id: str = Field(pattern=r"^p354\.response:[0-9a-f]{24}$")
    opportunity_id: str = Field(pattern=_ID_PATTERN)
    time_origin: TimeOriginKind
    local_time_delta_s: float = Field(allow_inf_nan=False)
    phase: str = Field(min_length=1)
    onset_pct: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    onset_resolution: Literal["phase_boundary"] = "phase_boundary"
    response_regime: DynamicResponseRegime
    driver_demand_state: Literal["matched", "changed", "mixed", "unavailable"]
    vehicle_response_state: Literal["changed", "not_established", "unavailable"]
    line_state: Literal["matched", "changed", "unavailable"]
    speed_dependence: Literal["not_established"] = "not_established"
    stint_dependence: Literal["not_established"] = "not_established"
    traffic_dependence: Literal["blocked", "clear", "unavailable"]
    surface_dependence: Literal["not_established"] = "not_established"
    front_rear_corner_scope: Literal["unresolved"] = "unresolved"
    strongest_contradiction: str = Field(min_length=1)
    authority: Literal["observation_only"] = "observation_only"
    component_cause_authorized: Literal[False] = False
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def signature_is_content_addressed(
        self, info: ValidationInfo
    ) -> VehicleProblemSignature:
        if not (info.context or {}).get("skip_content_hash") and self.signature_id != (
            _p354_content_id("p354.signature", self, "signature_id")
        ):
            raise ValueError("vehicle-problem signature ID does not match canonical content")
        return self


class MechanismSeparationRow(VehicleDynamicsModel):
    """Auditable support/contradiction/discriminator row for one mechanism."""

    mechanism_id: str = Field(pattern=_ID_PATTERN)
    response_observation_id: str = Field(pattern=r"^p354\.response:[0-9a-f]{24}$")
    required_response_kpi_ids: tuple[str, ...] = Field(min_length=1)
    support_artifact_ids: tuple[str, ...] = ()
    contradiction_artifact_ids: tuple[str, ...] = Field(min_length=1)
    missing_evidence: tuple[str, ...] = Field(min_length=1)
    discriminator_contract_ids: tuple[str, ...] = Field(min_length=1)
    protected_countereffects: tuple[str, ...] = Field(min_length=1)
    component_family_ids: tuple[str, ...] = Field(min_length=1)
    state: Literal["alive", "weakened", "blocked"]
    authority: Literal["candidate_only"] = "candidate_only"
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def separation_is_auditable(self) -> MechanismSeparationRow:
        for values in (
            self.required_response_kpi_ids,
            self.support_artifact_ids,
            self.contradiction_artifact_ids,
            self.missing_evidence,
            self.discriminator_contract_ids,
            self.protected_countereffects,
            self.component_family_ids,
        ):
            if len(values) != len(set(values)):
                raise ValueError("mechanism-separation values must be unique")
        if self.state == "alive" and not self.support_artifact_ids:
            raise ValueError("alive mechanisms require typed support")
        if self.state != "alive" and self.support_artifact_ids:
            raise ValueError("weakened/blocked mechanisms cannot carry positive support")
        return self


def build_phase_response_metric(payload: dict[str, Any]) -> PhaseResponseMetric:
    if "metric_id" in payload:
        raise ValueError("phase-response metric identity is derived")
    provisional = PhaseResponseMetric.model_validate(
        {**payload, "metric_id": f"p354.metric:{'0' * 24}"},
        context={"skip_content_hash": True},
    )
    return PhaseResponseMetric.model_validate(
        {
            **provisional.model_dump(mode="json", exclude={"metric_id"}),
            "metric_id": _p354_content_id("p354.metric", provisional, "metric_id"),
        }
    )


def build_vehicle_response_observation(
    payload: dict[str, Any],
) -> VehicleResponseObservation:
    if "observation_id" in payload:
        raise ValueError("phase-response observation identity is derived")
    provisional = VehicleResponseObservation.model_validate(
        {**payload, "observation_id": f"p354.response:{'0' * 24}"},
        context={"skip_content_hash": True},
    )
    return VehicleResponseObservation.model_validate(
        {
            **provisional.model_dump(mode="json", exclude={"observation_id"}),
            "observation_id": _p354_content_id(
                "p354.response", provisional, "observation_id"
            ),
        }
    )


def build_vehicle_problem_signature(payload: dict[str, Any]) -> VehicleProblemSignature:
    if "signature_id" in payload:
        raise ValueError("vehicle-problem signature identity is derived")
    provisional = VehicleProblemSignature.model_validate(
        {**payload, "signature_id": f"p354.signature:{'0' * 24}"},
        context={"skip_content_hash": True},
    )
    return VehicleProblemSignature.model_validate(
        {
            **provisional.model_dump(mode="json", exclude={"signature_id"}),
            "signature_id": _p354_content_id(
                "p354.signature", provisional, "signature_id"
            ),
        }
    )


class PerformanceMechanismAssessment(VehicleDynamicsModel):
    schema_version: Literal["p35.performance-mechanism-assessment.v1"] = (
        "p35.performance-mechanism-assessment.v1"
    )
    p35_assessment_sha256: str = Field(pattern=_SHA256_PATTERN)
    run_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    objective_id: str = Field(min_length=1)
    car_path: str = Field(min_length=1)
    car_version: str = Field(min_length=1)
    iracing_build_version: str = Field(min_length=1)
    track_package: str = Field(min_length=1)
    vehicle_runtime_identity_sha256: str = Field(pattern=_SHA256_PATTERN)
    graph_id: str = Field(pattern=r"^p35vdg_[0-9a-f]{24}$")
    graph_version: str = Field(pattern=r"^2026\.08\.next-gen-oval\.v1:[0-9a-f]{12}$")
    knowledge_version: str = Field(min_length=1)
    knowledge_graph_sha256: str = Field(pattern=_SHA256_PATTERN)
    p19_reasoning_snapshot_sha256: str = Field(pattern=_SHA256_PATTERN)
    p20_state_revision: str = Field(pattern=_SHA256_PATTERN)
    p20_profile_hash: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    p26_graph_version: str = Field(min_length=1)
    p26_knowledge_graph_sha256: str = Field(pattern=_SHA256_PATTERN)
    p32_projection_sha256: str = Field(pattern=_SHA256_PATTERN)
    p32_performance_mechanism_ids: tuple[str, ...] = ()
    performance_opportunity_ids: tuple[str, ...] = Field(default=(), max_length=1)
    measured_time_consequence_available: bool
    chain: tuple[VehicleDynamicsChainStage, ...] = Field(min_length=5, max_length=5)
    tire_demand_state_ids: tuple[str, ...] = ()
    load_path_ids: tuple[str, ...] = ()
    response_regime: DynamicResponseRegime | None = None
    response_observations: tuple[VehicleResponseObservation, ...] = Field(
        default=(), max_length=1
    )
    problem_signature: VehicleProblemSignature | None = None
    mechanism_separation: tuple[MechanismSeparationRow, ...] = ()
    candidates: tuple[PerformanceMechanismCandidate, ...] = ()
    focus_artifacts: tuple[VehicleDynamicsFocusArtifact, ...] = ()
    strongest_support_artifact_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    strongest_contradiction_artifact_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    next_discriminator_contract_id: str | None = Field(default=None, pattern=_ID_PATTERN)
    unavailable_quantity_ids: tuple[str, ...] = Field(min_length=1)
    traffic_blocked: bool
    applicability_state: Literal["ready", "unavailable", "incompatible", "unreviewed_build"]
    applicability_blockers: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    observation_authority: Literal["observation_only"] = "observation_only"
    mechanism_authority: Literal["candidate_only"] = "candidate_only"
    component_causal_claim_count: Literal[0] = 0
    setup_authorized: Literal[False] = False
    terminal_authority: Literal["p19_only"] = "p19_only"

    @model_validator(mode="after")
    def assessment_is_atomic_and_fail_closed(
        self, info: ValidationInfo
    ) -> PerformanceMechanismAssessment:
        expected_stages = tuple(DynamicsChainStageKind)
        if tuple(item.stage for item in self.chain) != expected_stages:
            raise ValueError("vehicle-dynamics chain requires the canonical five-stage order")
        if self.graph_id != f"p35vdg_{self.knowledge_graph_sha256[:24]}":
            raise ValueError("P35 assessment graph ID does not bind its knowledge content")
        if not self.graph_version.endswith(f":{self.knowledge_graph_sha256[:12]}"):
            raise ValueError("P35 assessment graph version does not bind its knowledge content")
        if self.applicability_state == "ready" and self.applicability_blockers:
            raise ValueError("ready P35 applicability cannot carry blockers")
        if self.applicability_state != "ready" and not self.applicability_blockers:
            raise ValueError("blocked P35 applicability requires explicit blockers")
        if self.applicability_state != "ready" and self.candidates:
            raise ValueError("unreviewed or incompatible builds cannot emit mechanism candidates")
        if self.traffic_blocked and not any(
            item.evidence_state is EvidenceState.BLOCKED_BY_CONTEXT for item in self.chain
        ):
            raise ValueError("traffic-blocked assessments require a context-blocked chain stage")
        if self.measured_time_consequence_available != (
            self.chain[-1].evidence_state
            in {
                EvidenceState.MEASURED,
                EvidenceState.CALCULATED,
                EvidenceState.OBSERVED_CORRELATION,
                EvidenceState.CONTROLLED_TEST_EFFECT,
            }
        ):
            raise ValueError("measured time availability must match the time-consequence stage")
        if self.measured_time_consequence_available != bool(
            self.performance_opportunity_ids
        ):
            raise ValueError(
                "measured P32 time requires exactly one performance opportunity identity"
            )
        if self.performance_opportunity_ids and (
            self.chain[-1].source_artifact_ids != self.performance_opportunity_ids
        ):
            raise ValueError(
                "the time-consequence stage must bind the selected P32 opportunity"
            )
        if self.candidates and len(self.performance_opportunity_ids) != 1:
            raise ValueError("P35 candidates require one selected P32 opportunity")
        if self.candidates and len(self.response_observations) != 1:
            raise ValueError("P35 candidates require one phase-response observation")
        if self.response_observations and not (
            self.performance_opportunity_ids and self.response_regime is not None
        ):
            raise ValueError(
                "phase response requires measured time and a reviewed response regime"
            )
        if bool(self.problem_signature) != bool(self.response_observations):
            raise ValueError("problem signature must bind the phase response")
        if self.response_observations:
            response = self.response_observations[0]
            chain_source_ids = {
                artifact_id
                for stage in self.chain
                for artifact_id in stage.source_artifact_ids
            }
            chain_source_channels = {
                channel for stage in self.chain for channel in stage.source_channels
            }
            if (
                response.run_id != self.run_id
                or response.opportunity_id != self.performance_opportunity_ids[0]
                or self.problem_signature is None
                or self.problem_signature.response_observation_id != response.observation_id
                or self.problem_signature.opportunity_id != response.opportunity_id
            ):
                raise ValueError("P35.4 response/signature scope is not atomic")
            if not set(response.source_artifact_ids) <= chain_source_ids:
                raise ValueError("phase-response sources must resolve through the chain")
            if not set(response.source_channels) <= chain_source_channels:
                raise ValueError("phase-response channels must resolve through the chain")
            signature = self.problem_signature
            elapsed_metrics = tuple(
                metric
                for metric in response.metrics
                if metric.quantity == "elapsed_time_delta_s"
            )
            if len(elapsed_metrics) != 1:
                raise ValueError("phase response requires one elapsed-time metric")
            if (
                signature.phase != response.phase
                or signature.onset_pct != response.onset_pct
                or signature.onset_resolution != response.onset_resolution
                or signature.response_regime != response.response_regime
                or signature.driver_demand_state != response.driver_demand_state
                or signature.vehicle_response_state != response.vehicle_response_state
                or signature.line_state != response.line_state
                or signature.local_time_delta_s != elapsed_metrics[0].value
            ):
                raise ValueError("problem signature must exactly mirror response truth")
            expected_traffic = (
                "blocked"
                if self.traffic_blocked
                else "clear"
                if response.context_state == "qualified"
                else "unavailable"
            )
            if signature.traffic_dependence != expected_traffic:
                raise ValueError("problem-signature traffic state does not match context")
            if self.traffic_blocked and response.context_state != "blocked":
                raise ValueError("traffic-blocked assessment requires blocked response context")
        elif self.problem_signature is not None:
            raise ValueError("problem signature cannot exist without a phase response")
        if len(self.mechanism_separation) != len(self.candidates):
            raise ValueError("every mechanism candidate requires one separation row")
        if tuple(
            item.mechanism_id for item in self.mechanism_separation
        ) != tuple(
            item.mechanism_id for item in self.candidates
        ):
            raise ValueError("mechanism separation order must match current candidates")
        if any(
            item.response_observation_id != self.response_observations[0].observation_id
            for item in self.mechanism_separation
        ):
            raise ValueError("mechanism separation must bind the current response observation")
        focus_ids = {item.artifact_id for item in self.focus_artifacts}
        focus_by_id = {item.artifact_id: item for item in self.focus_artifacts}
        for artifact_id in (
            self.strongest_support_artifact_id,
            self.strongest_contradiction_artifact_id,
        ):
            if artifact_id is not None and artifact_id not in focus_ids:
                raise ValueError("strongest P35 evidence must reference one focus artifact")
        if self.candidates and self.next_discriminator_contract_id is None:
            raise ValueError("mechanism candidates require a next discriminator")
        for values, label in (
            (self.p32_performance_mechanism_ids, "P32 mechanism"),
            (self.performance_opportunity_ids, "performance opportunity"),
            (self.tire_demand_state_ids, "tire-demand state"),
            (self.load_path_ids, "load path"),
            (self.unavailable_quantity_ids, "unavailable quantity"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"P35 assessment {label} identities must be unique")
        candidate_ids = [item.mechanism_id for item in self.candidates]
        focus_id_values = [item.artifact_id for item in self.focus_artifacts]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("P35 candidate mechanism identities must be unique")
        if len(focus_id_values) != len(set(focus_id_values)):
            raise ValueError("P35 focus artifact identities must be unique")
        candidate_focus_ids = {
            artifact_id
            for candidate in self.candidates
            for artifact_id in (
                *candidate.support_artifact_ids,
                *candidate.contradiction_artifact_ids,
            )
        }
        if not candidate_focus_ids <= focus_ids:
            raise ValueError("candidate evidence IDs must reference P35 focus artifacts")
        if any(
            focus_by_id[artifact_id].polarity != "support"
            or focus_by_id[artifact_id].mechanism_id != candidate.mechanism_id
            for candidate in self.candidates
            for artifact_id in candidate.support_artifact_ids
        ):
            raise ValueError("candidate support must reference same-mechanism support focus")
        if any(
            focus_by_id[artifact_id].polarity not in {"contradiction", "uncertainty"}
            or focus_by_id[artifact_id].mechanism_id != candidate.mechanism_id
            for candidate in self.candidates
            for artifact_id in candidate.contradiction_artifact_ids
        ):
            raise ValueError(
                "candidate contradiction IDs require same-mechanism contradiction/uncertainty focus"
            )
        candidate_by_mechanism = {
            candidate.mechanism_id: candidate for candidate in self.candidates
        }
        separation_by_mechanism = {
            row.mechanism_id: row for row in self.mechanism_separation
        }
        response = self.response_observations[0] if self.response_observations else None
        for candidate in self.candidates:
            row = separation_by_mechanism[candidate.mechanism_id]
            expected_state = (
                "alive" if candidate.relevance == "candidate" else "blocked"
            )
            if (
                row.state != expected_state
                or row.required_response_kpi_ids
                != (candidate.discriminator_contract_ids[0],)
                or row.support_artifact_ids != candidate.support_artifact_ids
                or row.contradiction_artifact_ids
                != candidate.contradiction_artifact_ids
                or row.discriminator_contract_ids
                != candidate.discriminator_contract_ids
                or row.component_family_ids != candidate.component_family_ids
            ):
                raise ValueError(
                    "mechanism separation must exactly mirror its candidate contract"
                )
            if candidate.relevance == "blocked" and (
                row.missing_evidence != candidate.blocker_reasons
            ):
                raise ValueError(
                    "blocked separation evidence must equal candidate blockers"
                )
            if candidate.relevance == "candidate" and (
                response is None
                or response.driver_demand_state != "matched"
                or response.vehicle_response_state != "changed"
                or response.line_state != "matched"
                or response.context_state != "qualified"
                or self.traffic_blocked
            ):
                raise ValueError(
                    "positive mechanism support requires matched demand, line, response, and context"
                )
        for focus in self.focus_artifacts:
            candidate = candidate_by_mechanism.get(focus.mechanism_id)
            if candidate is None:
                raise ValueError(
                    "every P35 focus must be owned by a same-mechanism candidate relation"
                )
            if focus.polarity == "support":
                owned = focus.artifact_id in candidate.support_artifact_ids
            elif focus.polarity in {"contradiction", "uncertainty"}:
                owned = focus.artifact_id in candidate.contradiction_artifact_ids
            else:
                owned = bool(
                    focus.observation_contract_id is not None
                    and focus.observation_contract_id
                    in candidate.discriminator_contract_ids
                    and focus.artifact_id not in candidate.support_artifact_ids
                    and focus.artifact_id not in candidate.contradiction_artifact_ids
                )
            if not owned:
                raise ValueError(
                    "every P35 focus must be owned by a same-mechanism candidate relation"
                )
        if response is not None:
            all_response_laps = (
                *response.source_lap_numbers,
                *response.reference_lap_numbers,
            )
            opportunity_sources = (response.opportunity_id,)
            for candidate in self.candidates:
                support_focus = tuple(
                    focus_by_id[artifact_id]
                    for artifact_id in candidate.support_artifact_ids
                )
                contradiction_focus = tuple(
                    focus_by_id[artifact_id]
                    for artifact_id in candidate.contradiction_artifact_ids
                )
                discriminator_focus = tuple(
                    focus
                    for focus in self.focus_artifacts
                    if focus.mechanism_id == candidate.mechanism_id
                    and focus.observation_contract_id is not None
                )
                if (
                    len(candidate.support_artifact_ids) > 1
                    or len(contradiction_focus) != 1
                    or len(discriminator_focus) != 1
                ):
                    raise ValueError(
                        "each mechanism requires bounded support, contradiction, and discriminator focus"
                    )
                if any(
                    focus.stage is not DynamicsChainStageKind.VEHICLE_RESPONSE
                    or focus.observation_contract_id is not None
                    or focus.source_artifact_ids == opportunity_sources
                    or focus.lap_numbers != response.source_lap_numbers
                    or focus.lap_pct_start != response.lap_pct_start
                    or focus.lap_pct_end != response.lap_pct_end
                    or focus.phase != response.phase
                    for focus in support_focus
                ):
                    raise ValueError("P35 support focus must match source response scope")
                challenge = contradiction_focus[0]
                if (
                    challenge.stage is not DynamicsChainStageKind.TIRE_PLATFORM_STATE
                    or challenge.observation_contract_id is not None
                    or challenge.source_artifact_ids != opportunity_sources
                    or challenge.lap_numbers != all_response_laps
                    or challenge.lap_pct_start != response.lap_pct_start
                    or challenge.lap_pct_end != response.lap_pct_end
                    or challenge.phase != response.phase
                ):
                    raise ValueError(
                        "P35 contradiction focus must match the full response comparison"
                    )
                discriminator = discriminator_focus[0]
                if (
                    discriminator.observation_contract_id
                    != candidate.discriminator_contract_ids[0]
                    or discriminator.polarity != "neutral"
                    or discriminator.stage
                    is not DynamicsChainStageKind.TIRE_PLATFORM_STATE
                    or discriminator.source_artifact_ids != opportunity_sources
                    or discriminator.lap_numbers != all_response_laps
                    or discriminator.lap_pct_start != response.lap_pct_start
                    or discriminator.lap_pct_end != response.lap_pct_end
                    or discriminator.phase != response.phase
                ):
                    raise ValueError(
                        "P35 discriminator focus must match its exact comparison contract"
                    )
        chain_source_ids = {
            artifact_id for stage in self.chain for artifact_id in stage.source_artifact_ids
        }
        if any(
            not set(item.source_artifact_ids) <= chain_source_ids
            for item in self.focus_artifacts
        ):
            raise ValueError("P35 focus sources must resolve through the current evidence chain")
        discriminator_ids = {
            contract_id
            for candidate in self.candidates
            for contract_id in candidate.discriminator_contract_ids
        }
        if (
            self.next_discriminator_contract_id is not None
            and self.next_discriminator_contract_id not in discriminator_ids
        ):
            raise ValueError("next P35 discriminator must belong to a current candidate")
        has_supported_candidate = any(
            candidate.relevance == "candidate" for candidate in self.candidates
        )
        if self.candidates and self.strongest_contradiction_artifact_id is None:
            raise ValueError(
                "candidate assessments require strongest contradiction/uncertainty"
            )
        if has_supported_candidate and self.strongest_support_artifact_id is None:
            raise ValueError("unblocked candidate assessments require strongest support")
        if not has_supported_candidate and self.strongest_support_artifact_id is not None:
            raise ValueError("all-blocked candidate assessments cannot publish strongest support")
        if self.strongest_support_artifact_id is not None and (
            focus_by_id[self.strongest_support_artifact_id].polarity != "support"
        ):
            raise ValueError("strongest P35 support must carry support polarity")
        if self.strongest_contradiction_artifact_id is not None and (
            focus_by_id[self.strongest_contradiction_artifact_id].polarity
            not in {"contradiction", "uncertainty"}
        ):
            raise ValueError(
                "strongest P35 contradiction must carry contradiction or uncertainty polarity"
            )
        candidate_support_ids = {
            artifact_id
            for candidate in self.candidates
            for artifact_id in candidate.support_artifact_ids
        }
        candidate_contradiction_ids = {
            artifact_id
            for candidate in self.candidates
            for artifact_id in candidate.contradiction_artifact_ids
        }
        if (
            self.strongest_support_artifact_id is not None
            and self.strongest_support_artifact_id not in candidate_support_ids
        ):
            raise ValueError("strongest P35 support must belong to a current candidate")
        if (
            self.strongest_contradiction_artifact_id is not None
            and self.strongest_contradiction_artifact_id
            not in candidate_contradiction_ids
        ):
            raise ValueError(
                "strongest P35 contradiction must belong to a current candidate"
            )
        if any(
            not set(candidate.p32_performance_mechanism_ids)
            <= set(self.p32_performance_mechanism_ids)
            for candidate in self.candidates
        ):
            raise ValueError("candidate P32 bridge IDs must belong to the assessment")
        if not self.candidates and any(
            value is not None
            for value in (
                self.strongest_support_artifact_id,
                self.strongest_contradiction_artifact_id,
                self.next_discriminator_contract_id,
            )
        ):
            raise ValueError("empty candidate assessments cannot publish candidate evidence")
        if not (info.context or {}).get("skip_content_hash"):
            expected = performance_mechanism_assessment_hash(self)
            if self.p35_assessment_sha256 != expected:
                raise ValueError("P35 assessment hash does not match canonical content")
        return self


def vehicle_dynamics_graph_hash(graph: VehicleDynamicsKnowledgeGraph) -> str:
    return canonical_json_sha256(
        graph.model_dump(
            mode="json",
            exclude={"content_sha256", "graph_id", "graph_version"},
        )
    )


def build_vehicle_dynamics_knowledge_graph(
    payload: dict[str, Any],
) -> VehicleDynamicsKnowledgeGraph:
    forbidden = {"content_sha256", "graph_id", "graph_version"} & set(payload)
    if forbidden:
        raise ValueError("vehicle-dynamics content identity is derived, not caller supplied")
    provisional = VehicleDynamicsKnowledgeGraph.model_validate(
        {
            **payload,
            "content_sha256": "0" * 64,
            "graph_id": f"p35vdg_{'0' * 24}",
            "graph_version": f"2026.08.next-gen-oval.v1:{'0' * 12}",
        },
        context={"skip_content_hash": True},
    )
    digest = vehicle_dynamics_graph_hash(provisional)
    return VehicleDynamicsKnowledgeGraph.model_validate(
        {
            **provisional.model_dump(
                mode="json",
                exclude={"content_sha256", "graph_id", "graph_version"},
            ),
            "content_sha256": digest,
            "graph_id": f"p35vdg_{digest[:24]}",
            "graph_version": f"2026.08.next-gen-oval.v1:{digest[:12]}",
        }
    )


def vehicle_dynamics_runtime_trust_hash(
    manifest: VehicleDynamicsRuntimeTrustManifest,
) -> str:
    return canonical_json_sha256(
        manifest.model_dump(mode="json", exclude={"runtime_trust_sha256"})
    )


def build_vehicle_dynamics_runtime_trust_manifest(
    payload: dict[str, Any],
) -> VehicleDynamicsRuntimeTrustManifest:
    if "runtime_trust_sha256" in payload:
        raise ValueError("runtime-trust content identity is derived, not caller supplied")
    provisional = VehicleDynamicsRuntimeTrustManifest.model_validate(
        {**payload, "runtime_trust_sha256": "0" * 64},
        context={"skip_content_hash": True},
    )
    digest = vehicle_dynamics_runtime_trust_hash(provisional)
    return VehicleDynamicsRuntimeTrustManifest.model_validate(
        {
            **provisional.model_dump(mode="json", exclude={"runtime_trust_sha256"}),
            "runtime_trust_sha256": digest,
        }
    )


def performance_mechanism_assessment_hash(
    assessment: PerformanceMechanismAssessment,
) -> str:
    return canonical_json_sha256(
        assessment.model_dump(mode="json", exclude={"p35_assessment_sha256"})
    )


def build_performance_mechanism_assessment(
    payload: dict[str, Any],
) -> PerformanceMechanismAssessment:
    if "p35_assessment_sha256" in payload:
        raise ValueError("P35 assessment identity is derived, not caller supplied")
    provisional = PerformanceMechanismAssessment.model_validate(
        {**payload, "p35_assessment_sha256": "0" * 64},
        context={"skip_content_hash": True},
    )
    digest = performance_mechanism_assessment_hash(provisional)
    return PerformanceMechanismAssessment.model_validate(
        {
            **provisional.model_dump(mode="json", exclude={"p35_assessment_sha256"}),
            "p35_assessment_sha256": digest,
        }
    )


def _lookup(values: tuple[Any, ...], identity: str, label: str) -> Any:
    for item in values:
        if item.definition_id == identity:
            return item
    raise KeyError(f"Unknown vehicle-dynamics {label}: {identity}")


def _version_key(value: str) -> tuple[int, tuple[int, ...] | tuple[str, ...]]:
    parts = value.split(".")
    if parts and all(part.isdigit() for part in parts):
        return (0, tuple(int(part) for part in parts))
    return (1, (value,))


__all__ = [name for name in globals() if not name.startswith("_")]
