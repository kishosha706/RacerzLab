import assert from "node:assert/strict";

import { isDialInHypothesisResponse } from "../src/utils/dialInResponseTrust.ts";

const authorityBlocker = "This Dial-In response is measurement guidance only. Only the controlled P19 workflow may authorize one exact setup target, Keep/Undo, or stop-testing.";
const response = {
  run_id: "run-1",
  complaint_raw: "loose off",
  confidence_label: "Needs clarification",
  readiness_label: "Measurement required",
  driver_message: "Engineering hypotheses only; no setup change is authorized from this response.",
  top_swings: [{
    id: "swing-1",
    title: "Cross Weight",
    setup_area: "cross_weight",
    current_relevance: "knowledge_only",
    p32_opportunity_id: null,
    knowledge_level: "measurable_hypothesis",
    bridge_id: `p351b_${"1".repeat(24)}`,
    bridge_sha256: "2".repeat(64),
    p35_mechanism_ids: ["mechanism:front_roll_support_limitation"],
    p20_mechanism_ids: ["corner_rotation"],
    p26_component_family_ids: ["springs"],
    p32_performance_mechanism_ids: ["corner_rotation"],
    inspection_tool_ids: ["inspect_steady_platform"],
    discriminator_contract_ids: ["contract:front_roll"],
    knowledge_version: "p351.test.v1",
    knowledge_graph_sha256: "3".repeat(64),
    candidate_control_label: "Cross Weight",
    related_control_keys: ["cross_weight_percent"],
    influence_label: "Medium",
    strength_label: "Hypothesis",
    risk_label: "Low risk",
    mechanism_to_verify: "Determine whether this control area's measured response contributes to the selected symptom.",
    counter_effect_to_watch: "Watch for a protected-phase regression or driver-execution change during controlled measurement.",
    validate_with: ["yaw_rate"],
    validate_with_labels: ["Yaw response"],
    watch_for: ["entry_phase_time"],
    watch_for_labels: ["Entry phase time"],
    readiness_label: "Measurement required",
    measurement_needed: "Repeat the selected symptom on eligible matched laps with the setup unchanged.",
    evidence_state: "needs_confirmation",
    source_channels: ["yaw_rate"],
    observed_evidence_flags: [],
    supporting_event_ids: [],
    blocker_reasons: [authorityBlocker],
  }],
  next_step: "Collect matched, eligible repeats for the selected phase, then use the controlled P19 workflow to decide whether one setup test is justified.",
  clarification: { needed: false, question: "Where is it happening?", options: [] },
  warnings: [authorityBlocker],
  evidence_state: "needs_confirmation",
  source_channels: ["yaw_rate"],
  blocker_reasons: [authorityBlocker],
  evidence_strength: {
    level: "unavailable",
    readiness: "blocked",
    capability_flags: [],
    observed_mechanism_flags: [],
    supporting_event_ids: [],
    setup_test_ready: false,
    requires_controlled_test: true,
    reason: "More evidence is required.",
  },
};

const expectation = { runId: "run-1", complaint: "loose off" };
assert.equal(isDialInHypothesisResponse(response, expectation), true);

const exactField = structuredClone(response);
exactField.top_swings[0].proposed_value = "52.0%";
assert.equal(isDialInHypothesisResponse(exactField, expectation), false);

for (const prose of [
  "Set cross weight to 52.0% now.",
  "Cross weight: set it to 52.0%.",
  "RF spring should be 500 lb/in.",
  "Use 500 lb/in for the RF spring.",
  "Retain the new setup.",
  "Revert this change.",
  "End testing this direction.",
  "Do not continue testing.",
  "Keep.",
  "Undo it.",
  "Stop the test.",
  "This change is a keep.",
  "The change should be reverted.",
  "Rollback now.",
  "No more testing.",
  "Testing is over.",
  "We are done testing.",
  "Do not test again.",
  "Cross weight: fifty-two percent.",
  "RF spring: five hundred pounds per inch.",
  "Set LF LS rebound to 4 clicks.",
  "LF LS compression: 6 clicks.",
  "Set RF HS compression slope to 3 clicks.",
  "Set front master cylinder to 17.8 mm.",
  "Rear master cylinder: 19.1 mm.",
  "Set LF toe-in to 1.5 mm.",
  "RF toe-in: 2 mm.",
  "Set cross_weight_percent to 52.0.",
  "Set front_mc_mm to 17.8.",
  "Set lf.ls_rebound to 4 clicks.",
]) {
  const proseTarget = structuredClone(response);
  proseTarget.top_swings[0].measurement_needed = prose;
  assert.equal(isDialInHypothesisResponse(proseTarget, expectation), false, prose);
}

const hostileClarification = structuredClone(response);
hostileClarification.clarification = {
  needed: true,
  question: "Cross weight: set it to 52.0%?",
  options: ["Entry"],
};
assert.equal(isDialInHypothesisResponse(hostileClarification, expectation), false);

const hostileUnexpectedField = structuredClone(response);
hostileUnexpectedField.top_swings[0].action_text = "Use 500 lb/in for the RF spring.";
assert.equal(isDialInHypothesisResponse(hostileUnexpectedField, expectation), false);

const nullableClarification = structuredClone(response);
nullableClarification.clarification = { needed: false, question: null, options: [] };
assert.equal(isDialInHypothesisResponse(nullableClarification, expectation), true);

const staleRun = structuredClone(response);
staleRun.run_id = "run-2";
assert.equal(isDialInHypothesisResponse(staleRun, expectation), false);

const hypotheses = Array.from({ length: 92 }, (_, index) => ({
  bridge_id: `p351b_${index.toString(16).padStart(24, "0")}`,
  effect_id: `effect_${index.toString().padStart(2, "0")}`,
  setup_area: `area_${index.toString().padStart(2, "0")}`,
  physical_role: "Explains one direction-neutral setup relationship.",
  level: "educational_knowledge",
  relevance: "knowledge_only",
  p32_opportunity_id: null,
  p35_mechanism_ids: [], p20_mechanism_ids: [], p26_component_family_ids: [],
  response_regimes: [], relevant_phases: [], expected_vehicle_response_ids: [],
  countereffect_ids: [], protected_outcomes: [], inspection_tool_ids: [],
  support_artifact_ids: [], contradiction_artifact_ids: [],
  discriminator_contract_ids: [], missing_evidence: ["Measurement is unavailable."],
  controlled_history: [], p19_control: null, authority: "knowledge_only",
  setup_authorized: false,
}));
const terminal = {
  kind: "no_call", title: "No setup call", instruction: "Keep measuring.",
  authority: "measurement_only", control_key: null, current_value: null,
  proposed_value: null, source_event_ids: [], workflow_id: null,
  workflow_revision: null, blocker_reasons: ["Evidence is incomplete."],
};
const sessionBound = structuredClone(response);
sessionBound.engineering_knowledge = {
  schema_version: "p351.current-engineering-knowledge.v1",
  projection_sha256: "4".repeat(64), run_id: "run-1", session_id: "session-1",
  complaint_prior: null, p19_reasoning_snapshot_sha256: "5".repeat(64),
  p20_state_revision: "6".repeat(64), p26_knowledge_graph_sha256: "7".repeat(64),
  p32_projection_sha256: "8".repeat(64), p35_assessment_sha256: "9".repeat(64),
  p33_projection_sha256: "a".repeat(64),
  bridge_coverage_sha256: "d3f9f95c41f85bdbc2ac697d242d6d1e560bd58575cf65155e3843f88c7c8680",
  p32_opportunity_id: null, hypotheses, leading_hypothesis_ids: [],
  next_discriminator_contract_id: null, blocker_reasons: ["Evidence is incomplete."],
  terminal_authority: "p19_only", non_p19_setup_authorized: false,
};
sessionBound.p19_terminal_decision = terminal;
sessionBound.top_swings[0] = {
  ...sessionBound.top_swings[0],
  id: hypotheses[0].effect_id,
  bridge_id: hypotheses[0].bridge_id,
  current_relevance: hypotheses[0].relevance,
  p32_opportunity_id: null,
  knowledge_level: hypotheses[0].level,
  p35_mechanism_ids: [], p20_mechanism_ids: [], p26_component_family_ids: [],
  inspection_tool_ids: [], discriminator_contract_ids: [],
};
const sessionExpectation = { ...expectation, sessionId: "session-1" };
assert.equal(isDialInHypothesisResponse(sessionBound, sessionExpectation), true);

const forgedControl = structuredClone(sessionBound);
forgedControl.engineering_knowledge.hypotheses[0] = {
  ...forgedControl.engineering_knowledge.hypotheses[0],
  level: "p19_testable_control",
  relevance: "supported_candidate",
  p32_opportunity_id: "p32o-forged",
  authority: "exact_p19_projection",
  setup_authorized: true,
  p19_control: {
    control_key: "cross_weight_percent", current_value: "50.0%",
    proposed_value: "52.0%", workflow_id: "workflow-forged",
    workflow_revision: "revision-forged", source_event_ids: ["event-forged"],
    authority: "exact_p19_projection",
  },
};
forgedControl.top_swings[0].knowledge_level = "p19_testable_control";
forgedControl.top_swings[0].current_relevance = "supported_candidate";
forgedControl.top_swings[0].p32_opportunity_id = "p32o-forged";
assert.equal(isDialInHypothesisResponse(forgedControl, sessionExpectation), false);
