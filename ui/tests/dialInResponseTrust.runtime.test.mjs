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
