import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DialInTab } from "./DialInTab";
import type { RunOverview } from "../types/telemetry";

const mocks = vi.hoisted(() => ({
  caseStatus: "error" as "loading" | "error",
  retry: vi.fn(),
  fetchControlledWorkflows: vi.fn(),
}));

vi.mock("../api/client", () => ({
  attachControlledWorkflowStage: vi.fn(),
  cancelControlledWorkflow: vi.fn(),
  fetchControlledWorkflowReport: vi.fn(),
  fetchControlledWorkflows: mocks.fetchControlledWorkflows,
  scoreControlledWorkflow: vi.fn(),
  submitAtomicDriverIntentWorkflow: vi.fn(),
}));

vi.mock("../store/EngineeringCaseContext", () => ({
  useEngineeringCase: () => ({
    engineeringCase: null,
    status: mocks.caseStatus,
    error: mocks.caseStatus === "error" ? "Case service is unavailable." : null,
    retry: mocks.retry,
    replaceRevision: vi.fn(() => false),
    invalidate: vi.fn(),
  }),
}));

vi.mock("../store/CompareBasketContext", () => ({
  useCompareBasket: () => ({ basket: { baseline: null, test: null } }),
}));

vi.mock("../store/TelemetrySelectionContext", () => ({
  useTelemetrySelection: () => ({
    selection: {
      selectedMode: "race",
      selectedRunId: "run-1",
      selectedWorkspace: "dial_in",
      selectedLapScope: "run",
      selectedLap: null,
      selectedRepresentativeLap: null,
      selectedLapWindowStart: null,
      selectedLapWindowEnd: null,
      selectedZoneStartPct: null,
      selectedZoneEndPct: null,
      selectedZoneLabel: null,
    },
    setWorkspace: vi.fn(),
  }),
}));

const overview = {
  run_id: "run-1",
  setup_snapshot: null,
  session: {
    car_name: "Stock car",
    track_name: "Test track",
    track_display_name: "Test track",
  },
} as unknown as RunOverview;

function renderDialIn() {
  return render(
    <DialInTab
      overview={overview}
      sessionId="session-1"
      workflowScopeRunIds={["run-1"]}
      workflowHandoffKey="session-1"
      workflowOpenIntentId={null}
      currentIntelligenceAuthority={null}
      intelligenceAuthorityStatus="idle"
      intelligenceAuthorityRecovery="Refresh intelligence."
      onWorkflowMutation={vi.fn()}
    />,
  );
}

beforeEach(() => {
  mocks.caseStatus = "error";
  mocks.retry.mockReset();
  mocks.fetchControlledWorkflows.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("DialIn exact-case gating", () => {
  it("disables the complaint field and offers retry when case binding fails", async () => {
    renderDialIn();
    await waitFor(() => expect(mocks.fetchControlledWorkflows).toHaveBeenCalled());

    expect((screen.getByLabelText("Driver complaint") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText(/Current case unavailable/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry current case" }));
    expect(mocks.retry).toHaveBeenCalledTimes(1);
  });

  it("shows binding copy while the provider is loading", () => {
    mocks.caseStatus = "loading";
    renderDialIn();

    expect((screen.getByLabelText("Driver complaint") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText("Binding current case…")).toBeTruthy();
  });
});
