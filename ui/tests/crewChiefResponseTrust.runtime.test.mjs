import assert from "node:assert/strict";
import {
  hasCanonicalMeasurementMissionDigest,
  isCrewChiefWorkspaceResponse,
} from "../src/utils/crewChiefResponseTrust.ts";
import { isPerformanceIntelligenceProjection } from "../src/utils/performanceIntelligenceTrust.js";
import { canonicalJsonSha256 } from "../src/utils/canonicalJsonSha256.ts";
import {
  canonicalEngineeringLearningSha256,
  hasCanonicalEngineeringLearningDigests,
} from "../src/utils/engineeringLearningTrust.js";

const h = (value) => value.repeat(64);
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
  schema_version: "p33.crew-chief-workspace.v1",
  identity: {
    run_id: "run-1", session_id: "session-1", reasoning_snapshot_sha256: h("a"),
    setup_id: "setup-1", setup_snapshot_sha256: h("b"), workspace_revision: h("c"),
    selected_scope_hash: h("f"), p20_profile_hash: null, p26_graph_version: "p26.v1",
    p20_state_revision: h("d"), p26_knowledge_graph_sha256: h("e"),
    p26_reasoning_snapshot_sha256: h("a"), active_workflow_id: null, active_workflow_revision: null,
    p32_projection_sha256: h("7"), objective_id: "race_long_run",
    learning_history_revision: h("1"), learning_projection_sha256: h("2"),
    vehicle_runtime_identity_hash: h("9"), investigation_id: null,
  },
  evidence_index: { workspace_revision: h("c"), index_hash: h("8"), entries: [] },
  p19_mission_contract: null,
  performance_intelligence: performance,
  learning_prior: emptyLearningPrior,
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
  opened_at: "2026-08-14T12:00:00Z",
  status: "open",
};
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
assert.equal(await hasCanonicalMeasurementMissionDigest(missionContract), true);
const staleMission = structuredClone(withMission);
staleMission.p19_mission_contract.setup_sha256 = h("0");
assert.equal(isCrewChiefWorkspaceResponse(staleMission, missionScope), true);
assert.equal(
  await hasCanonicalMeasurementMissionDigest(staleMission.p19_mission_contract),
  false,
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
