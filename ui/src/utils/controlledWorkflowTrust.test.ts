import { describe, expect, it } from "vitest";

import type { ControlledWorkflow } from "../types/telemetry";
import { currentIntelligenceAuthorityMatchesWorkflow } from "./currentIntelligenceAuthority";
import { isControlledWorkflowResponse } from "./controlledWorkflowTrust";

function authorityWorkflow(): ControlledWorkflow {
  return {
    workflow_id: "workflow-1",
    created_at: "2026-08-14T12:00:00Z",
    updated_at: "2026-08-14T12:05:00Z",
    status: "a_recorded",
    source_run_id: "run-a",
    complaint: "Tight in the center.",
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
    } as unknown as ControlledWorkflow["packet"],
    p32_opportunity_id: null,
    p32_projection_sha256: null,
    engineering_knowledge_projection_sha256: null,
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
}

describe("controlled workflow capture containment", () => {
  it("cannot acquire or alter P19 authority semantics", () => {
    const workflow = authorityWorkflow();
    const authority = {
      sourceRunId: "run-a",
      sessionId: "session-1",
      workflowId: "workflow-1",
      workflowUpdatedAt: "2026-08-14T12:05:00Z",
      stage: "B" as const,
      controlKey: "cross_weight_percent",
      currentValue: "50.0%",
      proposedValue: "50.5%",
      instruction: "50.0% -> 50.5% (adjacent observed tech-passing option)",
      sourceEventIds: ["event-1"],
    };
    expect(isControlledWorkflowResponse(workflow)).toBe(true);
    expect(currentIntelligenceAuthorityMatchesWorkflow(authority, workflow)).toBe(true);

    const forgedCapture: ControlledWorkflow = {
      ...workflow,
      learning_capture_state: "captured",
      learning_capture_experience_id: `p33x_${"a".repeat(24)}`,
      learning_capture_experience_sha256: "a".repeat(64),
    };
    expect(currentIntelligenceAuthorityMatchesWorkflow(authority, forgedCapture)).toBe(true);
    expect(isControlledWorkflowResponse(forgedCapture)).toBe(false);
  });
});
