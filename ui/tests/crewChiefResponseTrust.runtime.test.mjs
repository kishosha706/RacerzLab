import assert from "node:assert/strict";
import { isCrewChiefWorkspaceResponse } from "../src/utils/crewChiefResponseTrust.ts";
import { isPerformanceIntelligenceProjection } from "../src/utils/performanceIntelligenceTrust.js";

const h = (value) => value.repeat(64);
const report = {
  reasoning_snapshot_sha256: h("a"), setup_id: "setup-1", setup_snapshot_sha256: h("b"),
  briefing: { action: { kind: "measurement_mission", title: "Measure", instruction: "Collect three eligible laps.", setup_authorized: false, control_key: null, current_value: null, proposed_value: null, source_event_ids: [] } },
  next_trustworthy_move: null,
};
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
const workspace = {
  schema_version: "p32.crew-chief-workspace.v2",
  identity: {
    run_id: "run-1", session_id: "session-1", reasoning_snapshot_sha256: h("a"),
    setup_id: "setup-1", setup_snapshot_sha256: h("b"), workspace_revision: h("c"),
    selected_scope_hash: h("f"), p20_profile_hash: null, p26_graph_version: "p26.v1",
    p20_state_revision: h("d"), p26_knowledge_graph_sha256: h("e"),
    p26_reasoning_snapshot_sha256: h("a"), active_workflow_id: null, active_workflow_revision: null,
    p32_projection_sha256: h("7"), objective_id: "race_long_run",
    vehicle_runtime_identity_hash: h("9"), investigation_id: null,
  },
  evidence_index: { workspace_revision: h("c"), index_hash: h("8"), entries: [] },
  p19_mission_contract: null,
  performance_intelligence: performance,
  success_contract: {
    workspace_revision: h("c"), target_scope: "braking entry", acceptance_rule: "Repeat the metric.",
    independence_unit: "eligible lap",
  },
  run_sentinel: {
    mission_state: "collecting", p19_plan_kind: "measurement_mission",
    mission: "Collect evidence", need: "Three eligible laps", success: "Repeatable evidence",
    stop: ["Stop on integrity failure."], required_laps: 3, accepted_laps: 0,
    collection_complete: false, stage: "measurement", laps: [],
  },
  critique: { outcome: "pass", passed: true, findings: [], strongest_contradiction: null },
  adaptive_research: { state: "data_locked", authority: "none", activation_gate: "Held-out evidence is required." },
  current_subgoal: null, pending_driver_question: null, investigation: null, folded_state: null,
  blocker_reasons: [], post_run_brief: ["P19 status: ready."], response_history_ids: [], driver_memory_ids: [],
  terminal_decision: {
    kind: "measurement_mission", title: "Measure", instruction: "Collect three eligible laps.",
    authority: "measurement_only", control_key: null, current_value: null, proposed_value: null,
    source_event_ids: [], workflow_id: null, workflow_revision: null, blocker_reasons: [],
  },
};
const scope = { runId: "run-1", sessionId: "session-1", report, objectiveId: "race_long_run" };
assert.equal(isCrewChiefWorkspaceResponse(workspace, scope), true);
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
  setup_authorized: true, control_key: "cross_weight_percent", current_value: "51.5%",
  proposed_value: "52.0%", source_event_ids: ["event-1"],
};
controlledReport.next_trustworthy_move = { workflow_id: "workflow-1", workflow_updated_at: "revision-1" };
const controlled = structuredClone(workspace);
Object.assign(controlled.identity, { active_workflow_id: "workflow-1", active_workflow_revision: "revision-1" });
controlled.terminal_decision = {
  kind: "controlled_test", title: "One P19 test", instruction: "Set the exact card.",
  authority: "p19_projection_only", control_key: "cross_weight_percent", current_value: "51.5%",
  proposed_value: "52.0%", source_event_ids: ["event-1"], workflow_id: "workflow-1",
  workflow_revision: "revision-1", blocker_reasons: [],
};
controlled.performance_intelligence.speed_story.next = "Set the exact card.";
controlled.performance_intelligence.explanation_chain.p19_next_move = "Set the exact card.";
assert.equal(isCrewChiefWorkspaceResponse(controlled, { ...scope, report: controlledReport }), true);
controlled.terminal_decision.proposed_value = "53.0%";
assert.equal(isCrewChiefWorkspaceResponse(controlled, { ...scope, report: controlledReport }), false);

const rejectMutation = (label, mutate) => {
  const hostile = structuredClone(workspace);
  mutate(hostile);
  assert.equal(isCrewChiefWorkspaceResponse(hostile, scope), false, label);
};
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
withOpportunity.performance_intelligence.opportunity_map.opportunities = [{
  opportunity_id: "opportunity-1", start_pct: 20, end_pct: 30, track_region: "Turn 1", turn: "1",
  phase: "center", local_delta_s: 0.1, cumulative_delta_at_entry_s: 0.02,
  cumulative_delta_at_exit_s: 0.12, origin_kind: "local_generation", persistence_distance_pct: 8,
  following_phase_effect_s: 0.02, following_phase_start_pct: 30, following_phase_end_pct: 38,
  repeatability: "observed_once", noise_basis: "One eligible pair.",
  source_laps: [2], source_channels: ["speed_mph"], driver_execution_state: "unresolved",
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
  session_id: "session-1", setup_id: "setup-1", lap_numbers: [2], workspace_run_id: "run-1",
  workspace_session_id: "session-1", workspace_setup_id: "setup-1", source_run_id: "run-1",
  source_session_id: "session-1", source_setup_id: "setup-1", source_setup_sha256: h("b"),
  source_build_context_sha256: h("9"), source_provenance_available: true, lap_pct_start: 20,
  lap_pct_end: 30, phase: "center", mechanism_ids: ["unclassified"], component_ids: [],
  control_keys: [], objective: "race_long_run", source_channels: ["speed_mph"],
  evidence_state: "observed_correlation", polarity: "neutral", blocker_reasons: [],
  typed_artifact: {
    artifact_type: "lap_time_opportunity",
    opportunity: structuredClone(withOpportunity.performance_intelligence.opportunity_map.opportunities[0]),
  },
  authority_ceiling: "observation_only",
}];
const directScope = {
  runId: "run-1", sessionId: "session-1", setupId: "setup-1", setupSnapshotHash: h("b"),
  buildContextHash: h("9"), objectiveId: "race_long_run", p19Hash: h("a"), p20Revision: h("d"),
  p26Hash: h("e"), projectionHash: h("7"), p19Next: "Collect three eligible laps.",
  scopeRunIds: new Set(["run-1"]), opportunityEvidence: new Map([["opportunity-1", withOpportunity.evidence_index.entries[0]]]),
};
assert.equal(isPerformanceIntelligenceProjection(withOpportunity.performance_intelligence, directScope), true, "direct P32 opportunity contract");
assert.equal(isCrewChiefWorkspaceResponse(withOpportunity, scope), true, "atomically bound opportunity");
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
  source_setup_id: "setup-1", source_setup_sha256: h("b"), source_build_context_sha256: h("9"),
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
  source_setup_sha256: h("b"), source_build_context_sha256: h("9"), source_provenance_available: true,
  lap_numbers: [2], lap_pct_start: 0, lap_pct_end: 100, phase: "whole_run", mechanism_ids: [],
  component_ids: [], control_keys: [], objective: "race_long_run", source_channels: [],
  evidence_state: "calculated", polarity: "neutral", blocker_reasons: [], typed_artifact: null,
  authority_ceiling: "observation_only", ...overrides,
});
const opportunity = typedWorkspace.performance_intelligence.opportunity_map.opportunities[0];
typedWorkspace.evidence_index.entries = [
  p32Entry({ artifact_id: "opportunity-1", producer_id: "p32.lap_time_opportunity", lap_pct_start: 20, lap_pct_end: 30, phase: "center", mechanism_ids: ["unclassified"], source_channels: ["speed_mph"], evidence_state: "observed_correlation", typed_artifact: { artifact_type: "lap_time_opportunity", opportunity: structuredClone(opportunity) } }),
  p32Entry({ artifact_id: "opportunity-1:time-origin", producer_id: "p32.time_loss_origin", lap_pct_start: 20, lap_pct_end: 30, phase: "center", mechanism_ids: ["unclassified"], source_channels: ["speed_mph"], evidence_state: "observed_correlation", typed_artifact: { artifact_type: "time_loss_origin", opportunity: structuredClone(opportunity) } }),
  p32Entry({ artifact_id: "opportunity-1:exit-carry", producer_id: "p32.exit_carry", lap_pct_start: 30, lap_pct_end: 38, phase: "following_straight_carry", mechanism_ids: ["unclassified"], source_channels: ["speed_mph"], evidence_state: "observed_correlation", typed_artifact: { artifact_type: "exit_carry", opportunity: structuredClone(opportunity) } }),
  p32Entry({ artifact_id: "chain-1", producer_id: "p32.corner_performance_chain", lap_pct_start: 20, lap_pct_end: 30, phase: "corner_chain", source_channels: ["speed_mph", "lat", "lon"], evidence_state: "blocked_by_context", blocker_reasons: ["Reference unavailable."], typed_artifact: { artifact_type: "corner_performance_chain", start_pct: 20, end_pct: 30, chain: structuredClone(chain) } }),
  p32Entry({ artifact_id: "chain-1:path:center", producer_id: "p32.path_efficiency", lap_pct_start: 20, lap_pct_end: 30, phase: "center", source_channels: ["speed_mph", "lat", "lon"], evidence_state: "blocked_by_context", blocker_reasons: ["Reference unavailable."], typed_artifact: { artifact_type: "path_efficiency", chain_id: "chain-1", phase_state: structuredClone(phaseState) } }),
  p32Entry({ artifact_id: "separation-1", producer_id: "p32.driver_vehicle_separation", lap_pct_start: 20, lap_pct_end: 30, phase: "center", source_channels: ["speed_mph", "lat", "lon"], evidence_state: "blocked_by_context", blocker_reasons: ["Driver demand is incomplete."], authority_ceiling: "context_only", typed_artifact: { artifact_type: "driver_vehicle_separation", chain_id: "chain-1", track_region: "Turn 1", start_pct: 20, end_pct: 30, separation: structuredClone(separation) } }),
  p32Entry({ artifact_id: `p32-track-demand:${"1".repeat(20)}`, producer_id: "p32.track_demand", source_channels: ["speed_mph"], typed_artifact: { artifact_type: "track_demand", profile: structuredClone(typedWorkspace.performance_intelligence.track_demand) } }),
  p32Entry({ artifact_id: "influence-1", producer_id: "p32.component_performance_link", phase: "component_performance_link", mechanism_ids: ["unclassified"], component_ids: ["anti_roll_bars"], source_channels: ["lat_accel"], evidence_state: "needs_confirmation", typed_artifact: { artifact_type: "component_performance_link", influence: structuredClone(influence) } }),
  p32Entry({ artifact_id: `p32-objective:${"2".repeat(20)}`, producer_id: "p32.objective_envelope", authority_ceiling: "context_only", typed_artifact: { artifact_type: "objective_envelope", envelope: structuredClone(typedWorkspace.performance_intelligence.objective_envelope) } }),
];
assert.equal(isCrewChiefWorkspaceResponse(typedWorkspace, scope), true, "all nine typed performance artifacts");
const invalidDemandCoverage = structuredClone(typedWorkspace);
invalidDemandCoverage.performance_intelligence.corner_chains[0].center_state.driver_demand_source_coverage = 1.1;
assert.equal(isCrewChiefWorkspaceResponse(invalidDemandCoverage, scope), false, "driver-demand coverage stays bounded");
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
assert.equal(isCrewChiefWorkspaceResponse(incompleteMatchedDemand, scope), false, "matched inputs require complete co-observed demand");
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
  assert.equal(isCrewChiefWorkspaceResponse(hostile, scope), false, label);
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
