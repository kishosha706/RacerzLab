import { describe, expect, it } from "vitest";
import { isIntelligenceShellProjection } from "./intelligenceResponseTrust";

const expectation = { runId: "run-alpha", sessionId: "session-alpha" };

describe("intelligence shell projection trust", () => {
  it("accepts exact unbuilt state without report truth", () => {
    expect(isIntelligenceShellProjection({
      schema_version: "p19.intelligence-shell.v1",
      run_id: "run-alpha",
      session_id: "session-alpha",
      status: "not_built",
      reasoning_snapshot_sha256: null,
      setup_id: null,
      setup_snapshot_sha256: null,
      next_trustworthy_move: null,
      recovery: "Open Smart Engineer to assemble the exact-scope briefing.",
    }, expectation)).toBe(true);
  });

  it("rejects foreign scope and setup-authorized shell moves", () => {
    const base = {
      schema_version: "p19.intelligence-shell.v1",
      run_id: "run-alpha",
      session_id: "session-alpha",
      status: "ready",
      reasoning_snapshot_sha256: "a".repeat(64),
      setup_id: null,
      setup_snapshot_sha256: null,
      recovery: "Open the supporting view.",
    };
    expect(isIntelligenceShellProjection({ ...base, run_id: "foreign", next_trustworthy_move: null }, expectation)).toBe(false);
    expect(isIntelligenceShellProjection({
      ...base,
      next_trustworthy_move: {
        move_id: "test:workflow",
        kind: "controlled_test",
        title: "Controlled test",
        instruction: "Open Dial-In.",
        reason: "P19 authorized one test.",
        workspace: "dial_in",
        authority: "setup_authorized",
        run_id: "run-alpha",
        workflow_id: "workflow-alpha",
        workflow_updated_at: "2026-08-18T12:00:00Z",
        control_key: "front_arb",
        lap_number: null,
        window_start_lap: null,
        window_end_lap: null,
        lap_pct_start: null,
        lap_pct_end: null,
        source_event_ids: ["event-alpha"],
        blocker_reasons: [],
      },
    }, expectation)).toBe(false);
  });
});
