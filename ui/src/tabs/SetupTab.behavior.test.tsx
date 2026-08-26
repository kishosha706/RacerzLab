import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RunOverview } from "../types/telemetry";
import { SetupTab } from "./SetupTab";

const mocks = vi.hoisted(() => ({
  engineeringCase: null as Record<string, unknown> | null,
  focusEvidence: vi.fn(),
  setWorkspace: vi.fn(),
}));

vi.mock("../api/client", () => ({
  fetchSetup: vi.fn(),
}));

vi.mock("../components/EngineeringAwarenessPanel", () => ({
  EngineeringAwarenessPanel: () => null,
}));

vi.mock("../components/VehicleSystemsPanel", () => ({
  VehicleSystemsPanel: () => null,
}));

vi.mock("../store/CompareBasketContext", () => ({
  useCompareBasket: () => ({ basket: { baseline: null, test: null } }),
}));

vi.mock("../store/EngineeringCaseContext", () => ({
  useEngineeringCase: () => ({ engineeringCase: mocks.engineeringCase }),
}));

vi.mock("../store/TelemetrySelectionContext", () => ({
  useTelemetrySelection: () => ({
    selection: {
      selectedMode: "race",
      selectedEventId: null,
      selectedControlKeys: [],
    },
    focusEvidence: mocks.focusEvidence,
    setWorkspace: mocks.setWorkspace,
  }),
}));

function overview(withSetup = true): RunOverview {
  return {
    run_id: "run-1",
    session: {
      car_name: "Test Car",
      track_name: "test_track",
      track_display_name: "Test Track",
    },
    events: [],
    setup_snapshot: withSetup ? {
      run_id: "run-1",
      setup_id: "setup-1",
      setup_name: "Exact Setup",
      steering_ratio: "12:1",
      front_brake_bias_percent: 51,
      extra_values: {},
    } : null,
  } as unknown as RunOverview;
}

function exactCase(setupId = "setup-1") {
  return {
    case_id: "case-1",
    case_revision_sha256: "revision-1",
    case_sha256: "case-sha-1",
    run_id: "run-1",
    session_id: "session-1",
    setup_id: setupId,
    semantic_focus: {
      mechanism_ids: ["mechanism-1"],
      response_relation_id: "relation-1",
      component_ids: ["component-1"],
      p19_cause_ids: ["cause-1"],
    },
    effect_readiness: [{
      effect_id: "steering_ratio",
      exact_control_keys: ["steering_ratio"],
      authority: "p19_authorized",
    }],
    quantity_observability: [{ quantity_id: "steering_angle" }],
    active_discriminator_id: "discriminator-1",
  };
}

describe("SetupTab exact-case control mapping", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    mocks.engineeringCase = exactCase();
    mocks.focusEvidence.mockReset();
    mocks.setWorkspace.mockReset();
  });

  it("keeps hook order stable when a setup snapshot becomes available", () => {
    const { rerender } = render(<SetupTab overview={overview(false)} sessionId="session-1" />);
    expect(screen.getByText("Setup snapshot unavailable.")).toBeTruthy();

    rerender(<SetupTab overview={overview()} sessionId="session-1" />);
    expect(screen.getAllByText("Exact Setup").length).toBeGreaterThan(0);
  });

  it("only makes controls named by exact case readiness interactive", () => {
    render(<SetupTab overview={overview()} sessionId="session-1" />);

    expect(screen.getByText("Evidence route:")).toBeTruthy();
    expect(screen.getByText("Local handoff")).toBeTruthy();
    expect(screen.queryByText("What next:")).toBeNull();
    expect(screen.queryByText("Next")).toBeNull();
    const exactControl = screen.getByRole("button", { name: "Focus setup control Steering Ratio" });
    expect(screen.queryByRole("button", { name: "Focus setup control Front Brake Bias" })).toBeNull();

    fireEvent.click(exactControl);
    expect(mocks.focusEvidence).toHaveBeenCalledTimes(1);
    expect(mocks.focusEvidence).toHaveBeenCalledWith(expect.objectContaining({
      caseId: "case-1",
      caseRevision: "revision-1",
      caseSha256: "case-sha-1",
      effectIds: ["steering_ratio"],
      controlKeys: ["steering_ratio"],
      sourceRunId: "run-1",
      sourceSetupId: "setup-1",
      trustTier: "p19_authorized",
    }), "setup_impact");
  });

  it("withholds every setup handoff when the case setup identity differs", () => {
    mocks.engineeringCase = exactCase("setup-other");
    render(<SetupTab overview={overview()} sessionId="session-1" />);

    expect(screen.queryByRole("button", { name: /^Focus setup control/ })).toBeNull();
    expect(mocks.focusEvidence).not.toHaveBeenCalled();
  });
});
