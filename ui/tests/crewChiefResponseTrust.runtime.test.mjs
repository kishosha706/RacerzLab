import assert from "node:assert/strict";
import {
  canonicalCrewEvidenceIndexSha256,
  canonicalEngineeringAwarenessScientificSha256,
  hasCanonicalMeasurementMissionDigest,
  hasCanonicalRunSentinelDigest,
  hasCanonicalCrewEvidenceIndexDigest,
  hasCanonicalEngineeringAwarenessDigest,
  hasCanonicalVehicleRuntimeIdentityDigest,
  deriveP35ChainTruth,
  p35FocusEntriesMatchAssessment,
  isCrewChiefWorkspaceResponse,
  typedArtifactMatchesProjection,
} from "../src/utils/crewChiefResponseTrust.ts";
import { isPerformanceIntelligenceProjection } from "../src/utils/performanceIntelligenceTrust.js";
import { canonicalJsonSha256 } from "../src/utils/canonicalJsonSha256.ts";
import {
  canonicalEngineeringLearningSha256,
  hasCanonicalEngineeringLearningDigests,
} from "../src/utils/engineeringLearningTrust.js";
import {
  canonicalInvestigationImprovementSha256,
  hasCanonicalInvestigationImprovementDigests,
} from "../src/utils/investigationImprovementTrust.ts";
import { p35RuntimeTrustManifest } from "../src/utils/vehicleDynamicsRegistry.ts";
import {
  canonicalPerformanceMechanismAssessmentSha256,
  deriveCanonicalP35P32Binding,
  hasCanonicalPerformanceMechanismAssessmentDigest,
  isPerformanceMechanismAssessment,
} from "../src/utils/vehicleDynamicsTrust.ts";
import {
  hasCanonicalEngineeringKnowledgeDigest,
  isCurrentEngineeringKnowledgeProjection,
} from "../src/utils/engineeringKnowledgeTrust.ts";
import { ENGINEERING_KNOWLEDGE_STATIC_REGISTRY } from "../src/utils/engineeringKnowledgeRegistry.ts";

const h = (value) => value.repeat(64);
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
const requiredSupportChannels = (mechanism) => [...new Set(
  mechanism.support_required_channel_groups.flatMap((requirement) => (
    requirement.alternatives
      .slice(0, requirement.minimum_alternatives)
      .map((alternative) => alternative.accepted_source_channel_ids[0])
  )),
)];
const centerSupportTrust = p35RuntimeTrustManifest.mechanisms.find(
  (mechanism) => mechanism.mechanism_id === "mechanism:center_rotation_deficit",
);
assert.ok(centerSupportTrust);
const centerSupportChannels = requiredSupportChannels(centerSupportTrust);
const counts = (observationCount = 0) => ({
  observation_count: observationCount,
  independent_episode_count: observationCount,
  independent_workflow_count: 0,
  distinct_session_count: observationCount,
  distinct_context_count: observationCount,
});
const emptyLearningPrior = {
  schema_version: "p33.engineering-learning.v1",
  projection_sha256: h("2"), history_revision: h("1"),
  run_id: "run-1", session_id: "session-1", objective_id: "race_long_run",
  selected_scope_hash: h("f"), p19_reasoning_snapshot_sha256: h("a"),
  p32_projection_sha256: h("7"), current_context_sha256: h("3"),
  current_problem_sha256: h("4"), state: "insufficient_history",
  recurrence: {
    recurrence_id: "recurrence-new", classification: "new_problem",
    problem_sha256s: [h("4")], experience_ids: [], investigation_ids: [],
    statement: "No qualified recurrence is available.", useful_discriminator: null,
    prior_dead_end: null, strongest_contradiction: "No qualified prior experience.",
    transfer: null, counts: counts(), strength: "insufficient",
    authority: "attention_only", setup_authorized: false,
  },
  useful_prior_investigations: [], known_dead_ends: [], driver_tendencies: [],
  car_response_history: [], mind_change_history: [], recommended_attention_order: [],
  context_transfers: [], evidence_references: [], context_transfer_level: "blocked", strength: "insufficient",
  counts: counts(),
  ledger: {
    investigations_opened: 0, investigations_resolved: 0, no_call_outcomes: 0,
    driver_focus_outcomes: 0, measurement_missions: 0, controlled_tests: 0,
    keep_outcomes: 0, undo_outcomes: 0, retest_outcomes: 0,
    average_tool_steps_before_resolution: null, laps_consumed_before_resolution: 0,
    questions_asked: 0, repeated_dead_end_tools: [], successful_discriminators: [],
    recurring_problem_count: 0, recurrence_resolved_faster_count: 0,
    claims_lap_time_improvement: false,
  },
  post_run_brief: {
    state: "insufficient_history", what_we_learned: [], what_changed_our_mind: [],
    what_did_not_work: [], next_attention: [],
    blocker_reasons: ["No qualified engineering history is available."],
    authority: "attention_only", setup_authorized: false,
  },
  blocker_reasons: ["No qualified engineering history is available."],
  authority: "attention_only", setup_authorized: false, p19_rank_modified: false,
};
const vehicleRuntimeIdentity = {
  run_id: "run-1", car_path: "stockcars chevycamarozl1 2022",
  car_version: "next-gen", iracing_build_version: "2026.08.01.01",
  track_configuration_name: "oval", source_file_sha256: h("4"),
  telemetry_cache_sha256: h("5"), schema_fingerprint: h("6"),
  compatibility_fingerprint: h("7"),
  available_telemetry_channels: [...new Set(["speed_mph", ...centerSupportChannels])],
  source: "verified_telemetry_artifact",
};
const vehicleRuntimeIdentityHash = await canonicalJsonSha256(vehicleRuntimeIdentity);
const report = {
  reasoning_snapshot_sha256: h("a"), setup_id: "setup-1", setup_snapshot_sha256: h("b"),
  vehicle_systems: {
    graph_version: "p26.v1", knowledge_graph_sha256: h("e"),
    runtime_identity: structuredClone(vehicleRuntimeIdentity),
    component_states: [],
  },
  mechanism_observations: {
    status: "ready", run_id: "run-1", setup_id: "setup-1",
    authority: "observation_only", blocker_reasons: [],
    observations: [{
      observation_id: "p20-observation-corner-rotation", producer_id: "p20.corner_rotation",
      artifact_id: "observation-center_rotation", source_run_ids: ["run-1"],
      source_setup_ids: ["setup-1"], sample_coverage: 1, mechanism: "corner_rotation",
      mechanism_kinds: ["corner_rotation"], run_id: "run-1", setup_id: "setup-1",
      lap_number: 2, phase: "center", lap_pct_start: 20, lap_pct_end: 30,
      lap_pct_peak: 25, summary: "Higher steering demand with lower yaw response.",
      evidence_state: "observed_correlation", authority: "observation_only",
      observational_label: "typed_mechanism_observation", qualified: true,
      source_channels: [...centerSupportChannels],
      required_channels: [...centerSupportChannels],
      supporting_evidence: ["typed-current-observation"], contradicting_evidence: [],
      telemetry_sample_count: 32, repetition_count: 1,
      citations: [{
        run_id: "run-1", lap_number: 2, setup_id: "setup-1", lap_pct_start: 20,
        lap_pct_end: 30, lap_pct_peak: 25, phase: "center",
        evidence_state: "observed_correlation",
        source_channels: [...centerSupportChannels], event_id: null,
        telemetry_sample_count: 32,
        physical_segments: [{ start_pct: 20, end_pct: 30, sample_count: 32 }],
      }], blocker_reasons: [],
    }],
  },
  briefing: {
    success_check: "Repeatable evidence",
    action: { kind: "measurement_mission", title: "Measure", instruction: "Collect three eligible laps.", setup_authorized: false, control_key: null, setup_effect_id: null, experiment_factor_id: null, direction_sign: null, current_value: null, proposed_value: null, source_event_ids: [] },
  },
  next_trustworthy_move: null,
};
const p20TrustAxis = (basis) => ({
  state: "trusted", basis, blockers: [], source_artifact_ids: [],
});
const engineeringAwareness = {
  schema_version: "p20.awareness.v2",
  run_id: "run-1", session_id: "session-1",
  reasoning_snapshot_id: h("a"), state_revision: h("d"),
  request_identity: {
    run_id: "run-1", session_id: "session-1",
    reasoning_snapshot_id: h("a"), state_revision: h("d"),
  },
  generated_at: "2026-08-15T09:04:59Z", cache_state: "cold", build_duration_ms: 1,
  profile_hash: null, authority: "observation_only",
  trust_budget: {
    data_health: p20TrustAxis("Current telemetry is readable."),
    alignment_quality: p20TrustAxis("The physical window is position aligned."),
    context_comparability: p20TrustAxis("Current context is explicit."),
    driver_repeatability: p20TrustAxis("Driver demand coverage is measured."),
    mechanism_separation: p20TrustAxis("Mechanism evidence remains observational."),
    controlled_response_validity: p20TrustAxis("No controlled response is claimed."),
    policy_countereffect_risk: p20TrustAxis("Countereffects remain protected."),
    history_completeness: p20TrustAxis("Current-run evidence is complete for this scope."),
  },
  primary_state: null,
  subsystem_states: [{
    mechanism: "corner_rotation", status: "ready",
    summary: "Current center response is observed without causal authority.",
    phase: "center", lap_number: 2, lap_pct_start: 20, lap_pct_end: 30,
    evidence_state: "observed_correlation",
    source_artifact_ids: ["observation-center_rotation"],
    source_channels: [...centerSupportChannels],
    blocker_reasons: [], authority: "observation_only",
  }],
  episodes: [], state_drift_status: "no_finding", state_drift_findings: [],
  state_drift_blocker_reasons: [], expected_vs_observed: [], control_mutations: [],
  knowledge_debt: [], artifact_versions: [], raw_trace_included: false,
};
const engineeringAwarenessSha256 = await canonicalEngineeringAwarenessScientificSha256(
  engineeringAwareness,
);
const performance = {
  schema_version: "p32.performance-intelligence.v1", projection_sha256: h("7"),
  run_id: "run-1", session_id: "session-1", objective_id: "race_long_run",
  knowledge_version: "p32.v1", authority: "observation_only", setup_authorized: false,
  optimization_state: "data_locked", p19_reasoning_snapshot_sha256: h("a"),
  p20_state_revision: h("d"), p26_knowledge_graph_sha256: h("e"), blockers: [],
  component_context_state: "available", component_context_blockers: [],
  principles: Array.from({ length: 12 }, (_, index) => ({
    principle_id: `principle-${index}`, statement: "Measure elapsed time.",
    applicable_phases: ["center"], applicable_objectives: ["race_long_run"],
    required_evidence: ["qualified lap"], forbidden_claims: ["peak speed alone"],
    source_ids: ["time alignment"], authority: "knowledge_only",
  })),
  mechanisms: [{
    mechanism_id: "center_rotation", statement: "Ask whether center rotation changed time.",
    operating_phases: ["center"], required_telemetry: ["speed_mph"],
    derived_metrics: ["center time"], driver_confounders: ["line"],
    context_blockers: ["traffic"], p20_mechanism_families: ["corner_rotation"],
    p26_component_families: ["anti_roll_bars"], performance_outcomes: ["center_time"],
    countereffects: ["exit carry"], forbidden_claims: ["component cause"],
    source_ids: ["time alignment"], authority: "knowledge_only",
  }],
  outcomes: [{ outcome_id: "repeatability", label: "Repeatability", measured_by: ["eligible laps"], protected_outcomes: ["context"], authority: "measurement_only" }],
  objective_envelope: {
    objective_id: "race_long_run", primary_outcomes: ["repeatability"],
    protected_outcomes: ["stability"], countereffect_limits: ["Protect stability."],
    measurement_requirements: ["eligible laps"], policy_note: "Objective changes policy, not physics.",
    physics_changes: false, setup_authorized: false,
  },
  basis: {
    run_id: "run-1", reference_run_id: null, setup_id: "setup-1", reference_setup_id: null,
    source_lap_numbers: [2], reference_lap_numbers: [], physical_alignment_identity: h("6"),
    qualified_phase_segments: 0, sample_count: 10, source_channels: ["speed_mph"],
    time_basis: "unavailable", path_basis: "unavailable", coverage: 0,
    comparison_compatibility: "unavailable",
    context_blockers: ["Reference unavailable."], materialization: "narrow_run_owned_once",
  },
  opportunity_map: {
    run_id: "run-1", reference_run_id: null, setup_id: "setup-1", reference_setup_id: null,
    physical_alignment_identity: h("6"), opportunities: [], phase_totals_s: [],
    total_measured_delta_s: null, coverage: 0, noise_basis: "reference unavailable",
    context_blockers: ["Reference unavailable."], theoretical_composite_s: null,
    theoretical_is_guaranteed: false, setup_authorized: false,
  },
  corner_chains: [], component_influences: [], response_records: [],
  track_demand: {
    full_throttle_fraction: 0.5, braking_fraction: 0.1, cornering_fraction: 0.4,
    speed_min_mph: 100, speed_max_mph: 180, median_corner_duration_s: null,
    following_straight_carry_lengths_pct: [], combined_acceleration_fraction: 0.2,
    platform_load_speed_bands_mph: [150], disturbance_exposure_fraction: 0.01,
    traffic_exposure_fraction: 0, tire_state_development: "short_run", shift_limiter_zones: [],
    shift_zones: [], limiter_zones: [],
    dominant_measured_opportunity_ids: [], source_channels: ["speed_mph"], blockers: [],
    authority: "observation_only",
  },
  explanation_chain: {
    chain_id: "chain-1", node_ids: ["unavailable", "p19.next"], edges: [], branched: false,
    strongest_contradiction: "Attribution unavailable.", p19_next_move: "Collect three eligible laps.",
    setup_authority: "p19_only",
  },
  speed_story: {
    what_costs_time: "No measured opportunity.", where_it_starts: "Origin unavailable.",
    what_carries: "Carry unavailable.", driver: "Driver separation unresolved.",
    car: "Car response withheld.", systems: "No component attribution.", history: "No controlled history.",
    strongest_contradiction: "Attribution unavailable.", next: "Collect three eligible laps.",
    observed_difference_s: null, observed_direction: "unavailable",
    attribution_state: "unavailable", attribution: "Attribution unavailable.",
    source_context: "Source context unavailable.", reference_context: "Reference context unavailable.",
    comparison_window: "Comparison window unavailable.",
    authority: "observation_and_p19_projection",
  },
};
const mandatoryUnavailableDynamics = [
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
const dynamicsGraphSha = "c14af7ad22a752df5710a6e695b50f085fa4d15ecb20b271b3dc6205e3113030";
const vehicleDynamicsBody = {
  schema_version: "p35.performance-mechanism-assessment.v1",
  run_id: "run-1", session_id: "session-1", objective_id: "race_long_run",
  car_path: "stockcars chevycamarozl1 2022", car_version: "next-gen",
  iracing_build_version: "2026.08.01.01", track_package: "oval",
  vehicle_runtime_identity_sha256: vehicleRuntimeIdentityHash,
  graph_id: `p35vdg_${dynamicsGraphSha.slice(0, 24)}`,
  graph_version: `2026.08.next-gen-oval.v1:${dynamicsGraphSha.slice(0, 12)}`,
  knowledge_version: "2026.08.p35-next-gen-oval.v1",
  knowledge_graph_sha256: dynamicsGraphSha,
  p19_reasoning_snapshot_sha256: h("a"), p20_state_revision: h("d"),
  p20_profile_hash: null, p26_graph_version: "p26.v1",
  p26_knowledge_graph_sha256: h("e"), p32_projection_sha256: h("7"),
  p32_performance_mechanism_ids: [], performance_opportunity_ids: [],
  measured_time_consequence_available: false,
  chain: [
    ["driver_input", "Driver-input demand is unresolved in the typed P32 phase evidence."],
    ["vehicle_demand", "Run-specific vehicle demand is unavailable from the typed P32 track profile."],
    ["vehicle_response", "Yaw, acceleration, speed, and line response are unresolved in typed P32 evidence."],
    ["tire_platform_state", "Typed tire/platform proxies are unavailable; exact tire force and platform loads stay locked."],
    ["time_consequence", "No measured P32 elapsed-time consequence is available for a qualified physical scope."],
  ].map(([stage, reason]) => ({
    stage, evidence_state: "unavailable", source_artifact_ids: [], source_channels: [],
    summary: reason, blocker_reasons: [reason], authority: "observation_only",
  })),
  tire_demand_state_ids: [], load_path_ids: [], response_regime: null,
  response_observations: [], problem_signature: null, operational_response_evidence: [], mechanism_separation: [],
  candidates: [], focus_artifacts: [], strongest_support_artifact_id: null,
  strongest_contradiction_artifact_id: null, next_discriminator_contract_id: null,
  unavailable_quantity_ids: mandatoryUnavailableDynamics, traffic_blocked: false,
  applicability_state: "ready", applicability_blockers: [],
  blocker_reasons: ["No qualified P32 performance opportunity is available."],
  observation_authority: "observation_only", mechanism_authority: "candidate_only",
  component_causal_claim_count: 0, setup_authorized: false, terminal_authority: "p19_only",
};
const vehicleDynamics = {
  ...vehicleDynamicsBody,
  p35_assessment_sha256: await canonicalPerformanceMechanismAssessmentSha256(
    vehicleDynamicsBody,
  ),
};
const improvementBody = {
  schema_version: "p34.investigation-improvement-projection.v1",
  run_id: "run-1", session_id: "session-1", workspace_revision: h("c"),
  state: "unavailable", production_policy: "deterministic_baseline",
  memory_policy_state: "shadow_only", current_pair: null, current_context: null,
  current_pair_status: null,
  latest_completed_pair: null, latest_completed_comparison: null,
  latest_outcome_status: null, decisions_differ: false,
  difference_explanation: "The deterministic baseline remains production; no frozen pair is available.",
  memory_evidence_record_ids: [], context_transfer_class: "none",
  readiness: {
    production_policy: "deterministic_baseline", memory_policy_state: "shadow_only",
    activation_decision: "no_activation_earned", evaluation_decision: "no_activation_earned",
    effective_activation_decision_id: null, effective_activation_decision_sha256: null,
    qualified_historical_investigations: 0,
    qualified_prospective_investigations: 0, observable_comparisons: 0,
    unobservable_comparisons: 0, historical_deficit: 20, prospective_deficit: 12,
    exact_recurrence_deficit: 5, compatible_recurrence_deficit: 5, context_deficit: 3,
    problem_family_deficit: 4, objective_deficit: 2, safety_gate_passed: false,
    negative_controls_passed: false, subgroup_gate_passed: false,
    blockers: ["Limited attention has not earned the frozen gates."],
    remaining_collection_missions: ["Collect qualified independent investigations."],
    authority_ceiling: "attention_only", setup_authorized: false,
  },
  safety_blockers: ["No frozen pre-outcome P34 pair exists for this Crew revision."],
  p19_authority_unchanged: true, setup_authorized: false,
};
const investigationImprovement = {
  ...improvementBody,
  projection_sha256: await canonicalInvestigationImprovementSha256(improvementBody),
};
const p35ToolIds = [
  "inspect_tire_demand", "inspect_load_transfer", "inspect_roll_response",
  "inspect_pitch_response", "inspect_platform_state", "inspect_transient_settling",
  "inspect_steady_state_balance", "inspect_brake_vehicle_response",
  "inspect_power_on_response", "inspect_differential_response",
  "inspect_alignment_response", "inspect_tire_state_migration",
  "inspect_traffic_platform_response", "inspect_gear_acceleration_response",
];
const p34ExcludedToolIds = [
  ...p35ToolIds,
  "inspect_setup_knowledge_for_mechanism",
  "inspect_control_experiment_contract",
];
const availableTools = [
  {
    tool_id: "inspect_exit_carry", allowed_scope: "run", input_schema: "current run",
    output_artifact_type: "exit_carry", authority_ceiling: "measurement_only",
    required_sources: ["p32"],
  },
  {
    tool_id: "inspect_path_efficiency", allowed_scope: "run", input_schema: "current run",
    output_artifact_type: "path_efficiency", authority_ceiling: "measurement_only",
    required_sources: ["p32"],
  },
  ...p35ToolIds.map((toolId) => ({
    tool_id: toolId, allowed_scope: "run",
    input_schema: "P35 typed mechanism assessment and existing P20/P26/P32 evidence",
    output_artifact_type: `P35 ${toolId.replace(/^inspect_/, "").replaceAll("_", " ")} evidence`,
    authority_ceiling: "observation_only", required_sources: ["p35", "p20", "p32"],
  })),
  {
    tool_id: "inspect_setup_knowledge_for_mechanism", allowed_scope: "run",
    input_schema: "P35.1 direction-neutral mechanism/setup bridge",
    output_artifact_type: "educational or measurable setup-effect hypotheses",
    authority_ceiling: "measurement_only", required_sources: ["p351", "p35", "p32"],
  },
  {
    tool_id: "inspect_control_experiment_contract", allowed_scope: "workflow",
    input_schema: "P35.1 hypothesis plus exact P19/P26 experiment boundary",
    output_artifact_type: "measurement contract or exact P19 projection",
    authority_ceiling: "measurement_only", required_sources: ["p351", "p19", "p26"],
  },
];
const emptyKnowledgeHypotheses = ENGINEERING_KNOWLEDGE_STATIC_REGISTRY.map((identity) => ({
  bridge_id: identity.bridgeId,
  effect_id: identity.effectId,
  setup_area: "reviewed_setup_catalog",
  physical_role: "Provides a direction-neutral setup-system relationship.",
  direction_sign: identity.directionSign, experiment_factor_id: identity.experimentFactorId,
  level: identity.p35MechanismIds.length === 0 ? "unsupported_remove" : "educational_knowledge",
  relevance: identity.p35MechanismIds.length === 0 ? "inapplicable" : "knowledge_only",
  p32_opportunity_id: null, p35_mechanism_ids: [],
  p20_mechanism_ids: identity.p20MechanismIds.filter((mechanismId) => (
    engineeringAwareness.subsystem_states.some(
      (state) => state.status === "ready" && state.mechanism === mechanismId,
    )
  )),
  possible_component_family_ids: [...identity.possibleComponentFamilyIds],
  p26_component_family_ids: [],
  current_candidate_component_ids: [], current_supported_component_ids: [],
  contradicted_component_ids: [], blocked_component_ids: [],
  unobservable_component_ids: [], irrelevant_component_ids: [],
  response_regimes: [], relevant_phases: [], expected_vehicle_response_ids: [],
  expected_vehicle_state_ids: [`p352.expected_vehicle_state:${identity.effectId}:0:state`],
  validation_metric_ids: [`p352.validation_metric:${identity.effectId}:0:metric`],
  countereffect_ids: [],
  countereffect_state_ids: [`p352.countereffect_state:${identity.effectId}:0:countereffect`],
  protected_outcomes: [],
  protected_performance_outcome_ids: [`p352.protected_outcome:${identity.effectId}:0:outcome`],
  rollback_condition_ids: [`p352.rollback:${identity.effectId}`],
  inspection_tool_ids: [], support_artifact_ids: [], contradiction_artifact_ids: [],
  discriminator_contract_ids: [], missing_evidence: ["Current mechanism evidence is unavailable."],
  controlled_history: [], knowledge_applicability: identity.p35MechanismIds.length === 0
    ? "unsupported" : "educational_only",
  runtime_evidence_state: "unavailable", p19_control: null,
  authority: "knowledge_only", setup_authorized: false,
}));
const engineeringKnowledgeBody = {
  schema_version: "p352.current-engineering-knowledge.v1",
  run_id: "run-1", session_id: "session-1", complaint_prior: null,
  p19_reasoning_snapshot_sha256: h("a"), p20_state_revision: h("d"),
  p26_knowledge_graph_sha256: h("e"), p32_projection_sha256: h("7"),
  p35_assessment_sha256: vehicleDynamics.p35_assessment_sha256,
  p33_projection_sha256: h("2"),
  bridge_coverage_sha256: "a7dd3bcb645b037d803289dd94ffa7a0c89c6d01e7ce7c52e635c8471826cc1c",
  p32_opportunity_id: null, hypotheses: emptyKnowledgeHypotheses,
  leading_hypothesis_ids: [], next_discriminator_contract_id: null,
  blocker_reasons: ["No qualified P32 performance opportunity is available."],
  terminal_authority: "p19_only", non_p19_setup_authorized: false,
};
const engineeringKnowledge = {
  ...engineeringKnowledgeBody,
  projection_sha256: await canonicalJsonSha256(engineeringKnowledgeBody),
};
const selectLeadingKnowledgeHypotheses = (hypotheses, discriminatorId) => {
  const current = hypotheses.filter((item) => item.relevance === "supported_candidate"
    || item.relevance === "blocked_candidate");
  const selected = [];
  const mechanisms = new Set();
  const components = new Set();
  const discriminatorOwner = discriminatorId == null ? undefined : current.find(
    (item) => item.discriminator_contract_ids.includes(discriminatorId),
  );
  if (discriminatorOwner != null) selected.push(discriminatorOwner);
  selected.forEach((item) => {
    item.p35_mechanism_ids.forEach((id) => mechanisms.add(id));
    item.p26_component_family_ids.forEach((id) => components.add(id));
  });
  for (const item of current) {
    if (selected.includes(item)) continue;
    const addsMechanism = item.p35_mechanism_ids.some((id) => !mechanisms.has(id));
    const addsComponent = item.p26_component_family_ids.some((id) => !components.has(id));
    if (!addsMechanism && !addsComponent) continue;
    selected.push(item);
    item.p35_mechanism_ids.forEach((id) => mechanisms.add(id));
    item.p26_component_family_ids.forEach((id) => components.add(id));
    if (selected.length === 8) return selected.map((item) => item.effect_id);
  }
  for (const item of current) {
    if (!selected.includes(item)) selected.push(item);
    if (selected.length === 8) break;
  }
  return selected.map((item) => item.effect_id);
};
const synchronizeEngineeringKnowledge = async (value) => {
  const hypotheses = structuredClone(emptyKnowledgeHypotheses);
  hypotheses.forEach((hypothesis, hypothesisIndex) => {
    const identity = ENGINEERING_KNOWLEDGE_STATIC_REGISTRY[hypothesisIndex];
    const candidates = identity.p35MechanismIds.flatMap((mechanismId) => {
      const candidate = value.vehicle_dynamics.candidates.find(
        (item) => item.mechanism_id === mechanismId,
      );
      return candidate == null ? [] : [candidate];
    });
    if (candidates.length === 0) return;
    hypotheses[hypothesisIndex] = {
      ...hypothesis,
      level: "measurable_hypothesis",
      relevance: candidates.some((candidate) => candidate.relevance === "candidate")
        ? "supported_candidate" : "blocked_candidate",
      p32_opportunity_id: value.vehicle_dynamics.performance_opportunity_ids[0] ?? null,
      p35_mechanism_ids: candidates.map((candidate) => candidate.mechanism_id),
      support_artifact_ids: candidates.flatMap((candidate) => candidate.support_artifact_ids),
      contradiction_artifact_ids: candidates.flatMap(
        (candidate) => candidate.contradiction_artifact_ids,
      ),
      discriminator_contract_ids: [...new Set(candidates.flatMap(
        (candidate) => candidate.discriminator_contract_ids,
      ))],
      missing_evidence: [...new Set(candidates.flatMap((candidate) => candidate.blocker_reasons))],
      knowledge_applicability: "applicable",
      runtime_evidence_state: candidates.some((candidate) => candidate.relevance === "blocked")
        ? "blocked_by_context"
        : candidates.some((candidate) => candidate.support_artifact_ids.length > 0)
          ? value.vehicle_dynamics.focus_artifacts.find(
            (item) => candidates.some(
              (candidate) => candidate.support_artifact_ids.includes(item.artifact_id),
            ),
          )?.evidence_state ?? "unavailable"
          : "unavailable",
      authority: "measurement_only",
    };
  });
  const body = {
    ...value.engineering_knowledge,
    p35_assessment_sha256: value.vehicle_dynamics.p35_assessment_sha256,
    p32_opportunity_id: value.vehicle_dynamics.performance_opportunity_ids[0] ?? null,
    hypotheses,
    leading_hypothesis_ids: selectLeadingKnowledgeHypotheses(
      hypotheses,
      value.vehicle_dynamics.next_discriminator_contract_id,
    ),
    next_discriminator_contract_id: value.vehicle_dynamics.next_discriminator_contract_id,
    blocker_reasons: value.vehicle_dynamics.blocker_reasons.length > 0
      ? [...value.vehicle_dynamics.blocker_reasons]
      : ["Current mechanism evidence remains bounded by the P35 candidate contract."],
  };
  delete body.projection_sha256;
  value.engineering_knowledge = {
    ...body,
    projection_sha256: await canonicalJsonSha256(body),
  };
  value.engineering_case.p351_projection_sha256 = value.engineering_knowledge.projection_sha256;
  value.engineering_case.p35_assessment_sha256 = value.vehicle_dynamics.p35_assessment_sha256;
};
const workspace = {
  schema_version: "p352.crew-chief-workspace.v1",
  generated_at: "2026-08-15T09:05:00Z",
  identity: {
    run_id: "run-1", session_id: "session-1", reasoning_snapshot_sha256: h("a"),
    setup_id: "setup-1", setup_snapshot_sha256: h("b"), workspace_revision: h("c"),
    selected_scope_hash: h("f"), p20_profile_hash: null, p26_graph_version: "p26.v1",
    p20_state_revision: h("d"), p20_projection_sha256: engineeringAwarenessSha256,
    p26_knowledge_graph_sha256: h("e"),
    p26_reasoning_snapshot_sha256: h("a"), active_workflow_id: null, active_workflow_revision: null,
    p32_projection_sha256: h("7"), p35_assessment_sha256: vehicleDynamics.p35_assessment_sha256,
    run_sentinel_sha256: h("6"), objective_id: "race_long_run",
    learning_history_revision: h("1"), learning_ledger_head_sha256: null,
    learning_projection_sha256: h("2"),
    vehicle_runtime_identity_hash: vehicleRuntimeIdentityHash,
    vehicle_runtime_identity: structuredClone(vehicleRuntimeIdentity), investigation_id: null,
  },
  evidence_index: {
    workspace_revision: h("c"), index_hash: await canonicalJsonSha256([]), entries: [],
  },
  engineering_case: {
    schema_version: "p3543.canonical-engineering-case.v1",
    case_id: `p3543case_${h("c").slice(0, 24)}`,
    case_sha256: h("9"), case_revision_sha256: h("c"),
    run_id: "run-1", session_id: "session-1", recording_sha256: h("8"),
    setup_id: "setup-1", setup_snapshot_sha256: h("b"), objective_id: "race_long_run",
    condition_epoch_sha256: h("6"), p19_reasoning_snapshot_sha256: h("a"),
    p20_state_revision: h("d"), p26_knowledge_graph_sha256: h("e"),
    p32_projection_sha256: h("7"), p35_assessment_sha256: vehicleDynamics.p35_assessment_sha256,
    p351_projection_sha256: engineeringKnowledge.projection_sha256,
    p33_projection_sha256: h("2"), evidence_index_sha256: await canonicalJsonSha256([]),
    primary_opportunity_id: null, response_artifacts: [], p19_response_admissions: [],
    mechanism_ids: [], component_ids: [...new Set(ENGINEERING_KNOWLEDGE_STATIC_REGISTRY.flatMap(
      (item) => item.possibleComponentFamilyIds,
    ))],
    effect_readiness: emptyKnowledgeHypotheses.map((item) => ({
      effect_id: item.effect_id, bridge_id: item.bridge_id, state: "knowledge_only",
      response_artifact_ids: [], expected_response_relation_ids: [], exact_control_keys: [],
      experiment_factor_id: item.experiment_factor_id, countereffect_measurement_ids: [],
      missing_evidence: [...item.missing_evidence], authority: "knowledge_only",
      setup_authorized: false,
    })),
    active_discriminator_id: null, investigation_id: null, workspace_revision: h("c"),
    terminal_move_sha256: h("7"), capability_resolutions: [], quantity_observability: [],
    semantic_focus: {
      case_id: `p3543case_${h("c").slice(0, 24)}`, case_revision_sha256: h("c"),
      artifact_id: null, lap_numbers: [], lap_pct_start: null, lap_pct_end: null,
      phase: null, mechanism_ids: [], response_relation_id: null, component_ids: [],
      effect_ids: [], control_keys: [], p19_cause_ids: [], authority: "navigation_only",
    },
    campaign_capture: {
      state: "pending", blocker_reasons: ["Real qualified sessions are required."],
      historical_count_credited: false, null_count_credited: false,
      negative_control_count_credited: false, subgroup_count_credited: false,
      authority: "qualification_only",
    },
    authority: "case_receipt_only", p19_authority_unchanged: true, setup_authorized: false,
  },
  available_tools: availableTools,
  tool_eligibility: availableTools.map((tool) => ({
    tool_id: tool.tool_id,
    currently_relevant: false,
    required_by_mandatory_gate: ["inspect_data_quality", "inspect_lap_context"].includes(tool.tool_id),
    expected_to_separate: [],
    available_artifact_types: [],
    missing_inputs: [],
    cost_class: "cheap",
    safe_priority_tier: "p19_terminal",
    skip_reason: "Investigation is not open.",
  })),
  p19_mission_contract: null,
  engineering_awareness: engineeringAwareness,
  performance_intelligence: performance,
  vehicle_dynamics: vehicleDynamics,
  engineering_knowledge: engineeringKnowledge,
  learning_prior: emptyLearningPrior,
  investigation_improvement: investigationImprovement,
  success_contract: {
    workspace_revision: h("c"), target_scope: "braking entry", acceptance_rule: "Repeat the metric.",
    independence_unit: "eligible lap",
  },
  run_sentinel: {
    mission_state: "collecting", p19_plan_kind: "measurement_mission",
    mission: "Measure", need: "Collect three eligible laps.", success: "Repeatable evidence",
    hold_constant: ["Setup"], watch: ["Position-aligned response"],
    stop: ["Stop on integrity failure."], required_laps: 3, context_cleared_laps: 0,
    mission_accepted_lap_ids: [], measurement_attempt_ids: [], mission_acceptance_basis: "unbound",
    collection_complete: false, stage: "measurement", laps: [], blocker_reasons: [],
  },
  critique: { outcome: "pass", passed: true, findings: [], strongest_contradiction: null },
  adaptive_research: { state: "data_locked", authority: "none", activation_gate: "Held-out evidence is required." },
  current_subgoal: null, latest_tool_result: null, pending_driver_question: null,
  prospective_consumption: null, investigation: null, folded_state: null,
  blocker_reasons: [], post_run_brief: ["P19 status: ready."], response_history_ids: [], driver_memory_ids: [],
  p19_cause_ids: [],
  p26_component_ids: [...new Set(ENGINEERING_KNOWLEDGE_STATIC_REGISTRY.flatMap(
    (item) => item.possibleComponentFamilyIds,
  ))],
  p19_contradiction_artifact_ids: [],
  terminal_decision: {
    kind: "measurement_mission", title: "Measure", instruction: "Collect three eligible laps.",
    authority: "measurement_only", control_key: null, setup_effect_id: null,
    experiment_factor_id: null, direction_sign: null, current_value: null, proposed_value: null,
    source_event_ids: [], workflow_id: null, workflow_revision: null, blocker_reasons: [],
  },
};
workspace.identity.run_sentinel_sha256 = await canonicalEngineeringLearningSha256(workspace.run_sentinel);
workspace.engineering_case.condition_epoch_sha256 = workspace.identity.run_sentinel_sha256;
const scope = { runId: "run-1", sessionId: "session-1", report, objectiveId: "race_long_run" };
const rehashEngineeringKnowledge = async (value) => {
  const body = structuredClone(value.engineering_knowledge);
  delete body.projection_sha256;
  value.engineering_knowledge.projection_sha256 = await canonicalJsonSha256(body);
};
assert.equal(isCrewChiefWorkspaceResponse(workspace, scope), true);
assert.equal(await hasCanonicalEngineeringKnowledgeDigest(workspace.engineering_knowledge), true);
const forgedKnowledgeCoverage = structuredClone(workspace);
forgedKnowledgeCoverage.engineering_knowledge.bridge_coverage_sha256 = h("8");
await rehashEngineeringKnowledge(forgedKnowledgeCoverage);
assert.equal(
  isCrewChiefWorkspaceResponse(forgedKnowledgeCoverage, scope),
  false,
  "a rehashed projection cannot replace the reviewed 92-effect bridge inventory",
);
const duplicateKnowledgeBridge = structuredClone(workspace);
duplicateKnowledgeBridge.engineering_knowledge.hypotheses[1].bridge_id =
  duplicateKnowledgeBridge.engineering_knowledge.hypotheses[0].bridge_id;
await rehashEngineeringKnowledge(duplicateKnowledgeBridge);
assert.equal(
  isCrewChiefWorkspaceResponse(duplicateKnowledgeBridge, scope),
  false,
  "the 92-effect projection cannot reuse one bridge identity",
);
const forgedKnowledgeDirection = structuredClone(workspace);
forgedKnowledgeDirection.engineering_knowledge.hypotheses[0].direction_sign = -1;
await rehashEngineeringKnowledge(forgedKnowledgeDirection);
assert.equal(
  isCrewChiefWorkspaceResponse(forgedKnowledgeDirection, scope),
  false,
  "a coordinated rehash cannot swap the reviewed direction of a setup effect",
);
const forgedKnowledgeComponents = structuredClone(workspace);
forgedKnowledgeComponents.engineering_knowledge.hypotheses[0]
  .possible_component_family_ids = ["invented_component_family"];
await rehashEngineeringKnowledge(forgedKnowledgeComponents);
assert.equal(
  isCrewChiefWorkspaceResponse(forgedKnowledgeComponents, scope),
  false,
  "a coordinated rehash cannot replace the reviewed static component relationship",
);
const forgedKnowledgeHistory = structuredClone(workspace);
forgedKnowledgeHistory.engineering_knowledge.hypotheses[0].controlled_history = [{
  experience_id: `p33x_${"1".repeat(24)}`, workflow_id: "workflow-forged",
  component_family_id: "springs", control_key: "spring_rate",
  transfer_level: "exact", mechanism_assessment: "supported",
  control_response: "matched", policy_verdict: "keep", countereffects: [],
  source_artifact_ids: [], authority: "controlled_history_only", setup_authorized: false,
}];
await rehashEngineeringKnowledge(forgedKnowledgeHistory);
assert.equal(
  isCrewChiefWorkspaceResponse(forgedKnowledgeHistory, scope),
  false,
  "controlled knowledge history must resolve to the exact current P33 projection",
);
const forgedKnowledgeControl = structuredClone(workspace);
Object.assign(forgedKnowledgeControl.engineering_knowledge.hypotheses[0], {
  level: "p19_testable_control", relevance: "supported_candidate",
  p32_opportunity_id: "opportunity-forged", authority: "exact_p19_projection",
  setup_authorized: true,
  p19_control: {
    control_key: "spring_rate", current_value: "1000", proposed_value: "1050",
    workflow_id: "workflow-forged", workflow_revision: "revision-forged",
    source_event_ids: ["event-forged"], authority: "exact_p19_projection",
  },
});
await rehashEngineeringKnowledge(forgedKnowledgeControl);
assert.equal(
  isCrewChiefWorkspaceResponse(forgedKnowledgeControl, scope),
  false,
  "a knowledge-only response cannot manufacture an exact P19 setup target",
);
assert.equal(await hasCanonicalEngineeringAwarenessDigest(workspace), true);
assert.equal(await hasCanonicalCrewEvidenceIndexDigest(workspace), true);
assert.equal(await hasCanonicalVehicleRuntimeIdentityDigest(workspace), true);
const p20DeliveryVariant = structuredClone(workspace);
p20DeliveryVariant.engineering_awareness.generated_at = "2026-08-15T09:05:01Z";
p20DeliveryVariant.engineering_awareness.cache_state = "warm";
p20DeliveryVariant.engineering_awareness.build_duration_ms = 99;
assert.equal(
  await hasCanonicalEngineeringAwarenessDigest(p20DeliveryVariant),
  true,
  "P20 delivery metadata is excluded from the scientific identity",
);
const integerValuedP20Controls = structuredClone(workspace);
integerValuedP20Controls.engineering_awareness.control_mutations = [{
  mutation_id: "control-integer-float",
  run_id: "run-1",
  control_key: "requested_fuel_fill",
  mutation_kind: "requested_state",
  previous_value: 0,
  new_value: 1,
  session_time: 4008,
  lap: 5,
  lap_pct: 10,
  confirmation_artifact_ids: [],
  context_revision: 1,
  evidence_state: "measured",
  authority: "context_only",
  applied_state_confirmed: false,
}];
integerValuedP20Controls.identity.p20_projection_sha256 =
  await canonicalEngineeringAwarenessScientificSha256(
    integerValuedP20Controls.engineering_awareness,
  );
assert.equal(
  await hasCanonicalEngineeringAwarenessDigest(integerValuedP20Controls),
  true,
  "integer-looking P20 float fields retain Python canonical-number semantics",
);
integerValuedP20Controls.engineering_awareness.control_mutations[0].lap_pct = 11;
assert.equal(
  await hasCanonicalEngineeringAwarenessDigest(integerValuedP20Controls),
  false,
  "P20 numeric drift cannot retain a stale scientific digest",
);
const staleP20ScientificBody = structuredClone(workspace);
staleP20ScientificBody.engineering_awareness.subsystem_states[0].summary =
  "A different scientific observation.";
assert.equal(
  await hasCanonicalEngineeringAwarenessDigest(staleP20ScientificBody),
  false,
  "P20 scientific content remains bound to the workspace identity",
);
const unavailableRuntimeWorkspace = structuredClone(workspace);
const unavailableRuntimeReport = structuredClone(report);
unavailableRuntimeReport.vehicle_systems = null;
unavailableRuntimeWorkspace.identity.vehicle_runtime_identity = null;
const unavailableDynamicsBody = structuredClone(unavailableRuntimeWorkspace.vehicle_dynamics);
delete unavailableDynamicsBody.p35_assessment_sha256;
unavailableDynamicsBody.car_path = "unavailable";
unavailableDynamicsBody.car_version = "unavailable";
unavailableDynamicsBody.iracing_build_version = "unavailable";
unavailableDynamicsBody.track_package = "unavailable";
unavailableDynamicsBody.applicability_state = "unavailable";
unavailableDynamicsBody.applicability_blockers = [
  "Verified P26 runtime identity is unavailable.",
];
unavailableDynamicsBody.blocker_reasons = [
  ...unavailableDynamicsBody.blocker_reasons,
  "Verified P26 runtime identity is unavailable.",
];
unavailableRuntimeWorkspace.vehicle_dynamics = {
  ...unavailableDynamicsBody,
  p35_assessment_sha256: await canonicalPerformanceMechanismAssessmentSha256(
    unavailableDynamicsBody,
  ),
};
unavailableRuntimeWorkspace.identity.p35_assessment_sha256 =
  unavailableRuntimeWorkspace.vehicle_dynamics.p35_assessment_sha256;
unavailableRuntimeWorkspace.engineering_knowledge.p35_assessment_sha256 =
  unavailableRuntimeWorkspace.vehicle_dynamics.p35_assessment_sha256;
unavailableRuntimeWorkspace.engineering_knowledge.hypotheses.forEach((item) => {
  if (item.level !== "unsupported_remove") item.knowledge_applicability = "blocked_by_build";
});
{
  const { projection_sha256: _digest, ...body } = unavailableRuntimeWorkspace.engineering_knowledge;
  unavailableRuntimeWorkspace.engineering_knowledge.projection_sha256 = await canonicalJsonSha256(body);
}
unavailableRuntimeWorkspace.engineering_case.p35_assessment_sha256 =
  unavailableRuntimeWorkspace.vehicle_dynamics.p35_assessment_sha256;
unavailableRuntimeWorkspace.engineering_case.p351_projection_sha256 =
  unavailableRuntimeWorkspace.engineering_knowledge.projection_sha256;
const unavailableRuntimeScope = { ...scope, report: unavailableRuntimeReport };
assert.equal(
  isCrewChiefWorkspaceResponse(unavailableRuntimeWorkspace, unavailableRuntimeScope),
  true,
  "P26/P35 unavailable remains a valid observation-only workspace",
);
assert.equal(
  await hasCanonicalVehicleRuntimeIdentityDigest(unavailableRuntimeWorkspace),
  true,
  "the canonical unavailable runtime carries no P35 candidate or focus",
);
assert.equal(
  await hasCanonicalInvestigationImprovementDigests(
    workspace.investigation_improvement,
    workspace,
  ),
  true,
);
assert.equal(
  await hasCanonicalRunSentinelDigest(workspace.run_sentinel, workspace.identity.run_sentinel_sha256),
  true,
);
const staleSentinelDigest = structuredClone(workspace);
staleSentinelDigest.run_sentinel.blocker_reasons = ["New safe blocker."];
assert.equal(isCrewChiefWorkspaceResponse(staleSentinelDigest, scope), true);
assert.equal(
  await hasCanonicalRunSentinelDigest(
    staleSentinelDigest.run_sentinel,
    staleSentinelDigest.identity.run_sentinel_sha256,
  ),
  false,
  "mission progress body must remain bound to its canonical identity",
);
const withInvestigation = structuredClone(workspace);
withInvestigation.identity.investigation_id = "investigation-1";
withInvestigation.investigation = {
  investigation_id: "investigation-1",
  workspace_identity: structuredClone(workspace.identity),
  origin: "driver_report",
  objective: "race_long_run",
  raw_driver_report: "The balance changed in the center.",
  canonical_problem: "balance changed in the center",
  opening_reasoning: {
    reasoning_snapshot_sha256: h("a"), causes: [], measurement_plan_kind: "measurement_only",
    discriminator_ids: [], authority_level: "measurement", setup_authorized: false,
  },
  opening_problem: {
    problem_sha256: h("3"), physical_episode_id: "episode-1",
    performance_opportunity_id: "opportunity-1", phase: "center",
    physical_region: "T1-T2", time_origin_class: "local_loss",
    carry_behavior: "no_measured_carry", driver_demand_state: "matched_inputs",
    vehicle_response_state: "changed_response", p20_mechanism_families: ["platform"],
    p26_component_families: ["rf_tire"], traffic_context_state: "clear",
    tire_stint_state: "short_run", objective: "race_long_run",
    source_artifact_ids: ["artifact-opening"],
  },
  opened_at: "2026-08-15T09:00:00Z",
  consumption_baseline: null,
  status: "open",
};
withInvestigation.folded_state = {
  investigation_id: "investigation-1", status: "open", event_count: 0,
  last_sequence: 0, objective: "race_long_run", completed_tool_ids: [],
  pending_driver_question_id: null, driver_answers: ["center changed"],
  driver_answer_interpretations: [{
    answer: "center changed", phase_scope: [], response_regime_scope: [],
    traffic_scope: "all", stint_scope: "all", power_state_scope: "all",
    time_origin_scope: "all", driver_demand_scope: [], context_record_only: true,
  }],
  hypotheses: [],
  latest_critique_outcome: null,
  last_decision_kind: null, accepted_workspace_revision: h("c"),
};
withInvestigation.current_subgoal = {
  subgoal_id: "subgoal-1", title: "Inspect exit carry",
  selected_tool: "inspect_exit_carry",
  why_this_tool: "This bounded measurement addresses the next evidence gap.",
  distinguishes_cause_ids: [], mechanism_ids: [], bridge_ids: [], effect_ids: [],
  opportunity_id: null, required_discriminator_id: null, exact_control_keys: [],
  experiment_factor_ids: [],
  driver_answer_interpretation: structuredClone(
    withInvestigation.folded_state.driver_answer_interpretations[
      withInvestigation.folded_state.driver_answer_interpretations.length - 1
    ],
  ),
  required_evidence: ["qualified elapsed time"],
  stop_condition: "Stop when the bounded inspection resolves.",
  priority_rank: 1,
};
const exitEligibility = withInvestigation.tool_eligibility.find(
  (item) => item.tool_id === "inspect_exit_carry",
);
exitEligibility.currently_relevant = true;
exitEligibility.skip_reason = null;
assert.equal(isCrewChiefWorkspaceResponse(withInvestigation, scope), true);
for (const [label, mutate] of [
  ["missing opening problem", (value) => { delete value.investigation.opening_problem; }],
  ["unknown investigation field", (value) => { value.investigation.hidden_setup_call = "52%"; }],
  ["unknown opening reasoning field", (value) => { value.investigation.opening_reasoning.confidence = 1; }],
  ["missing opening identity field", (value) => { delete value.investigation.workspace_identity.p32_projection_sha256; }],
  ["opening reasoning identity mismatch", (value) => { value.investigation.opening_reasoning.reasoning_snapshot_sha256 = h("0"); }],
  ["opening problem objective mismatch", (value) => { value.investigation.opening_problem.objective = "qualifying_peak"; }],
]) {
  const hostile = structuredClone(withInvestigation);
  mutate(hostile);
  assert.equal(isCrewChiefWorkspaceResponse(hostile, scope), false, label);
}

const memoryRecordId = `p33x_${"4".repeat(24)}`;
const baselineP34Decision = {
  decision_kind: "inspect_tool", action_id: "inspect_exit_carry",
  priority_tier: "driver_car_confounders", safe_reorder_group: "performance_measurement",
  baseline_ordinal: 4, selected_ordinal: 4,
  reason: "Deterministic evidence order selected this inspection.",
  mandatory_check_ids: [
    "workspace_identity", "data_integrity", "telemetry_health",
    "context_comparability", "traffic_contamination", "vehicle_condition_epoch",
    "applied_control_state", "strongest_contradiction", "driver_car_separation",
  ],
  source_memory_record_ids: [], setup_authorized: false, terminal_policy_authorized: false,
};
const memoryP34Decision = {
  ...baselineP34Decision,
  reason: "No qualified memory changed the executable inspection.",
};
const authorityIdentity = structuredClone(withInvestigation.identity);
for (const key of [
  "objective_id", "investigation_id", "workspace_revision", "learning_history_revision",
  "learning_ledger_head_sha256", "learning_projection_sha256", "run_sentinel_sha256",
  "p35_assessment_sha256",
]) delete authorityIdentity[key];
const currentP34Truth = await canonicalJsonSha256({
  identity: withInvestigation.identity,
  evidence_index_sha256: withInvestigation.evidence_index.index_hash,
  terminal_decision: withInvestigation.terminal_decision,
  p19_cause_ids: withInvestigation.p19_cause_ids,
  p19_cause_states: [],
  p19_contradiction_artifact_ids: withInvestigation.p19_contradiction_artifact_ids,
});
const noRelevantHistoryProof = {
  condition: "no_relevant_history", p33_projection_sha256: h("2"),
  p33_state: "insufficient_history", context_transfer_record_ids: [],
  context_transfer_levels: [], useful_prior_experience_ids: [],
  component_history_experience_ids: [], physical_scope_mismatch_dimensions: [],
  recurrence_class: "new_problem", corruption_blocker_sha256s: [],
  future_memory_record_ids: [], future_memory_record_completed_ats: [],
  driver_drift_state: "unknown",
};
const p34PairBody = {
  schema_version: "p34.paired-investigation-decision.v1",
  investigation_id: "investigation-1", investigation_opened_at: "2026-08-15T09:00:00Z",
  run_id: "run-1", session_id: "session-1",
  workspace_revision: h("c"), authority_revision: await canonicalJsonSha256(authorityIdentity),
  step_number: 0, baseline_policy_id: "p34pol_48190cf9a560de6fae1bb655",
  baseline_policy_sha256: "48190cf9a560de6fae1bb655fe365b41478038825653743b2a391d62ea788709",
  memory_policy_id: "p34pol_de720756ba383ec92910e64e",
  memory_policy_sha256: "de720756ba383ec92910e64e6360685d9d0f900adb4e5f9156db4488b3e55198",
  activation_protocol_id: "p34proto_487dd9698e01a7f77d493d01",
  activation_protocol_sha256: "487dd9698e01a7f77d493d011e4f0ec0246ba0ed7efdaea17ef164cbc7a8fd61",
  activation_state: "shadow_only",
  activation_decision_id: null, activation_decision_sha256: null,
  production_policy_kind: "deterministic_baseline",
  baseline_decision: baselineP34Decision, memory_decision: memoryP34Decision,
  production_decision: baselineP34Decision,
  available_tool_ids: availableTools.filter((tool) => !p34ExcludedToolIds.includes(tool.tool_id)).map((tool) => tool.tool_id),
  eligible_tool_ids: availableTools.filter((tool) => !p34ExcludedToolIds.includes(tool.tool_id)).map((tool) => tool.tool_id), completed_tool_ids: [],
  available_artifact_ids: [], qualified_available_artifact_ids: [],
  qualified_available_artifact_evidence_states: [],
  qualified_available_artifact_provenance_sha256s: [], current_evidence_pinned_tool_ids: [],
  current_truth_sha256: currentP34Truth, p19_snapshot_sha256: h("a"),
  p20_projection_sha256: h("d"), p26_projection_sha256: h("e"), p32_projection_sha256: h("7"),
  current_p19_cause_ids: [], current_p19_cause_states: [],
  current_contradiction_ids: [], strongest_contradiction_id: null,
  current_objective: "race_long_run", p33_projection_sha256: h("2"),
  p33_history_revision: h("1"), p33_ledger_head_sha256: null, p33_context_sha256: h("3"),
  p33_problem_sha256: h("4"), track: "Atlanta Motor Speedway",
  track_configuration: "Oval", package_type: "stockcar", iracing_build: "2026.08",
  problem_family: "center", problem_orientation: "vehicle", track_class: "intermediate",
  phase: "center", context_subgroup_keys: [
    "weak_history", "vehicle_response", "center", "race_long_run_objective",
    "intermediate", "driver_state_unknown", "same_build",
  ],
  build_review_state: "same_build", driver_drift_state: "unknown",
  negative_control_condition: "no_relevant_history",
  negative_control_evidence: noRelevantHistoryProof, future_memory_record_ids: [],
  memory_records_consulted: [],
  context_transfer_class: "none", decision_frozen_at: "2026-08-15T09:04:00Z",
  outcome_exposed: false, p19_rank_unchanged: true, p19_authority_unchanged: true,
  p19_terminal_action_unchanged: true, setup_authorized: false,
};
const p34PairDigest = await canonicalInvestigationImprovementSha256(p34PairBody);
const p34Pair = {
  ...p34PairBody,
  pair_id: `p34pair_${p34PairDigest.slice(0, 24)}`,
  pair_sha256: p34PairDigest,
};
const p34ContextBody = {
  schema_version: "p34.investigation-adaptation-context.v1",
  run_id: p34Pair.run_id, session_id: p34Pair.session_id,
  workspace_revision: p34Pair.workspace_revision,
  current_truth_sha256: p34Pair.current_truth_sha256,
  p19_snapshot_sha256: p34Pair.p19_snapshot_sha256,
  p20_projection_sha256: p34Pair.p20_projection_sha256,
  p26_projection_sha256: p34Pair.p26_projection_sha256,
  p32_projection_sha256: p34Pair.p32_projection_sha256,
  p33_projection_sha256: p34Pair.p33_projection_sha256,
  p33_context_sha256: p34Pair.p33_context_sha256,
  p33_problem_sha256: p34Pair.p33_problem_sha256,
  qualified_available_artifact_ids: [], qualified_available_artifact_evidence_states: [],
  qualified_available_artifact_provenance_sha256s: [], current_evidence_pinned_tool_ids: [],
  track: p34Pair.track, track_configuration: p34Pair.track_configuration,
  package_type: p34Pair.package_type, iracing_build: p34Pair.iracing_build,
  problem_family: p34Pair.problem_family, problem_orientation: p34Pair.problem_orientation,
  track_class: p34Pair.track_class, phase: p34Pair.phase,
  current_objective: p34Pair.current_objective, build_review_state: p34Pair.build_review_state,
  driver_drift_state: p34Pair.driver_drift_state,
  context_subgroup_keys: p34Pair.context_subgroup_keys,
  negative_control_condition: p34Pair.negative_control_condition,
  negative_control_evidence_sha256: await canonicalInvestigationImprovementSha256(noRelevantHistoryProof),
};
const p34Context = {
  ...p34ContextBody,
  context_binding_sha256: await canonicalInvestigationImprovementSha256(p34ContextBody),
};
const availableImprovementBody = {
  ...improvementBody,
  state: "available", current_pair: p34Pair, current_context: p34Context,
  current_pair_status: "pending",
  decisions_differ: false,
  difference_explanation: "The baseline and shadow retain the same executable action.",
  memory_evidence_record_ids: [], context_transfer_class: "none",
  safety_blockers: ["Limited attention has not earned the frozen gates."],
};
const availableImprovement = {
  ...availableImprovementBody,
  projection_sha256: await canonicalInvestigationImprovementSha256(availableImprovementBody),
};
const withP34Pair = structuredClone(withInvestigation);
withP34Pair.investigation_improvement = availableImprovement;
assert.deepEqual(
  withP34Pair.investigation_improvement.current_pair.available_tool_ids,
  withP34Pair.available_tools
    .filter((tool) => !p34ExcludedToolIds.includes(tool.tool_id))
    .map((tool) => tool.tool_id),
);
assert.equal(
  isCurrentEngineeringKnowledgeProjection(
    withP34Pair.engineering_knowledge,
    withP34Pair,
    report.vehicle_systems,
  ),
  true,
  "P35.1 projection remains valid for the P34 pair fixture",
);
assert.equal(
  isCrewChiefWorkspaceResponse(withP34Pair, scope),
  true,
  "P34 provenance-only differences must not become executable differences",
);
assert.equal(
  await hasCanonicalInvestigationImprovementDigests(
    withP34Pair.investigation_improvement,
    withP34Pair,
  ),
  true,
);

const forgedP34ProjectionDigest = structuredClone(withP34Pair);
forgedP34ProjectionDigest.investigation_improvement.difference_explanation = "Safe wording changed after hashing.";
assert.equal(
  await hasCanonicalInvestigationImprovementDigests(
    forgedP34ProjectionDigest.investigation_improvement,
    forgedP34ProjectionDigest,
  ),
  false,
  "P34 projection content must remain bound to its digest",
);
const forgedP34PairDigest = structuredClone(withP34Pair);
forgedP34PairDigest.investigation_improvement.current_pair.memory_decision.reason = "Safe pair wording changed after freeze.";
assert.equal(
  await hasCanonicalInvestigationImprovementDigests(
    forgedP34PairDigest.investigation_improvement,
    forgedP34PairDigest,
  ),
  false,
  "P34 pair content must remain bound to its digest",
);
for (const [label, mutate] of [
  ["unobserved saved laps", (value) => { value.investigation_improvement.difference_explanation = "The shadow saved 2 laps."; }],
  ["unobserved percent improvement", (value) => { value.investigation_improvement.difference_explanation = "The shadow delivered a 20% improvement."; }],
  ["unobserved success claim", (value) => { value.investigation_improvement.difference_explanation = "The memory policy was successful."; }],
  ["future-frozen decision", (value) => { value.investigation_improvement.current_pair.decision_frozen_at = "2026-08-15T09:06:00Z"; }],
  ["decision before investigation", (value) => { value.investigation_improvement.current_pair.investigation_opened_at = "2026-08-15T09:04:30Z"; }],
  ["foreign available tool", (value) => { value.investigation_improvement.current_pair.available_tool_ids.push("inspect_secret_setup"); }],
  ["foreign eligible tool", (value) => { value.investigation_improvement.current_pair.eligible_tool_ids.push("inspect_secret_setup"); }],
  ["stale completed tool", (value) => { value.investigation_improvement.current_pair.completed_tool_ids.push("inspect_exit_carry"); }],
  ["foreign current artifact", (value) => { value.investigation_improvement.current_pair.available_artifact_ids.push("artifact-foreign"); }],
  ["fabricated qualified artifact", (value) => {
    value.investigation_improvement.current_pair.available_artifact_ids.push("artifact-fabricated");
    value.investigation_improvement.current_pair.qualified_available_artifact_ids.push("artifact-fabricated");
    value.investigation_improvement.current_pair.qualified_available_artifact_evidence_states.push("measured");
    value.investigation_improvement.current_pair.qualified_available_artifact_provenance_sha256s.push(h("f"));
  }],
  ["unsupported current evidence pin", (value) => { value.investigation_improvement.current_pair.current_evidence_pinned_tool_ids.push("inspect_exit_carry"); }],
  ["stale P19 cause state", (value) => {
    value.investigation_improvement.current_pair.current_p19_cause_ids.push("cause-stale");
    value.investigation_improvement.current_pair.current_p19_cause_states.push({ cause_id: "cause-stale", state: "likely" });
  }],
  ["foreign P33 projection", (value) => { value.investigation_improvement.current_pair.p33_projection_sha256 = h("9"); }],
  ["foreign P33 context", (value) => { value.investigation_improvement.current_pair.p33_context_sha256 = h("9"); }],
  ["malformed workspace revision", (value) => { value.investigation_improvement.current_pair.workspace_revision = "revision-1"; }],
  ["invented subgroup", (value) => { value.investigation_improvement.current_pair.context_subgroup_keys.push("winning_cases"); }],
  ["contradictory negative control", (value) => { value.investigation_improvement.current_pair.negative_control_condition = "material_driver_drift"; }],
  ["future memory without proof", (value) => { value.investigation_improvement.current_pair.future_memory_record_ids.push(memoryRecordId); }],
  ["provenance-only executable claim", (value) => { value.investigation_improvement.decisions_differ = true; }],
]) {
  const hostile = structuredClone(withP34Pair);
  mutate(hostile);
  assert.equal(isCrewChiefWorkspaceResponse(hostile, scope), false, label);
}

async function rehashP34Projection(value) {
  for (const key of ["current_pair", "latest_completed_pair"]) {
    const pair = value.investigation_improvement[key];
    if (pair === null) continue;
    const body = structuredClone(pair);
    delete body.pair_id;
    delete body.pair_sha256;
    const digest = await canonicalInvestigationImprovementSha256(body);
    pair.pair_id = `p34pair_${digest.slice(0, 24)}`;
    pair.pair_sha256 = digest;
  }
  if (value.investigation_improvement.current_context !== null) {
    const contextBody = structuredClone(value.investigation_improvement.current_context);
    delete contextBody.context_binding_sha256;
    value.investigation_improvement.current_context.context_binding_sha256 =
      await canonicalInvestigationImprovementSha256(contextBody);
  }
  const comparison = value.investigation_improvement.latest_completed_comparison;
  if (comparison !== null) {
    const body = structuredClone(comparison);
    delete body.comparison_id;
    delete body.comparison_sha256;
    const digest = await canonicalInvestigationImprovementSha256(body);
    comparison.comparison_id = `p34cmp_${digest.slice(0, 24)}`;
    comparison.comparison_sha256 = digest;
  }
  const projectionBody = structuredClone(value.investigation_improvement);
  delete projectionBody.projection_sha256;
  value.investigation_improvement.projection_sha256 = await canonicalInvestigationImprovementSha256(projectionBody);
}

const rehashedReasonBenefit = structuredClone(withP34Pair);
rehashedReasonBenefit.investigation_improvement.current_pair.memory_decision.reason =
  "The unobserved memory path saved 2 investigation steps.";
await rehashP34Projection(rehashedReasonBenefit);
assert.equal(
  isCrewChiefWorkspaceResponse(rehashedReasonBenefit, scope),
  false,
  "a digest-valid frozen decision reason cannot claim unobserved benefit",
);

const rehashedCausalReason = structuredClone(withP34Pair);
rehashedCausalReason.investigation_improvement.current_pair.memory_decision.reason =
  "Shocks caused the time loss.";
await rehashP34Projection(rehashedCausalReason);
assert.equal(
  isCrewChiefWorkspaceResponse(rehashedCausalReason, scope),
  false,
  "a digest-valid P34 reason cannot claim component causality",
);

const forgedCurrentTruth = structuredClone(withP34Pair);
forgedCurrentTruth.investigation_improvement.current_pair.current_truth_sha256 = h("9");
forgedCurrentTruth.investigation_improvement.current_context.current_truth_sha256 = h("9");
await rehashP34Projection(forgedCurrentTruth);
assert.equal(isCrewChiefWorkspaceResponse(forgedCurrentTruth, scope), true);
assert.equal(
  await hasCanonicalInvestigationImprovementDigests(
    forgedCurrentTruth.investigation_improvement,
    forgedCurrentTruth,
  ),
  false,
  "a rehashed pair cannot replace the exact current Crew truth digest",
);

const forgedAuthority = structuredClone(withP34Pair);
forgedAuthority.investigation_improvement.current_pair.authority_revision = h("9");
await rehashP34Projection(forgedAuthority);
assert.equal(isCrewChiefWorkspaceResponse(forgedAuthority, scope), true);
assert.equal(
  await hasCanonicalInvestigationImprovementDigests(
    forgedAuthority.investigation_improvement,
    forgedAuthority,
  ),
  false,
  "a rehashed pair cannot replace the producer-owned authority revision",
);

const forgedProductionBinding = structuredClone(withP34Pair);
forgedProductionBinding.current_subgoal.selected_tool = "inspect_path_efficiency";
assert.equal(isCrewChiefWorkspaceResponse(forgedProductionBinding, scope), false);
assert.equal(
  await hasCanonicalInvestigationImprovementDigests(
    forgedProductionBinding.investigation_improvement,
    forgedProductionBinding,
  ),
  false,
  "the frozen production action must equal the public current Crew action",
);

const historicalPairBody = {
  ...structuredClone(p34PairBody),
  investigation_id: "historical-investigation", run_id: "historical-run",
  session_id: "historical-session", workspace_revision: h("5"),
  investigation_opened_at: "2026-08-15T08:20:00Z",
  authority_revision: h("6"), current_truth_sha256: h("7"),
  available_tool_ids: [...p34PairBody.available_tool_ids, "inspect_track_demand"],
  available_artifact_ids: ["historical-artifact"],
  decision_frozen_at: "2026-08-15T08:30:00Z",
};
const historicalPairDigest = await canonicalInvestigationImprovementSha256(historicalPairBody);
const historicalPair = {
  ...historicalPairBody,
  pair_id: `p34pair_${historicalPairDigest.slice(0, 24)}`,
  pair_sha256: historicalPairDigest,
};
const historicalComparisonBody = {
  schema_version: "p34.paired-investigation-comparison.v1",
  investigation_id: historicalPair.investigation_id,
  pair_id: historicalPair.pair_id, pair_sha256: historicalPair.pair_sha256,
  activation_protocol_id: historicalPair.activation_protocol_id,
  activation_protocol_sha256: historicalPair.activation_protocol_sha256,
  certificate_id: `p34out_${"5".repeat(24)}`, certificate_sha256: h("5"),
  discriminator_outcome_id: null, discriminator_outcome_sha256: null,
  outcome_followup_id: null, outcome_followup_sha256: null,
  counterfactual_source_certificate_id: null,
  counterfactual_source_certificate_sha256: null,
  independently_observed_artifact_ids: [],
  decision_frozen_at: historicalPair.decision_frozen_at,
  observability: "counterfactual_unobservable", context_identity_sha256: h("3"),
  problem_family: "center", objective: "race_long_run",
  context_transfer_class: historicalPair.context_transfer_class,
  subgroup_keys: historicalPair.context_subgroup_keys,
  baseline_tool_steps: 2, memory_path_metrics_observed: false,
  bounded_reorder_observed: false, bounded_discriminator_step_advance: 0,
  bounded_discriminator_step_delay: 0, bounded_dead_end_promoted: false,
  memory_tool_steps: null, baseline_elapsed_seconds: 120,
  memory_elapsed_seconds: null, baseline_consumption_metrics_observed: true,
  memory_consumption_metrics_observed: false, baseline_laps: 3, memory_laps: null,
  baseline_questions: 1, memory_questions: null,
  baseline_dead_ends: 0, memory_dead_ends: null,
  baseline_measurement_missions: 1, memory_measurement_missions: null,
  baseline_repeated_no_findings: 0, memory_repeated_no_findings: null,
  baseline_useful_discriminator_step: 2, memory_useful_discriminator_step: null,
  baseline_unresolved_or_abandoned: false, memory_unresolved_or_abandoned: null,
  useful_discriminator_hit: true, strongest_contradiction_handled: true,
  recurrence_match_correct: null, context_transfer_correct: null,
  driver_car_separation_correct: null, eventual_p19_resolution: true,
  no_call_stable: true, authority_violations: 0, p19_action_mismatches: 0,
  stale_workspace_actions: 0, mandatory_check_violations: 0,
  hidden_contradiction_failures: 0, incompatible_history_transfers: 0,
  driver_memory_mechanical_diagnoses: 0, memory_only_terminal_actions: 0,
  prospective: true, synthetic: false, qualified: false,
  blockers: ["The historical memory path was not directly observed."],
  compared_at: "2026-08-15T08:40:00Z", setup_authorized: false,
};
const historicalComparisonDigest = await canonicalInvestigationImprovementSha256(historicalComparisonBody);
const historicalComparison = {
  ...historicalComparisonBody,
  comparison_id: `p34cmp_${historicalComparisonDigest.slice(0, 24)}`,
  comparison_sha256: historicalComparisonDigest,
};
const historicalProjectionBody = {
  ...structuredClone(improvementBody), state: "available",
  latest_completed_pair: historicalPair,
  latest_completed_comparison: historicalComparison,
  latest_outcome_status: historicalComparison.observability,
  memory_evidence_record_ids: [], context_transfer_class: "none",
  difference_explanation: "The historical pair retained the same executable action; no benefit is inferred.",
};
const historicalProjection = {
  ...historicalProjectionBody,
  projection_sha256: await canonicalInvestigationImprovementSha256(historicalProjectionBody),
};
const withHistoricalP34 = structuredClone(workspace);
withHistoricalP34.investigation_improvement = historicalProjection;
assert.equal(
  isCrewChiefWorkspaceResponse(withHistoricalP34, scope),
  true,
  "a completed historical pair is not falsely rebound to current workspace tools or scope",
);
assert.equal(
  await hasCanonicalInvestigationImprovementDigests(
    withHistoricalP34.investigation_improvement,
    withHistoricalP34,
  ),
  true,
  "historical pair and comparison identities remain independently content-addressed",
);

const completedPairSwappedCurrent = structuredClone(withHistoricalP34);
completedPairSwappedCurrent.investigation_improvement.current_pair =
  structuredClone(completedPairSwappedCurrent.investigation_improvement.latest_completed_pair);
completedPairSwappedCurrent.investigation_improvement.current_pair_status = "pending";
completedPairSwappedCurrent.investigation_improvement.latest_completed_pair = null;
completedPairSwappedCurrent.investigation_improvement.latest_completed_comparison = null;
completedPairSwappedCurrent.investigation_improvement.latest_outcome_status = null;
await rehashP34Projection(completedPairSwappedCurrent);
assert.equal(
  isCrewChiefWorkspaceResponse(completedPairSwappedCurrent, scope),
  false,
  "a completed historical pair cannot be swapped into the current-workspace slot",
);

const futureHistoricalFreeze = structuredClone(withHistoricalP34);
futureHistoricalFreeze.investigation_improvement.latest_completed_pair.decision_frozen_at =
  "2026-08-16T12:06:00Z";
futureHistoricalFreeze.investigation_improvement.latest_completed_comparison.decision_frozen_at =
  "2026-08-16T12:06:00Z";
futureHistoricalFreeze.investigation_improvement.latest_completed_comparison.compared_at =
  "2026-08-16T12:07:00Z";
await rehashP34Projection(futureHistoricalFreeze);
futureHistoricalFreeze.investigation_improvement.latest_completed_comparison.pair_id =
  futureHistoricalFreeze.investigation_improvement.latest_completed_pair.pair_id;
futureHistoricalFreeze.investigation_improvement.latest_completed_comparison.pair_sha256 =
  futureHistoricalFreeze.investigation_improvement.latest_completed_pair.pair_sha256;
await rehashP34Projection(futureHistoricalFreeze);
assert.equal(
  isCrewChiefWorkspaceResponse(futureHistoricalFreeze, scope),
  true,
  "a historical frozen decision is not falsely rebound to current workspace time",
);
assert.equal(
  await hasCanonicalInvestigationImprovementDigests(
    futureHistoricalFreeze.investigation_improvement,
    futureHistoricalFreeze,
  ),
  true,
  "a content-addressed historical chain remains standalone across runs and times",
);

const futureHistoricalComparison = structuredClone(withHistoricalP34);
futureHistoricalComparison.investigation_improvement.latest_completed_comparison.compared_at =
  "2026-08-17T12:06:00Z";
await rehashP34Projection(futureHistoricalComparison);
assert.equal(
  isCrewChiefWorkspaceResponse(futureHistoricalComparison, scope),
  true,
  "a historical comparison is not rebound to current workspace time",
);

const forgedHistoricalParent = structuredClone(withHistoricalP34);
forgedHistoricalParent.investigation_improvement.latest_completed_comparison.pair_id = `p34pair_${"0".repeat(24)}`;
await rehashP34Projection(forgedHistoricalParent);
assert.equal(
  isCrewChiefWorkspaceResponse(forgedHistoricalParent, scope),
  false,
  "a completed comparison must bind its exact historical parent pair",
);
const fabricatedHistoricalOutcome = structuredClone(withHistoricalP34);
fabricatedHistoricalOutcome.investigation_improvement.latest_completed_comparison.memory_tool_steps = 1;
await rehashP34Projection(fabricatedHistoricalOutcome);
assert.equal(
  isCrewChiefWorkspaceResponse(fabricatedHistoricalOutcome, scope),
  false,
  "an unobservable comparison cannot fabricate memory-path efficiency",
);
const fabricatedHistoricalCorrectness = structuredClone(withHistoricalP34);
fabricatedHistoricalCorrectness.investigation_improvement.latest_completed_comparison.context_transfer_correct = true;
await rehashP34Projection(fabricatedHistoricalCorrectness);
assert.equal(
  isCrewChiefWorkspaceResponse(fabricatedHistoricalCorrectness, scope),
  false,
  "an unobservable comparison cannot claim learned-path correctness",
);
const fabricatedHistoricalBenefit = structuredClone(withHistoricalP34);
fabricatedHistoricalBenefit.investigation_improvement.latest_completed_comparison.blockers = [
  "The unobserved memory path saved 2 investigation steps.",
];
await rehashP34Projection(fabricatedHistoricalBenefit);
assert.equal(
  isCrewChiefWorkspaceResponse(fabricatedHistoricalBenefit, scope),
  false,
  "unobservable comparison prose cannot claim time, lap, step, or success benefits",
);
const fabricatedInvalidSuccess = structuredClone(withHistoricalP34);
fabricatedInvalidSuccess.investigation_improvement.latest_completed_comparison.observability = "invalid";
fabricatedInvalidSuccess.investigation_improvement.latest_outcome_status = "invalid";
fabricatedInvalidSuccess.investigation_improvement.latest_completed_comparison.blockers = [
  "The memory policy was successful.",
];
await rehashP34Projection(fabricatedInvalidSuccess);
assert.equal(
  isCrewChiefWorkspaceResponse(fabricatedInvalidSuccess, scope),
  false,
  "invalid comparison prose cannot claim success",
);
const missionBody = {
  schema_version: "p19.measurement-mission.v2",
  candidate_id: "measurement-mission-1",
  run_id: "run-1",
  session_id: "session-1",
  session_run_ids: ["run-1"],
  source_setup_id: "setup-1",
  setup_sha256: h("d"),
  compatibility_fingerprint: h("e"),
  purpose: "Acquire the missing evidence discriminator.",
  procedure: ["Record the declared channels."],
  required_channels: ["speed_mph"],
  controlled_variables: ["setup"],
  required_laps: 3,
  acceptance_thresholds: ["Three eligible laps."],
  integrity_stop_rules: ["Discard an invalid lap."],
  source_event_ids: [],
  cause_ids: [],
  telemetry_health_identity: h("6"),
  resource_snapshot: {
    remaining_laps: null, remaining_time_s: null, fuel_laps_available: null,
    tire_sets_available: null, source: "unknown",
  },
};
const missionDigest = await canonicalJsonSha256(missionBody, {
  pythonFloatKeys: new Set(["remaining_time_s", "fuel_laps_available"]),
});
const missionContract = {
  ...missionBody,
  contract_id: `mission:${missionDigest.slice(0, 20)}`,
  contract_sha256: missionDigest,
  created_at: "2026-08-14T12:00:00Z",
  resource_snapshot: {
    ...missionBody.resource_snapshot,
    captured_at: "2026-08-14T12:00:00Z",
  },
};
const withMission = structuredClone(workspace);
withMission.p19_mission_contract = missionContract;
const missionScope = structuredClone(scope);
missionScope.report.briefing.action.mission_contract_id = missionContract.contract_id;
missionScope.report.briefing.action.mission_contract_sha256 = missionContract.contract_sha256;
assert.equal(isCrewChiefWorkspaceResponse(withMission, missionScope), true);
assert.equal(
  isCrewChiefWorkspaceResponse(workspace, missionScope),
  false,
  "a trusted P19 mission identity requires its exact workspace contract",
);
const halfBoundMissionScope = structuredClone(scope);
halfBoundMissionScope.report.briefing.action.mission_contract_id = missionContract.contract_id;
halfBoundMissionScope.report.briefing.action.mission_contract_sha256 = null;
assert.equal(
  isCrewChiefWorkspaceResponse(workspace, halfBoundMissionScope),
  false,
  "a P19 action cannot publish half of a mission identity",
);
assert.equal(await hasCanonicalMeasurementMissionDigest(missionContract), true);
const staleMission = structuredClone(withMission);
staleMission.p19_mission_contract.setup_sha256 = h("0");
assert.equal(isCrewChiefWorkspaceResponse(staleMission, missionScope), true);
assert.equal(
  await hasCanonicalMeasurementMissionDigest(staleMission.p19_mission_contract),
  false,
);
const discriminatorWorkspace = structuredClone(withMission);
discriminatorWorkspace.run_sentinel.p19_plan_kind = "discriminator";
discriminatorWorkspace.run_sentinel.mission = "Run the evidence discriminator";
discriminatorWorkspace.run_sentinel.need = "Record an unchanged-setup comparison.";
discriminatorWorkspace.terminal_decision.title = "Run the evidence discriminator";
discriminatorWorkspace.terminal_decision.instruction = "Record an unchanged-setup comparison.";
discriminatorWorkspace.performance_intelligence.speed_story.next = "Record an unchanged-setup comparison.";
discriminatorWorkspace.performance_intelligence.explanation_chain.p19_next_move = "Record an unchanged-setup comparison.";
discriminatorWorkspace.identity.run_sentinel_sha256 = await canonicalEngineeringLearningSha256(
  discriminatorWorkspace.run_sentinel,
);
discriminatorWorkspace.engineering_case.condition_epoch_sha256 =
  discriminatorWorkspace.identity.run_sentinel_sha256;
const discriminatorScope = structuredClone(missionScope);
discriminatorScope.report.best_measurement = { title: "Evidence discriminator" };
discriminatorScope.report.briefing.action.title = "Run the evidence discriminator";
discriminatorScope.report.briefing.action.instruction = "Record an unchanged-setup comparison.";
assert.equal(
  isCrewChiefWorkspaceResponse(discriminatorWorkspace, discriminatorScope),
  true,
  "the sentinel must bind the public P19 action rather than a differently titled detail card",
);
for (const instruction of ["Set cross_weight_percent to 52.0.", "Keep.", "Stop the test."]) {
  const hostile = structuredClone(workspace);
  hostile.terminal_decision.instruction = instruction;
  assert.equal(isCrewChiefWorkspaceResponse(hostile, scope), false, instruction);
}
const foreign = structuredClone(workspace);
foreign.identity.session_id = "session-2";
assert.equal(isCrewChiefWorkspaceResponse(foreign, scope), false);
const forged = structuredClone(workspace);
forged.terminal_decision.control_key = "cross_weight_percent";
assert.equal(isCrewChiefWorkspaceResponse(forged, scope), false);
const malformedNested = structuredClone(workspace);
delete malformedNested.evidence_index.entries;
assert.equal(isCrewChiefWorkspaceResponse(malformedNested, scope), false);
const smuggledBrief = structuredClone(workspace);
smuggledBrief.post_run_brief = ["Set lf.ls_rebound to 4 clicks."];
assert.equal(isCrewChiefWorkspaceResponse(smuggledBrief, scope), false);
const foreignEvidence = structuredClone(workspace);
foreignEvidence.evidence_index.entries = [{
  artifact_id: "event-2", producer_id: "p19.reasoning_snapshot", run_id: "run-2",
  session_id: "session-1", setup_id: "setup-1", lap_numbers: [4],
  workspace_run_id: "run-1", workspace_session_id: "session-1", workspace_setup_id: "setup-1",
  source_run_id: "run-2", source_session_id: "session-1", source_setup_id: "setup-1",
  source_setup_sha256: h("7"), source_build_context_sha256: h("6"),
  source_provenance_available: true,
  lap_pct_start: 20, lap_pct_end: 30, phase: "center", mechanism_ids: [],
  component_ids: [], control_keys: [], source_channels: ["YawRate"],
  objective: "race_long_run",
  evidence_state: "measured", polarity: "support", blocker_reasons: [],
  typed_artifact: null,
  authority_ceiling: "measurement_only",
}];
assert.equal(isCrewChiefWorkspaceResponse(foreignEvidence, scope), false);
assert.equal(isCrewChiefWorkspaceResponse(
  foreignEvidence, { ...scope, scopeRunIds: ["run-1", "run-2"] },
), true);
foreignEvidence.evidence_index.entries[0].lap_pct_start = 40;
assert.equal(isCrewChiefWorkspaceResponse(
  foreignEvidence, { ...scope, scopeRunIds: ["run-1", "run-2"] },
), false);

const controlledReport = structuredClone(report);
controlledReport.briefing.action = {
  kind: "controlled_test", title: "One P19 test", instruction: "Set the exact card.",
  setup_authorized: true, control_key: "cross_weight_percent",
  setup_effect_id: "add_crossweight_small", experiment_factor_id: "factor:crossweight",
  direction_sign: 1, current_value: "51.5%",
  proposed_value: "52.0%", source_event_ids: ["event-1"],
};
controlledReport.next_trustworthy_move = { workflow_id: "workflow-1", workflow_updated_at: "revision-1" };
const controlled = structuredClone(workspace);
Object.assign(controlled.identity, { active_workflow_id: "workflow-1", active_workflow_revision: "revision-1" });
controlled.terminal_decision = {
  kind: "controlled_test", title: "One P19 test", instruction: "Set the exact card.",
  authority: "p19_projection_only", control_key: "cross_weight_percent",
  setup_effect_id: "add_crossweight_small", experiment_factor_id: "factor:crossweight",
  direction_sign: 1, current_value: "51.5%",
  proposed_value: "52.0%", source_event_ids: ["event-1"], workflow_id: "workflow-1",
  workflow_revision: "revision-1", blocker_reasons: [],
};
controlled.performance_intelligence.speed_story.next = "Set the exact card.";
controlled.performance_intelligence.explanation_chain.p19_next_move = "Set the exact card.";
controlled.run_sentinel.p19_plan_kind = "controlled_test";
controlled.run_sentinel.mission = "One P19 test";
controlled.run_sentinel.need = "Set the exact card.";
assert.equal(isCrewChiefWorkspaceResponse(controlled, { ...scope, report: controlledReport }), true);
controlled.terminal_decision.proposed_value = "53.0%";
assert.equal(isCrewChiefWorkspaceResponse(controlled, { ...scope, report: controlledReport }), false);

const rejectMutation = (label, mutate) => {
  const hostile = structuredClone(workspace);
  mutate(hostile);
  assert.equal(isCrewChiefWorkspaceResponse(hostile, scope), false, label);
};
rejectMutation("unbound sentinel cannot claim mission-accepted laps", (value) => {
  value.run_sentinel.mission_accepted_lap_ids = ["run-1:1"];
});
rejectMutation("context count must match exact lap decisions", (value) => {
  value.run_sentinel.context_cleared_laps = 1;
});
rejectMutation("mission completion requires contract-accepted laps", (value) => {
  value.run_sentinel.collection_complete = true;
  value.run_sentinel.mission_state = "collection_complete";
});
rejectMutation("sentinel lap identity and ordinal are required", (value) => {
  value.run_sentinel.context_cleared_laps = 1;
  value.run_sentinel.laps = [{
    lap_id: "run-1:1", lap_number: 1, status: "context_cleared", reasons: [], context_ordinal: null,
  }];
});
rejectMutation("P33 exact keys reject a missing section", (value) => { delete value.learning_prior.evidence_references; });
rejectMutation("P33 exact keys reject an extra nested field", (value) => { value.learning_prior.recurrence.setup_call = "hidden"; });
rejectMutation("P33 history revision binds workspace identity", (value) => { value.learning_prior.history_revision = h("0"); });
rejectMutation("P33 projection digest binds workspace identity", (value) => { value.learning_prior.projection_sha256 = h("0"); });
rejectMutation("P33 cannot authorize setup", (value) => { value.learning_prior.setup_authorized = true; });
rejectMutation("P33 cannot modify P19 cause rank", (value) => { value.learning_prior.p19_rank_modified = true; });
rejectMutation("P33 recurrence cannot smuggle a setup directive", (value) => {
  value.learning_prior.recurrence.statement = "Set cross weight to 52.0.";
});
rejectMutation("P33 recurrence cannot claim component causality", (value) => {
  value.learning_prior.recurrence.statement = "Shocks produced the loss.";
});
rejectMutation("P33 recurrence cannot hide causality behind time wording", (value) => {
  value.learning_prior.recurrence.statement = "Shocks caused the time loss.";
});
for (const statement of [
  "The shocks drove the loss.",
  "The loss came from the dampers.",
  "This explains the handling problem.",
  "The instability was attributable to cross weight.",
]) {
  rejectMutation(`P33 causal bypass is forbidden: ${statement}`, (value) => {
    value.learning_prior.recurrence.statement = statement;
  });
}
const boundedNegativeKnowledge = structuredClone(workspace);
boundedNegativeKnowledge.learning_prior.recurrence.statement = "Shock inspection produced no discriminating evidence and did not cause the observed loss.";
assert.equal(
  isCrewChiefWorkspaceResponse(boundedNegativeKnowledge, scope),
  true,
  "negative knowledge and explicit causal negation remain representable",
);
rejectMutation("P33 post-run brief cannot smuggle setup authority", (value) => {
  value.learning_prior.post_run_brief.blocker_reasons = ["Increase rear spring by 25 lb/in."];
  value.learning_prior.blocker_reasons = ["Increase rear spring by 25 lb/in."];
});
rejectMutation("P33 ledger cannot claim lap-time improvement", (value) => {
  value.learning_prior.ledger.claims_lap_time_improvement = true;
});
rejectMutation("available P33 memory requires a qualified item", (value) => {
  value.learning_prior.state = "available";
});

const historicalMemory = structuredClone(workspace);
const experienceId = `p33x_${"a".repeat(24)}`;
const secondExperienceId = `p33x_${"d".repeat(24)}`;
const referenceId = `p33ref_${"b".repeat(24)}`;
Object.assign(historicalMemory.learning_prior, {
  state: "available",
  recurrence: {
    recurrence_id: "recurrence-1", classification: "possible_recurrence",
    problem_sha256s: [h("4")], experience_ids: [experienceId], investigation_ids: [],
    statement: "A similar qualified driver pattern was observed once.", useful_discriminator: null,
    prior_dead_end: null, strongest_contradiction: "Only one independent episode is available.",
    transfer: null, counts: counts(1), strength: "single_case",
    authority: "attention_only", setup_authorized: false,
  },
  driver_tendencies: [{
    fingerprint_id: "driver-fingerprint-1", driver_id: "driver-1", transfer_level: "compatible",
    state: "repeatable_tendency", tendencies: [{
      contribution_id: "driver-contribution-1", metric: "brake_release_timing_consistency",
      tendency: "repeatable_tendency", statement: "Brake release timing repeated in the qualified source window.",
      physical_episode_ids: [], source_artifact_ids: ["historical-artifact-1"], source_lap_count: 1,
      authority: "driver_context_only", setup_authorized: false,
    }], counts: counts(2), source_experience_ids: [experienceId, secondExperienceId], contradictions: [],
    authority: "driver_context_only", setup_authorized: false,
  }],
  evidence_references: [{
    reference_id: referenceId, experience_id: experienceId,
    provenance: {
      provenance_sha256: h("5"), artifact_id: "historical-artifact-1",
      producer_id: "p20.physical_episode", run_id: "run-history", session_id: "session-history",
      setup_id: "setup-history", setup_snapshot_sha256: h("6"), build_context_sha256: h("8"),
      lap_numbers: [7], lap_pct_start: 22, lap_pct_end: 31, phase: "entry",
      source_channels: ["speed_mph", "brake_pct"], evidence_state: "measured", polarity: "support",
    },
    state: "available", blocker_reasons: [], authority: "attention_only", setup_authorized: false,
  }],
  context_transfer_level: "compatible", strength: "single_case", counts: counts(1),
  post_run_brief: {
    state: "available", what_we_learned: ["Brake release timing repeated in one qualified source window."],
    what_changed_our_mind: [], what_did_not_work: [], next_attention: [], blocker_reasons: [],
    authority: "attention_only", setup_authorized: false,
  },
  blocker_reasons: [],
});
historicalMemory.evidence_index.entries = [{
  artifact_id: referenceId, producer_id: "p33.engineering_experience",
  run_id: "run-history", session_id: "session-history", setup_id: "setup-history",
  workspace_run_id: "run-1", workspace_session_id: "session-1", workspace_setup_id: "setup-1",
  source_run_id: "run-history", source_session_id: "session-history", source_setup_id: "setup-history",
  source_setup_sha256: h("6"), source_build_context_sha256: h("8"), source_provenance_available: true,
  lap_numbers: [7], lap_pct_start: 22, lap_pct_end: 31, phase: "entry",
  mechanism_ids: [], component_ids: [], control_keys: [], objective: "race_long_run",
  source_channels: ["speed_mph", "brake_pct"], evidence_state: "measured", polarity: "support",
  blocker_reasons: [], typed_artifact: null, authority_ceiling: "attention_only",
}];
const reasoning = (digest) => ({
  reasoning_snapshot_sha256: digest, causes: [], measurement_plan_kind: "measurement_mission",
  discriminator_ids: [], authority_level: "measurement", setup_authorized: false,
});
historicalMemory.learning_prior.useful_prior_investigations = [{
  outcome_id: "outcome-1", experience_id: experienceId, transfer_level: "compatible",
  outcome: {
    investigation_id: "investigation-1", started_at: "2026-08-14T10:00:00Z",
    completed_at: "2026-08-14T10:05:00Z", initial_cause_ids: [], tools_inspected: ["inspect_time_origin"],
    driver_question_ids: [], driver_answers: [], requested_measurement_ids: ["inspect_time_origin"],
    completed_measurement_ids: ["inspect_time_origin"], strongest_contradiction: "One source window remained unmatched.",
    eliminated_cause_ids: [], unresolved_cause_ids: [], terminal_decision: "no_call", workflow_ids: [],
    elapsed_seconds: 300, laps_consumed: 1, tool_steps_consumed: 1, driver_questions_consumed: 0,
    successful_discriminator_ids: ["inspect_time_origin"], source_artifact_ids: [],
    historical_retrieval_used: true, historical_match_confirmed: true,
  },
  counts: counts(1), useful: true, explanation: "The prior inspection reached a bounded no-call quickly.",
  authority: "attention_only",
}];
historicalMemory.learning_prior.known_dead_ends = [{
  experience_ids: [experienceId, secondExperienceId], transfer_level: "compatible",
  fact: {
    dead_end_id: "dead-end-1", kind: "repeated_no_finding_tool", tool_id: "inspect_component",
    component_family: null, control: null, statement: "This inspection produced no discriminator in the saved context.",
    source_artifact_ids: [], source_workflow_ids: [], current_evidence_may_override: true,
    authority: "attention_only",
  },
  counts: counts(2), may_deprioritize_within_band: true, may_veto_current_evidence: false,
}];
historicalMemory.learning_prior.car_response_history = [{
  fingerprint_id: "car-fingerprint-1", transfer_level: "compatible",
  response: {
    response_id: "response-1", component: "platform", control: "cross_weight_percent", direction: "increase",
    magnitude_class: "small", expected_vehicle_response: "More center rotation was expected.",
    observed_vehicle_response: "The response remained inconclusive.", p32_time_origin: "center",
    phase_time_effect_s: null, carry_effect_s: null, recovery_surrender: "unavailable", countereffects: [],
    p19_mechanism_assessment: "inconclusive", control_response_assessment: "inconclusive",
    policy_verdict: "retest", source_workflow_id: "workflow-history", source_response_record_id: null,
    source_artifact_ids: [], setup_authorized: false,
  },
  counts: { ...counts(2), independent_workflow_count: 2 },
  source_experience_ids: [experienceId, secondExperienceId],
  source_workflow_ids: ["workflow-history", "workflow-history-2"],
  contradictions: [], statement: "The controlled response remained inconclusive in the saved context.",
  authority: "controlled_history_only", setup_authorized: false,
}];
historicalMemory.learning_prior.mind_change_history = [{
  experience_id: experienceId, transfer_level: "compatible",
  fact: {
    mind_change_id: "mind-change-1", before_reasoning: reasoning(h("a")), after_reasoning: reasoning(h("b")),
    new_artifact_ids: ["mind-artifact-1"], new_evidence_states: ["measured"],
    causes_promoted: [], causes_demoted: ["cause-1"], causes_ruled_out: [],
    measurement_discriminator_id: "inspect_time_origin", evidence_discriminated: true,
    driver_question_involved: false, controlled_evidence_involved: false, context_gate_involved: true,
  },
  statement: "A measured contradiction changed the saved P19 ordering.", authority: "attention_only",
}];
historicalMemory.learning_prior.recommended_attention_order = [{
  tool_id: "inspect_time_origin", safety_band: "observation", learned_rank_within_band: 1,
  baseline_rank_within_band: 2, reason: "This inspection was useful in two compatible saved contexts.",
  transfer_level: "compatible", source_experience_ids: [experienceId, secondExperienceId], investigation_count: 2,
  session_count: 1, independent_workflow_count: 0, authority: "attention_only",
}];
historicalMemory.learning_prior.context_transfers = [{
  experience_id: experienceId, level: "compatible", matching_dimensions: ["car", "track"],
  mismatched_dimensions: [], drift_reasons: [], blocker_reasons: [],
}];
assert.equal(isCrewChiefWorkspaceResponse(historicalMemory, scope), true, "cross-session P33 evidence keeps exact source provenance");
const repeatedEvidenceState = structuredClone(historicalMemory);
repeatedEvidenceState.learning_prior.mind_change_history[0].fact.new_artifact_ids.push("mind-artifact-2");
repeatedEvidenceState.learning_prior.mind_change_history[0].fact.new_evidence_states.push("measured");
assert.equal(
  isCrewChiefWorkspaceResponse(repeatedEvidenceState, scope),
  true,
  "multiple exact artifacts may share one P33 evidence state",
);
const unpairedEvidenceState = structuredClone(repeatedEvidenceState);
unpairedEvidenceState.learning_prior.mind_change_history[0].fact.new_evidence_states.pop();
assert.equal(
  isCrewChiefWorkspaceResponse(unpairedEvidenceState, scope),
  false,
  "P33 mind-change states pair one-for-one with artifacts",
);
const tiedP19Ranks = structuredClone(historicalMemory);
const tiedCauses = [
  { cause_id: "cause-tied-1", status: "possible", ordinal_rank: 2, mechanism_family: "platform" },
  { cause_id: "cause-tied-2", status: "possible", ordinal_rank: 2, mechanism_family: "platform" },
];
tiedP19Ranks.learning_prior.mind_change_history[0].fact.before_reasoning.causes = tiedCauses;
tiedP19Ranks.learning_prior.mind_change_history[0].fact.after_reasoning.causes = tiedCauses;
assert.equal(
  isCrewChiefWorkspaceResponse(tiedP19Ranks, scope),
  true,
  "P33 preserves canonical tied P19 ordinal ranks",
);
const duplicateP19Cause = structuredClone(tiedP19Ranks);
duplicateP19Cause.learning_prior.mind_change_history[0].fact.after_reasoning.causes[1].cause_id = "cause-tied-1";
assert.equal(
  isCrewChiefWorkspaceResponse(duplicateP19Cause, scope),
  false,
  "P33 tied ranks do not permit duplicate cause identity",
);

const bindCanonicalLearningDigests = async (prior) => {
  for (const reference of prior.evidence_references) {
    const provenance = { ...reference.provenance };
    delete provenance.provenance_sha256;
    reference.provenance.provenance_sha256 = await canonicalEngineeringLearningSha256(provenance);
    const digest = await canonicalJsonSha256({
      experience_id: reference.experience_id,
      provenance_sha256: reference.provenance.provenance_sha256,
    });
    reference.reference_id = `p33ref_${digest.slice(0, 24)}`;
  }
  const projection = { ...prior };
  delete projection.projection_sha256;
  prior.projection_sha256 = await canonicalEngineeringLearningSha256(projection);
};
const digestBoundHistory = structuredClone(historicalMemory);
await bindCanonicalLearningDigests(digestBoundHistory.learning_prior);
assert.equal(
  await hasCanonicalEngineeringLearningDigests(digestBoundHistory.learning_prior),
  true,
  "canonical P33 prior/provenance/reference identities",
);
const staleProjectionDigest = structuredClone(digestBoundHistory.learning_prior);
staleProjectionDigest.post_run_brief.what_we_learned[0] = "A different safe historical observation.";
assert.equal(
  await hasCanonicalEngineeringLearningDigests(staleProjectionDigest),
  false,
  "P33 content cannot retain a stale copied projection hash",
);
const forgedProvenanceDigest = structuredClone(digestBoundHistory.learning_prior);
forgedProvenanceDigest.evidence_references[0].provenance.source_channels = ["speed_mph"];
forgedProvenanceDigest.evidence_references[0].provenance.provenance_sha256 = h("9");
const forgedProjectionBody = { ...forgedProvenanceDigest };
delete forgedProjectionBody.projection_sha256;
forgedProvenanceDigest.projection_sha256 = await canonicalEngineeringLearningSha256(forgedProjectionBody);
assert.equal(
  await hasCanonicalEngineeringLearningDigests(forgedProvenanceDigest),
  false,
  "P33 provenance rejects an attacker-supplied digest even when the parent digest is recomputed",
);
const detachedReferenceDigest = structuredClone(digestBoundHistory.learning_prior);
const detachedReference = detachedReferenceDigest.evidence_references[0];
detachedReference.experience_id = `p33x_${"c".repeat(24)}`;
const detachedReferenceHash = await canonicalJsonSha256({
  experience_id: detachedReference.experience_id,
  provenance_sha256: detachedReference.provenance.provenance_sha256,
});
detachedReference.reference_id = `p33ref_${detachedReferenceHash.slice(0, 24)}`;
const detachedReferenceBody = { ...detachedReferenceDigest };
delete detachedReferenceBody.projection_sha256;
detachedReferenceDigest.projection_sha256 = await canonicalEngineeringLearningSha256(detachedReferenceBody);
const detachedReferenceWorkspace = structuredClone(historicalMemory);
detachedReferenceWorkspace.learning_prior = detachedReferenceDigest;
detachedReferenceWorkspace.identity.learning_projection_sha256 = detachedReferenceDigest.projection_sha256;
detachedReferenceWorkspace.evidence_index.entries[0].artifact_id = detachedReference.reference_id;
assert.equal(
  isCrewChiefWorkspaceResponse(detachedReferenceWorkspace, scope),
  false,
  "a correctly re-identified reference still cannot detach from surfaced experience",
);
for (const [label, mutate] of [
  ["P33 investigation chronology", (value) => { value.learning_prior.useful_prior_investigations[0].outcome.completed_at = "2026-08-14T09:00:00Z"; }],
  ["P33 investigation operation counts", (value) => { value.learning_prior.useful_prior_investigations[0].outcome.tool_steps_consumed = 2; }],
  ["P33 completed measurements require a durable request", (value) => {
    value.learning_prior.useful_prior_investigations[0].outcome.requested_measurement_ids = ["another-measurement"];
  }],
  ["P33 successful discriminators require a completed measurement", (value) => {
    value.learning_prior.useful_prior_investigations[0].outcome.completed_measurement_ids = [];
  }],
  ["P33 successful discriminators require the inspected tool result", (value) => {
    value.learning_prior.useful_prior_investigations[0].outcome.tools_inspected = ["inspect_track_demand"];
  }],
  ["P33 non-discriminating mind changes cannot retain a discriminator", (value) => {
    value.learning_prior.mind_change_history[0].fact.evidence_discriminated = false;
  }],
  ["P33 mind changes bind the successful discriminator from the same experience", (value) => {
    value.learning_prior.mind_change_history[0].fact.measurement_discriminator_id = "inspect_track_demand";
  }],
  ["P33 mind changes require their same-experience investigation outcome", (value) => {
    value.learning_prior.mind_change_history[0].experience_id = secondExperienceId;
  }],
  ["P33 dead ends cannot veto current evidence", (value) => { value.learning_prior.known_dead_ends[0].may_veto_current_evidence = true; }],
  ["P33 undo history requires a countereffect", (value) => { value.learning_prior.car_response_history[0].response.policy_verdict = "undo"; }],
  ["P33 car history cannot smuggle an exact setup value", (value) => {
    value.learning_prior.car_response_history[0].response.observed_vehicle_response = "Set cross weight to 52%.";
  }],
  ["P33 car history requires a categorical magnitude", (value) => {
    value.learning_prior.car_response_history[0].response.magnitude_class = "0.5%";
  }],
  ["P33 mind changes require a changed snapshot", (value) => {
    value.learning_prior.mind_change_history[0].fact.after_reasoning.reasoning_snapshot_sha256 = h("a");
  }],
  ["P33 attention cannot cross a weak transfer gate", (value) => { value.learning_prior.context_transfer_level = "weak"; }],
  ["P33 exact transfer cannot carry drift", (value) => {
    value.learning_prior.context_transfers[0].level = "exact";
    value.learning_prior.context_transfers[0].drift_reasons = ["weather drift"];
  }],
  ["P33 repeatable driver history needs two independent units", (value) => {
    value.learning_prior.driver_tendencies[0].counts = counts(1);
  }],
  ["P33 driver contributions match the parent fingerprint state", (value) => {
    value.learning_prior.driver_tendencies[0].tendencies[0].tendency = "context_dependent_tendency";
  }],
  ["P33 car response counts bind exact workflow IDs", (value) => {
    value.learning_prior.car_response_history[0].counts.independent_workflow_count = 1;
  }],
  ["P33 dead ends cannot deprioritize across weak transfer", (value) => {
    value.learning_prior.known_dead_ends[0].transfer_level = "weak";
  }],
  ["P33 dead ends need two independent units to deprioritize", (value) => {
    value.learning_prior.known_dead_ends[0].counts = counts(1);
  }],
  ["P33 learned attention needs two investigations", (value) => {
    value.learning_prior.recommended_attention_order[0].investigation_count = 1;
  }],
  ["P33 learned attention needs two source experiences", (value) => {
    value.learning_prior.recommended_attention_order[0].source_experience_ids = [experienceId];
  }],
  ["P33 evidence references require surfaced experience", (value) => {
    value.learning_prior.evidence_references[0].experience_id = `p33x_${"c".repeat(24)}`;
  }],
]) {
  const hostile = structuredClone(historicalMemory);
  mutate(hostile);
  assert.equal(isCrewChiefWorkspaceResponse(hostile, scope), false, label);
}
const detachedHistory = structuredClone(historicalMemory);
detachedHistory.evidence_index.entries[0].source_setup_sha256 = h("9");
assert.equal(isCrewChiefWorkspaceResponse(detachedHistory, scope), false, "P33 navigation target cannot drift from provenance");
const smuggledHistoricalComponent = structuredClone(historicalMemory);
smuggledHistoricalComponent.evidence_index.entries[0].component_ids = ["shocks"];
assert.equal(isCrewChiefWorkspaceResponse(smuggledHistoricalComponent, scope), false, "P33 navigation target cannot smuggle component focus");
const unavailableHistory = structuredClone(historicalMemory);
unavailableHistory.learning_prior.evidence_references[0].state = "unavailable";
unavailableHistory.learning_prior.evidence_references[0].blocker_reasons = ["Saved source session is unavailable."];
unavailableHistory.evidence_index.entries = [];
assert.equal(isCrewChiefWorkspaceResponse(unavailableHistory, scope), true, "unavailable P33 source has an explicit blocker and no focus target");
rejectMutation("request objective is bound", (value) => { value.identity.objective_id = "qualifying_peak"; });
rejectMutation("track fractions are finite", (value) => { value.performance_intelligence.track_demand.braking_fraction = Number.NaN; });
rejectMutation("track fractions stay bounded", (value) => { value.performance_intelligence.track_demand.traffic_exposure_fraction = 1.1; });
rejectMutation("legacy limiter view stays exact", (value) => { value.performance_intelligence.track_demand.shift_limiter_zones = ["12% limiter"]; });
rejectMutation("component state and authority pair", (value) => {
  value.performance_intelligence.component_context_state = "unavailable";
  value.performance_intelligence.component_context_blockers = [];
});
rejectMutation("causal story prose is forbidden", (value) => { value.performance_intelligence.speed_story.systems = "The loss was caused by shocks."; });
rejectMutation("subject-first causal prose is forbidden", (value) => { value.performance_intelligence.speed_story.systems = "Shocks caused the loss."; });
rejectMutation("due-to causal prose is forbidden", (value) => { value.performance_intelligence.speed_story.systems = "The loss was due to shocks."; });
rejectMutation("proof causal prose is forbidden", (value) => { value.performance_intelligence.speed_story.systems = "This proves shocks created the time loss."; });
rejectMutation("produced causal prose is forbidden", (value) => { value.performance_intelligence.speed_story.systems = "Shocks produced the time loss."; });
rejectMutation("generated causal prose is forbidden", (value) => { value.performance_intelligence.speed_story.systems = "Shocks generated the time loss."; });
rejectMutation("resulted-in causal prose is forbidden", (value) => { value.performance_intelligence.speed_story.systems = "The shock response resulted in the time loss."; });
rejectMutation("optimal prose is forbidden", (value) => { value.performance_intelligence.speed_story.car = "This is the optimal setup."; });
rejectMutation("P19 next move is exact", (value) => { value.performance_intelligence.explanation_chain.p19_next_move = "Collect two laps."; });
const explicitNonCausalOutcome = structuredClone(workspace);
explicitNonCausalOutcome.performance_intelligence.speed_story.systems = "The shocks did not produce the observed loss.";
assert.equal(isCrewChiefWorkspaceResponse(explicitNonCausalOutcome, scope), true, "explicitly negated causal outcomes remain truthful");
const withControlledHistory = structuredClone(workspace);
withControlledHistory.performance_intelligence.response_records = [{
  record_id: "response-1", workflow_id: "workflow-1", context_run_ids: ["run-1"],
  control: "cross weight", component: "platform", expected_state: "rotation changes",
  observed_state: "rotation changed", time_origin: "center", time_origin_pct: 25,
  phase_effect: "center improved", phase_effect_s: -0.05,
  downstream_carry: "recovered before exit", downstream_carry_s: 0,
  performance_result: "observed gain", countereffects: [],
  mechanism_assessment: "observed response", control_response_assessment: "repeatable",
  policy_verdict: "keep", exact_context: true, setup_authorized: false,
}];
assert.equal(isCrewChiefWorkspaceResponse(withControlledHistory, scope), true, "exact non-invalid controlled history");
for (const [label, field, invalid] of [
  ["inexact controlled history", "exact_context", false],
  ["invalid controlled history", "policy_verdict", "invalid"],
  ["detached time-origin value", "time_origin_pct", null],
  ["detached carry value", "downstream_carry_s", null],
]) {
  const hostile = structuredClone(withControlledHistory);
  hostile.performance_intelligence.response_records[0][field] = invalid;
  assert.equal(isCrewChiefWorkspaceResponse(hostile, scope), false, label);
}
rejectMutation("phase evidence state matches metrics", (value) => {
  value.performance_intelligence.corner_chains = [{
    chain_id: "corner-1", track_region: "Turn 1", turn: "1", lap_numbers: [2], reference_lap_numbers: [],
    approach_state: { phase: "entry", start_pct: 10, end_pct: 12, elapsed_delta_s: null, speed_delta_mph: null, throttle_delta_pct: null, brake_delta_pct: null, steering_delta_deg: null, yaw_rate_delta: null, long_accel_delta: null, path_delta_m: null, line_separation_m: null, driver_demand_source_coverage: null, driver_demand_reference_coverage: null, evidence_state: "measured", source_channels: [], blockers: [] },
    braking_state: null, entry_state: null, center_state: null, exit_state: null, carry_state: null,
    local_time_effect_s: null, downstream_time_effect_s: null, driver_vehicle_separation: [],
    context: [], contradictions: ["No qualified chain."], authority: "observation_only",
  }];
});

const withOpportunity = structuredClone(workspace);
withOpportunity.performance_intelligence.basis.context_blockers = [];
withOpportunity.performance_intelligence.basis.source_lap_numbers = [2, 3];
withOpportunity.performance_intelligence.opportunity_map.opportunities = [{
  opportunity_id: "opportunity-1", start_pct: 20, end_pct: 30, track_region: "Turn 1", turn: "1",
  phase: "center", local_delta_s: 0.1, cumulative_delta_at_entry_s: 0.02,
  cumulative_delta_at_exit_s: 0.12, origin_kind: "local_generation", persistence_distance_pct: 8,
  following_phase_effect_s: 0.02, following_phase_start_pct: 30, following_phase_end_pct: 38,
  repeatability: "observed_once", noise_basis: "One eligible pair.",
  source_laps: [2, 3], source_channels: ["speed_mph"], driver_execution_state: "unresolved",
  vehicle_response_state: "candidate only", context_state: "qualified_pair", attribution_state: "candidate_only",
  source_traffic_exposure_fraction: 0, reference_traffic_exposure_fraction: 0,
  mechanism_candidates: ["center_rotation"], component_candidates: [], contradictions: ["One pair only."],
  setup_authorized: false,
}];
withOpportunity.performance_intelligence.track_demand.dominant_measured_opportunity_ids = ["opportunity-1"];
Object.assign(withOpportunity.performance_intelligence.speed_story, {
  what_costs_time: "Observed 0.100 s slower through this region.", observed_difference_s: 0.1,
  observed_direction: "loss", attribution_state: "candidate_only", attribution: "Candidate only.",
  source_context: "Source traffic exposure 0.0%.", reference_context: "Reference traffic exposure 0.0%.",
  comparison_window: "Turn 1, 20.0% to 30.0%.",
});
withOpportunity.evidence_index.entries = [{
  artifact_id: "opportunity-1", producer_id: "p32.lap_time_opportunity", run_id: "run-1",
  session_id: "session-1", setup_id: "setup-1", lap_numbers: [2, 3], workspace_run_id: "run-1",
  workspace_session_id: "session-1", workspace_setup_id: "setup-1", source_run_id: "run-1",
  source_session_id: "session-1", source_setup_id: "setup-1", source_setup_sha256: h("b"),
  source_build_context_sha256: vehicleRuntimeIdentityHash, source_provenance_available: true, lap_pct_start: 20,
  lap_pct_end: 30, phase: "center", mechanism_ids: ["unclassified"], component_ids: [],
  control_keys: [], objective: "race_long_run", source_channels: ["speed_mph"],
  evidence_state: "observed_correlation", polarity: "neutral", blocker_reasons: [],
  typed_artifact: {
    artifact_type: "lap_time_opportunity",
    opportunity: structuredClone(withOpportunity.performance_intelligence.opportunity_map.opportunities[0]),
  },
  authority_ceiling: "observation_only",
}];
const p35TrackDemandArtifactId = `p32-track-demand:${"1".repeat(20)}`;
withOpportunity.evidence_index.entries.push({
  artifact_id: p35TrackDemandArtifactId, producer_id: "p32.track_demand",
  run_id: "run-1", session_id: "session-1", setup_id: "setup-1",
  workspace_run_id: "run-1", workspace_session_id: "session-1", workspace_setup_id: "setup-1",
  source_run_id: "run-1", source_session_id: "session-1", source_setup_id: "setup-1",
  source_setup_sha256: h("b"), source_build_context_sha256: vehicleRuntimeIdentityHash,
  source_provenance_available: true, lap_numbers: [2, 3], lap_pct_start: 0, lap_pct_end: 100,
  phase: "whole_run", mechanism_ids: [], component_ids: [], control_keys: [],
  objective: "race_long_run", source_channels: ["speed_mph"], evidence_state: "calculated",
  polarity: "neutral", blocker_reasons: [],
  typed_artifact: {
    artifact_type: "track_demand",
    profile: structuredClone(withOpportunity.performance_intelligence.track_demand),
  },
  authority_ceiling: "observation_only",
});
const focusArtifactId = async (mechanism, kind, sourceArtifactId = null, contractId = null) => {
  const parts = kind === "support"
    ? ["opportunity-1", mechanism.mechanism_id, sourceArtifactId, "support"]
    : kind === "uncertainty"
      ? ["opportunity-1", mechanism.mechanism_id, "uncertainty"]
      : ["opportunity-1", mechanism.mechanism_id, contractId, "discriminator"];
  return `${mechanism.focus_artifact_prefix}${(await canonicalJsonSha256(parts)).slice(0, 24)}`;
};
const expectedCenterMechanisms = p35RuntimeTrustManifest.mechanisms.filter((mechanism) => (
  mechanism.p32_performance_mechanism_ids.includes("center_rotation")
  && mechanism.relevant_phases.includes("center")
  && mechanism.allowed_time_origin_kinds.includes("local_generation")
  && ["steady_state", "both"].includes(mechanism.response_regime)
)).slice(0, 6);
const blockedCandidates = [];
const blockedFocusArtifacts = [];
for (const mechanism of expectedCenterMechanisms) {
  const contradictionId = await focusArtifactId(mechanism, "uncertainty");
  const discriminatorId = await focusArtifactId(
    mechanism,
    "discriminator",
    null,
    mechanism.discriminator_observation_contract_ids[0],
  );
  blockedCandidates.push({
    mechanism_id: mechanism.mechanism_id,
    p32_performance_mechanism_ids: mechanism.p32_performance_mechanism_ids
      .filter((id) => id === "center_rotation"),
    support_artifact_ids: [], contradiction_artifact_ids: [contradictionId],
    discriminator_contract_ids: [...mechanism.discriminator_observation_contract_ids],
    component_family_ids: [...mechanism.component_family_ids],
    blocker_reasons: ["A typed P20 observation is unavailable in this exact scope."],
    relevance: "blocked", authority: "candidate_only",
    component_cause_authorized: false, setup_authorized: false,
  });
  blockedFocusArtifacts.push(
    {
      artifact_id: contradictionId, mechanism_id: mechanism.mechanism_id,
      observation_contract_id: null, inspection_tool_id: mechanism.inspection_tool_id,
      stage: "tire_platform_state", evidence_state: "needs_confirmation",
      source_artifact_ids: ["opportunity-1"], source_channels: ["speed_mph"],
      lap_numbers: [2, 3], lap_pct_start: 20, lap_pct_end: 30, phase: "center",
      polarity: "uncertainty",
      summary: "The exact current window does not yet support this mechanism candidate.",
      blocker_reasons: ["A typed P20 observation is unavailable in this exact scope."],
      authority: "observation_only",
    },
    {
      artifact_id: discriminatorId, mechanism_id: mechanism.mechanism_id,
      observation_contract_id: mechanism.discriminator_observation_contract_ids[0],
      inspection_tool_id: mechanism.inspection_tool_id,
      stage: "tire_platform_state", evidence_state: "needs_confirmation",
      source_artifact_ids: ["opportunity-1"], source_channels: ["speed_mph"],
      lap_numbers: [2, 3], lap_pct_start: 20, lap_pct_end: 30, phase: "center",
      polarity: "neutral", summary: "This typed observation is the next bounded discriminator.",
      blocker_reasons: ["The discriminator has not been observed."],
      authority: "observation_only",
    },
  );
}
const appendP35EvidenceEntries = (value) => {
  const supportIds = new Set(value.vehicle_dynamics.candidates.flatMap((item) => item.support_artifact_ids));
  const contradictionIds = new Set(
    value.vehicle_dynamics.candidates.flatMap((item) => item.contradiction_artifact_ids),
  );
  const sourceById = new Map(value.evidence_index.entries.map((entry) => [entry.artifact_id, entry]));
  for (const focus of value.vehicle_dynamics.focus_artifacts) {
    const sources = focus.source_artifact_ids.map((id) => sourceById.get(id));
    const mechanismIds = [...new Set(sources.flatMap((entry) => entry.mechanism_ids))];
    value.evidence_index.entries.push({
      artifact_id: focus.artifact_id,
      producer_id: `p35.${focus.inspection_tool_id.replace(/^inspect_/, "")}`,
      run_id: "run-1", session_id: "session-1", setup_id: "setup-1",
      workspace_run_id: "run-1", workspace_session_id: "session-1", workspace_setup_id: "setup-1",
      source_run_id: "run-1", source_session_id: "session-1", source_setup_id: "setup-1",
      source_setup_sha256: h("b"), source_build_context_sha256: vehicleRuntimeIdentityHash,
      source_provenance_available: true, lap_numbers: [...focus.lap_numbers],
      lap_pct_start: focus.lap_pct_start, lap_pct_end: focus.lap_pct_end, phase: focus.phase,
      mechanism_ids: mechanismIds, component_ids: [], control_keys: [], objective: "race_long_run",
      source_channels: [...focus.source_channels], evidence_state: focus.evidence_state,
      polarity: supportIds.has(focus.artifact_id)
        ? "support" : contradictionIds.has(focus.artifact_id) ? "contradiction" : "neutral",
      blocker_reasons: [...focus.blocker_reasons],
      typed_artifact: {
        artifact_type: "vehicle_dynamics_focus", inspection_tool_id: focus.inspection_tool_id,
        assessment_sha256: value.vehicle_dynamics.p35_assessment_sha256,
        focus: structuredClone(focus),
      },
      authority_ceiling: "observation_only",
    });
  }
};
const opportunityDynamicsBody = structuredClone(withOpportunity.vehicle_dynamics);
delete opportunityDynamicsBody.p35_assessment_sha256;
opportunityDynamicsBody.p32_performance_mechanism_ids = ["center_rotation"];
opportunityDynamicsBody.performance_opportunity_ids = ["opportunity-1"];
opportunityDynamicsBody.measured_time_consequence_available = true;
opportunityDynamicsBody.response_regime = "steady_state";
const p354ResponseId = `p354.response:${"1".repeat(24)}`;
opportunityDynamicsBody.response_observations = [{
  observation_id: p354ResponseId, opportunity_id: "opportunity-1", run_id: "run-1",
  source_lap_numbers: [2], reference_lap_numbers: [3], phase: "center",
  lap_pct_start: 20, lap_pct_end: 30, onset_pct: 20,
  onset_resolution: "phase_boundary", response_regime: "steady_state",
  driver_demand_state: "unavailable", vehicle_response_state: "unavailable",
  line_state: "unavailable", context_state: "qualified", persistence: "phase_local",
  metrics: [{
    metric_id: `p354.metric:${"4".repeat(24)}`, quantity: "elapsed_time_delta_s",
    value: 0.1, units: "s", semantics: "calculated_delta", source_channels: ["speed_mph"],
    force_like: false, setup_authorized: false,
  }, {
    metric_id: `p354.metric:${"2".repeat(24)}`, quantity: "speed_delta_mph",
    value: -1, units: "mph", semantics: "measured_delta", source_channels: ["speed_mph"],
    force_like: false, setup_authorized: false,
  }],
  source_artifact_ids: ["opportunity-1"], source_channels: ["speed_mph"],
  blocker_reasons: [], evidence_state: "measured", authority: "observation_only",
  component_cause_authorized: false, setup_authorized: false,
}];
opportunityDynamicsBody.problem_signature = {
  signature_id: `p354.signature:${"3".repeat(24)}`,
  response_observation_id: p354ResponseId, opportunity_id: "opportunity-1",
  time_origin: "local_generation", local_time_delta_s: 0.1, phase: "center",
  onset_pct: 20, onset_resolution: "phase_boundary", response_regime: "steady_state",
  driver_demand_state: "unavailable", vehicle_response_state: "unavailable",
  line_state: "unavailable", speed_dependence: "not_established",
  stint_dependence: "not_established", traffic_dependence: "clear",
  surface_dependence: "not_established", front_rear_corner_scope: "unresolved",
  strongest_contradiction: "A typed P20 observation is unavailable in this exact scope.",
  authority: "observation_only", component_cause_authorized: false,
  setup_authorized: false,
};
opportunityDynamicsBody.candidates = blockedCandidates;
opportunityDynamicsBody.mechanism_separation = blockedCandidates.map((candidate) => ({
  mechanism_id: candidate.mechanism_id, response_observation_id: p354ResponseId,
  required_response_kpi_ids: [candidate.discriminator_contract_ids[0]],
  response_evidence_ids: [],
  support_artifact_ids: [], contradiction_artifact_ids: [...candidate.contradiction_artifact_ids],
  missing_evidence: [...candidate.blocker_reasons],
  discriminator_contract_ids: [...candidate.discriminator_contract_ids],
  protected_countereffects: ["Protect stability, tire state, workload, and downstream time."],
  component_family_ids: [...candidate.component_family_ids], state: "blocked",
  authority: "candidate_only", setup_authorized: false,
}));
opportunityDynamicsBody.focus_artifacts = blockedFocusArtifacts;
opportunityDynamicsBody.strongest_support_artifact_id = null;
opportunityDynamicsBody.strongest_contradiction_artifact_id =
  blockedCandidates[0].contradiction_artifact_ids[0];
opportunityDynamicsBody.next_discriminator_contract_id =
  blockedCandidates[0].discriminator_contract_ids[0];
opportunityDynamicsBody.chain = [
  {
    stage: "driver_input", evidence_state: "unavailable", source_artifact_ids: [],
    source_channels: [], summary: "Driver-input demand is unresolved in the typed P32 phase evidence.",
    blocker_reasons: ["Driver-input demand is unresolved in the typed P32 phase evidence."],
    authority: "observation_only",
  },
  {
    stage: "vehicle_demand", evidence_state: "estimated_proxy",
    source_artifact_ids: [p35TrackDemandArtifactId], source_channels: ["speed_mph"],
    summary: "Typed relative vehicle-demand proxies are available; exact loads remain unavailable.",
    blocker_reasons: [], authority: "observation_only",
  },
  {
    stage: "vehicle_response", evidence_state: "unavailable", source_artifact_ids: [],
    source_channels: [], summary: "Yaw, acceleration, speed, and line response are unresolved in typed P32 evidence.",
    blocker_reasons: ["Yaw, acceleration, speed, and line response are unresolved in typed P32 evidence."],
    authority: "observation_only",
  },
  {
    stage: "tire_platform_state", evidence_state: "estimated_proxy",
    source_artifact_ids: [p35TrackDemandArtifactId], source_channels: ["speed_mph"],
    summary: "Typed relative tire/platform proxies are available; exact forces remain unavailable.",
    blocker_reasons: [], authority: "observation_only",
  },
  {
    stage: "time_consequence", evidence_state: "measured",
    source_artifact_ids: ["opportunity-1"], source_channels: ["speed_mph"],
    summary: "P32 measured +0.100000 s in this physical window; P35 does not assign causation.",
    blocker_reasons: [], authority: "observation_only",
  },
];
await sealP354(opportunityDynamicsBody);
withOpportunity.vehicle_dynamics = {
  ...opportunityDynamicsBody,
  p35_assessment_sha256: await canonicalPerformanceMechanismAssessmentSha256(
    opportunityDynamicsBody,
  ),
};
withOpportunity.identity.p35_assessment_sha256 = withOpportunity.vehicle_dynamics.p35_assessment_sha256;
appendP35EvidenceEntries(withOpportunity);
await synchronizeEngineeringKnowledge(withOpportunity);
const directScope = {
  runId: "run-1", sessionId: "session-1", setupId: "setup-1", setupSnapshotHash: h("b"),
  buildContextHash: vehicleRuntimeIdentityHash, objectiveId: "race_long_run", p19Hash: h("a"), p20Revision: h("d"),
  p26Hash: h("e"), projectionHash: h("7"), p19Next: "Collect three eligible laps.",
  scopeRunIds: new Set(["run-1"]), opportunityEvidence: new Map([["opportunity-1", withOpportunity.evidence_index.entries[0]]]),
};
assert.equal(isPerformanceIntelligenceProjection(withOpportunity.performance_intelligence, directScope), true, "direct P32 opportunity contract");
const pairedLapProjection = structuredClone(withOpportunity.performance_intelligence);
pairedLapProjection.basis.source_lap_numbers = [2];
pairedLapProjection.basis.reference_lap_numbers = [3];
const pairedLapEvidence = structuredClone(withOpportunity.evidence_index.entries[0]);
assert.equal(isPerformanceIntelligenceProjection(pairedLapProjection, {
  ...directScope,
  opportunityEvidence: new Map([["opportunity-1", pairedLapEvidence]]),
}), true, "within-run opportunity evidence preserves the exact source/reference lap pair");
pairedLapEvidence.lap_numbers = [2];
assert.equal(isPerformanceIntelligenceProjection(pairedLapProjection, {
  ...directScope,
  opportunityEvidence: new Map([["opportunity-1", pairedLapEvidence]]),
}), false, "within-run opportunity evidence cannot omit the reference lap");
assert.equal(isCrewChiefWorkspaceResponse(withOpportunity, scope), true, "atomically bound opportunity");
const unavailableRuntimeWithCandidate = structuredClone(unavailableRuntimeWorkspace);
unavailableRuntimeWithCandidate.vehicle_dynamics.candidates = structuredClone(
  withOpportunity.vehicle_dynamics.candidates,
);
const unavailableCandidateBody = structuredClone(
  unavailableRuntimeWithCandidate.vehicle_dynamics,
);
delete unavailableCandidateBody.p35_assessment_sha256;
unavailableRuntimeWithCandidate.vehicle_dynamics.p35_assessment_sha256 =
  await canonicalPerformanceMechanismAssessmentSha256(unavailableCandidateBody);
unavailableRuntimeWithCandidate.identity.p35_assessment_sha256 =
  unavailableRuntimeWithCandidate.vehicle_dynamics.p35_assessment_sha256;
assert.equal(
  isCrewChiefWorkspaceResponse(unavailableRuntimeWithCandidate, unavailableRuntimeScope),
  false,
  "an unavailable P26/P35 runtime cannot carry mechanism candidates or support",
);

const tiedOpportunitiesWorkspace = structuredClone(withOpportunity);
const tiedOpportunity = structuredClone(
  tiedOpportunitiesWorkspace.performance_intelligence.opportunity_map.opportunities[0],
);
tiedOpportunity.opportunity_id = "opportunity-z";
tiedOpportunitiesWorkspace.performance_intelligence.opportunity_map.opportunities = [
  tiedOpportunity,
  tiedOpportunitiesWorkspace.performance_intelligence.opportunity_map.opportunities[0],
];
const tiedOpportunityEntry = structuredClone(tiedOpportunitiesWorkspace.evidence_index.entries[0]);
tiedOpportunityEntry.artifact_id = "opportunity-z";
tiedOpportunityEntry.typed_artifact.opportunity = structuredClone(tiedOpportunity);
tiedOpportunitiesWorkspace.evidence_index.entries.push(tiedOpportunityEntry);
assert.equal(
  isCrewChiefWorkspaceResponse(tiedOpportunitiesWorkspace, scope),
  true,
  "equal-delta P32 ordering cannot change the canonical earliest/smallest opportunity binding",
);
const rehashedAlternateTieWorkspace = structuredClone(tiedOpportunitiesWorkspace);
const alternateTieDynamicsBody = structuredClone(rehashedAlternateTieWorkspace.vehicle_dynamics);
delete alternateTieDynamicsBody.p35_assessment_sha256;
alternateTieDynamicsBody.performance_opportunity_ids = ["opportunity-z"];
alternateTieDynamicsBody.chain[4].source_artifact_ids = ["opportunity-z"];
rehashedAlternateTieWorkspace.vehicle_dynamics = {
  ...alternateTieDynamicsBody,
  p35_assessment_sha256: await canonicalPerformanceMechanismAssessmentSha256(
    alternateTieDynamicsBody,
  ),
};
rehashedAlternateTieWorkspace.identity.p35_assessment_sha256 =
  rehashedAlternateTieWorkspace.vehicle_dynamics.p35_assessment_sha256;
assert.equal(
  isCrewChiefWorkspaceResponse(rehashedAlternateTieWorkspace, scope),
  false,
  "a rehashed alternate equal-delta opportunity cannot replace the canonical P32 leader",
);

const rehashedEmptyDynamicsWorkspace = structuredClone(withOpportunity);
const emptyDynamicsBody = structuredClone(rehashedEmptyDynamicsWorkspace.vehicle_dynamics);
delete emptyDynamicsBody.p35_assessment_sha256;
emptyDynamicsBody.p32_performance_mechanism_ids = [];
emptyDynamicsBody.performance_opportunity_ids = [];
emptyDynamicsBody.measured_time_consequence_available = false;
emptyDynamicsBody.response_regime = null;
emptyDynamicsBody.response_observations = [];
emptyDynamicsBody.problem_signature = null;
emptyDynamicsBody.mechanism_separation = [];
emptyDynamicsBody.candidates = [];
emptyDynamicsBody.focus_artifacts = [];
emptyDynamicsBody.strongest_support_artifact_id = null;
emptyDynamicsBody.strongest_contradiction_artifact_id = null;
emptyDynamicsBody.next_discriminator_contract_id = null;
emptyDynamicsBody.chain[4] = {
  stage: "time_consequence", evidence_state: "unavailable",
  source_artifact_ids: [], source_channels: [],
  summary: "No measured P32 elapsed-time consequence is available.",
  blocker_reasons: ["No measured P32 opportunity is available."],
  authority: "observation_only",
};
rehashedEmptyDynamicsWorkspace.vehicle_dynamics = {
  ...emptyDynamicsBody,
  p35_assessment_sha256: await canonicalPerformanceMechanismAssessmentSha256(
    emptyDynamicsBody,
  ),
};
rehashedEmptyDynamicsWorkspace.identity.p35_assessment_sha256 =
  rehashedEmptyDynamicsWorkspace.vehicle_dynamics.p35_assessment_sha256;
rehashedEmptyDynamicsWorkspace.evidence_index.entries =
  rehashedEmptyDynamicsWorkspace.evidence_index.entries.filter(
    (entry) => !entry.producer_id.startsWith("p35."),
  );
assert.equal(
  isCrewChiefWorkspaceResponse(rehashedEmptyDynamicsWorkspace, scope),
  false,
  "a fully rehashed empty P35 assessment cannot omit nonempty trusted P32 truth",
);

const focusedDynamicsWorkspace = structuredClone(withOpportunity);
focusedDynamicsWorkspace.evidence_index.entries = focusedDynamicsWorkspace.evidence_index.entries.filter(
  (entry) => !entry.producer_id.startsWith("p35."),
);
focusedDynamicsWorkspace.performance_intelligence.basis.source_lap_numbers = [2, 3];
focusedDynamicsWorkspace.performance_intelligence.basis.reference_lap_numbers = [3];
focusedDynamicsWorkspace.evidence_index.entries.find(
  (entry) => entry.artifact_id === p35TrackDemandArtifactId,
).lap_numbers = [2, 3];
const focusedOpportunity =
  focusedDynamicsWorkspace.performance_intelligence.opportunity_map.opportunities[0];
focusedOpportunity.source_laps = [2, 3];
const focusedOpportunityEntry = focusedDynamicsWorkspace.evidence_index.entries.find(
  (entry) => entry.artifact_id === "opportunity-1",
);
focusedOpportunityEntry.lap_numbers = [2, 3];
focusedOpportunityEntry.typed_artifact.opportunity = structuredClone(focusedOpportunity);
const focusedPhaseState = {
  phase: "center", start_pct: 20, end_pct: 30, elapsed_delta_s: 0.1,
  speed_delta_mph: -1, throttle_delta_pct: 2, brake_delta_pct: 0,
  steering_delta_deg: 1.5, yaw_rate_delta: -0.8, long_accel_delta: 0.1,
  path_delta_m: null, line_separation_m: 0.2,
  driver_demand_source_coverage: 1, driver_demand_reference_coverage: 1,
  evidence_state: "measured",
  source_channels: [...new Set(["speed_mph", ...centerSupportChannels])],
  blockers: [],
};
const focusedSeparation = {
  separation_id: "separation-p35-center", phase: "center",
  driver_demand_changed: false, vehicle_response_changed: true,
  line_changed: false, context_changed: false, time_changed: true,
  result: "vehicle_response_changed_with_matched_inputs",
  support: ["Exact driver demand is matched."], contradictions: [], blockers: [],
  authority: "observation_only",
};
const focusedChain = {
  chain_id: "chain-p35-center", track_region: "Turn 1", turn: "1",
  lap_numbers: [2], reference_lap_numbers: [3], approach_state: null,
  braking_state: null, entry_state: null, center_state: focusedPhaseState,
  exit_state: null, carry_state: null, local_time_effect_s: 0.1,
  downstream_time_effect_s: 0.02, driver_vehicle_separation: [focusedSeparation],
  context: [], contradictions: ["One qualified comparison does not establish component cause."],
  authority: "observation_only",
};
focusedDynamicsWorkspace.performance_intelligence.corner_chains = [focusedChain];
focusedDynamicsWorkspace.evidence_index.entries.push({
  artifact_id: focusedChain.chain_id, producer_id: "p32.corner_performance_chain",
  run_id: "run-1", session_id: "session-1", setup_id: "setup-1",
  workspace_run_id: "run-1", workspace_session_id: "session-1", workspace_setup_id: "setup-1",
  source_run_id: "run-1", source_session_id: "session-1", source_setup_id: "setup-1",
  source_setup_sha256: h("b"), source_build_context_sha256: vehicleRuntimeIdentityHash,
  source_provenance_available: true, lap_numbers: [2, 3], lap_pct_start: 20, lap_pct_end: 30,
  phase: "corner_chain", mechanism_ids: [], component_ids: [], control_keys: [],
  objective: "race_long_run", source_channels: [...focusedPhaseState.source_channels],
  evidence_state: "calculated", polarity: "neutral", blocker_reasons: [],
  typed_artifact: {
    artifact_type: "corner_performance_chain", start_pct: 20, end_pct: 30,
    chain: structuredClone(focusedChain),
  },
  authority_ceiling: "observation_only",
});
const p20SupportArtifactId = "observation-center_rotation";
focusedDynamicsWorkspace.evidence_index.entries.push({
  artifact_id: p20SupportArtifactId, producer_id: "p20.mechanism_observation",
  run_id: "run-1", session_id: "session-1", setup_id: "setup-1",
  workspace_run_id: "run-1", workspace_session_id: "session-1", workspace_setup_id: "setup-1",
  source_run_id: "run-1", source_session_id: "session-1", source_setup_id: "setup-1",
  source_setup_sha256: h("b"), source_build_context_sha256: vehicleRuntimeIdentityHash,
  source_provenance_available: true, lap_numbers: [2], lap_pct_start: 20, lap_pct_end: 30,
  phase: "center", mechanism_ids: ["corner_rotation"], component_ids: [], control_keys: [],
  objective: "race_long_run", source_channels: [...centerSupportChannels],
  evidence_state: "observed_correlation", polarity: "support", blocker_reasons: [],
  typed_artifact: null, authority_ceiling: "observation_only",
});
const leadingMechanism = expectedCenterMechanisms[0];
const supportFocusId = await focusArtifactId(
  leadingMechanism,
  "support",
  p20SupportArtifactId,
);
const supportFocus = {
  artifact_id: supportFocusId, mechanism_id: leadingMechanism.mechanism_id,
  observation_contract_id: null, inspection_tool_id: leadingMechanism.inspection_tool_id,
  stage: "vehicle_response", evidence_state: "observed_correlation",
  source_artifact_ids: [p20SupportArtifactId],
  source_channels: [...centerSupportChannels],
  lap_numbers: [2], lap_pct_start: 20, lap_pct_end: 30, phase: "center",
  polarity: "support", summary: "The exact typed P20 response supports candidate relevance only.",
  blocker_reasons: [], authority: "observation_only",
};
const focusedDynamicsBody = structuredClone(focusedDynamicsWorkspace.vehicle_dynamics);
delete focusedDynamicsBody.p35_assessment_sha256;
focusedDynamicsBody.candidates[0].support_artifact_ids = [supportFocusId];
focusedDynamicsBody.candidates[0].blocker_reasons = [];
focusedDynamicsBody.candidates[0].relevance = "candidate";
focusedDynamicsBody.mechanism_separation[0].support_artifact_ids = [supportFocusId];
focusedDynamicsBody.mechanism_separation[0].missing_evidence = [
  "The candidate still requires its controlled discriminator.",
];
focusedDynamicsBody.mechanism_separation[0].state = "alive";
focusedDynamicsBody.response_observations[0].driver_demand_state = "matched";
focusedDynamicsBody.response_observations[0].vehicle_response_state = "changed";
focusedDynamicsBody.response_observations[0].line_state = "matched";
focusedDynamicsBody.problem_signature.driver_demand_state = "matched";
focusedDynamicsBody.problem_signature.vehicle_response_state = "changed";
focusedDynamicsBody.problem_signature.line_state = "matched";
focusedDynamicsBody.focus_artifacts = [supportFocus, ...focusedDynamicsBody.focus_artifacts];
for (const focus of focusedDynamicsBody.focus_artifacts.slice(1)) focus.lap_numbers = [2, 3];
focusedDynamicsBody.chain[2] = {
  stage: "vehicle_response", evidence_state: "measured",
  source_artifact_ids: [focusedChain.chain_id, p20SupportArtifactId],
  source_channels: [...focusedPhaseState.source_channels],
  summary: "P20 observed a current-scope vehicle response; no component cause is assigned.",
  blocker_reasons: [], authority: "observation_only",
};
focusedDynamicsBody.chain[0] = {
  stage: "driver_input", evidence_state: "measured",
  source_artifact_ids: [focusedChain.chain_id], source_channels: [...focusedPhaseState.source_channels],
  summary: "Measured driver demand is available for the exact phase.",
  blocker_reasons: [], authority: "observation_only",
};
focusedDynamicsBody.strongest_support_artifact_id = supportFocusId;
await sealP354(focusedDynamicsBody);
focusedDynamicsWorkspace.vehicle_dynamics = {
  ...focusedDynamicsBody,
  p35_assessment_sha256: await canonicalPerformanceMechanismAssessmentSha256(
    focusedDynamicsBody,
  ),
};
focusedDynamicsWorkspace.identity.p35_assessment_sha256 =
  focusedDynamicsWorkspace.vehicle_dynamics.p35_assessment_sha256;
appendP35EvidenceEntries(focusedDynamicsWorkspace);
await synchronizeEngineeringKnowledge(focusedDynamicsWorkspace);
assert.equal(
  isPerformanceIntelligenceProjection(
    focusedDynamicsWorkspace.performance_intelligence,
    {
      ...directScope,
      opportunityEvidence: new Map([["opportunity-1", focusedOpportunityEntry]]),
    },
  ),
  true,
  "supported P35 fixture retains a trusted exact P32 chain and separation",
);
const focusedBinding = deriveCanonicalP35P32Binding(
  focusedDynamicsWorkspace.performance_intelligence.opportunity_map.opportunities,
  focusedDynamicsWorkspace.performance_intelligence.basis.context_blockers,
);
const focusedChainTruth = deriveP35ChainTruth(
  focusedDynamicsWorkspace.performance_intelligence,
  focusedDynamicsWorkspace.evidence_index.entries,
  focusedBinding,
);
assert.equal(isPerformanceMechanismAssessment(focusedDynamicsWorkspace.vehicle_dynamics, {
  runId: "run-1", sessionId: "session-1", objectiveId: "race_long_run",
  assessmentSha256: focusedDynamicsWorkspace.identity.p35_assessment_sha256,
  carPath: vehicleRuntimeIdentity.car_path, carVersion: vehicleRuntimeIdentity.car_version,
  iRacingBuildVersion: vehicleRuntimeIdentity.iracing_build_version, trackPackage: "oval",
  vehicleRuntimeIdentitySha256: vehicleRuntimeIdentityHash,
  p19ReasoningSnapshotSha256: h("a"), p20StateRevision: h("d"), p20ProfileHash: null,
  p26GraphVersion: "p26.v1", p26KnowledgeGraphSha256: h("e"), p32ProjectionSha256: h("7"),
  ...focusedBinding, ...focusedChainTruth,
  evidenceArtifactIds: focusedDynamicsWorkspace.evidence_index.entries
    .filter((entry) => !entry.producer_id.startsWith("p35."))
    .map((entry) => entry.artifact_id),
}), true, "supported P35 assessment mirrors exact P32/P20 chain truth");
assert.equal(p35FocusEntriesMatchAssessment(
  focusedDynamicsWorkspace.evidence_index.entries,
  focusedDynamicsWorkspace.vehicle_dynamics,
  focusedDynamicsWorkspace.identity,
  report,
  focusedDynamicsWorkspace.engineering_awareness,
), true, "supported P35 Crew focus entries bind exact P20/P32 sources");
for (const entry of focusedDynamicsWorkspace.evidence_index.entries) {
  assert.equal(
    typedArtifactMatchesProjection(
      entry,
      focusedDynamicsWorkspace.performance_intelligence,
      focusedDynamicsWorkspace.identity,
    ),
    true,
    `supported P35 fixture entry ${entry.artifact_id} binds its typed projection`,
  );
}
assert.equal(
  isCrewChiefWorkspaceResponse(focusedDynamicsWorkspace, scope),
  true,
  "typed P35 support, contradiction, and discriminator entries bind to exact current evidence",
);
focusedDynamicsWorkspace.evidence_index.index_hash = await canonicalCrewEvidenceIndexSha256(
  focusedDynamicsWorkspace.evidence_index.entries,
);
assert.equal(
  await hasCanonicalCrewEvidenceIndexDigest(focusedDynamicsWorkspace),
  true,
  "the ordered evidence index binds every current P20/P32/P35 entry",
);
const staleFocusedEvidenceIndex = structuredClone(focusedDynamicsWorkspace);
staleFocusedEvidenceIndex.evidence_index.entries.find(
  (entry) => entry.artifact_id === p20SupportArtifactId,
).source_channels = ["steering_angle_deg"];
assert.equal(
  await hasCanonicalCrewEvidenceIndexDigest(staleFocusedEvidenceIndex),
  false,
  "evidence-entry drift invalidates the ordered index digest",
);

const projectionDetachedP20Support = structuredClone(focusedDynamicsWorkspace);
projectionDetachedP20Support.engineering_awareness.subsystem_states[0].source_artifact_ids = [
  "observation-unrelated",
];
projectionDetachedP20Support.identity.p20_projection_sha256 =
  await canonicalEngineeringAwarenessScientificSha256(
    projectionDetachedP20Support.engineering_awareness,
);
assert.equal(
  await hasCanonicalEngineeringAwarenessDigest(projectionDetachedP20Support),
  true,
  "a coordinated P20 scientific rehash is internally consistent",
);
assert.equal(
  isCrewChiefWorkspaceResponse(projectionDetachedP20Support, scope),
  false,
  "P35 support must remain owned by the separately hashed P20 projection",
);

const rehashFocusedDynamics = async (value) => {
  const body = structuredClone(value.vehicle_dynamics);
  delete body.p35_assessment_sha256;
  await sealP354(body);
  value.vehicle_dynamics = {
    ...body,
    p35_assessment_sha256: await canonicalPerformanceMechanismAssessmentSha256(body),
  };
  value.identity.p35_assessment_sha256 = value.vehicle_dynamics.p35_assessment_sha256;
  for (const entry of value.evidence_index.entries.filter((item) => item.producer_id.startsWith("p35."))) {
    entry.typed_artifact.assessment_sha256 = value.vehicle_dynamics.p35_assessment_sha256;
    entry.typed_artifact.focus = structuredClone(
      value.vehicle_dynamics.focus_artifacts.find((focus) => focus.artifact_id === entry.artifact_id),
    );
  }
  await synchronizeEngineeringKnowledge(value);
};
const rehashedFordRelabel = structuredClone(focusedDynamicsWorkspace);
rehashedFordRelabel.vehicle_dynamics.car_path = "stockcars fordmustang 2022";
await rehashFocusedDynamics(rehashedFordRelabel);
rehashedFordRelabel.evidence_index.index_hash = await canonicalCrewEvidenceIndexSha256(
  rehashedFordRelabel.evidence_index.entries,
);
assert.equal(
  await hasCanonicalPerformanceMechanismAssessmentDigest(
    rehashedFordRelabel.vehicle_dynamics,
  ),
  true,
  "the foreign-car P35 assessment and envelopes are fully rehashed",
);
assert.equal(await hasCanonicalVehicleRuntimeIdentityDigest(rehashedFordRelabel), true);
assert.equal(
  isCrewChiefWorkspaceResponse(rehashedFordRelabel, scope),
  false,
  "an Atlanta Chevrolet runtime cannot be relabeled as an allowed Ford",
);
const rehashedFordRuntimeMirror = structuredClone(rehashedFordRelabel);
rehashedFordRuntimeMirror.identity.vehicle_runtime_identity.car_path =
  "stockcars fordmustang 2022";
assert.equal(
  await hasCanonicalVehicleRuntimeIdentityDigest(rehashedFordRuntimeMirror),
  false,
  "a coordinated full runtime relabel cannot retain the old independent runtime hash",
);
assert.equal(
  isCrewChiefWorkspaceResponse(rehashedFordRuntimeMirror, scope),
  false,
  "the response-owned runtime mirror also remains equal to trusted Run Intelligence",
);
const retargetFocusedSupport = async (value, sourceArtifactId) => {
  const candidate = value.vehicle_dynamics.candidates.find(
    (item) => item.relevance === "candidate",
  );
  const oldSupportId = candidate.support_artifact_ids[0];
  const focus = value.vehicle_dynamics.focus_artifacts.find(
    (item) => item.artifact_id === oldSupportId,
  );
  const oldSourceId = focus.source_artifact_ids[0];
  const source = value.evidence_index.entries.find(
    (entry) => entry.artifact_id === sourceArtifactId,
  );
  const newSupportId = `${p35RuntimeTrustManifest.mechanisms.find(
    (item) => item.mechanism_id === candidate.mechanism_id,
  ).focus_artifact_prefix}${(await canonicalJsonSha256([
    value.vehicle_dynamics.performance_opportunity_ids[0],
    focus.mechanism_id,
    sourceArtifactId,
    "support",
  ])).slice(0, 24)}`;
  focus.artifact_id = newSupportId;
  focus.source_artifact_ids = [sourceArtifactId];
  focus.source_channels = [...source.source_channels];
  focus.lap_numbers = [...source.lap_numbers];
  focus.lap_pct_start = source.lap_pct_start;
  focus.lap_pct_end = source.lap_pct_end;
  focus.phase = source.phase;
  focus.evidence_state = source.evidence_state;
  focus.blocker_reasons = [];
  candidate.support_artifact_ids = [newSupportId];
  value.vehicle_dynamics.strongest_support_artifact_id = newSupportId;
  const responseStage = value.vehicle_dynamics.chain.find(
    (item) => item.stage === "vehicle_response",
  );
  responseStage.source_artifact_ids = responseStage.source_artifact_ids.map(
    (item) => item === oldSourceId ? sourceArtifactId : item,
  );
  responseStage.source_channels = [...new Set([
    ...responseStage.source_channels,
    ...source.source_channels,
  ])];
  value.evidence_index.entries = value.evidence_index.entries.filter(
    (entry) => !entry.producer_id.startsWith("p35."),
  );
  await rehashFocusedDynamics(value);
  appendP35EvidenceEntries(value);
  value.evidence_index.index_hash = await canonicalCrewEvidenceIndexSha256(
    value.evidence_index.entries,
  );
};
const unrelatedP20Support = structuredClone(focusedDynamicsWorkspace);
const unrelatedP20Entry = structuredClone(unrelatedP20Support.evidence_index.entries.find(
  (entry) => entry.artifact_id === p20SupportArtifactId,
));
unrelatedP20Entry.artifact_id = "observation-unrelated";
unrelatedP20Support.evidence_index.entries.push(unrelatedP20Entry);
await retargetFocusedSupport(unrelatedP20Support, unrelatedP20Entry.artifact_id);
assert.equal(
  await hasCanonicalPerformanceMechanismAssessmentDigest(
    unrelatedP20Support.vehicle_dynamics,
  ),
  true,
  "the unrelated-P20 hostile rehashes its assessment and focus identities",
);
assert.equal(await hasCanonicalCrewEvidenceIndexDigest(unrelatedP20Support), true);
assert.equal(
  isCrewChiefWorkspaceResponse(unrelatedP20Support, scope),
  false,
  "response-owned evidence cannot invent P20 support absent from the hashed projection and report",
);
const p32ChainAsSupport = structuredClone(focusedDynamicsWorkspace);
await retargetFocusedSupport(p32ChainAsSupport, focusedChain.chain_id);
assert.equal(
  await hasCanonicalPerformanceMechanismAssessmentDigest(
    p32ChainAsSupport.vehicle_dynamics,
  ),
  true,
  "the P32-chain-as-support hostile rehashes all P35 focus identities",
);
assert.equal(await hasCanonicalCrewEvidenceIndexDigest(p32ChainAsSupport), true);
assert.equal(
  isCrewChiefWorkspaceResponse(p32ChainAsSupport, scope),
  false,
  "a P32 chain cannot impersonate the exact P20 support producer",
);
const detachedP35Envelope = structuredClone(focusedDynamicsWorkspace);
detachedP35Envelope.evidence_index.entries.find(
  (entry) => entry.producer_id.startsWith("p35."),
).typed_artifact.assessment_sha256 = h("f");
assert.equal(isCrewChiefWorkspaceResponse(detachedP35Envelope, scope), false, "P35 entry envelope binds the assessment digest");
const wrongP35Producer = structuredClone(focusedDynamicsWorkspace);
wrongP35Producer.evidence_index.entries.find(
  (entry) => entry.producer_id.startsWith("p35."),
).producer_id = "p35.definitely_wrong";
assert.equal(isCrewChiefWorkspaceResponse(wrongP35Producer, scope), false, "P35 producer binds the exact inspection tool");
const wrongP35Polarity = structuredClone(focusedDynamicsWorkspace);
wrongP35Polarity.evidence_index.entries.find(
  (entry) => entry.producer_id.startsWith("p35.") && entry.polarity === "contradiction",
).polarity = "support";
assert.equal(isCrewChiefWorkspaceResponse(wrongP35Polarity, scope), false, "candidate contradiction cannot navigate as support");
const missingP35FocusEntry = structuredClone(focusedDynamicsWorkspace);
missingP35FocusEntry.evidence_index.entries.pop();
assert.equal(isCrewChiefWorkspaceResponse(missingP35FocusEntry, scope), false, "every P35 focus has exactly one Crew entry");
const rehashedP35ScopeUnion = structuredClone(focusedDynamicsWorkspace);
rehashedP35ScopeUnion.vehicle_dynamics.focus_artifacts[0].lap_pct_start = 21;
rehashedP35ScopeUnion.evidence_index.entries.find(
  (entry) => entry.artifact_id === rehashedP35ScopeUnion.vehicle_dynamics.focus_artifacts[0].artifact_id,
).lap_pct_start = 21;
await rehashFocusedDynamics(rehashedP35ScopeUnion);
assert.equal(isCrewChiefWorkspaceResponse(rehashedP35ScopeUnion, scope), false, "a rehashed focus cannot synthesize scope beyond its typed source");
const rehashedP35SetupDirective = structuredClone(focusedDynamicsWorkspace);
rehashedP35SetupDirective.vehicle_dynamics.focus_artifacts[0].summary = "Increase the right-front spring by 25 lb/in.";
await rehashFocusedDynamics(rehashedP35SetupDirective);
assert.equal(isCrewChiefWorkspaceResponse(rehashedP35SetupDirective, scope), false, "P35 cannot smuggle setup authority through focus narration");
const missingTypedArtifact = structuredClone(withOpportunity);
missingTypedArtifact.evidence_index.entries[0].typed_artifact = null;
assert.equal(isCrewChiefWorkspaceResponse(missingTypedArtifact, scope), false, "P32 evidence requires typed payload");
const wrongTypedDiscriminator = structuredClone(withOpportunity);
wrongTypedDiscriminator.evidence_index.entries[0].typed_artifact.artifact_type = "time_loss_origin";
assert.equal(isCrewChiefWorkspaceResponse(wrongTypedDiscriminator, scope), false, "producer and typed discriminator stay paired");
const detachedTypedOpportunity = structuredClone(withOpportunity);
detachedTypedOpportunity.evidence_index.entries[0].typed_artifact.opportunity.local_delta_s = 0.2;
assert.equal(isCrewChiefWorkspaceResponse(detachedTypedOpportunity, scope), false, "typed opportunity binds exact P32 payload");
const foreignOpportunitySetup = structuredClone(withOpportunity);
foreignOpportunitySetup.evidence_index.entries[0].source_setup_id = "setup-2";
foreignOpportunitySetup.evidence_index.entries[0].setup_id = "setup-2";
assert.equal(isCrewChiefWorkspaceResponse(foreignOpportunitySetup, scope), false, "foreign opportunity setup");
const detachedOpportunityEvidence = structuredClone(withOpportunity);
detachedOpportunityEvidence.evidence_index.entries[0].source_channels = ["YawRate"];
assert.equal(isCrewChiefWorkspaceResponse(detachedOpportunityEvidence, scope), false, "opportunity evidence scope drift");
const missingOpportunityEvidence = structuredClone(withOpportunity);
missingOpportunityEvidence.evidence_index.entries = [];
assert.equal(isCrewChiefWorkspaceResponse(missingOpportunityEvidence, scope), false, "opportunity requires exact evidence");

const unavailableWorkspace = structuredClone(workspace);
unavailableWorkspace.evidence_index.entries = [{
  artifact_id: `p32.lap_time_opportunity:unavailable:${"a".repeat(16)}`,
  producer_id: "p32.lap_time_opportunity", run_id: "run-1", session_id: "session-1",
  setup_id: "setup-1", workspace_run_id: "run-1", workspace_session_id: "session-1",
  workspace_setup_id: "setup-1", source_run_id: "run-1", source_session_id: "session-1",
  source_setup_id: "setup-1", source_setup_sha256: h("b"), source_build_context_sha256: vehicleRuntimeIdentityHash,
  source_provenance_available: true, lap_numbers: [2], lap_pct_start: 0, lap_pct_end: 100,
  phase: "unavailable", mechanism_ids: [], component_ids: [], control_keys: [],
  objective: "race_long_run", source_channels: [], evidence_state: "unavailable", polarity: "neutral",
  blocker_reasons: ["No measured lap-time opportunity is available."],
  typed_artifact: {
    artifact_type: "unavailable", claimed_artifact_type: "lap_time_opportunity",
    blocker_reasons: ["No measured lap-time opportunity is available."],
  },
  authority_ceiling: "observation_only",
}];
assert.equal(isCrewChiefWorkspaceResponse(unavailableWorkspace, scope), true, "typed unavailable artifact");
const wrongUnavailableClaim = structuredClone(unavailableWorkspace);
wrongUnavailableClaim.evidence_index.entries[0].typed_artifact.claimed_artifact_type = "track_demand";
assert.equal(isCrewChiefWorkspaceResponse(wrongUnavailableClaim, scope), false, "unavailable claim matches producer");
const typedGenericEvidence = structuredClone(foreignEvidence);
typedGenericEvidence.evidence_index.entries[0].typed_artifact = unavailableWorkspace.evidence_index.entries[0].typed_artifact;
assert.equal(isCrewChiefWorkspaceResponse(
  typedGenericEvidence, { ...scope, scopeRunIds: ["run-1", "run-2"] },
), false, "non-P32 evidence cannot carry a performance artifact");

const typedWorkspace = structuredClone(withOpportunity);
const phaseState = {
  phase: "center", start_pct: 20, end_pct: 30, elapsed_delta_s: 0.1, speed_delta_mph: -1,
  throttle_delta_pct: null, brake_delta_pct: null, steering_delta_deg: null, yaw_rate_delta: null,
  long_accel_delta: null, path_delta_m: 1.2, line_separation_m: 0.4, evidence_state: "measured",
  driver_demand_source_coverage: 1, driver_demand_reference_coverage: 1,
  source_channels: ["speed_mph", "lat", "lon"], blockers: [],
};
const separation = {
  separation_id: "separation-1", phase: "center", driver_demand_changed: null,
  vehicle_response_changed: null, line_changed: null, context_changed: null, time_changed: true,
  result: "unresolved", support: [], contradictions: ["Driver demand is incomplete."],
  blockers: ["Driver demand is incomplete."], authority: "observation_only",
};
const chain = {
  chain_id: "chain-1", track_region: "Turn 1", turn: "1", lap_numbers: [2], reference_lap_numbers: [],
  approach_state: null, braking_state: null, entry_state: null, center_state: phaseState,
  exit_state: null, carry_state: null, local_time_effect_s: 0.1, downstream_time_effect_s: 0.02,
  driver_vehicle_separation: [separation], context: [], contradictions: ["One pair only."],
  authority: "observation_only",
};
const influence = {
  influence_id: "influence-1", component_id: "anti_roll_bars",
  performance_mechanism_ids: ["center_rotation"], expected_state_ids: ["roll_support"],
  measurable_through: ["lat_accel"], runtime_support_state: "mechanically_relevant",
  source_artifact_ids: [], contradictions: ["Relevance does not establish cause."],
  authority: "knowledge_only", setup_authorized: false,
};
typedWorkspace.performance_intelligence.corner_chains = [chain];
typedWorkspace.performance_intelligence.component_influences = [influence];
const p32Entry = (overrides) => ({
  artifact_id: "", producer_id: "", run_id: "run-1", session_id: "session-1", setup_id: "setup-1",
  workspace_run_id: "run-1", workspace_session_id: "session-1", workspace_setup_id: "setup-1",
  source_run_id: "run-1", source_session_id: "session-1", source_setup_id: "setup-1",
  source_setup_sha256: h("b"), source_build_context_sha256: vehicleRuntimeIdentityHash, source_provenance_available: true,
  lap_numbers: [2], lap_pct_start: 0, lap_pct_end: 100, phase: "whole_run", mechanism_ids: [],
  component_ids: [], control_keys: [], objective: "race_long_run", source_channels: [],
  evidence_state: "calculated", polarity: "neutral", blocker_reasons: [], typed_artifact: null,
  authority_ceiling: "observation_only", ...overrides,
});
const opportunity = typedWorkspace.performance_intelligence.opportunity_map.opportunities[0];
typedWorkspace.evidence_index.entries = [
  p32Entry({ artifact_id: "opportunity-1", producer_id: "p32.lap_time_opportunity", lap_numbers: [2, 3], lap_pct_start: 20, lap_pct_end: 30, phase: "center", mechanism_ids: ["unclassified"], source_channels: ["speed_mph"], evidence_state: "observed_correlation", typed_artifact: { artifact_type: "lap_time_opportunity", opportunity: structuredClone(opportunity) } }),
  p32Entry({ artifact_id: "opportunity-1:time-origin", producer_id: "p32.time_loss_origin", lap_numbers: [2, 3], lap_pct_start: 20, lap_pct_end: 30, phase: "center", mechanism_ids: ["unclassified"], source_channels: ["speed_mph"], evidence_state: "observed_correlation", typed_artifact: { artifact_type: "time_loss_origin", opportunity: structuredClone(opportunity) } }),
  p32Entry({ artifact_id: "opportunity-1:exit-carry", producer_id: "p32.exit_carry", lap_numbers: [2, 3], lap_pct_start: 30, lap_pct_end: 38, phase: "following_straight_carry", mechanism_ids: ["unclassified"], source_channels: ["speed_mph"], evidence_state: "observed_correlation", typed_artifact: { artifact_type: "exit_carry", opportunity: structuredClone(opportunity) } }),
  p32Entry({ artifact_id: "chain-1", producer_id: "p32.corner_performance_chain", lap_pct_start: 20, lap_pct_end: 30, phase: "corner_chain", source_channels: ["speed_mph", "lat", "lon"], typed_artifact: { artifact_type: "corner_performance_chain", start_pct: 20, end_pct: 30, chain: structuredClone(chain) } }),
  p32Entry({ artifact_id: "chain-1:path:center", producer_id: "p32.path_efficiency", lap_pct_start: 20, lap_pct_end: 30, phase: "center", source_channels: ["speed_mph", "lat", "lon"], typed_artifact: { artifact_type: "path_efficiency", chain_id: "chain-1", phase_state: structuredClone(phaseState) } }),
  p32Entry({ artifact_id: "separation-1", producer_id: "p32.driver_vehicle_separation", lap_pct_start: 20, lap_pct_end: 30, phase: "center", source_channels: ["speed_mph", "lat", "lon"], evidence_state: "blocked_by_context", blocker_reasons: ["Driver demand is incomplete."], authority_ceiling: "context_only", typed_artifact: { artifact_type: "driver_vehicle_separation", chain_id: "chain-1", track_region: "Turn 1", start_pct: 20, end_pct: 30, separation: structuredClone(separation) } }),
  p32Entry({ artifact_id: `p32-track-demand:${"1".repeat(20)}`, producer_id: "p32.track_demand", lap_numbers: [2, 3], source_channels: ["speed_mph"], typed_artifact: { artifact_type: "track_demand", profile: structuredClone(typedWorkspace.performance_intelligence.track_demand) } }),
  p32Entry({ artifact_id: "influence-1", producer_id: "p32.component_performance_link", lap_numbers: [2, 3], phase: "component_performance_link", mechanism_ids: ["unclassified"], component_ids: ["anti_roll_bars"], source_channels: ["lat_accel"], evidence_state: "needs_confirmation", typed_artifact: { artifact_type: "component_performance_link", influence: structuredClone(influence) } }),
  p32Entry({ artifact_id: `p32-objective:${"2".repeat(20)}`, producer_id: "p32.objective_envelope", lap_numbers: [2, 3], authority_ceiling: "context_only", typed_artifact: { artifact_type: "objective_envelope", envelope: structuredClone(typedWorkspace.performance_intelligence.objective_envelope) } }),
];
for (const entry of typedWorkspace.evidence_index.entries) {
  assert.equal(
    typedArtifactMatchesProjection(
      entry,
      typedWorkspace.performance_intelligence,
      typedWorkspace.identity,
    ),
    true,
    `all-nine fixture entry ${entry.artifact_id} binds its typed projection`,
  );
}
assert.equal(
  isPerformanceIntelligenceProjection(typedWorkspace.performance_intelligence, {
    ...directScope,
    opportunityEvidence: new Map([["opportunity-1", typedWorkspace.evidence_index.entries[0]]]),
  }),
  true,
  "all-nine fixture retains a trusted performance projection",
);
const invalidDemandCoverage = structuredClone(typedWorkspace);
invalidDemandCoverage.performance_intelligence.corner_chains[0].center_state.driver_demand_source_coverage = 1.1;
assert.equal(isPerformanceIntelligenceProjection(invalidDemandCoverage.performance_intelligence, {
  ...directScope,
  opportunityEvidence: new Map([["opportunity-1", invalidDemandCoverage.evidence_index.entries[0]]]),
}), false, "driver-demand coverage stays bounded");
const incompleteMatchedDemand = structuredClone(typedWorkspace);
Object.assign(incompleteMatchedDemand.performance_intelligence.corner_chains[0].driver_vehicle_separation[0], {
  driver_demand_changed: false,
  vehicle_response_changed: true,
  line_changed: false,
  context_changed: false,
  result: "vehicle_response_changed_with_matched_inputs",
  blockers: [],
});
incompleteMatchedDemand.performance_intelligence.corner_chains[0].center_state.driver_demand_source_coverage = 0.9;
assert.equal(isPerformanceIntelligenceProjection(incompleteMatchedDemand.performance_intelligence, {
  ...directScope,
  opportunityEvidence: new Map([["opportunity-1", incompleteMatchedDemand.evidence_index.entries[0]]]),
}), false, "matched inputs require complete co-observed demand");
for (const [label, mutate] of [
  ["time-origin payload drift", (value) => { value.evidence_index.entries[1].typed_artifact.opportunity.origin_kind = "carried_in"; }],
  ["exit-carry window drift", (value) => { value.evidence_index.entries[2].typed_artifact.opportunity.following_phase_end_pct = 39; }],
  ["corner-chain payload drift", (value) => { value.evidence_index.entries[3].typed_artifact.chain.local_time_effect_s = 0.2; }],
  ["path payload drift", (value) => { value.evidence_index.entries[4].typed_artifact.phase_state.path_delta_m = 9; }],
  ["separation payload drift", (value) => { value.evidence_index.entries[5].typed_artifact.track_region = "Turn 2"; }],
  ["track-demand payload drift", (value) => { value.evidence_index.entries[6].typed_artifact.profile.braking_fraction = 0.9; }],
  ["component-link payload drift", (value) => { value.evidence_index.entries[7].typed_artifact.influence.component_id = "springs"; }],
  ["objective payload drift", (value) => { value.evidence_index.entries[8].typed_artifact.envelope.objective_id = "qualifying_peak"; }],
  ["typed evidence-state drift", (value) => { value.evidence_index.entries[7].evidence_state = "calculated"; }],
]) {
  const hostile = structuredClone(typedWorkspace);
  mutate(hostile);
  assert.equal(hostile.evidence_index.entries.every((entry) => typedArtifactMatchesProjection(
    entry,
    hostile.performance_intelligence,
    hostile.identity,
  )), false, label);
}

const trafficBlocked = structuredClone(withOpportunity);
Object.assign(trafficBlocked.performance_intelligence.opportunity_map.opportunities[0], {
  attribution_state: "blocked_by_traffic", context_state: "traffic_contaminated",
  source_traffic_exposure_fraction: 1, contradictions: ["Traffic covered the comparison window."],
});
Object.assign(trafficBlocked.performance_intelligence.speed_story, {
  attribution_state: "blocked_by_traffic", attribution: "Attribution blocked by traffic.",
  strongest_contradiction: "Traffic covered the comparison window.",
});
trafficBlocked.performance_intelligence.explanation_chain.strongest_contradiction = "Traffic covered the comparison window.";
trafficBlocked.evidence_index.entries[0].evidence_state = "blocked_by_context";
trafficBlocked.evidence_index.entries[0].blocker_reasons = ["Traffic covered the comparison window."];
trafficBlocked.evidence_index.entries[0].typed_artifact.opportunity = structuredClone(
  trafficBlocked.performance_intelligence.opportunity_map.opportunities[0],
);
const trafficBinding = deriveCanonicalP35P32Binding(
  trafficBlocked.performance_intelligence.opportunity_map.opportunities,
  trafficBlocked.performance_intelligence.basis.context_blockers,
);
const trafficChainTruth = deriveP35ChainTruth(
  trafficBlocked.performance_intelligence,
  trafficBlocked.evidence_index.entries,
  trafficBinding,
);
trafficBlocked.vehicle_dynamics.traffic_blocked = true;
trafficBlocked.vehicle_dynamics.response_observations[0].context_state = "blocked";
trafficBlocked.vehicle_dynamics.response_observations[0].evidence_state = "blocked_by_context";
trafficBlocked.vehicle_dynamics.response_observations[0].blocker_reasons = [
  "Traffic covered the comparison window.",
];
trafficBlocked.vehicle_dynamics.problem_signature.traffic_dependence = "blocked";
trafficBlocked.vehicle_dynamics.chain = trafficBlocked.vehicle_dynamics.chain.map((stage, index) => ({
  ...stage,
  ...trafficChainTruth.expectedChain[index],
}));
await rehashFocusedDynamics(trafficBlocked);
assert.equal(isPerformanceIntelligenceProjection(
  trafficBlocked.performance_intelligence,
  {
    ...directScope,
    opportunityEvidence: new Map([["opportunity-1", trafficBlocked.evidence_index.entries[0]]]),
  },
), true, "traffic fixture retains exact P32 truth");
assert.equal(isPerformanceMechanismAssessment(trafficBlocked.vehicle_dynamics, {
  runId: "run-1", sessionId: "session-1", objectiveId: "race_long_run",
  assessmentSha256: trafficBlocked.identity.p35_assessment_sha256,
  carPath: vehicleRuntimeIdentity.car_path, carVersion: vehicleRuntimeIdentity.car_version,
  iRacingBuildVersion: vehicleRuntimeIdentity.iracing_build_version, trackPackage: "oval",
  vehicleRuntimeIdentitySha256: vehicleRuntimeIdentityHash,
  p19ReasoningSnapshotSha256: h("a"), p20StateRevision: h("d"), p20ProfileHash: null,
  p26GraphVersion: "p26.v1", p26KnowledgeGraphSha256: h("e"), p32ProjectionSha256: h("7"),
  ...trafficBinding, ...trafficChainTruth,
  evidenceArtifactIds: trafficBlocked.evidence_index.entries
    .filter((entry) => !entry.producer_id.startsWith("p35."))
    .map((entry) => entry.artifact_id),
}), true, "traffic fixture retains exact P35 blocked truth");
assert.equal(isCrewChiefWorkspaceResponse(trafficBlocked, scope), true, "traffic difference remains visible but blocked");
const contextBlockedWithComponent = structuredClone(trafficBlocked);
Object.assign(contextBlockedWithComponent.performance_intelligence.opportunity_map.opportunities[0], {
  attribution_state: "blocked_by_context",
  context_state: "nearby_context_unavailable",
  component_candidates: ["springs"],
  contradictions: ["Nearby-car context is unavailable."],
});
Object.assign(contextBlockedWithComponent.performance_intelligence.speed_story, {
  attribution_state: "blocked_by_context",
  attribution: "Attribution blocked by unavailable nearby-car context.",
  strongest_contradiction: "Nearby-car context is unavailable.",
});
contextBlockedWithComponent.performance_intelligence.explanation_chain.strongest_contradiction = "Nearby-car context is unavailable.";
contextBlockedWithComponent.evidence_index.entries[0].component_ids = ["springs"];
contextBlockedWithComponent.evidence_index.entries[0].blocker_reasons = ["Nearby-car context is unavailable."];
contextBlockedWithComponent.evidence_index.entries[0].typed_artifact.opportunity = structuredClone(
  contextBlockedWithComponent.performance_intelligence.opportunity_map.opportunities[0],
);
assert.equal(isCrewChiefWorkspaceResponse(contextBlockedWithComponent, scope), false, "context-blocked opportunities cannot publish component candidates");
trafficBlocked.performance_intelligence.speed_story.strongest_contradiction = "Line changed.";
trafficBlocked.performance_intelligence.explanation_chain.strongest_contradiction = "Line changed.";
assert.equal(isCrewChiefWorkspaceResponse(trafficBlocked, scope), false, "traffic must stay strongest");
