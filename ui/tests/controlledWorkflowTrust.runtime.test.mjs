import assert from "node:assert/strict";

import {
  hasValidLearningCaptureMetadata,
  isControlledWorkflowResponse,
} from "../src/utils/controlledWorkflowTrust.ts";

const digest = "a".repeat(64);
const exactExperienceId = `p33x_${digest.slice(0, 24)}`;
const workflow = {
  workflow_id: "workflow-1",
  created_at: "2026-08-14T12:00:00Z",
  updated_at: "2026-08-14T12:05:00Z",
  status: "a_recorded",
  source_run_id: "run-a",
  complaint: "Tight in the center.",
  p32_opportunity_id: null,
  p32_projection_sha256: null,
  engineering_knowledge_projection_sha256: null,
  packet: {
    decision: "test",
    primary_test: {
      control_key: "cross_weight_percent",
      control_label: "Cross Weight",
      current_value: 50,
      proposed_value_raw: 50.5,
      proposed_value: "50.5%",
      exact_change: "50.0% -> 50.5% (adjacent observed tech-passing option)",
      evidence_event_ids: ["event-1"],
      stop_rule: "Stop on an integrity failure.",
      success_metrics: ["Repeatable center response."],
      stages: [
        { stage: "A", setup_instruction: "Record the baseline.", warmup_laps: 0, required_flying_laps: 1 },
        {
          stage: "B",
          setup_instruction: "Change only Cross Weight: 50.0% -> 50.5% (adjacent observed tech-passing option).",
          warmup_laps: 0,
          required_flying_laps: 1,
        },
        { stage: "A2", setup_instruction: "Return to the baseline.", warmup_laps: 0, required_flying_laps: 1 },
      ],
    },
  },
  stage_run_ids: { A: "run-a" },
  stage_eligible_lap_numbers: { A: [3, 4, 5] },
  stage_experiment_contexts: {},
  analysis_version: "controlled-workflow-aba2-v1",
  execution: null,
  reproduction_snapshot: {},
  quality: null,
  controlled_response_receipt: null,
  learning_admitted: null,
  learning_capture_state: "not_applicable",
  learning_capture_experience_id: null,
  learning_capture_experience_sha256: null,
  learning_capture_blocker_reason: null,
};

assert.equal(isControlledWorkflowResponse(workflow), true);
assert.equal(hasValidLearningCaptureMetadata(workflow), true);

const p32Bound = structuredClone(workflow);
p32Bound.p32_opportunity_id = "p32o-current";
p32Bound.p32_projection_sha256 = "b".repeat(64);
p32Bound.engineering_knowledge_projection_sha256 = "c".repeat(64);
assert.equal(isControlledWorkflowResponse(p32Bound), true);

const captured = structuredClone(workflow);
captured.status = "scored";
captured.learning_capture_state = "captured";
captured.learning_capture_experience_id = exactExperienceId;
captured.learning_capture_experience_sha256 = digest;
assert.equal(isControlledWorkflowResponse(captured), true);

const blocked = structuredClone(captured);
blocked.learning_capture_state = "blocked";
blocked.learning_capture_blocker_reason = "Engineering history failed integrity verification; no experience was appended.";
assert.equal(isControlledWorkflowResponse(blocked), true);

const rejectMutation = (label, source, mutate) => {
  const hostile = structuredClone(source);
  mutate(hostile);
  assert.equal(isControlledWorkflowResponse(hostile), false, label);
};

rejectMutation("missing capture state", workflow, (value) => { delete value.learning_capture_state; });
rejectMutation("missing experience hash", captured, (value) => { delete value.learning_capture_experience_sha256; });
rejectMutation("unknown capture state", workflow, (value) => { value.learning_capture_state = "pending"; });
rejectMutation("unknown workflow field", workflow, (value) => { value.setup_authorized = true; });
rejectMutation("partial P32 identity", p32Bound, (value) => { value.p32_projection_sha256 = null; });
rejectMutation("partial captured identity", captured, (value) => { value.learning_capture_experience_sha256 = null; });
rejectMutation("forged experience ID", captured, (value) => { value.learning_capture_experience_id = `p33x_${"b".repeat(24)}`; });
rejectMutation("forged experience hash", captured, (value) => { value.learning_capture_experience_sha256 = "b".repeat(64); });
rejectMutation("captured state with blocker", captured, (value) => { value.learning_capture_blocker_reason = "Capture failed."; });
rejectMutation("blocked state without blocker", blocked, (value) => { value.learning_capture_blocker_reason = null; });
rejectMutation("blocked setup directive", blocked, (value) => { value.learning_capture_blocker_reason = "Set cross weight to 52%."; });
rejectMutation("not-applicable state with identity", captured, (value) => { value.learning_capture_state = "not_applicable"; });
rejectMutation("non-scored workflow claims capture", captured, (value) => { value.status = "a_recorded"; });
