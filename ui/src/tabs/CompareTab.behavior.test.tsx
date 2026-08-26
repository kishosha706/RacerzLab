import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CompareResponse } from "../types/compare";
import type { RunListItem } from "../types/telemetry";
import { CompareTab } from "./CompareTab";

const api = vi.hoisted(() => ({
  fetchCompareInsights: vi.fn(),
  fetchComparePreview: vi.fn(),
  runCompare: vi.fn(),
}));

const contexts = vi.hoisted(() => ({
  engineeringCase: null as Record<string, unknown> | null,
  engineeringCaseStatus: "ready",
  focusEvidence: vi.fn(),
  setWorkspace: vi.fn(),
}));

vi.mock("../api/client", () => api);
vi.mock("../components/EngineeringAwarenessPanel", () => ({
  EngineeringAwarenessPanel: () => null,
}));
vi.mock("../store/CompareBasketContext", () => ({
  useCompareBasket: () => ({ basket: { baseline: null, test: null } }),
}));
vi.mock("../store/EngineeringCaseContext", () => ({
  useEngineeringCase: () => ({
    engineeringCase: contexts.engineeringCase,
    status: contexts.engineeringCaseStatus,
  }),
}));
vi.mock("../store/TelemetrySelectionContext", () => ({
  useTelemetrySelection: () => ({
    selection: {
      selectedRunId: "run-1",
      selectedMode: "race",
      selectedZoneId: null,
      selectedZoneLabel: null,
      selectedZoneStartPct: null,
      selectedZoneEndPct: null,
    },
    focusEvidence: contexts.focusEvidence,
    setWorkspace: contexts.setWorkspace,
  }),
}));

const baseline: RunListItem = {
  run_id: "run-1",
  track_name: "Baseline run",
  recording_sha256: "a".repeat(64),
};
const testRun: RunListItem = {
  run_id: "run-2",
  track_name: "Test run",
  recording_sha256: "b".repeat(64),
};

function comparison(): CompareResponse {
  return {
    comparison_id: "comparison-1",
    baseline_run_id: "run-1",
    test_run_id: "run-2",
    baseline_lap: null,
    test_lap: null,
    target_zone_start_pct: 55,
    target_zone_end_pct: 70,
    target_zone: null,
    whole_car_index: null,
    pace_comparison: null,
    platform: null,
    corner_matrix: {},
    tire_comparison: null,
    shock_comparison: null,
    driver_comparison: null,
    powertrain_comparison: null,
    setup_changes: [],
    context_changes: [],
    test_discipline: null,
    observation: null,
    sim_integrity: null,
    warnings: [],
    confidence_score: 0,
    compare_identity: {
      schema_version: "p31.compare-identity.v1",
      baseline: {
        run_id: "run-1",
        source_file_sha256: "c".repeat(64),
        telemetry_cache_sha256: "d".repeat(64),
        compatibility_fingerprint: "baseline",
        build_identity: {},
        setup_id: null,
        setup_sha256: null,
      },
      test: {
        run_id: "run-2",
        source_file_sha256: "e".repeat(64),
        telemetry_cache_sha256: "f".repeat(64),
        compatibility_fingerprint: "test",
        build_identity: {},
        setup_id: null,
        setup_sha256: null,
      },
      baseline_lap: null,
      test_lap: null,
      target_zone_start_pct: 55,
      target_zone_end_pct: 70,
      identity_sha256: "1".repeat(64),
    },
  };
}

const testSetupSha = "2".repeat(64);

function exactComparison(): CompareResponse {
  const result = comparison();
  result.test_lap = 7;
  result.compare_identity.test_lap = 7;
  result.compare_identity.test.setup_id = "setup-test";
  result.compare_identity.test.setup_sha256 = testSetupSha;
  return result;
}

function exactCase({
  runId = "run-2",
  sessionId = "session-1",
  setupId = "setup-test",
  setupSha = testSetupSha,
} = {}) {
  return {
    case_id: "case-test",
    case_revision_sha256: "revision-test",
    case_sha256: "case-sha-test",
    run_id: runId,
    session_id: sessionId,
    setup_id: setupId,
    setup_snapshot_sha256: setupSha,
    semantic_focus: {
      mechanism_ids: ["mechanism-test"],
      response_relation_id: "relation-test",
      component_ids: ["component-test"],
      effect_ids: ["effect-test"],
      control_keys: ["control-test"],
      p19_cause_ids: ["cause-test"],
    },
    quantity_observability: [{ quantity_id: "quantity-test" }],
    active_discriminator_id: "discriminator-test",
    active_workflow_id: null,
  };
}

async function renderComparison(currentRunId: "run-1" | "run-2") {
  render(<CompareTab runs={[baseline, testRun]} currentRunId={currentRunId} sessionId="session-1" />);
  if (currentRunId === "run-2") {
    fireEvent.change(screen.getByLabelText("Baseline Run"), { target: { value: "run-1" } });
  }
  fireEvent.change(screen.getByLabelText("Test Run"), { target: { value: "run-2" } });
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));
  return screen.findByRole("button", { name: "Explain this comparison" });
}

describe("CompareTab interaction boundaries", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    api.fetchComparePreview.mockReset();
    api.fetchCompareInsights.mockReset();
    api.runCompare.mockReset();
    contexts.focusEvidence.mockReset();
    contexts.setWorkspace.mockReset();
    contexts.engineeringCase = null;
    contexts.engineeringCaseStatus = "ready";
    api.fetchComparePreview.mockResolvedValue({
      baseline_laps: [],
      test_laps: [],
      suggested_baseline_lap: null,
      suggested_test_lap: null,
      setup_changes: [],
      context_changes: [],
      warnings: [],
    });
    api.fetchCompareInsights.mockImplementation(() => new Promise(() => {}));
    api.runCompare.mockResolvedValue(comparison());
  });

  it("keeps hook order stable as a live session gains and loses a comparable run", () => {
    const { rerender } = render(<CompareTab runs={[baseline]} currentRunId="run-1" sessionId="session-1" />);
    expect(screen.getByText("Bank one more comparable run.")).toBeTruthy();

    rerender(<CompareTab runs={[baseline, testRun]} currentRunId="run-1" sessionId="session-1" />);
    expect(screen.getByLabelText("Baseline Run")).toBeTruthy();
    expect(screen.getByLabelText("Test Run")).toBeTruthy();
    expect(screen.getByRole("group", { name: "Target Zone" })).toBeTruthy();
    expect(screen.getByRole("spinbutton", { name: "Target zone start percentage" })).toBeTruthy();
    expect(screen.getByRole("spinbutton", { name: "Target zone end percentage" })).toBeTruthy();

    rerender(<CompareTab runs={[baseline]} currentRunId="run-1" sessionId="session-1" />);
    expect(screen.getByText("Bank one more comparable run.")).toBeTruthy();
  });

  it("uses a roving-tabindex tablist with keyboard selection and one active panel", async () => {
    render(<CompareTab runs={[baseline, testRun]} currentRunId="run-1" sessionId="session-1" />);
    fireEvent.change(screen.getByLabelText("Test Run"), { target: { value: "run-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));

    await screen.findByRole("tablist", { name: "Compare subviews" });
    const observation = screen.getByRole("tab", { name: "Observation" });
    const index = screen.getByRole("tab", { name: "Index" });
    const evidence = screen.getByRole("tab", { name: "Evidence" });
    expect(observation.getAttribute("aria-selected")).toBe("true");
    expect(observation.tabIndex).toBe(0);
    expect(index.tabIndex).toBe(-1);

    observation.focus();
    fireEvent.keyDown(observation, { key: "ArrowRight" });
    await waitFor(() => expect(index.getAttribute("aria-selected")).toBe("true"));
    expect(index.tabIndex).toBe(0);
    expect(observation.tabIndex).toBe(-1);
    expect(document.activeElement).toBe(index);

    fireEvent.keyDown(index, { key: "End" });
    await waitFor(() => expect(evidence.getAttribute("aria-selected")).toBe("true"));
    expect(document.activeElement).toBe(evidence);
    const panel = screen.getByRole("tabpanel");
    expect(panel.tabIndex).toBe(0);
    expect(panel.getAttribute("aria-labelledby")).toBe(evidence.id);
  });

  it("fails closed and visibly explains when the active case belongs to the baseline run", async () => {
    contexts.engineeringCase = exactCase({ runId: "run-1" });
    api.runCompare.mockResolvedValue(exactComparison());

    const button = await renderComparison("run-1");

    expect((button as HTMLButtonElement).disabled).toBe(true);
    const explanation = screen.getByText(
      "Explanation unavailable: open the chosen test run so its canonical Engineering Case is active.",
    );
    expect(button.getAttribute("aria-describedby")).toBe(explanation.id);
    fireEvent.click(button);
    expect(contexts.focusEvidence).not.toHaveBeenCalled();
  });

  it("fails closed when the test run case is from another session", async () => {
    contexts.engineeringCase = exactCase({ sessionId: "session-other" });
    api.runCompare.mockResolvedValue(exactComparison());

    const button = await renderComparison("run-2");

    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(
      "Explanation unavailable: the chosen test run is not bound to the active session's Engineering Case.",
    )).toBeTruthy();
  });

  it("fails closed when the exact test setup does not match the active case", async () => {
    contexts.engineeringCase = exactCase({ setupSha: "3".repeat(64) });
    api.runCompare.mockResolvedValue(exactComparison());

    const button = await renderComparison("run-2");

    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(
      "Explanation unavailable: the chosen test setup does not match the active Engineering Case.",
    )).toBeTruthy();
  });

  it("publishes one exact test reality only after run, session, and setup all match", async () => {
    contexts.engineeringCase = exactCase();
    api.runCompare.mockResolvedValue(exactComparison());

    const button = await renderComparison("run-2");

    expect((button as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByText(/^Explanation unavailable:/)).toBeNull();
    fireEvent.click(button);
    expect(contexts.focusEvidence).toHaveBeenCalledTimes(1);
    expect(contexts.focusEvidence).toHaveBeenCalledWith(expect.objectContaining({
      runId: "run-2",
      lapNumber: 7,
      artifactId: null,
      caseId: "case-test",
      caseRevision: "revision-test",
      caseSha256: "case-sha-test",
      sourceRunId: "run-2",
      sourceSetupId: "setup-test",
      compareRole: "test",
    }), "engineer");
  });

  it("binds Review against hypothesis to the exact case workflow and comparison scope", async () => {
    contexts.engineeringCase = {
      ...exactCase(),
      active_workflow_id: "workflow-1",
      active_workflow_revision: "4".repeat(64),
    };
    api.runCompare.mockResolvedValue(exactComparison());

    await renderComparison("run-2");
    const review = screen.getByRole("button", { name: "Review against hypothesis" });
    expect((review as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(review);

    expect(contexts.focusEvidence).toHaveBeenCalledTimes(1);
    expect(contexts.focusEvidence).toHaveBeenCalledWith(expect.objectContaining({
      runId: "run-2",
      lapNumber: 7,
      caseId: "case-test",
      caseSha256: "case-sha-test",
      workflowId: "workflow-1",
      workflowRevision: "4".repeat(64),
      sourceRunId: "run-2",
      sourceSetupId: "setup-test",
    }), "engineer");
  });
});
