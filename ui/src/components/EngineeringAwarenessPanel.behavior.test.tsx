import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EngineeringAwarenessProjection } from "../types/engineeringAwareness";
import { EngineeringAwarenessPanel } from "./EngineeringAwarenessPanel";

const api = vi.hoisted(() => ({ fetchEngineeringAwareness: vi.fn() }));
const state = vi.hoisted(() => ({
  engineeringCase: null as any,
  focusEvidence: vi.fn(),
}));

vi.mock("../api/client", () => ({
  fetchEngineeringAwareness: api.fetchEngineeringAwareness,
}));

vi.mock("../store/EngineeringCaseContext", () => ({
  useEngineeringCase: () => ({ engineeringCase: state.engineeringCase }),
}));

vi.mock("../store/TelemetrySelectionContext", () => ({
  useTelemetrySelection: () => ({
    selection: { selectedMode: "race" },
    focusEvidence: state.focusEvidence,
  }),
}));

const SNAPSHOT_A = "a".repeat(64);
const SNAPSHOT_B = "b".repeat(64);
const SNAPSHOT_FORK = "f".repeat(64);
const STATE_A = "1".repeat(64);
const STATE_B = "2".repeat(64);

function engineeringCase(reasoningSnapshotId: string, stateRevision: string) {
  return {
    p19_reasoning_snapshot_sha256: reasoningSnapshotId,
    p20_state_revision: stateRevision,
  };
}

function projection(
  label: string,
  reasoningSnapshotId: string,
  stateRevision: string,
): EngineeringAwarenessProjection {
  const trustAxis = {
    state: "trusted" as const,
    basis: "Exact current-case evidence.",
    blockers: [],
    source_artifact_ids: ["artifact-1"],
  };
  return {
    schema_version: "p20.awareness.v2",
    run_id: "run-1",
    session_id: "session-1",
    reasoning_snapshot_id: reasoningSnapshotId,
    state_revision: stateRevision,
    request_identity: {
      run_id: "run-1",
      session_id: "session-1",
      reasoning_snapshot_id: reasoningSnapshotId,
      state_revision: stateRevision,
    },
    generated_at: "2026-08-26T00:00:00Z",
    cache_state: "cold",
    build_duration_ms: 1,
    profile_hash: null,
    authority: "observation_only",
    trust_budget: {
      data_health: trustAxis,
      alignment_quality: trustAxis,
      context_comparability: trustAxis,
      driver_repeatability: trustAxis,
      mechanism_separation: trustAxis,
      controlled_response_validity: trustAxis,
      policy_countereffect_risk: trustAxis,
      history_completeness: trustAxis,
    },
    primary_state: {
      state_id: `state-${label}`,
      label,
      mechanism: "corner_rotation",
      lap_number: 4,
      phase: "center",
      lap_pct_start: 40,
      lap_pct_end: 50,
      lap_pct_peak: 45,
      evidence_state: "calculated",
      source_artifact_ids: ["artifact-1"],
      source_channels: ["YawRate"],
      authority: "observation_only",
    },
    subsystem_states: [],
    episodes: [],
    state_drift_status: "unavailable",
    state_drift_findings: [],
    state_drift_blocker_reasons: ["No qualified stint."],
    expected_vs_observed: [],
    control_mutations: [],
    knowledge_debt: ["More evidence is required."],
    artifact_versions: [],
    raw_trace_included: false,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolver) => { resolve = resolver; });
  return { promise, resolve };
}

describe("EngineeringAwarenessPanel", () => {
  beforeEach(() => {
    api.fetchEngineeringAwareness.mockReset();
    state.focusEvidence.mockReset();
    state.engineeringCase = engineeringCase(SNAPSHOT_A, STATE_A);
  });

  afterEach(() => cleanup());

  it("never renders a delayed projection from the prior Engineering Case", async () => {
    const stale = deferred<EngineeringAwarenessProjection>();
    api.fetchEngineeringAwareness.mockReturnValueOnce(stale.promise);
    const { rerender } = render(
      <EngineeringAwarenessPanel runId="run-1" sessionId="session-1" surface="overview" />,
    );
    await waitFor(() => expect(api.fetchEngineeringAwareness).toHaveBeenCalledTimes(1));

    state.engineeringCase = engineeringCase(SNAPSHOT_B, STATE_B);
    api.fetchEngineeringAwareness.mockResolvedValueOnce(
      projection("Current mechanism", SNAPSHOT_B, STATE_B),
    );
    rerender(<EngineeringAwarenessPanel runId="run-1" sessionId="session-1" surface="overview" />);
    await waitFor(() => expect(screen.getByText("Current mechanism")).toBeTruthy());

    await act(async () => {
      stale.resolve(projection("Stale mechanism", SNAPSHOT_A, STATE_A));
      await stale.promise;
    });

    expect(screen.queryByText("Stale mechanism")).toBeNull();
    expect(screen.getByText("Current mechanism")).toBeTruthy();
  });

  it.each([
    ["top-level response identity", (value: EngineeringAwarenessProjection) => {
      value.reasoning_snapshot_id = SNAPSHOT_FORK;
    }],
    ["request identity", (value: EngineeringAwarenessProjection) => {
      value.request_identity.reasoning_snapshot_id = SNAPSHOT_FORK;
    }],
  ])("fails closed for a forked P19 snapshot in the %s", async (_label, fork) => {
    const response = projection("Forked mechanism", SNAPSHOT_A, STATE_A);
    fork(response);
    api.fetchEngineeringAwareness.mockResolvedValueOnce(response);

    render(<EngineeringAwarenessPanel runId="run-1" sessionId="session-1" surface="overview" />);

    await waitFor(() => expect(screen.getByText("Whole-car awareness unavailable")).toBeTruthy());
    expect(screen.queryByText("Forked mechanism")).toBeNull();
  });
});
