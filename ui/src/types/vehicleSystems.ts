import type { EvidenceState } from "./telemetry";

export const VEHICLE_SYSTEM_COMPONENT_IDS = [
  "tires",
  "alignment",
  "springs",
  "dampers",
  "anti_roll_bars",
  "weight_distribution",
  "platform",
  "brakes",
  "differential",
  "final_drive",
  "steering",
  "cooling_configuration",
] as const;

export type VehicleSystemComponentId = typeof VEHICLE_SYSTEM_COMPONENT_IDS[number];

export function isVehicleSystemComponentId(value: unknown): value is VehicleSystemComponentId {
  return typeof value === "string"
    && VEHICLE_SYSTEM_COMPONENT_IDS.includes(value as VehicleSystemComponentId);
}

export type ComponentObservabilityState =
  | "definition_known"
  | "setup_captured"
  | "live_response_observable"
  | "current_response_observed"
  | "mechanism_supported"
  | "controlled_response_known"
  | "exact_context_policy_known"
  | "unavailable";

export type ComponentRelevance =
  | "irrelevant"
  | "candidate"
  | "supported"
  | "contradicted"
  | "blocked"
  | "tested";

export type VehicleSystemsNodeKind =
  | "component"
  | "engineering_area"
  | "control"
  | "component_property"
  | "vehicle_state"
  | "observation"
  | "symptom"
  | "outcome"
  | "context";

export type VehicleSystemsEdgeKind =
  | "component_has_engineering_area"
  | "engineering_area_has_control"
  | "control_adjusts_property"
  | "property_expected_to_influence_state"
  | "state_may_present_as_symptom"
  | "state_observable_by"
  | "component_couples_with_component"
  | "control_requires_invariant"
  | "control_has_countereffect"
  | "observation_supports_state"
  | "observation_contradicts_state"
  | "controlled_test_observed_response"
  | "policy_rejected_due_to_countereffect";

export type BuildApplicability = {
  car_family: string;
  car_paths: string[];
  car_versions: string[];
  iracing_build_min: string | null;
  iracing_build_max: string | null;
  track_package_types: string[];
  source_version: string;
};

export type VehicleSystemsRuntimeIdentity = {
  run_id: string;
  car_path: string;
  car_version: string;
  iracing_build_version: string;
  track_configuration_name: string;
  source_file_sha256: string;
  telemetry_cache_sha256: string;
  schema_fingerprint: string;
  compatibility_fingerprint: string;
  available_telemetry_channels: string[];
  source: "verified_telemetry_artifact";
};

export type ComponentObservabilityContract = {
  static_setting_channels: string[];
  live_telemetry_channels: string[];
  derived_metrics: string[];
  indirect_proxies: string[];
  unavailable_quantities: string[];
  interpretation_blockers: string[];
};

export type ComponentInteraction = {
  interaction_id: string;
  source_component_id: string;
  target_component_id: string;
  interaction_type:
    | "mechanically_coupled"
    | "garage_autocompensated"
    | "requires_manual_recheck"
    | "setup_only_relationship"
    | "telemetry_observable"
    | "unknown_for_build";
  description: string;
  applicability: BuildApplicability;
  source_ids: string[];
  authority: "engineering_expectation_only";
};

export type ComponentDefinition = {
  component_id: string;
  system_id: string;
  label: string;
  physical_location: string;
  physical_role: string;
  applicability: BuildApplicability;
  adjustable_property_ids: string[];
  operating_phases: string[];
  speed_load_relevance: string;
  setup_keys: string[];
  coordinated_control_groups: string[][];
  observability: ComponentObservabilityContract;
  coupled_component_ids: string[];
  compensating_control_keys: string[];
  invariants: string[];
  expected_state_ids: string[];
  symptom_ids: string[];
  performance_targets: string[];
  countereffects: string[];
  supporting_signatures: string[];
  contradicting_signatures: string[];
  confounders: string[];
  measurement_requirements: string[];
  rollback_conditions: string[];
  source_ids: string[];
  evidence_authority_ceiling: "hypothesis_only";
};

export type VehicleSystemsNode = {
  node_id: string;
  kind: VehicleSystemsNodeKind;
  label: string;
  description: string | null;
  component_id: string | null;
  engineering_area_mode: "static_setup" | "live_telemetry" | "derived_proxy" | "mixed" | null;
  source_ids: string[];
  authority: "knowledge_only" | "observation_only" | "controlled_history";
};

export type VehicleSystemsEdge = {
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
  kind: VehicleSystemsEdgeKind;
  direction: "increase" | "decrease" | "bidirectional" | "observed" | null;
  interaction_type: string | null;
  source_ids: string[];
  authority: "engineering_expectation_only" | "observation_only" | "controlled_history";
};

export type SetupExperimentFactor = {
  factor_id: string;
  component_id: string;
  physical_property_id: string;
  primary_controls: string[];
  coordinated_controls: string[];
  automatic_sim_compensations: string[];
  required_manual_compensations: string[];
  invariants_to_hold: string[];
  preconditions: string[];
  expected_component_response: string[];
  expected_vehicle_response: string[];
  countereffects: string[];
  success_metrics: string[];
  rollback_rule: string;
  source_ids: string[];
  authority: "experiment_definition_only";
  setup_authorized: false;
};

export type ComponentControlledHistory = {
  workflow_id: string;
  source_run_id: string;
  stage_run_ids: string[];
  eligible_lap_ids: string[];
  control_key: string;
  metric: string;
  phase: string;
  mechanism_state: string;
  control_response: string;
  policy_verdict: "keep" | "undo" | "retest" | "invalid";
  countereffects: string[];
  blocker_reasons: string[];
  diagnostic_validity: "mechanism_diagnostic" | "control_response_only";
  exact_context: boolean;
};

export type ComponentObservationScope = {
  artifact_id: string;
  observation_id: string;
  lap_number: number;
  phase: string;
  lap_pct_start: number;
  lap_pct_end: number;
};

export type QuantityObservabilityCertificate = {
  quantity_id: string;
  required_channels: string[];
  available_channels: string[];
  missing_channels: string[];
  health_basis: "qualified_producer" | "manifest_presence_only" | "missing";
  minimum_coobserved_coverage: number;
  coobserved_coverage: number | null;
  state: "observed" | "screenable" | "unavailable";
  producer_artifact_ids: string[];
  supported_derived_outputs: string[];
  blocker_reasons: string[];
};

export type ComponentAwarenessState = {
  component_id: string;
  run_id: string;
  observation_scopes: ComponentObservationScope[];
  current_settings: string[];
  present_setting_keys: string[];
  missing_setting_keys: string[];
  current_setting_provenance: string[];
  observability_states: ComponentObservabilityState[];
  quantity_observability: QuantityObservabilityCertificate[];
  current_response_state: "observed" | "not_observed" | "unavailable";
  relevance: ComponentRelevance;
  supporting_artifact_ids: string[];
  supporting_citation_ids: string[];
  contradicting_citation_ids: string[];
  supporting_cause_ids: string[];
  contradicting_cause_ids: string[];
  confounders: string[];
  unavailable_quantities: string[];
  measurement_requirements: string[];
  coupled_component_ids: string[];
  interaction_summaries: string[];
  controlled_history: ComponentControlledHistory[];
  blocked_control_keys: string[];
  testable_control_keys: string[];
  authorized_control_key: string | null;
  available_live_channel_ids: string[];
  live_response_blocker_reasons: string[];
  next_discriminator: string;
  current_testability: "measurement_only" | "policy_blocked" | "p19_authorized";
  authority_state: "knowledge_only" | "observation_only" | "controlled_history" | "p19_authorized";
  evidence_states: EvidenceState[];
  blocker_reasons: string[];
  setup_authorized: boolean;
};

export type VehicleSystemsRuntimeGraph = {
  schema_version: "p26.runtime-graph.v3";
  reasoning_snapshot_sha256: string;
  nodes: VehicleSystemsNode[];
  edges: VehicleSystemsEdge[];
  authority: "observation_and_controlled_history_only";
  setup_authorized: false;
};

export type VehicleSystemsProjection = {
  schema_version: "p26.component-awareness.v4";
  run_id: string;
  session_id: string | null;
  graph_version: string;
  knowledge_graph_sha256: string;
  reasoning_snapshot_sha256: string;
  setup_id: string | null;
  setup_snapshot_sha256: string | null;
  runtime_identity: VehicleSystemsRuntimeIdentity;
  leading_system: string;
  leading_component_ids: string[];
  next_discriminator: string;
  strongest_contradiction: string;
  knowledge_debt: string[];
  component_states: ComponentAwarenessState[];
  experiment_factors: SetupExperimentFactor[];
  runtime_graph: VehicleSystemsRuntimeGraph;
  authority: "p19_projection_only";
  setup_authorized: boolean;
};

export type ComponentInspectionResponse = {
  run_id: string;
  session_id: string | null;
  graph_version: string;
  knowledge_graph_sha256: string;
  reasoning_snapshot_sha256: string;
  setup_id: string | null;
  setup_snapshot_sha256: string | null;
  runtime_identity: VehicleSystemsRuntimeIdentity;
  component_id: string;
  definition: ComponentDefinition;
  state: ComponentAwarenessState;
  interactions: ComponentInteraction[];
  controls: string[];
  authority: "p19_projection_only";
};

export type ControlMechanismTraceResponse = {
  run_id: string;
  control_key: string;
  graph_version: string;
  graph_content_sha256: string;
  runtime_identity: VehicleSystemsRuntimeIdentity;
  authority: "engineering_expectation_only";
  setup_authorized: false;
  nodes: VehicleSystemsNode[];
  edges: VehicleSystemsEdge[];
};

export type VehicleSystemsScopeExpectation = {
  runId: string;
  sessionId: string | null;
  setupId?: string | null;
};

type UnknownRecord = Record<string, unknown>;

const sha256Pattern = /^[0-9a-f]{64}$/;
const buildPattern = /^\d{4}\.\d{2}\.\d{2}\.\d{2}$/;
const nextGenCarPaths = [
  "stockcars chevycamarozl12022",
  "stockcars fordmustang2022",
  "stockcars toyotacamry2022",
] as const;
const nextGenCarVersion = "2026.06.08.02";
const nextGenBuildMin = "2026.01.00.00";
const nextGenBuildMax = "2026.06.24.02";
const observabilityStates: readonly ComponentObservabilityState[] = [
  "definition_known", "setup_captured", "live_response_observable",
  "current_response_observed", "mechanism_supported", "controlled_response_known",
  "exact_context_policy_known", "unavailable",
];
const relevanceStates: readonly ComponentRelevance[] = [
  "irrelevant", "candidate", "supported", "contradicted", "blocked", "tested",
];
const evidenceStates: readonly EvidenceState[] = [
  "measured", "calculated", "estimated_proxy", "observed_correlation",
  "controlled_test_effect", "unavailable", "blocked_by_context", "needs_confirmation",
];
const nodeKinds: readonly VehicleSystemsNodeKind[] = [
  "component", "engineering_area", "control", "component_property", "vehicle_state", "observation",
  "symptom", "outcome", "context",
];
const edgeKinds: readonly VehicleSystemsEdgeKind[] = [
  "component_has_engineering_area", "engineering_area_has_control",
  "control_adjusts_property", "property_expected_to_influence_state",
  "state_may_present_as_symptom", "state_observable_by", "component_couples_with_component",
  "control_requires_invariant", "control_has_countereffect", "observation_supports_state",
  "observation_contradicts_state", "controlled_test_observed_response",
  "policy_rejected_due_to_countereffect",
];
const runtimeEdgeKinds = new Set<VehicleSystemsEdgeKind>([
  "observation_supports_state", "observation_contradicts_state",
  "controlled_test_observed_response", "policy_rejected_due_to_countereffect",
]);
const interactionTypes = [
  "mechanically_coupled", "garage_autocompensated", "requires_manual_recheck",
  "setup_only_relationship", "telemetry_observable", "unknown_for_build",
] as const;
const responseStates = ["observed", "not_observed", "unavailable"] as const;
const testabilityStates = ["measurement_only", "policy_blocked", "p19_authorized"] as const;
const authorityStates = ["knowledge_only", "observation_only", "controlled_history", "p19_authorized"] as const;
const historyVerdicts = ["keep", "undo", "retest", "invalid"] as const;
const diagnosticValidity = ["mechanism_diagnostic", "control_response_only"] as const;
const edgeDirections = ["increase", "decrease", "bidirectional", "observed"] as const;
const engineeringAreaModes = ["static_setup", "live_telemetry", "derived_proxy", "mixed"] as const;

const allowedEdgeEndpoints: Record<VehicleSystemsEdgeKind, [VehicleSystemsNodeKind[], VehicleSystemsNodeKind[]]> = {
  component_has_engineering_area: [["component"], ["engineering_area"]],
  engineering_area_has_control: [["engineering_area"], ["control"]],
  control_adjusts_property: [["control"], ["component_property"]],
  property_expected_to_influence_state: [["component_property"], ["vehicle_state"]],
  state_may_present_as_symptom: [["vehicle_state"], ["symptom"]],
  state_observable_by: [["vehicle_state"], ["observation"]],
  component_couples_with_component: [["component"], ["component"]],
  control_requires_invariant: [["control"], ["context"]],
  control_has_countereffect: [["control"], ["outcome"]],
  observation_supports_state: [["observation"], ["vehicle_state"]],
  observation_contradicts_state: [["observation"], ["vehicle_state"]],
  controlled_test_observed_response: [["control"], ["outcome"]],
  policy_rejected_due_to_countereffect: [["outcome"], ["outcome"]],
};

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isCanonicalString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.trim() === value;
}

function isNullableCanonicalString(value: unknown): value is string | null {
  return value === null || isCanonicalString(value);
}

function isEnumValue<T extends string>(value: unknown, values: readonly T[]): value is T {
  return typeof value === "string" && values.includes(value as T);
}

function isStringArray(value: unknown, minimum = 0, unique = false): value is string[] {
  return Array.isArray(value)
    && value.length >= minimum
    && value.every(isCanonicalString)
    && (!unique || new Set(value).size === value.length);
}

function isNullableNumber(
  value: unknown,
  minimum: number,
  maximum: number,
  integer = false,
): value is number | null {
  return value === null || (
    typeof value === "number"
    && Number.isFinite(value)
    && value >= minimum
    && value <= maximum
    && (!integer || Number.isInteger(value))
  );
}

function sameStringSet(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((item) => right.includes(item));
}

function sameStringSequence(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function isBuildApplicability(value: unknown): value is BuildApplicability {
  if (!isRecord(value)) return false;
  const min = value.iracing_build_min;
  const max = value.iracing_build_max;
  return value.car_family === "next_gen"
    && isStringArray(value.car_paths, nextGenCarPaths.length, true)
    && sameStringSet(value.car_paths, nextGenCarPaths)
    && isStringArray(value.car_versions, 1, true)
    && sameStringSet(value.car_versions, [nextGenCarVersion])
    && isStringArray(value.track_package_types, 1, true)
    && sameStringSet(value.track_package_types, ["oval"])
    && isCanonicalString(value.source_version)
    && min === nextGenBuildMin
    && max === nextGenBuildMax;
}

function isRuntimeIdentity(value: unknown, runId: string): value is VehicleSystemsRuntimeIdentity {
  if (!isRecord(value)) return false;
  return value.run_id === runId
    && value.source === "verified_telemetry_artifact"
    && isEnumValue(value.car_path, nextGenCarPaths)
    && value.car_version === nextGenCarVersion
    && typeof value.iracing_build_version === "string"
    && buildPattern.test(value.iracing_build_version)
    && value.iracing_build_version >= nextGenBuildMin
    && value.iracing_build_version <= nextGenBuildMax
    && value.track_configuration_name === "Oval"
    && [
      value.source_file_sha256,
      value.telemetry_cache_sha256,
      value.schema_fingerprint,
      value.compatibility_fingerprint,
    ].every((item) => typeof item === "string" && sha256Pattern.test(item))
    && isStringArray(value.available_telemetry_channels, 1, true);
}

function runtimeIdentityMatches(
  left: VehicleSystemsRuntimeIdentity,
  right: VehicleSystemsRuntimeIdentity,
): boolean {
  return left.run_id === right.run_id
    && left.car_path === right.car_path
    && left.car_version === right.car_version
    && left.iracing_build_version === right.iracing_build_version
    && left.track_configuration_name === right.track_configuration_name
    && left.source_file_sha256 === right.source_file_sha256
    && left.telemetry_cache_sha256 === right.telemetry_cache_sha256
    && left.schema_fingerprint === right.schema_fingerprint
    && left.compatibility_fingerprint === right.compatibility_fingerprint
    && left.source === right.source
    && sameStringSequence(left.available_telemetry_channels, right.available_telemetry_channels);
}

function isObservabilityContract(value: unknown): value is ComponentObservabilityContract {
  if (!isRecord(value)) return false;
  return isStringArray(value.static_setting_channels, 0, true)
    && isStringArray(value.live_telemetry_channels, 0, true)
    && isStringArray(value.derived_metrics, 0, true)
    && isStringArray(value.indirect_proxies, 0, true)
    && isStringArray(value.unavailable_quantities, 1, true)
    && isStringArray(value.interpretation_blockers, 1, true);
}

function isComponentDefinition(value: unknown): value is ComponentDefinition {
  if (!isRecord(value)) return false;
  return [
    value.component_id, value.system_id, value.label, value.physical_location,
    value.physical_role, value.speed_load_relevance,
  ].every(isCanonicalString)
    && isBuildApplicability(value.applicability)
    && isStringArray(value.adjustable_property_ids, 1, true)
    && isStringArray(value.operating_phases, 1, true)
    && isStringArray(value.setup_keys, 0, true)
    && Array.isArray(value.coordinated_control_groups)
    && value.coordinated_control_groups.every((group) => isStringArray(group, 1, true))
    && isObservabilityContract(value.observability)
    && isStringArray(value.coupled_component_ids, 0, true)
    && isStringArray(value.compensating_control_keys, 0, true)
    && isStringArray(value.invariants)
    && isStringArray(value.expected_state_ids, 1, true)
    && isStringArray(value.symptom_ids, 1, true)
    && isStringArray(value.performance_targets, 1, true)
    && isStringArray(value.countereffects, 1)
    && isStringArray(value.supporting_signatures, 1)
    && isStringArray(value.contradicting_signatures, 1)
    && isStringArray(value.confounders, 1)
    && isStringArray(value.measurement_requirements, 1)
    && isStringArray(value.rollback_conditions, 1)
    && isStringArray(value.source_ids, 1, true)
    && value.evidence_authority_ceiling === "hypothesis_only";
}

function isComponentInteraction(value: unknown): value is ComponentInteraction {
  if (!isRecord(value)) return false;
  return isCanonicalString(value.interaction_id)
    && isCanonicalString(value.source_component_id)
    && isCanonicalString(value.target_component_id)
    && value.source_component_id !== value.target_component_id
    && isEnumValue(value.interaction_type, interactionTypes)
    && isCanonicalString(value.description)
    && isBuildApplicability(value.applicability)
    && isStringArray(value.source_ids, 1, true)
    && value.authority === "engineering_expectation_only";
}

function isVehicleSystemsNode(value: unknown): value is VehicleSystemsNode {
  if (!isRecord(value)) return false;
  return isCanonicalString(value.node_id)
    && isEnumValue(value.kind, nodeKinds)
    && isCanonicalString(value.label)
    && isNullableCanonicalString(value.description)
    && isNullableCanonicalString(value.component_id)
    && (value.engineering_area_mode === null
      || isEnumValue(value.engineering_area_mode, engineeringAreaModes))
    && ((value.kind === "engineering_area") === (value.engineering_area_mode !== null))
    && isStringArray(value.source_ids, 1, true)
    && isEnumValue(value.authority, ["knowledge_only", "observation_only", "controlled_history"] as const);
}

function isVehicleSystemsEdge(value: unknown): value is VehicleSystemsEdge {
  if (!isRecord(value)) return false;
  return [value.edge_id, value.source_node_id, value.target_node_id].every(isCanonicalString)
    && isEnumValue(value.kind, edgeKinds)
    && (value.direction === null || isEnumValue(value.direction, edgeDirections))
    && isNullableCanonicalString(value.interaction_type)
    && isStringArray(value.source_ids, 1, true)
    && isEnumValue(
      value.authority,
      ["engineering_expectation_only", "observation_only", "controlled_history"] as const,
    );
}

function isExperimentFactor(value: unknown): value is SetupExperimentFactor {
  if (!isRecord(value)) return false;
  const primary = value.primary_controls;
  const coordinated = value.coordinated_controls;
  return [value.factor_id, value.component_id, value.physical_property_id, value.rollback_rule]
    .every(isCanonicalString)
    && isStringArray(primary, 1, true)
    && isStringArray(coordinated, 0, true)
    && new Set([...(primary as string[]), ...(coordinated as string[])]).size
      === (primary as string[]).length + (coordinated as string[]).length
    && isStringArray(value.automatic_sim_compensations)
    && isStringArray(value.required_manual_compensations)
    && isStringArray(value.invariants_to_hold, 1)
    && isStringArray(value.preconditions, 1)
    && isStringArray(value.expected_component_response, 1)
    && isStringArray(value.expected_vehicle_response, 1)
    && isStringArray(value.countereffects, 1)
    && isStringArray(value.success_metrics, 1)
    && isStringArray(value.source_ids, 1, true)
    && value.authority === "experiment_definition_only"
    && value.setup_authorized === false;
}

function isControlledHistory(value: unknown): value is ComponentControlledHistory {
  if (!isRecord(value)) return false;
  return [
    value.workflow_id, value.source_run_id, value.control_key, value.metric,
    value.phase, value.mechanism_state, value.control_response,
  ].every(isCanonicalString)
    && isStringArray(value.stage_run_ids, 0, true)
    && isStringArray(value.eligible_lap_ids, 0, true)
    && isEnumValue(value.policy_verdict, historyVerdicts)
    && isStringArray(value.countereffects)
    && isStringArray(value.blocker_reasons)
    && isEnumValue(value.diagnostic_validity, diagnosticValidity)
    && typeof value.exact_context === "boolean"
    && !(value.policy_verdict === "invalid" && value.exact_context);
}

function isObservationScope(value: unknown): value is ComponentObservationScope {
  if (!isRecord(value)) return false;
  return isCanonicalString(value.artifact_id)
    && isCanonicalString(value.observation_id)
    && isNullableNumber(value.lap_number, 0, Number.MAX_SAFE_INTEGER, true)
    && value.lap_number !== null
    && isCanonicalString(value.phase)
    && isNullableNumber(value.lap_pct_start, 0, 100)
    && value.lap_pct_start !== null
    && isNullableNumber(value.lap_pct_end, 0, 100)
    && value.lap_pct_end !== null
    && value.lap_pct_end >= value.lap_pct_start;
}

export function isComponentAwarenessState(
  value: unknown,
  runId: string,
  runtimeIdentity?: VehicleSystemsRuntimeIdentity,
): value is ComponentAwarenessState {
  if (!isRecord(value)) return false;
  const scopes = value.observation_scopes;
  const histories = value.controlled_history;
  const observedArtifacts = value.supporting_artifact_ids;
  const observability = value.observability_states;
  const blockedControls = value.blocked_control_keys;
  const testableControls = value.testable_control_keys;
  const liveChannels = value.available_live_channel_ids;
  const liveBlockers = value.live_response_blocker_reasons;
  const quantityCertificates = value.quantity_observability;
  const presentSettings = value.present_setting_keys;
  const missingSettings = value.missing_setting_keys;
  if (
    !isCanonicalString(value.component_id)
    || value.run_id !== runId
    || !Array.isArray(scopes)
    || !scopes.every(isObservationScope)
    || !isStringArray(value.current_settings)
    || !isStringArray(value.present_setting_keys, 0, true)
    || !isStringArray(value.missing_setting_keys, 0, true)
    || (isStringArray(presentSettings, 0, true) && isStringArray(missingSettings, 0, true)
      && presentSettings.some((key) => missingSettings.includes(key)))
    || !isStringArray(value.current_setting_provenance)
    || !Array.isArray(observability)
    || observability.length === 0
    || !observability.every((item) => isEnumValue(item, observabilityStates))
    || new Set(observability).size !== observability.length
    || !Array.isArray(quantityCertificates)
    || quantityCertificates.length === 0
    || !quantityCertificates.every((certificate) => {
      if (!isRecord(certificate)
        || !isCanonicalString(certificate.quantity_id)
        || !isStringArray(certificate.required_channels, 1, true)
        || !isStringArray(certificate.available_channels, 0, true)
        || !isStringArray(certificate.missing_channels, 0, true)
        || !["qualified_producer", "manifest_presence_only", "missing"].includes(String(certificate.health_basis))
        || !isNullableNumber(certificate.minimum_coobserved_coverage, 0, 1)
        || certificate.minimum_coobserved_coverage === null
        || !isNullableNumber(certificate.coobserved_coverage, 0, 1)
        || !["observed", "screenable", "unavailable"].includes(String(certificate.state))
        || !isStringArray(certificate.producer_artifact_ids, 0, true)
        || !isStringArray(certificate.supported_derived_outputs, 0, true)
        || !isStringArray(certificate.blocker_reasons)) return false;
      const required = certificate.required_channels as string[];
      const available = certificate.available_channels as string[];
      const missing = certificate.missing_channels as string[];
      return sameStringSet([...available, ...missing], required)
        && !available.some((channel) => missing.includes(channel))
        && (certificate.state !== "observed" || (
          certificate.health_basis === "qualified_producer"
          && typeof certificate.coobserved_coverage === "number"
          && certificate.coobserved_coverage >= Number(certificate.minimum_coobserved_coverage)
          && certificate.producer_artifact_ids.length > 0
        ));
    })
    || !isEnumValue(value.current_response_state, responseStates)
    || !isEnumValue(value.relevance, relevanceStates)
    || !isStringArray(observedArtifacts, 0, true)
    || !isStringArray(value.supporting_citation_ids, 0, true)
    || !isStringArray(value.contradicting_citation_ids, 0, true)
    || !isStringArray(value.supporting_cause_ids, 0, true)
    || !isStringArray(value.contradicting_cause_ids, 0, true)
    || !isStringArray(value.confounders)
    || !isStringArray(value.unavailable_quantities, 1)
    || !isStringArray(value.measurement_requirements, 1)
    || !isStringArray(value.coupled_component_ids, 0, true)
    || !isStringArray(value.interaction_summaries)
    || !Array.isArray(histories)
    || !histories.every(isControlledHistory)
    || !isStringArray(blockedControls, 0, true)
    || !isStringArray(testableControls, 0, true)
    || !isNullableCanonicalString(value.authorized_control_key)
    || !isStringArray(liveChannels, 0, true)
    || !isStringArray(liveBlockers)
    || !isCanonicalString(value.next_discriminator)
    || !isEnumValue(value.current_testability, testabilityStates)
    || !isEnumValue(value.authority_state, authorityStates)
    || !Array.isArray(value.evidence_states)
    || !value.evidence_states.every((item) => isEnumValue(item, evidenceStates))
    || new Set(value.evidence_states).size !== value.evidence_states.length
    || !isStringArray(value.blocker_reasons)
    || typeof value.setup_authorized !== "boolean"
  ) return false;

  const state = value as unknown as ComponentAwarenessState;
  const responseObserved = state.current_response_state === "observed";
  const responseKnown = state.controlled_history.some((history) => (
    history.exact_context
    && ["matched", "missed"].includes(history.control_response)
    && history.policy_verdict !== "invalid"
  ));
  const policyKnown = state.controlled_history.some((history) => (
    history.exact_context
    && ["keep", "undo", "retest"].includes(history.policy_verdict)
  ));
  const liveObservable = state.observability_states.includes("live_response_observable");
  const undoControls = Array.from(new Set(
    state.controlled_history
      .filter((history) => history.exact_context && history.policy_verdict === "undo")
      .map((history) => history.control_key),
  ));
  const policyBlocked = state.blocked_control_keys.length > 0
    && state.testable_control_keys.length === 0
    && !state.setup_authorized;
  if (
    (state.observability_states.includes("unavailable") && state.observability_states.length > 1)
    || responseObserved !== state.observability_states.includes("current_response_observed")
    || responseObserved !== (state.observation_scopes.length > 0)
    || (responseObserved && state.supporting_artifact_ids.length === 0)
    || !sameStringSet(
      Array.from(new Set(state.observation_scopes.map((scope) => scope.artifact_id))),
      state.supporting_artifact_ids,
    )
    || (state.current_settings.length > 0 && state.current_setting_provenance.length === 0)
    || responseKnown !== state.observability_states.includes("controlled_response_known")
    || policyKnown !== state.observability_states.includes("exact_context_policy_known")
    || liveObservable !== state.quantity_observability.some((item) => item.state === "observed")
    || !sameStringSet(
      Array.from(new Set(state.quantity_observability.flatMap((item) => item.available_channels))),
      state.available_live_channel_ids,
    )
    || !sameStringSet(undoControls, state.blocked_control_keys)
    || state.blocked_control_keys.some((control) => state.testable_control_keys.includes(control))
    || (state.current_testability === "policy_blocked") !== policyBlocked
    || (state.relevance === "blocked") !== policyBlocked
    || (state.current_testability === "p19_authorized") !== state.setup_authorized
    || (state.authority_state === "p19_authorized") !== state.setup_authorized
    || (state.setup_authorized && (
      state.authorized_control_key === null
      || !state.testable_control_keys.includes(state.authorized_control_key)
      || state.blocked_control_keys.includes(state.authorized_control_key)
    ))
    || (!state.setup_authorized && state.authorized_control_key !== null)
    || (runtimeIdentity != null && state.available_live_channel_ids.some(
      (channel) => !runtimeIdentity.available_telemetry_channels.includes(channel),
    ))
  ) return false;
  return true;
}

function isRuntimeGraph(value: unknown, componentIds: readonly string[]): value is VehicleSystemsRuntimeGraph {
  if (!isRecord(value)) return false;
  if (
    value.schema_version !== "p26.runtime-graph.v3"
    || typeof value.reasoning_snapshot_sha256 !== "string"
    || !sha256Pattern.test(value.reasoning_snapshot_sha256)
    || value.authority !== "observation_and_controlled_history_only"
    || value.setup_authorized !== false
    || !Array.isArray(value.nodes)
    || !value.nodes.every(isVehicleSystemsNode)
    || !Array.isArray(value.edges)
    || !value.edges.every(isVehicleSystemsEdge)
  ) return false;
  const graph = value as unknown as VehicleSystemsRuntimeGraph;
  const nodeIds = graph.nodes.map((node) => node.node_id);
  const edgeIds = graph.edges.map((edge) => edge.edge_id);
  if (
    new Set(nodeIds).size !== nodeIds.length
    || new Set(edgeIds).size !== edgeIds.length
    || graph.nodes.some((node) => (
      node.authority === "knowledge_only"
      || (node.component_id !== null && !componentIds.includes(node.component_id))
    ))
  ) return false;
  const nodeKindsById = new Map(graph.nodes.map((node) => [node.node_id, node.kind]));
  return graph.edges.every((edge) => {
    if (!runtimeEdgeKinds.has(edge.kind) || edge.authority === "engineering_expectation_only") return false;
    const sourceKind = nodeKindsById.get(edge.source_node_id);
    const targetKind = nodeKindsById.get(edge.target_node_id);
    const allowed = allowedEdgeEndpoints[edge.kind];
    return sourceKind != null && targetKind != null
      && allowed[0].includes(sourceKind) && allowed[1].includes(targetKind);
  });
}

export function isVehicleSystemsProjection(
  value: unknown,
  expectation: VehicleSystemsScopeExpectation,
): value is VehicleSystemsProjection {
  if (!isRecord(value)) return false;
  const expectedSessionId = expectation.sessionId ?? null;
  if (
    value.schema_version !== "p26.component-awareness.v4"
    || value.run_id !== expectation.runId
    || value.session_id !== expectedSessionId
    || value.authority !== "p19_projection_only"
    || typeof value.setup_authorized !== "boolean"
    || !isCanonicalString(value.graph_version)
    || typeof value.knowledge_graph_sha256 !== "string"
    || !sha256Pattern.test(value.knowledge_graph_sha256)
    || !value.graph_version.endsWith(`:${value.knowledge_graph_sha256.slice(0, 12)}`)
    || typeof value.reasoning_snapshot_sha256 !== "string"
    || !sha256Pattern.test(value.reasoning_snapshot_sha256)
    || !isNullableCanonicalString(value.setup_id)
    || (value.setup_snapshot_sha256 !== null && (
      typeof value.setup_snapshot_sha256 !== "string"
      || !sha256Pattern.test(value.setup_snapshot_sha256)
    ))
    || ((value.setup_id === null) !== (value.setup_snapshot_sha256 === null))
    || (expectation.setupId !== undefined && value.setup_id !== expectation.setupId)
    || !isRuntimeIdentity(value.runtime_identity, expectation.runId)
    || !isCanonicalString(value.leading_system)
    || !isStringArray(value.leading_component_ids, 0, true)
    || !isCanonicalString(value.next_discriminator)
    || !isCanonicalString(value.strongest_contradiction)
    || !isStringArray(value.knowledge_debt)
    || !Array.isArray(value.component_states)
    || value.component_states.length === 0
    || !Array.isArray(value.experiment_factors)
    || value.experiment_factors.length === 0
  ) return false;
  const identity = value.runtime_identity as VehicleSystemsRuntimeIdentity;
  if (!value.component_states.every((state) => (
    isComponentAwarenessState(state, expectation.runId, identity)
  ))) return false;
  const projection = value as unknown as VehicleSystemsProjection;
  const componentIds = projection.component_states.map((state) => state.component_id);
  const componentIdSet = new Set<string>(componentIds);
  const factorIds = projection.experiment_factors
    .filter(isExperimentFactor)
    .map((factor) => factor.factor_id);
  if (
    componentIdSet.size !== componentIds.length
    || !componentIds.every(isVehicleSystemComponentId)
    || projection.leading_component_ids.some((componentId) => !componentIdSet.has(componentId))
    || factorIds.length !== projection.experiment_factors.length
    || new Set(factorIds).size !== factorIds.length
    || projection.experiment_factors.some((factor) => !componentIdSet.has(factor.component_id))
    || !isRuntimeGraph(projection.runtime_graph, componentIds)
    || projection.reasoning_snapshot_sha256 !== projection.runtime_graph.reasoning_snapshot_sha256
  ) return false;
  const authorized = projection.component_states.filter((state) => state.setup_authorized);
  return authorized.length <= 1 && projection.setup_authorized === (authorized.length === 1);
}

export function isComponentInspectionResponse(
  value: unknown,
  projection: VehicleSystemsProjection,
  componentId: string,
): value is ComponentInspectionResponse {
  if (!isRecord(value)) return false;
  if (
    value.run_id !== projection.run_id
    || value.session_id !== projection.session_id
    || value.graph_version !== projection.graph_version
    || value.knowledge_graph_sha256 !== projection.knowledge_graph_sha256
    || value.reasoning_snapshot_sha256 !== projection.reasoning_snapshot_sha256
    || value.setup_id !== projection.setup_id
    || value.setup_snapshot_sha256 !== projection.setup_snapshot_sha256
    || value.component_id !== componentId
    || value.authority !== "p19_projection_only"
    || !isRuntimeIdentity(value.runtime_identity, projection.run_id)
    || !runtimeIdentityMatches(value.runtime_identity, projection.runtime_identity)
    || !isComponentDefinition(value.definition)
    || value.definition.component_id !== componentId
    || !isComponentAwarenessState(value.state, projection.run_id, projection.runtime_identity)
    || value.state.component_id !== componentId
    || !Array.isArray(value.interactions)
    || !value.interactions.every(isComponentInteraction)
    || value.interactions.some((interaction) => ![
      interaction.source_component_id, interaction.target_component_id,
    ].includes(componentId))
    || value.interactions.some((interaction) => (
      !projection.component_states.some((state) => state.component_id === interaction.source_component_id)
      || !projection.component_states.some((state) => state.component_id === interaction.target_component_id)
    ))
    || !isStringArray(value.controls, 0, true)
    || !sameStringSequence(value.controls, value.definition.setup_keys)
  ) return false;
  const rootState = projection.component_states.find((state) => state.component_id === componentId);
  const state = value.state as ComponentAwarenessState;
  return rootState != null
    && state.setup_authorized === rootState.setup_authorized
    && state.authorized_control_key === rootState.authorized_control_key
    && state.current_testability === rootState.current_testability
    && state.authority_state === rootState.authority_state
    && state.relevance === rootState.relevance
    && state.next_discriminator === rootState.next_discriminator;
}

export function isControlMechanismTraceResponse(
  value: unknown,
  projection: VehicleSystemsProjection,
  controlKey: string,
): value is ControlMechanismTraceResponse {
  if (!isRecord(value)) return false;
  if (
    value.run_id !== projection.run_id
    || value.control_key !== controlKey
    || value.graph_version !== projection.graph_version
    || value.graph_content_sha256 !== projection.knowledge_graph_sha256
    || !value.graph_version.endsWith(`:${value.graph_content_sha256.slice(0, 12)}`)
    || value.authority !== "engineering_expectation_only"
    || value.setup_authorized !== false
    || !isRuntimeIdentity(value.runtime_identity, projection.run_id)
    || !runtimeIdentityMatches(value.runtime_identity, projection.runtime_identity)
    || !Array.isArray(value.nodes)
    || value.nodes.length === 0
    || !value.nodes.every(isVehicleSystemsNode)
    || !Array.isArray(value.edges)
    || value.edges.length === 0
    || !value.edges.every(isVehicleSystemsEdge)
  ) return false;
  const nodes = value.nodes as VehicleSystemsNode[];
  const edges = value.edges as VehicleSystemsEdge[];
  const nodeIds = nodes.map((node) => node.node_id);
  const edgeIds = edges.map((edge) => edge.edge_id);
  const nodeKindsById = new Map(nodes.map((node) => [node.node_id, node.kind]));
  const componentIds = projection.component_states.map((state) => state.component_id);
  return new Set(nodeIds).size === nodeIds.length
    && new Set(edgeIds).size === edgeIds.length
    && nodes.every((node) => (
      node.authority === "knowledge_only"
      && (node.component_id === null || componentIds.includes(node.component_id))
    ))
    && edges.some((edge) => edge.source_node_id === `control:${controlKey}`)
    && edges.every((edge) => (
      !runtimeEdgeKinds.has(edge.kind)
      && edge.authority === "engineering_expectation_only"
      && nodeKindsById.has(edge.source_node_id)
      && nodeKindsById.has(edge.target_node_id)
      && allowedEdgeEndpoints[edge.kind][0].includes(nodeKindsById.get(edge.source_node_id) as VehicleSystemsNodeKind)
      && allowedEdgeEndpoints[edge.kind][1].includes(nodeKindsById.get(edge.target_node_id) as VehicleSystemsNodeKind)
    ));
}
