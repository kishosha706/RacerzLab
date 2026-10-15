import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DialInTab } from "./DialInTab";
import type { RunOverview } from "../types/telemetry";

const mocks = vi.hoisted(() => ({
  caseStatus: "error" as "loading" | "error" | "ready",
  engineeringCase: null as unknown,
  retry: vi.fn(),
  fetchControlledWorkflows: vi.fn(),
  fetchHandlingKnowledge: vi.fn(),
}));

vi.mock("../api/client", () => ({
  attachControlledWorkflowStage: vi.fn(),
  cancelControlledWorkflow: vi.fn(),
  fetchControlledWorkflowReport: vi.fn(),
  fetchControlledWorkflows: mocks.fetchControlledWorkflows,
  fetchHandlingKnowledge: mocks.fetchHandlingKnowledge,
  scoreControlledWorkflow: vi.fn(),
  submitAtomicDriverIntentWorkflow: vi.fn(),
}));

vi.mock("../store/EngineeringCaseContext", () => ({
  useEngineeringCase: () => ({
    engineeringCase: mocks.engineeringCase,
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
    focusEvidence: vi.fn(),
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
  mocks.engineeringCase = null;
  mocks.retry.mockReset();
  mocks.fetchControlledWorkflows.mockResolvedValue([]);
  mocks.fetchHandlingKnowledge.mockReset();
  try {
    window.sessionStorage.clear();
  } catch {
    // Storage unavailable in this environment; handoff tests will not run.
  }
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

const CASE_ID = "p3543case_" + "f".repeat(24);
const REVISION = "a".repeat(64);
const CASE_SHA = "b".repeat(64);
const ASSESSMENT_ID = "hba_" + "1".repeat(24);

function knowledgeFixture(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "p356.handling-knowledge.v1",
    projection_sha256: "c".repeat(64),
    run_id: "run-1",
    session_id: "session-1",
    setup_id: "setup-1",
    case_id: CASE_ID,
    case_revision_sha256: REVISION,
    case_sha256: CASE_SHA,
    assessment_id: ASSESSMENT_ID,
    phase: "center",
    classification: "kinematic_residual_observation",
    canonical_symptom_id: null,
    corroborated: false,
    observed_behavior: "Kinematic residual observation without steering-response corroboration.",
    evidence_qualification: "Single-strand kinematic diagnostic; no canonical symptom is attached.",
    mechanisms: [],
    relevant_knowledge: [],
    countereffects: [],
    evidence_status: [],
    next_evidence_channels: ["steering_deg", "yaw_rate"],
    next_action: {
      kind: "measure",
      instruction: "Review matched steering and yaw traces across the qualified lap group.",
    },
    authority: "derived_observation_view",
    setup_authorized: false,
    p19_authority_unchanged: true,
    ...overrides,
  };
}

function caseFixture(overrides: Record<string, unknown> = {}) {
  return {
    case_id: CASE_ID,
    case_revision_sha256: REVISION,
    case_sha256: CASE_SHA,
    run_id: "run-1",
    session_id: "session-1",
    setup_id: "setup-1",
    handling_investigation: {
      assessment_refs: [{
        assessment_id: ASSESSMENT_ID,
        run_id: "run-1",
        phase: "center",
        classification: "kinematic_residual_observation",
        canonical_symptom_id: null,
        corroborated: false,
        lap_numbers: [1, 2, 3, 4, 5, 6],
      }],
      findings: [],
    },
    ...overrides,
  };
}

function writeHandoff(overrides: Record<string, unknown> = {}) {
  const handoff = {
    runId: "run-1",
    sessionId: "session-1",
    assessmentId: ASSESSMENT_ID,
    phase: "center",
    canonicalSymptomId: null,
    caseId: CASE_ID,
    caseRevision: REVISION,
    caseSha256: CASE_SHA,
    ...overrides,
  };
  window.sessionStorage.setItem(
    "racerzlab:handling-observation-handoff:session-1",
    JSON.stringify(handoff),
  );
  return handoff;
}

describe("DialIn telemetry-observed handling handoff", () => {
  it("shows telemetry-observed knowledge for a valid exact-case handoff without touching the complaint", async () => {
    mocks.caseStatus = "ready";
    mocks.engineeringCase = caseFixture();
    mocks.fetchHandlingKnowledge.mockResolvedValue(knowledgeFixture());
    writeHandoff();
    renderDialIn();
    await waitFor(() => expect(mocks.fetchControlledWorkflows).toHaveBeenCalled());

    expect(await screen.findByText(/Telemetry-observed handling behavior/)).toBeTruthy();
    expect(screen.getByText(/Kinematic residual observation without steering-response corroboration./)).toBeTruthy();
    expect(screen.getByText(/None — no tight\/loose claim/)).toBeTruthy();
    expect((screen.getByLabelText("Driver complaint") as HTMLInputElement).value).toBe("");
    expect(screen.getByText(/did not fill the complaint box/)).toBeTruthy();
  });

  it("discards a stale case-revision handoff", async () => {
    mocks.caseStatus = "ready";
    mocks.engineeringCase = caseFixture({ case_revision_sha256: "d".repeat(64) });
    mocks.fetchHandlingKnowledge.mockResolvedValue(knowledgeFixture());
    writeHandoff();
    renderDialIn();
    await waitFor(() => expect(mocks.fetchControlledWorkflows).toHaveBeenCalled());

    expect(screen.queryByText(/Telemetry-observed handling behavior/)).toBeNull();
    expect(mocks.fetchHandlingKnowledge).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem("racerzlab:handling-observation-handoff:session-1")).toBeNull();
  });

  it("discards a foreign-case handoff", async () => {
    mocks.caseStatus = "ready";
    mocks.engineeringCase = caseFixture({ case_id: "p3543case_" + "e".repeat(24) });
    mocks.fetchHandlingKnowledge.mockResolvedValue(knowledgeFixture());
    writeHandoff();
    renderDialIn();
    await waitFor(() => expect(mocks.fetchControlledWorkflows).toHaveBeenCalled());

    expect(screen.queryByText(/Telemetry-observed handling behavior/)).toBeNull();
    expect(mocks.fetchHandlingKnowledge).not.toHaveBeenCalled();
  });

  it("discards a handoff whose assessment or phase is not in the exact case", async () => {
    mocks.caseStatus = "ready";
    mocks.engineeringCase = caseFixture();
    mocks.fetchHandlingKnowledge.mockResolvedValue(knowledgeFixture());
    writeHandoff({ phase: "exit" });
    renderDialIn();
    await waitFor(() => expect(mocks.fetchControlledWorkflows).toHaveBeenCalled());

    expect(screen.queryByText(/Telemetry-observed handling behavior/)).toBeNull();
    expect(mocks.fetchHandlingKnowledge).not.toHaveBeenCalled();
  });

  it("rejects a symptom mismatch between handoff and the exact case", async () => {
    mocks.caseStatus = "ready";
    mocks.engineeringCase = caseFixture();
    mocks.fetchHandlingKnowledge.mockResolvedValue(knowledgeFixture());
    writeHandoff({ canonicalSymptomId: "tight_center" });
    renderDialIn();
    await waitFor(() => expect(mocks.fetchControlledWorkflows).toHaveBeenCalled());

    expect(screen.queryByText(/Telemetry-observed handling behavior/)).toBeNull();
    expect(mocks.fetchHandlingKnowledge).not.toHaveBeenCalled();
  });

  it("preserves a legitimately corroborated canonical symptom in the card", async () => {
    mocks.caseStatus = "ready";
    mocks.engineeringCase = caseFixture({
      handling_investigation: {
        assessment_refs: [{
          assessment_id: ASSESSMENT_ID,
          run_id: "run-1",
          phase: "center",
          classification: "rotation_response_deficit",
          canonical_symptom_id: "tight_center",
          corroborated: true,
          lap_numbers: [1, 2, 3, 4, 5, 6],
        }],
        findings: [],
      },
    });
    mocks.fetchHandlingKnowledge.mockResolvedValue(knowledgeFixture({
      canonical_symptom_id: "tight_center",
      corroborated: true,
      classification: "rotation_response_deficit",
      observed_behavior: "Telemetry corroborates a center rotation-response signature.",
    }));
    writeHandoff({ canonicalSymptomId: "tight_center" });
    renderDialIn();
    await waitFor(() => expect(mocks.fetchControlledWorkflows).toHaveBeenCalled());

    expect(await screen.findByText(/Telemetry-observed handling behavior/)).toBeTruthy();
    expect(screen.getByText(/Tight Center/)).toBeTruthy();
    expect((screen.getByLabelText("Driver complaint") as HTMLInputElement).value).toBe("");
  });
});
