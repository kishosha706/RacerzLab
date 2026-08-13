import assert from "node:assert/strict";

import {
  isComponentInspectionResponse,
  isControlMechanismTraceResponse,
  isVehicleSystemsProjection,
} from "../src/types/vehicleSystems.ts";

const knowledgeHash = "a".repeat(64);
const reasoningHash = "b".repeat(64);
const setupHash = "c".repeat(64);
const artifactHash = "d".repeat(64);
const cacheHash = "e".repeat(64);
const schemaHash = "f".repeat(64);
const compatibilityHash = "1".repeat(64);
const graphVersion = `next-gen-vehicle-systems.v3:${knowledgeHash.slice(0, 12)}`;

const runtimeIdentity = {
  run_id: "run-1",
  car_path: "stockcars chevycamarozl12022",
  car_version: "2026.06.08.02",
  iracing_build_version: "2026.06.24.02",
  track_configuration_name: "Oval",
  source_file_sha256: artifactHash,
  telemetry_cache_sha256: cacheHash,
  schema_fingerprint: schemaHash,
  compatibility_fingerprint: compatibilityHash,
  available_telemetry_channels: ["Speed"],
  source: "verified_telemetry_artifact",
};

const baseState = {
  component_id: "springs",
  run_id: "run-1",
  observation_scopes: [],
  current_settings: [],
  present_setting_keys: [],
  missing_setting_keys: [],
  current_setting_provenance: [],
  observability_states: ["definition_known"],
  current_response_state: "unavailable",
  relevance: "candidate",
  supporting_artifact_ids: [],
  supporting_citation_ids: [],
  contradicting_citation_ids: [],
  supporting_cause_ids: [],
  contradicting_cause_ids: [],
  confounders: [],
  unavailable_quantities: ["direct spring force"],
  measurement_requirements: ["qualified track-position response"],
  coupled_component_ids: [],
  interaction_summaries: [],
  controlled_history: [],
  blocked_control_keys: [],
  testable_control_keys: ["rf_spring_n_per_mm"],
  authorized_control_key: null,
  available_live_channel_ids: [],
  live_response_blocker_reasons: ["No verified live spring-response channel."],
  quantity_observability: [{
    quantity_id: "spring response",
    required_channels: ["lf_shock_defl_in", "rf_shock_defl_in", "lr_shock_defl_in", "rr_shock_defl_in"],
    available_channels: [],
    missing_channels: ["lf_shock_defl_in", "rf_shock_defl_in", "lr_shock_defl_in", "rr_shock_defl_in"],
    health_basis: "missing",
    minimum_coobserved_coverage: 0.7,
    coobserved_coverage: null,
    state: "unavailable",
    producer_artifact_ids: [],
    supported_derived_outputs: [],
    blocker_reasons: ["Required response channels are unavailable."],
  }],
  next_discriminator: "Measure response in the same qualified corner phase.",
  current_testability: "measurement_only",
  authority_state: "knowledge_only",
  evidence_states: [],
  blocker_reasons: [],
  setup_authorized: false,
};

const factor = {
  factor_id: "spring-rate-factor",
  component_id: "springs",
  physical_property_id: "spring_rate",
  primary_controls: ["rf_spring_n_per_mm"],
  coordinated_controls: [],
  automatic_sim_compensations: [],
  required_manual_compensations: [],
  invariants_to_hold: ["All non-test controls remain unchanged."],
  preconditions: ["P19 explicitly authorizes this control."],
  expected_component_response: ["Spring rate changes."],
  expected_vehicle_response: ["Response must be measured, not assumed."],
  countereffects: ["Platform response can confound balance."],
  success_metrics: ["Qualified same-position delta."],
  rollback_rule: "Undo when P19 returns Undo.",
  source_ids: ["next-gen-reference"],
  authority: "experiment_definition_only",
  setup_authorized: false,
};

const projection = {
  schema_version: "p26.component-awareness.v4",
  run_id: "run-1",
  session_id: null,
  graph_version: graphVersion,
  knowledge_graph_sha256: knowledgeHash,
  reasoning_snapshot_sha256: reasoningHash,
  setup_id: "setup-1",
  setup_snapshot_sha256: setupHash,
  runtime_identity: runtimeIdentity,
  leading_system: "Springs",
  leading_component_ids: ["springs"],
  next_discriminator: "Measure the exact response before changing setup.",
  strongest_contradiction: "No qualified contradiction is available.",
  knowledge_debt: ["Direct spring force is unavailable."],
  component_states: [baseState],
  experiment_factors: [factor],
  runtime_graph: {
    schema_version: "p26.runtime-graph.v3",
    reasoning_snapshot_sha256: reasoningHash,
    nodes: [],
    edges: [],
    authority: "observation_and_controlled_history_only",
    setup_authorized: false,
  },
  authority: "p19_projection_only",
  setup_authorized: false,
};

const expectation = { runId: "run-1", sessionId: null, setupId: "setup-1" };
assert.equal(isVehicleSystemsProjection(projection, expectation), true);

const foreignSession = structuredClone(projection);
foreignSession.session_id = "session-foreign";
assert.equal(isVehicleSystemsProjection(foreignSession, expectation), false);

const missingNullSession = structuredClone(projection);
delete missingNullSession.session_id;
assert.equal(isVehicleSystemsProjection(missingNullSession, expectation), false);

const foreignSetup = structuredClone(projection);
foreignSetup.setup_id = "setup-foreign";
assert.equal(isVehicleSystemsProjection(foreignSetup, expectation), false);

const malformedNestedState = structuredClone(projection);
delete malformedNestedState.component_states[0].supporting_citation_ids;
assert.equal(isVehicleSystemsProjection(malformedNestedState, expectation), false);

const staleKnowledgeGraph = structuredClone(projection);
staleKnowledgeGraph.knowledge_graph_sha256 = "2".repeat(64);
assert.equal(isVehicleSystemsProjection(staleKnowledgeGraph, expectation), false);

const leakedRuntimeAuthority = structuredClone(projection);
leakedRuntimeAuthority.runtime_graph.nodes.push({
  node_id: "component:springs",
  kind: "component",
  label: "Springs",
  description: null,
  component_id: "springs",
  engineering_area_mode: null,
  source_ids: ["next-gen-reference"],
  authority: "knowledge_only",
});
assert.equal(isVehicleSystemsProjection(leakedRuntimeAuthority, expectation), false);

const blockedAndAuthorized = structuredClone(projection);
Object.assign(blockedAndAuthorized.component_states[0], {
  relevance: "blocked",
  observability_states: ["definition_known", "exact_context_policy_known"],
  controlled_history: [{
    workflow_id: "workflow-1",
    source_run_id: "run-0",
    stage_run_ids: ["run-0", "run-1"],
    eligible_lap_ids: ["run-0:lap:4"],
    control_key: "rf_spring_n_per_mm",
    metric: "corner_min_speed_mps",
    phase: "center",
    mechanism_state: "supported",
    control_response: "unavailable",
    policy_verdict: "undo",
    countereffects: ["exit loss"],
    blocker_reasons: [],
    diagnostic_validity: "control_response_only",
    exact_context: true,
  }],
  blocked_control_keys: ["rf_spring_n_per_mm"],
  testable_control_keys: ["rf_spring_n_per_mm"],
  authorized_control_key: "rf_spring_n_per_mm",
  current_testability: "p19_authorized",
  authority_state: "p19_authorized",
  setup_authorized: true,
});
blockedAndAuthorized.setup_authorized = true;
assert.equal(isVehicleSystemsProjection(blockedAndAuthorized, expectation), false);

const nonExactUndo = structuredClone(projection);
nonExactUndo.component_states[0].controlled_history = [{
  workflow_id: "workflow-old",
  source_run_id: "run-old",
  stage_run_ids: [],
  eligible_lap_ids: [],
  control_key: "rf_spring_n_per_mm",
  metric: "corner_min_speed_mps",
  phase: "center",
  mechanism_state: "unknown",
  control_response: "unavailable",
  policy_verdict: "undo",
  countereffects: [],
  blocker_reasons: ["Context does not match."],
  diagnostic_validity: "control_response_only",
  exact_context: false,
}];
assert.equal(isVehicleSystemsProjection(nonExactUndo, expectation), true);

const partialExactUndo = structuredClone(projection);
Object.assign(partialExactUndo.component_states[0], {
  relevance: "tested",
  observability_states: ["definition_known", "exact_context_policy_known"],
  controlled_history: [{
    workflow_id: "workflow-partial",
    source_run_id: "run-0",
    stage_run_ids: ["run-0", "run-1"],
    eligible_lap_ids: ["run-0:lap:5"],
    control_key: "lf_spring_n_per_mm",
    metric: "corner_min_speed_mps",
    phase: "center",
    mechanism_state: "supported",
    control_response: "unavailable",
    policy_verdict: "undo",
    countereffects: ["exit loss"],
    blocker_reasons: [],
    diagnostic_validity: "control_response_only",
    exact_context: true,
  }],
  blocked_control_keys: ["lf_spring_n_per_mm"],
  testable_control_keys: ["rf_spring_n_per_mm"],
  authority_state: "controlled_history",
  blocker_reasons: ["The left-front spring exact context remains blocked."],
});
assert.equal(isVehicleSystemsProjection(partialExactUndo, expectation), true);

const unavailableLiveChannel = structuredClone(projection);
unavailableLiveChannel.component_states[0].observability_states = [
  "definition_known",
  "live_response_observable",
];
unavailableLiveChannel.component_states[0].available_live_channel_ids = ["SpringForceRF"];
unavailableLiveChannel.component_states[0].live_response_blocker_reasons = [];
assert.equal(isVehicleSystemsProjection(unavailableLiveChannel, expectation), false);

const foreignCar = structuredClone(projection);
foreignCar.runtime_identity.car_path = "stockcars camaro zl1 2018 legacy";
assert.equal(isVehicleSystemsProjection(foreignCar, expectation), false);

const unreviewedBuild = structuredClone(projection);
unreviewedBuild.runtime_identity.iracing_build_version = "2026.06.24.03";
assert.equal(isVehicleSystemsProjection(unreviewedBuild, expectation), false);

const applicability = {
  car_family: "next_gen",
  car_paths: [
    "stockcars chevycamarozl12022",
    "stockcars fordmustang2022",
    "stockcars toyotacamry2022",
  ],
  car_versions: ["2026.06.08.02"],
  iracing_build_min: "2026.01.00.00",
  iracing_build_max: "2026.06.24.02",
  track_package_types: ["oval"],
  source_version: "reviewed-local-next-gen-manual-digest-v1",
};
const definition = {
  component_id: "springs",
  system_id: "chassis",
  label: "Springs",
  physical_location: "Four corners",
  physical_role: "Supports platform load.",
  applicability,
  adjustable_property_ids: ["spring_rate"],
  operating_phases: ["entry", "center", "exit"],
  speed_load_relevance: "Load dependent.",
  setup_keys: ["rf_spring_n_per_mm"],
  coordinated_control_groups: [["rf_spring_n_per_mm"]],
  observability: {
    static_setting_channels: ["CarSetup"],
    live_telemetry_channels: ["SpringForceRF"],
    derived_metrics: ["platform_response"],
    indirect_proxies: ["ride_height"],
    unavailable_quantities: ["direct spring force"],
    interpretation_blockers: ["No direct force channel."],
  },
  coupled_component_ids: [],
  compensating_control_keys: [],
  invariants: ["Hold all other controls."],
  expected_state_ids: ["spring_rate_response"],
  symptom_ids: ["platform_shift"],
  performance_targets: ["repeatable balance"],
  countereffects: ["platform coupling"],
  supporting_signatures: ["same-position response"],
  contradicting_signatures: ["no repeatable response"],
  confounders: ["traffic"],
  measurement_requirements: ["qualified laps"],
  rollback_conditions: ["P19 Undo"],
  source_ids: ["next-gen-reference"],
  evidence_authority_ceiling: "hypothesis_only",
};

const inspection = {
  run_id: "run-1",
  session_id: null,
  graph_version: graphVersion,
  knowledge_graph_sha256: knowledgeHash,
  reasoning_snapshot_sha256: reasoningHash,
  setup_id: "setup-1",
  setup_snapshot_sha256: setupHash,
  runtime_identity: runtimeIdentity,
  component_id: "springs",
  definition,
  state: baseState,
  interactions: [],
  controls: ["rf_spring_n_per_mm"],
  authority: "p19_projection_only",
};
assert.equal(isComponentInspectionResponse(inspection, projection, "springs"), true);

const foreignInspection = structuredClone(inspection);
foreignInspection.reasoning_snapshot_sha256 = "2".repeat(64);
assert.equal(isComponentInspectionResponse(foreignInspection, projection, "springs"), false);

const controlNode = {
  node_id: "control:rf_spring_n_per_mm",
  kind: "control",
  label: "Right-front spring",
  description: null,
  component_id: "springs",
  engineering_area_mode: null,
  source_ids: ["next-gen-reference"],
  authority: "knowledge_only",
};
const propertyNode = {
  node_id: "property:springs:spring_rate",
  kind: "component_property",
  label: "Spring rate",
  description: null,
  component_id: "springs",
  engineering_area_mode: null,
  source_ids: ["next-gen-reference"],
  authority: "knowledge_only",
};
const trace = {
  run_id: "run-1",
  control_key: "rf_spring_n_per_mm",
  graph_version: graphVersion,
  graph_content_sha256: knowledgeHash,
  runtime_identity: runtimeIdentity,
  authority: "engineering_expectation_only",
  setup_authorized: false,
  nodes: [controlNode, propertyNode],
  edges: [{
    edge_id: "edge:spring-rate",
    source_node_id: controlNode.node_id,
    target_node_id: propertyNode.node_id,
    kind: "control_adjusts_property",
    direction: "bidirectional",
    interaction_type: null,
    source_ids: ["next-gen-reference"],
    authority: "engineering_expectation_only",
  }],
};
assert.equal(isControlMechanismTraceResponse(trace, projection, "rf_spring_n_per_mm"), true);

const crossSnapshotTrace = structuredClone(trace);
crossSnapshotTrace.graph_content_sha256 = "2".repeat(64);
assert.equal(isControlMechanismTraceResponse(crossSnapshotTrace, projection, "rf_spring_n_per_mm"), false);

const danglingTrace = structuredClone(trace);
danglingTrace.nodes.pop();
assert.equal(isControlMechanismTraceResponse(danglingTrace, projection, "rf_spring_n_per_mm"), false);

const runtimeClaimInTrace = structuredClone(trace);
runtimeClaimInTrace.edges[0].kind = "controlled_test_observed_response";
runtimeClaimInTrace.edges[0].target_node_id = propertyNode.node_id;
assert.equal(isControlMechanismTraceResponse(runtimeClaimInTrace, projection, "rf_spring_n_per_mm"), false);

console.log("vehicle-systems runtime guards: ok");
