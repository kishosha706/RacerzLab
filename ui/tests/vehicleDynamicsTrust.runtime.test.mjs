import assert from "node:assert/strict";

import {
  canonicalPerformanceMechanismAssessmentSha256,
  deriveCanonicalP35P32Binding,
  hasCanonicalPerformanceMechanismAssessmentDigest,
  isPerformanceMechanismAssessment,
} from "../src/utils/vehicleDynamicsTrust.ts";
import { canonicalJsonSha256 } from "../src/utils/canonicalJsonSha256.ts";
import { p35RuntimeTrustManifest } from "../src/utils/vehicleDynamicsRegistry.ts";

const h = (character) => character.repeat(64);
const requiredUnavailable = [
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
];
const sources = {
  driver: "p20-driver-input",
  demand: "p20-vehicle-demand",
  response: "p20-vehicle-response",
  platform: "p20-tire-platform",
  time: "opportunity-a",
  contradiction: "p20-response-contradiction",
  discriminator: "p20-response-discriminator",
};
const mechanismId = "mechanism:gearing_headroom_limitation";
const inspectionToolId = "inspect_gear_acceleration_response";
const discriminatorContractId = "observation:gearing_headroom_limitation:support_discriminator";
const contradictionContractId = "observation:gearing_headroom_limitation:contradiction";
const focusPrefix = "p35.focus.gear_acceleration_response:";
const mechanismTrust = p35RuntimeTrustManifest.mechanisms.find(
  (item) => item.mechanism_id === mechanismId,
);
assert.ok(mechanismTrust);
const supportChannels = [...new Set(mechanismTrust.support_required_channel_groups.flatMap(
  (requirement) => requirement.alternatives
    .slice(0, requirement.minimum_alternatives)
    .map((alternative) => alternative.accepted_source_channel_ids[0]),
))];
const supportId = `${focusPrefix}${(await canonicalJsonSha256([
  sources.time, mechanismId, sources.response, "support",
])).slice(0, 24)}`;
const contradictionId = `${focusPrefix}${(await canonicalJsonSha256([
  sources.time, mechanismId, "uncertainty",
])).slice(0, 24)}`;
const discriminatorId = `${focusPrefix}${(await canonicalJsonSha256([
  sources.time, mechanismId, discriminatorContractId, "discriminator",
])).slice(0, 24)}`;
const graphSha = "c14af7ad22a752df5710a6e695b50f085fa4d15ecb20b271b3dc6205e3113030";
const responseObservationId = `p354.response:${"1".repeat(24)}`;

const stage = (kind, sourceArtifactIds, summary, evidenceState = "measured", blockers = []) => ({
  stage: kind,
  evidence_state: evidenceState,
  source_artifact_ids: sourceArtifactIds,
  source_channels: [...supportChannels],
  summary,
  blocker_reasons: blockers,
  authority: "observation_only",
});

const focus = ({
  artifactId,
  sourceArtifactId,
  summary,
  mechanism = mechanismId,
  contract = null,
  evidenceState = "observed_correlation",
  blockers = [],
  polarity = "neutral",
}) => ({
  artifact_id: artifactId,
  mechanism_id: mechanism,
  observation_contract_id: contract,
  inspection_tool_id: inspectionToolId,
  stage: polarity === "support" ? "vehicle_response" : "tire_platform_state",
  evidence_state: evidenceState,
  source_artifact_ids: [sourceArtifactId],
  source_channels: [...supportChannels],
  lap_numbers: polarity === "support" ? [4] : [4, 5],
  lap_pct_start: 20,
  lap_pct_end: 30,
  phase: "straight",
  polarity,
  summary,
  blocker_reasons: blockers,
  authority: "observation_only",
});

const assessment = {
  schema_version: "p35.performance-mechanism-assessment.v1",
  p35_assessment_sha256: h("a"),
  run_id: "run-1",
  session_id: "session-1",
  objective_id: "race_long_run",
  car_path: "stockcars chevycamarozl1 2022",
  car_version: "next-gen",
  iracing_build_version: "2026.08.01.01",
  track_package: "oval",
  vehicle_runtime_identity_sha256: h("b"),
  graph_id: `p35vdg_${graphSha.slice(0, 24)}`,
  graph_version: `2026.08.next-gen-oval.v1:${graphSha.slice(0, 12)}`,
  knowledge_version: "2026.08.p35-next-gen-oval.v1",
  knowledge_graph_sha256: graphSha,
  p19_reasoning_snapshot_sha256: h("c"),
  p20_state_revision: h("d"),
  p20_profile_hash: null,
  p26_graph_version: "p26.next-gen.v1",
  p26_knowledge_graph_sha256: h("e"),
  p32_projection_sha256: h("f"),
  p32_performance_mechanism_ids: ["gearing_headroom"],
  performance_opportunity_ids: [sources.time],
  measured_time_consequence_available: true,
  chain: [
    stage("driver_input", [sources.driver], "Steering demand is measured in the selected window."),
    stage("vehicle_demand", [sources.demand], "The selected window carries sustained corner demand."),
    stage("vehicle_response", [sources.response, sources.contradiction, sources.discriminator], "Yaw response is observed alongside steering demand."),
    stage("tire_platform_state", [sources.platform], "Relative tire and platform state remains a proxy."),
    stage("time_consequence", [sources.time], "The selected window has a measured time consequence."),
  ],
  tire_demand_state_ids: [],
  load_path_ids: [],
  response_regime: "steady_state",
  response_observations: [{
    observation_id: responseObservationId, opportunity_id: sources.time,
    run_id: "run-1", source_lap_numbers: [4], reference_lap_numbers: [5],
    phase: "straight", lap_pct_start: 20, lap_pct_end: 30, onset_pct: 20,
    onset_resolution: "phase_boundary", response_regime: "steady_state",
    driver_demand_state: "matched", vehicle_response_state: "changed",
    line_state: "matched", context_state: "qualified", persistence: "phase_local",
    metrics: [{
      metric_id: `p354.metric:${"4".repeat(24)}`, quantity: "elapsed_time_delta_s",
      value: 0.1, units: "s", semantics: "calculated_delta",
      source_channels: ["speed_mph"], force_like: false, setup_authorized: false,
    }, {
      metric_id: `p354.metric:${"2".repeat(24)}`, quantity: "speed_delta_mph",
      value: -1, units: "mph", semantics: "measured_delta",
      source_channels: ["speed_mph"], force_like: false, setup_authorized: false,
    }],
    source_artifact_ids: [sources.time, sources.response], source_channels: ["speed_mph"],
    blocker_reasons: [], evidence_state: "measured", authority: "observation_only",
    component_cause_authorized: false, setup_authorized: false,
  }],
  problem_signature: {
    signature_id: `p354.signature:${"3".repeat(24)}`,
    response_observation_id: responseObservationId, opportunity_id: sources.time,
    time_origin: "local_generation", local_time_delta_s: 0.1, phase: "straight",
    onset_pct: 20, onset_resolution: "phase_boundary", response_regime: "steady_state",
    driver_demand_state: "matched", vehicle_response_state: "changed",
    line_state: "matched", speed_dependence: "not_established",
    stint_dependence: "not_established", traffic_dependence: "clear",
    surface_dependence: "not_established", front_rear_corner_scope: "unresolved",
    strongest_contradiction: "The current discriminator remains unobserved.",
    authority: "observation_only", component_cause_authorized: false,
    setup_authorized: false,
  },
  mechanism_separation: [{
    mechanism_id: mechanismId, response_observation_id: responseObservationId,
    required_response_kpi_ids: [discriminatorContractId],
    support_artifact_ids: [supportId], contradiction_artifact_ids: [contradictionId],
    missing_evidence: ["The current discriminator remains unobserved."],
    discriminator_contract_ids: [discriminatorContractId, contradictionContractId],
    protected_countereffects: ["Protect the following phase response."],
    component_family_ids: ["final_drive"], state: "alive",
    authority: "candidate_only", setup_authorized: false,
  }],
  candidates: [{
    mechanism_id: mechanismId,
    p32_performance_mechanism_ids: ["gearing_headroom"],
    support_artifact_ids: [supportId],
    contradiction_artifact_ids: [contradictionId],
    discriminator_contract_ids: [discriminatorContractId, contradictionContractId],
    component_family_ids: ["final_drive"],
    blocker_reasons: [],
    relevance: "candidate",
    authority: "candidate_only",
    component_cause_authorized: false,
    setup_authorized: false,
  }],
  focus_artifacts: [
    focus({
      artifactId: supportId,
      sourceArtifactId: sources.response,
      summary: "Higher steering demand and lower yaw support front-demand relevance.",
      polarity: "support",
    }),
    focus({
      artifactId: contradictionId,
      sourceArtifactId: sources.time,
      summary: "The current observation does not separate compatible mechanisms.",
      polarity: "uncertainty",
      evidenceState: "needs_confirmation",
      blockers: ["A clean repeated response is required."],
    }),
    focus({
      artifactId: discriminatorId,
      sourceArtifactId: sources.time,
      summary: "A clean repeated response window would separate the candidates.",
      contract: discriminatorContractId,
      evidenceState: "needs_confirmation",
      blockers: ["A repeated clean window is required."],
    }),
  ],
  strongest_support_artifact_id: supportId,
  strongest_contradiction_artifact_id: contradictionId,
  next_discriminator_contract_id: discriminatorContractId,
  unavailable_quantity_ids: requiredUnavailable,
  traffic_blocked: false,
  applicability_state: "ready",
  applicability_blockers: [],
  blocker_reasons: [],
  observation_authority: "observation_only",
  mechanism_authority: "candidate_only",
  component_causal_claim_count: 0,
  setup_authorized: false,
  terminal_authority: "p19_only",
};

const sealP354 = async (value) => {
  for (const response of value.response_observations) {
    for (const metric of response.metrics) {
      const metricBody = structuredClone(metric);
      delete metricBody.metric_id;
      metric.metric_id = `p354.metric:${(await canonicalJsonSha256(
        metricBody,
        { pythonFloatKeys: new Set(["value"]) },
      )).slice(0, 24)}`;
    }
    const responseBody = structuredClone(response);
    delete responseBody.observation_id;
    response.observation_id = `p354.response:${(await canonicalJsonSha256(
      responseBody,
      { pythonFloatKeys: new Set(["lap_pct_end", "lap_pct_start", "onset_pct", "value"]) },
    )).slice(0, 24)}`;
  }
  if (value.problem_signature) {
    value.problem_signature.response_observation_id = value.response_observations[0].observation_id;
    for (const row of value.mechanism_separation) {
      row.response_observation_id = value.response_observations[0].observation_id;
    }
    const signatureBody = structuredClone(value.problem_signature);
    delete signatureBody.signature_id;
    value.problem_signature.signature_id = `p354.signature:${(await canonicalJsonSha256(
      signatureBody,
      { pythonFloatKeys: new Set(["local_time_delta_s", "onset_pct"]) },
    )).slice(0, 24)}`;
  }
};
await sealP354(assessment);

const baseP32Binding = deriveCanonicalP35P32Binding([{
  opportunity_id: sources.time,
  local_delta_s: 0.1,
  start_pct: 20,
  end_pct: 30,
  phase: "straight",
  origin_kind: "local_generation",
  source_laps: [4, 5],
  source_channels: [...supportChannels],
  mechanism_candidates: ["gearing_headroom"],
  context_state: "qualified_pair",
  attribution_state: "candidate_only",
}]);
const scope = {
  runId: assessment.run_id,
  sessionId: assessment.session_id,
  objectiveId: assessment.objective_id,
  assessmentSha256: assessment.p35_assessment_sha256,
  carPath: assessment.car_path,
  carVersion: assessment.car_version,
  iRacingBuildVersion: assessment.iracing_build_version,
  trackPackage: assessment.track_package,
  vehicleRuntimeIdentitySha256: assessment.vehicle_runtime_identity_sha256,
  p19ReasoningSnapshotSha256: assessment.p19_reasoning_snapshot_sha256,
  p20StateRevision: assessment.p20_state_revision,
  p20ProfileHash: null,
  p26GraphVersion: assessment.p26_graph_version,
  p26KnowledgeGraphSha256: assessment.p26_knowledge_graph_sha256,
  p32ProjectionSha256: assessment.p32_projection_sha256,
  ...baseP32Binding,
  supportAdmissionAvailable: true,
  expectedChain: assessment.chain.map((item) => ({
    stage: item.stage,
    evidence_state: item.evidence_state,
    source_artifact_ids: [...item.source_artifact_ids],
    source_channels: [...item.source_channels],
    blocker_reasons: [...item.blocker_reasons],
  })),
  evidenceArtifactIds: Object.values(sources),
};

assert.equal(isPerformanceMechanismAssessment(assessment, scope), true);

const canonical = structuredClone(assessment);
const canonicalBody = structuredClone(canonical);
delete canonicalBody.p35_assessment_sha256;
canonical.p35_assessment_sha256 = await canonicalPerformanceMechanismAssessmentSha256(
  canonicalBody,
);
assert.equal(await hasCanonicalPerformanceMechanismAssessmentDigest(canonical), true);
canonical.focus_artifacts[0].summary = "Digest drift.";
assert.equal(await hasCanonicalPerformanceMechanismAssessmentDigest(canonical), false);
const coordinatedNestedDrift = structuredClone(assessment);
coordinatedNestedDrift.response_observations[0].metrics[0].value = 9.9;
const coordinatedNestedBody = structuredClone(coordinatedNestedDrift);
delete coordinatedNestedBody.p35_assessment_sha256;
coordinatedNestedDrift.p35_assessment_sha256 =
  await canonicalPerformanceMechanismAssessmentSha256(coordinatedNestedBody);
assert.equal(
  await hasCanonicalPerformanceMechanismAssessmentDigest(coordinatedNestedDrift),
  false,
  "a coordinated assessment rehash cannot preserve a stale nested response identity",
);

const reject = (label, mutate, customScope = scope) => {
  const hostile = structuredClone(assessment);
  mutate(hostile);
  assert.equal(isPerformanceMechanismAssessment(hostile, customScope), false, label);
};

reject("assessment exact keys", (value) => { value.hidden_setup = "52% cross weight"; });
reject("focus exact keys", (value) => { value.focus_artifacts[0].hidden_force = 1200; });
reject("focus requires a mechanism identity", (value) => { value.focus_artifacts[0].mechanism_id = null; });
reject("focus scope bounds are paired", (value) => { value.focus_artifacts[0].lap_pct_end = null; });
reject("focus scope is not reversed", (value) => { value.focus_artifacts[0].lap_pct_start = 31; });
reject("positive focus has laps", (value) => { value.focus_artifacts[0].lap_numbers = []; });
reject("positive focus has phase", (value) => { value.focus_artifacts[0].phase = null; });
reject("focus laps are unique", (value) => { value.focus_artifacts[0].lap_numbers = [4, 4]; });
reject("unblocked candidate support is required", (value) => { value.candidates[0].support_artifact_ids = []; });
reject("blocked candidates cannot retain support", (value) => {
  value.candidates[0].relevance = "blocked";
  value.candidates[0].blocker_reasons = ["Traffic blocks attribution."];
});
reject("blocked candidates retain contradiction or uncertainty", (value) => {
  value.candidates[0].relevance = "blocked";
  value.candidates[0].blocker_reasons = ["Traffic blocks attribution."];
  value.candidates[0].support_artifact_ids = [];
  value.candidates[0].contradiction_artifact_ids = [];
});
reject("support and contradiction cannot overlap", (value) => { value.candidates[0].contradiction_artifact_ids = [supportId]; });
reject("candidate evidence belongs to that mechanism", (value) => { value.focus_artifacts[0].mechanism_id = "mechanism:other"; });
reject("candidate contradiction belongs to that mechanism", (value) => { value.focus_artifacts[1].mechanism_id = "mechanism:other"; });
reject("focus sources stay in the chain", (value) => { value.focus_artifacts[0].source_artifact_ids = ["foreign-source"]; });
reject("focus sources resolve current evidence", (value) => { value.focus_artifacts[0].source_artifact_ids = ["not-indexed"]; });
reject("strongest support is candidate support", (value) => { value.strongest_support_artifact_id = discriminatorId; });
reject("strongest contradiction is candidate contradiction", (value) => { value.strongest_contradiction_artifact_id = discriminatorId; });
reject("next discriminator has typed focus", (value) => { value.focus_artifacts[2].observation_contract_id = "contract:other"; });
reject("next discriminator belongs to its candidate mechanism", (value) => { value.focus_artifacts[2].mechanism_id = "mechanism:other"; });
reject("next discriminator focus remains neutral", (value) => { value.focus_artifacts[2].polarity = "uncertainty"; });
reject("focus artifacts cannot outlive their candidates", (value) => { value.candidates = []; });
reject("foreign neutral focus artifacts cannot be injected", (value) => {
  value.focus_artifacts.push({
    ...value.focus_artifacts[2],
    artifact_id: `p35.focus.roll_response:${"d".repeat(24)}`,
    observation_contract_id: null,
  });
});
reject("unavailable physics locks remain complete", (value) => { value.unavailable_quantity_ids.pop(); });
reject("current tire-demand state remains locked", (value) => {
  value.tire_demand_state_ids = ["state:invented_current_tire_force"];
});
reject("current load path remains locked", (value) => {
  value.load_path_ids = ["load_path:invented_current_transfer"];
});
reject("driver stage cannot be upgraded beyond trusted P32", (value) => {
  value.chain[0].source_channels = ["invented_driver_channel"];
});
reject("vehicle-response stage cannot be upgraded beyond trusted P32", (value) => {
  value.chain[2].evidence_state = "controlled_test_effect";
});
reject("tire-platform stage cannot be upgraded beyond trusted P32", (value) => {
  value.chain[3].source_artifact_ids = ["invented-platform-state"];
});
reject("legacy solid-axle controls are rejected", (value) => { value.candidates[0].component_family_ids = ["component_family:track_bar"]; });
reject("component cause authority stays zero", (value) => { value.component_causal_claim_count = 1; });
reject("setup authority stays false", (value) => { value.setup_authorized = true; });
reject("terminal authority stays P19", (value) => { value.terminal_authority = "p35"; });
reject("causal narration is rejected", (value) => { value.focus_artifacts[0].summary = "The front roll system caused the loss."; });
reject("setup narration is rejected", (value) => { value.focus_artifacts[0].summary = "Increase the right-front spring by 25 lb/in."; });
reject("exact unavailable physics is rejected", (value) => { value.focus_artifacts[0].summary = "Wheel load is 1200 lb."; });
reject("traffic needs a blocked chain stage", (value) => { value.traffic_blocked = true; });
reject("time availability matches the chain", (value) => { value.measured_time_consequence_available = false; });
reject("response context and evidence state remain atomic", (value) => {
  value.response_observations[0].context_state = "blocked";
});
reject("response source and reference laps remain exact", (value) => {
  value.response_observations[0].source_lap_numbers = [5];
  value.response_observations[0].reference_lap_numbers = [4];
});
reject("problem signature cannot drift from response demand", (value) => {
  value.problem_signature.driver_demand_state = "mixed";
});
reject("separation KPI must equal the candidate discriminator", (value) => {
  value.mechanism_separation[0].required_response_kpi_ids = ["observation:foreign"];
});
reject("positive candidate requires matched response truth", (value) => {
  value.response_observations[0].driver_demand_state = "mixed";
});
reject("P32 mechanisms remain current", (value) => { value.p32_performance_mechanism_ids = ["mechanism:foreign"]; });
reject("P32 opportunities remain current", (value) => { value.performance_opportunity_ids = ["opportunity-foreign"]; });
reject("P35 selects at most one P32 opportunity", (value) => { value.performance_opportunity_ids.push("opportunity-extra"); });
reject("candidate assessments require a measured P32 opportunity", (value) => {
  value.performance_opportunity_ids = [];
  value.measured_time_consequence_available = false;
});
reject("static graph identity cannot be replaced by a coordinated rehash", (value) => {
  value.knowledge_graph_sha256 = h("9");
  value.graph_id = `p35vdg_${value.knowledge_graph_sha256.slice(0, 24)}`;
  value.graph_version = `2026.08.next-gen-oval.v1:${value.knowledge_graph_sha256.slice(0, 12)}`;
  value.knowledge_version = "2026.08.forged.v1";
});

const brakeTrust = p35RuntimeTrustManifest.mechanisms.find(
  (item) => item.mechanism_id === "mechanism:brake_entry_instability",
);
assert.ok(brakeTrust);
const brakeRequiredChannels = [...new Set(brakeTrust.support_required_channel_groups.flatMap(
  (requirement) => requirement.alternatives
    .slice(0, requirement.minimum_alternatives)
    .map((alternative) => alternative.accepted_source_channel_ids[0]),
))];
const buildBrakeAssessment = async (channels) => {
  const opportunity = {
    opportunity_id: sources.time,
    local_delta_s: 0.1,
    start_pct: 20,
    end_pct: 30,
    phase: "brake",
    origin_kind: "local_generation",
    source_laps: [4, 5],
    source_channels: [...channels],
    mechanism_candidates: ["entry_rotation"],
    context_state: "qualified_pair",
    attribution_state: "candidate_only",
  };
  const binding = deriveCanonicalP35P32Binding([opportunity]);
  const supportArtifactId = `${brakeTrust.focus_artifact_prefix}${(await canonicalJsonSha256([
    sources.time,
    brakeTrust.mechanism_id,
    sources.response,
    "support",
  ])).slice(0, 24)}`;
  const contradictionArtifactId = `${brakeTrust.focus_artifact_prefix}${(await canonicalJsonSha256([
    sources.time,
    brakeTrust.mechanism_id,
    "uncertainty",
  ])).slice(0, 24)}`;
  const discriminatorContract = brakeTrust.discriminator_observation_contract_ids[0];
  const discriminatorArtifactId = `${brakeTrust.focus_artifact_prefix}${(await canonicalJsonSha256([
    sources.time,
    brakeTrust.mechanism_id,
    discriminatorContract,
    "discriminator",
  ])).slice(0, 24)}`;
  const value = structuredClone(assessment);
  value.p32_performance_mechanism_ids = ["entry_rotation"];
  value.response_regime = "transient";
  value.chain = value.chain.map((item) => ({
    ...item,
    source_channels: [...channels],
  }));
  value.candidates = [{
    mechanism_id: brakeTrust.mechanism_id,
    p32_performance_mechanism_ids: ["entry_rotation"],
    support_artifact_ids: [supportArtifactId],
    contradiction_artifact_ids: [contradictionArtifactId],
    discriminator_contract_ids: [...brakeTrust.discriminator_observation_contract_ids],
    component_family_ids: [...brakeTrust.component_family_ids],
    blocker_reasons: [], relevance: "candidate", authority: "candidate_only",
    component_cause_authorized: false, setup_authorized: false,
  }];
  value.response_observations[0].phase = "brake";
  value.response_observations[0].response_regime = "transient";
  value.problem_signature.phase = "brake";
  value.problem_signature.response_regime = "transient";
  value.mechanism_separation = [{
    mechanism_id: brakeTrust.mechanism_id,
    response_observation_id: value.response_observations[0].observation_id,
    required_response_kpi_ids: [brakeTrust.discriminator_observation_contract_ids[0]],
    support_artifact_ids: [supportArtifactId],
    contradiction_artifact_ids: [contradictionArtifactId],
    missing_evidence: ["The controlled brake discriminator remains unobserved."],
    discriminator_contract_ids: [...brakeTrust.discriminator_observation_contract_ids],
    protected_countereffects: ["Protect entry stability and downstream time."],
    component_family_ids: [...brakeTrust.component_family_ids],
    state: "alive", authority: "candidate_only", setup_authorized: false,
  }];
  value.focus_artifacts = [
    {
      ...value.focus_artifacts[0], artifact_id: supportArtifactId,
      mechanism_id: brakeTrust.mechanism_id,
      inspection_tool_id: brakeTrust.inspection_tool_id,
      observation_contract_id: null, source_channels: [...channels],
      lap_numbers: [4], phase: "brake", polarity: "support",
    },
    {
      ...value.focus_artifacts[1], artifact_id: contradictionArtifactId,
      mechanism_id: brakeTrust.mechanism_id,
      inspection_tool_id: brakeTrust.inspection_tool_id,
      observation_contract_id: null, source_channels: [...channels],
      lap_numbers: [4, 5], phase: "brake", polarity: "uncertainty",
    },
    {
      ...value.focus_artifacts[2], artifact_id: discriminatorArtifactId,
      mechanism_id: brakeTrust.mechanism_id,
      inspection_tool_id: brakeTrust.inspection_tool_id,
      observation_contract_id: discriminatorContract, source_channels: [...channels],
      lap_numbers: [4, 5], phase: "brake", polarity: "neutral",
    },
  ];
  value.strongest_support_artifact_id = supportArtifactId;
  value.strongest_contradiction_artifact_id = contradictionArtifactId;
  value.next_discriminator_contract_id = discriminatorContract;
  await sealP354(value);
  const body = structuredClone(value);
  delete body.p35_assessment_sha256;
  value.p35_assessment_sha256 = await canonicalPerformanceMechanismAssessmentSha256(body);
  return {
    value,
    scope: {
      ...scope,
      ...binding,
      assessmentSha256: value.p35_assessment_sha256,
      supportAdmissionAvailable: true,
      expectedChain: value.chain.map((item) => ({
        stage: item.stage,
        evidence_state: item.evidence_state,
        source_artifact_ids: [...item.source_artifact_ids],
        source_channels: [...item.source_channels],
        blocker_reasons: [...item.blocker_reasons],
      })),
    },
  };
};
const validBrakeAssessment = await buildBrakeAssessment(brakeRequiredChannels);
assert.equal(
  isPerformanceMechanismAssessment(validBrakeAssessment.value, validBrakeAssessment.scope),
  true,
  "brake-entry support clears only with every reviewed layer and paired channel group",
);
const steeringYawOnlyBrake = await buildBrakeAssessment([
  "SteeringWheelAngle",
  "YawRate",
]);
assert.equal(
  await hasCanonicalPerformanceMechanismAssessmentDigest(steeringYawOnlyBrake.value),
  true,
  "the hostile brake payload is fully rehashed",
);
assert.equal(
  isPerformanceMechanismAssessment(steeringYawOnlyBrake.value, steeringYawOnlyBrake.scope),
  false,
  "generic Steering/Yaw cannot earn brake-entry support without exact brake pressures and wheel response",
);

const tiedOpportunities = [
  {
    opportunity_id: "opportunity-z",
    local_delta_s: 0.1,
    start_pct: 20,
    end_pct: 30,
    phase: "straight",
    origin_kind: "local_generation",
    source_laps: [4, 5],
    source_channels: ["steering_angle_deg", "yaw_rate_deg_s"],
    mechanism_candidates: ["gearing_headroom"],
    context_state: "qualified_pair",
    attribution_state: "candidate_only",
  },
  {
    opportunity_id: sources.time,
    local_delta_s: 0.1,
    start_pct: 20,
    end_pct: 30,
    phase: "straight",
    origin_kind: "local_generation",
    source_laps: [4, 5],
    source_channels: ["steering_angle_deg", "yaw_rate_deg_s"],
    mechanism_candidates: ["gearing_headroom"],
    context_state: "qualified_pair",
    attribution_state: "candidate_only",
  },
];
const tiedBinding = deriveCanonicalP35P32Binding(tiedOpportunities);
assert.deepEqual(tiedBinding, deriveCanonicalP35P32Binding([...tiedOpportunities].reverse()));
assert.deepEqual(tiedBinding.performanceOpportunityIds, [sources.time]);
assert.deepEqual(
  deriveCanonicalP35P32Binding([{ ...tiedOpportunities[0], source_laps: [] }]),
  {
    p32PerformanceMechanismIds: [],
    performanceOpportunityIds: [],
    measuredTimeConsequenceAvailable: false,
    timeConsequenceSourceChannels: [],
    phaseKind: null,
    responseRegime: null,
    timeOriginKind: null,
    trafficBlocked: false,
    attributionBlocked: false,
    candidateOpportunityAvailable: false,
    opportunityLapNumbers: [],
    supportLapNumbers: [],
    opportunityLapPctStart: null,
    opportunityLapPctEnd: null,
    opportunityPhase: null,
  },
  "a local delta without complete lap/channel provenance cannot become a P35 time source",
);
const zeroDeltaBinding = deriveCanonicalP35P32Binding([{
  ...tiedOpportunities[0], opportunity_id: "opportunity-zero", local_delta_s: 0,
  source_channels: [...supportChannels],
}]);
assert.equal(zeroDeltaBinding.measuredTimeConsequenceAvailable, true);
assert.equal(zeroDeltaBinding.candidateOpportunityAvailable, false);
assert.deepEqual(zeroDeltaBinding.performanceOpportunityIds, ["opportunity-zero"]);
assert.deepEqual(
  deriveCanonicalP35P32Binding([
    { ...tiedOpportunities[0], opportunity_id: "gain-large", local_delta_s: -0.5 },
    { ...tiedOpportunities[0], opportunity_id: "loss-small", local_delta_s: 0.1 },
  ]).performanceOpportunityIds,
  ["loss-small"],
  "positive loss remains the canonical cohort before a larger-magnitude gain",
);
assert.deepEqual(
  deriveCanonicalP35P32Binding([
    { ...tiedOpportunities[0], opportunity_id: "zero", local_delta_s: 0 },
    { ...tiedOpportunities[0], opportunity_id: "gain", local_delta_s: -0.2 },
  ]).performanceOpportunityIds,
  ["gain"],
  "without a loss, absolute magnitude selects the measured gain over zero",
);
const zeroDeltaAssessment = structuredClone(assessment);
zeroDeltaAssessment.performance_opportunity_ids = ["opportunity-zero"];
zeroDeltaAssessment.chain[4].source_artifact_ids = ["opportunity-zero"];
zeroDeltaAssessment.candidates = [];
zeroDeltaAssessment.response_observations[0].opportunity_id = "opportunity-zero";
zeroDeltaAssessment.response_observations[0].source_artifact_ids = [
  "opportunity-zero",
  sources.response,
];
zeroDeltaAssessment.response_observations[0].metrics.find(
  (metric) => metric.quantity === "elapsed_time_delta_s",
).value = 0;
zeroDeltaAssessment.problem_signature.opportunity_id = "opportunity-zero";
zeroDeltaAssessment.problem_signature.local_time_delta_s = 0;
zeroDeltaAssessment.mechanism_separation = [];
zeroDeltaAssessment.focus_artifacts = [];
zeroDeltaAssessment.strongest_support_artifact_id = null;
zeroDeltaAssessment.strongest_contradiction_artifact_id = null;
zeroDeltaAssessment.next_discriminator_contract_id = null;
assert.equal(isPerformanceMechanismAssessment(zeroDeltaAssessment, {
  ...scope,
  ...zeroDeltaBinding,
  assessmentSha256: zeroDeltaAssessment.p35_assessment_sha256,
  supportAdmissionAvailable: false,
  expectedChain: zeroDeltaAssessment.chain.map((item) => ({
    stage: item.stage,
    evidence_state: item.evidence_state,
    source_artifact_ids: [...item.source_artifact_ids],
    source_channels: [...item.source_channels],
    blocker_reasons: [...item.blocker_reasons],
  })),
  evidenceArtifactIds: [...Object.values(sources), "opportunity-zero"],
}), true, "zero elapsed delta retains measured P32 time but earns no P35 candidate");

const alternateTieSelection = structuredClone(assessment);
alternateTieSelection.performance_opportunity_ids = ["opportunity-z"];
alternateTieSelection.chain[4].source_artifact_ids = ["opportunity-z"];
alternateTieSelection.focus_artifacts[1].source_artifact_ids = ["opportunity-z"];
alternateTieSelection.focus_artifacts[2].source_artifact_ids = ["opportunity-z"];
const alternateSupportId = `${focusPrefix}${(await canonicalJsonSha256([
  "opportunity-z", mechanismId, sources.response, "support",
])).slice(0, 24)}`;
const alternateContradictionId = `${focusPrefix}${(await canonicalJsonSha256([
  "opportunity-z", mechanismId, "uncertainty",
])).slice(0, 24)}`;
const alternateDiscriminatorId = `${focusPrefix}${(await canonicalJsonSha256([
  "opportunity-z", mechanismId, discriminatorContractId, "discriminator",
])).slice(0, 24)}`;
alternateTieSelection.focus_artifacts[0].artifact_id = alternateSupportId;
alternateTieSelection.focus_artifacts[1].artifact_id = alternateContradictionId;
alternateTieSelection.focus_artifacts[2].artifact_id = alternateDiscriminatorId;
alternateTieSelection.candidates[0].support_artifact_ids = [alternateSupportId];
alternateTieSelection.candidates[0].contradiction_artifact_ids = [alternateContradictionId];
alternateTieSelection.strongest_support_artifact_id = alternateSupportId;
alternateTieSelection.strongest_contradiction_artifact_id = alternateContradictionId;
const alternateTieBody = structuredClone(alternateTieSelection);
delete alternateTieBody.p35_assessment_sha256;
alternateTieSelection.p35_assessment_sha256 =
  await canonicalPerformanceMechanismAssessmentSha256(alternateTieBody);
assert.equal(await hasCanonicalPerformanceMechanismAssessmentDigest(alternateTieSelection), true);
assert.equal(isPerformanceMechanismAssessment(alternateTieSelection, {
  ...scope,
  ...tiedBinding,
  assessmentSha256: alternateTieSelection.p35_assessment_sha256,
  evidenceArtifactIds: [...Object.values(sources), "opportunity-z"],
}), false, "a fully rehashed alternate equal-delta selection cannot replace the canonical ID tie-break");

const inventedComponentRelation = structuredClone(assessment);
inventedComponentRelation.candidates[0].component_family_ids = ["invented_active_aero"];
const inventedComponentBody = structuredClone(inventedComponentRelation);
delete inventedComponentBody.p35_assessment_sha256;
inventedComponentRelation.p35_assessment_sha256 =
  await canonicalPerformanceMechanismAssessmentSha256(inventedComponentBody);
assert.equal(await hasCanonicalPerformanceMechanismAssessmentDigest(inventedComponentRelation), true);
assert.equal(isPerformanceMechanismAssessment(inventedComponentRelation, {
  ...scope,
  assessmentSha256: inventedComponentRelation.p35_assessment_sha256,
}), false, "a rehashed payload cannot invent a component relation under the frozen graph identity");

const inventedContractRelation = structuredClone(assessment);
const inventedContractId = "observation:invented:discriminator";
const inventedDiscriminatorId = `${focusPrefix}${(await canonicalJsonSha256([
  sources.time, mechanismId, inventedContractId, "discriminator",
])).slice(0, 24)}`;
inventedContractRelation.candidates[0].discriminator_contract_ids = [
  inventedContractId,
  contradictionContractId,
];
inventedContractRelation.focus_artifacts[2].observation_contract_id = inventedContractId;
inventedContractRelation.focus_artifacts[2].artifact_id = inventedDiscriminatorId;
inventedContractRelation.next_discriminator_contract_id = inventedContractId;
const inventedContractBody = structuredClone(inventedContractRelation);
delete inventedContractBody.p35_assessment_sha256;
inventedContractRelation.p35_assessment_sha256 =
  await canonicalPerformanceMechanismAssessmentSha256(inventedContractBody);
assert.equal(await hasCanonicalPerformanceMechanismAssessmentDigest(inventedContractRelation), true);
assert.equal(isPerformanceMechanismAssessment(inventedContractRelation, {
  ...scope,
  assessmentSha256: inventedContractRelation.p35_assessment_sha256,
}), false, "a coordinated rehash cannot invent an observation-contract relationship");

const rehashedEmpty = structuredClone(assessment);
rehashedEmpty.p32_performance_mechanism_ids = [];
rehashedEmpty.performance_opportunity_ids = [];
rehashedEmpty.measured_time_consequence_available = false;
rehashedEmpty.chain[4] = stage(
  "time_consequence",
  [],
  "No measured P32 elapsed-time consequence is available.",
  "unavailable",
  ["No measured P32 opportunity is available."],
);
rehashedEmpty.response_regime = null;
rehashedEmpty.candidates = [];
rehashedEmpty.focus_artifacts = [];
rehashedEmpty.strongest_support_artifact_id = null;
rehashedEmpty.strongest_contradiction_artifact_id = null;
rehashedEmpty.next_discriminator_contract_id = null;
const rehashedEmptyBody = structuredClone(rehashedEmpty);
delete rehashedEmptyBody.p35_assessment_sha256;
rehashedEmpty.p35_assessment_sha256 =
  await canonicalPerformanceMechanismAssessmentSha256(rehashedEmptyBody);
assert.equal(await hasCanonicalPerformanceMechanismAssessmentDigest(rehashedEmpty), true);
assert.equal(isPerformanceMechanismAssessment(rehashedEmpty, {
  ...scope,
  assessmentSha256: rehashedEmpty.p35_assessment_sha256,
}), false, "a rehashed empty assessment cannot omit nonempty trusted P32 truth");

const trafficBlockedCandidate = structuredClone(assessment);
trafficBlockedCandidate.candidates[0].relevance = "blocked";
trafficBlockedCandidate.candidates[0].blocker_reasons = ["Traffic blocks mechanism attribution."];
trafficBlockedCandidate.candidates[0].support_artifact_ids = [];
trafficBlockedCandidate.mechanism_separation[0].support_artifact_ids = [];
trafficBlockedCandidate.mechanism_separation[0].missing_evidence = [
  "Traffic blocks mechanism attribution.",
];
trafficBlockedCandidate.mechanism_separation[0].state = "blocked";
trafficBlockedCandidate.focus_artifacts = trafficBlockedCandidate.focus_artifacts.slice(1);
trafficBlockedCandidate.strongest_support_artifact_id = null;
assert.equal(
  isPerformanceMechanismAssessment(trafficBlockedCandidate, scope),
  true,
  "all-blocked traffic candidates retain contradiction and discriminator without invented support",
);

const explicitBoundary = structuredClone(assessment);
explicitBoundary.focus_artifacts[0].summary = "This observation does not establish a component cause.";
assert.equal(isPerformanceMechanismAssessment(explicitBoundary, scope), true);
assert.equal(isPerformanceMechanismAssessment(assessment, { ...scope, p20ProfileHash: h("9") }), false);

console.log("vehicle dynamics runtime trust tests passed");
