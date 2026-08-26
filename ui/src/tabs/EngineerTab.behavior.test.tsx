import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CanonicalEngineeringCase, EngineeringCaseRevision } from "../types/engineeringCase";
import type { IntelligenceQueryResponse, RunIntelligenceReport } from "../types/intelligence";
import { EngineerTab } from "./EngineerTab";

const RUN_ID = "run-1";
const SESSION_ID = "session-1";
const CASE_ID = `p3543case_${"a".repeat(24)}`;
const SETUP_ID = "setup-1";
const SETUP_SHA = "9".repeat(64);

const mocks = vi.hoisted(() => ({
  caseContext: null as any,
  fetchRunIntelligence: vi.fn(),
  queryRunIntelligence: vi.fn(),
  isRunIntelligenceResponse: vi.fn(),
  isIntelligenceQueryResponseBoundToReport: vi.fn(),
  retryCase: vi.fn(),
  focusEvidence: vi.fn(),
  setWorkspace: vi.fn(),
  selection: { selectedMode: "race" } as any,
}));

vi.mock("../api/client", () => ({
  fetchRunIntelligence: mocks.fetchRunIntelligence,
  queryRunIntelligence: mocks.queryRunIntelligence,
  fetchLearningReadiness: vi.fn(),
  freezeProspectivePrediction: vi.fn(),
  startEvidenceCampaign: vi.fn(),
}));

vi.mock("../store/EngineeringCaseContext", () => ({
  useEngineeringCase: () => mocks.caseContext,
}));

vi.mock("../store/TelemetrySelectionContext", () => ({
  useTelemetrySelection: () => ({
    selection: mocks.selection,
    focusEvidence: mocks.focusEvidence,
    setWorkspace: mocks.setWorkspace,
  }),
}));

vi.mock("../utils/intelligenceResponseTrust", () => ({
  isRunIntelligenceResponse: mocks.isRunIntelligenceResponse,
  isIntelligenceQueryResponseBoundToReport: mocks.isIntelligenceQueryResponseBoundToReport,
}));

vi.mock("../utils/currentIntelligenceAuthority", () => ({
  deriveCurrentReportSetupAuthority: () => null,
}));

vi.mock("../components/EngineeringAwarenessPanel", () => ({
  EngineeringAwarenessPanel: () => null,
}));

vi.mock("../components/VehicleSystemsPanel", () => ({
  VehicleSystemsPanel: () => null,
}));

vi.mock("../components/CrewChiefCommandDeck", () => ({
  CrewChiefCommandDeck: () => null,
}));

vi.mock("../components/SmartIntelligenceCards", () => ({
  exactMindChangeCriteria: () => [],
  MindChangeCriteriaCard: () => null,
  SmartIntelligenceCards: () => null,
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function engineeringCase(revisionNumber: number, revisionSha: string, caseSha: string, snapshotSha: string) {
  const engineeringCase = {
    case_id: CASE_ID,
    case_sha256: caseSha,
    case_revision_sha256: revisionSha,
    run_id: RUN_ID,
    session_id: SESSION_ID,
    setup_id: SETUP_ID,
    setup_snapshot_sha256: SETUP_SHA,
    p19_reasoning_snapshot_sha256: snapshotSha,
  } as CanonicalEngineeringCase;
  const revision = {
    case_id: CASE_ID,
    case_revision: revisionNumber,
    case_sha256: caseSha,
    case: engineeringCase,
  } as EngineeringCaseRevision;
  return { engineeringCase, revision };
}

function readyCase(revisionNumber: number, revisionSha: string, caseSha: string, snapshotSha: string) {
  const bound = engineeringCase(revisionNumber, revisionSha, caseSha, snapshotSha);
  return {
    ...bound,
    status: "ready",
    error: null,
    retry: mocks.retryCase,
  };
}

function report(snapshotSha: string, issue: string): RunIntelligenceReport {
  return {
    schema_version: "p19.run-intelligence.v1",
    run_id: RUN_ID,
    session_id: SESSION_ID,
    reasoning_snapshot_sha256: snapshotSha,
    setup_id: SETUP_ID,
    setup_snapshot_sha256: SETUP_SHA,
    status: "ready",
    decision_status: "blocked",
    briefing: {
      issue,
      confidence_label: "Guarded",
      success_check: "Evidence remains bound to this snapshot.",
      blocker_reasons: [],
      action: {
        kind: "no_call",
        title: "Evidence only",
        instruction: `${issue} evidence`,
        setup_authorized: false,
        evidence_state: "unavailable",
        source_event_ids: [],
        blocker_reasons: [],
      },
    },
    competing_causes: [],
    mind_change_criteria: [],
    context_matches: [],
    calibration: {
      status: "insufficient_history",
      summary: "No calibration record.",
      caveat: "Evidence only.",
    },
    narrative: [],
    suggested_questions: ["Where is the evidence?"],
    blocker_reasons: [],
  } as RunIntelligenceReport;
}

function queryResponse(
  caseSha: string,
  snapshotSha: string,
  question: string,
  answer: string,
): IntelligenceQueryResponse {
  return {
    schema_version: "p3544.engineering-case-query.v1",
    run_id: RUN_ID,
    session_id: SESSION_ID,
    case_id: CASE_ID,
    case_sha256: caseSha,
    reasoning_snapshot_sha256: snapshotSha,
    setup_id: SETUP_ID,
    setup_snapshot_sha256: SETUP_SHA,
    scope_run_ids: [RUN_ID],
    selected_lap: null,
    status: "ready",
    question,
    headline: "Grounded result",
    answer,
    interpreted_lap_number: null,
    interpreted_window_start_lap: null,
    interpreted_window_end_lap: null,
    interpreted_window_representative_lap: null,
    interpreted_phase: null,
    interpreted_control_key: null,
    interpreted_component_id: null,
    interpreted_track_region_id: null,
    interpreted_track_region_label: null,
    clarification_required: false,
    action_authorized: false,
    action_source_event_ids: [],
    source_artifact_ids: [],
    authority_ceiling: "evidence_only",
    evidence_state: "unavailable",
    citations: [],
    suggested_navigation: [],
    mind_change_criteria: [],
    blocker_reasons: [],
    follow_up_questions: [],
  };
}

const props = {
  runId: RUN_ID,
  sessionId: SESSION_ID,
  selectedLap: null,
  selectedLapScope: "run" as const,
  selectedLapWindowStart: null,
  selectedLapWindowEnd: null,
  selectedRepresentativeLap: null,
  sessionRunScopeKey: JSON.stringify([RUN_ID]),
  workflowId: null,
  workflowUpdatedAt: null,
  onNavigateCitation: vi.fn(),
  onNavigateCrewEvidence: vi.fn(),
};

describe("EngineerTab exact Engineering Case binding", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.selection = { selectedMode: "race" };
    mocks.caseContext = readyCase(1, "1".repeat(64), "2".repeat(64), "3".repeat(64));
    mocks.isRunIntelligenceResponse.mockImplementation((value: RunIntelligenceReport, expectation: any) => (
      value.run_id === expectation.runId
      && value.session_id === expectation.sessionId
      && value.reasoning_snapshot_sha256 === expectation.reasoningSnapshotSha256
    ));
    mocks.isIntelligenceQueryResponseBoundToReport.mockImplementation((value: IntelligenceQueryResponse, boundReport: RunIntelligenceReport) => (
      value.run_id === boundReport.run_id
      && value.session_id === boundReport.session_id
      && value.reasoning_snapshot_sha256 === boundReport.reasoning_snapshot_sha256
      && value.setup_id === boundReport.setup_id
      && value.setup_snapshot_sha256 === boundReport.setup_snapshot_sha256
    ));
  });

  it("shows a semantic handoff only when it belongs to the exact active case", async () => {
    mocks.selection = {
      selectedMode: "race",
      selectedRunId: RUN_ID,
      selectedLap: 7,
      selectedCaseId: CASE_ID,
      selectedCaseRevision: "1".repeat(64),
      selectedCaseSha256: "2".repeat(64),
      selectedSourceRunId: RUN_ID,
      selectedSourceSetupId: SETUP_ID,
      selectedZoneLabel: "Compare baseline → test",
      selectedSystem: "compare",
      selectedWorkflowId: null,
      selectedWorkflowRevision: null,
    };
    mocks.fetchRunIntelligence.mockResolvedValue(report("3".repeat(64), "CURRENT REPORT"));

    render(<EngineerTab {...props} />);

    const focus = await screen.findByRole("region", { name: "Focused Engineering Case context" });
    expect(focus.textContent).toContain("Compare baseline → test");
    expect(focus.textContent).toContain("Lap 7");
    expect(focus.getAttribute("data-case-sha256")).toBe("2".repeat(64));
  });

  it("rejects a delayed report after the active case revision changes", async () => {
    const stale = deferred<RunIntelligenceReport>();
    const current = deferred<RunIntelligenceReport>();
    mocks.fetchRunIntelligence
      .mockImplementationOnce(() => stale.promise)
      .mockImplementationOnce(() => current.promise);
    const { rerender } = render(<EngineerTab {...props} />);
    await waitFor(() => expect(mocks.fetchRunIntelligence).toHaveBeenCalledTimes(1));

    mocks.caseContext = readyCase(2, "4".repeat(64), "5".repeat(64), "6".repeat(64));
    rerender(<EngineerTab {...props} />);
    await waitFor(() => expect(mocks.fetchRunIntelligence).toHaveBeenCalledTimes(2));

    await act(async () => { stale.resolve(report("3".repeat(64), "STALE REPORT")); });
    expect(screen.queryByText("STALE REPORT evidence")).toBeNull();

    const currentReport = report("6".repeat(64), "CURRENT REPORT");
    await act(async () => { current.resolve(currentReport); });
    await waitFor(() => expect(screen.getByText("Engineering evidence status")).toBeTruthy());
    const workspace = screen.getByText("Engineering evidence status").closest(".smart-engineer-workspace");
    expect(workspace?.getAttribute("data-case-revision-sha256")).toBe("4".repeat(64));
    expect(workspace?.getAttribute("data-p19-reasoning-snapshot-sha256")).toBe("6".repeat(64));
    expect(mocks.isRunIntelligenceResponse).toHaveBeenLastCalledWith(
      currentReport,
      expect.objectContaining({ reasoningSnapshotSha256: "6".repeat(64) }),
    );
  });

  it("fails closed when the current report does not match the case P19 snapshot", async () => {
    mocks.fetchRunIntelligence.mockResolvedValueOnce(report("7".repeat(64), "WRONG SNAPSHOT"));
    render(<EngineerTab {...props} />);

    await waitFor(() => expect(screen.getByText("No stale briefing was kept")).toBeTruthy());
    expect(screen.queryByText("Engineering evidence status")).toBeNull();
    expect(screen.queryByText("WRONG SNAPSHOT evidence")).toBeNull();
    expect(mocks.isRunIntelligenceResponse).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ reasoningSnapshotSha256: "3".repeat(64) }),
    );
  });

  it("clears a delayed question and prevents its old case promise from committing", async () => {
    mocks.fetchRunIntelligence
      .mockResolvedValueOnce(report("3".repeat(64), "CASE A"))
      .mockResolvedValueOnce(report("6".repeat(64), "CASE B"));
    const delayedAnswer = deferred<IntelligenceQueryResponse>();
    mocks.queryRunIntelligence.mockImplementationOnce(() => delayedAnswer.promise);
    const { rerender } = render(<EngineerTab {...props} />);
    await waitFor(() => expect(screen.getByText("Engineering evidence status")).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: /Supporting evidence and tools/i }));
    const input = screen.getByLabelText(/Question about the selected run/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Where is the evidence?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(mocks.queryRunIntelligence).toHaveBeenCalledTimes(1));

    mocks.caseContext = readyCase(2, "4".repeat(64), "5".repeat(64), "6".repeat(64));
    rerender(<EngineerTab {...props} />);
    await waitFor(() => expect(mocks.fetchRunIntelligence).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByText("Engineering evidence status")).toBeTruthy());

    await act(async () => {
      delayedAnswer.resolve(queryResponse(
        "2".repeat(64),
        "3".repeat(64),
        "Where is the evidence?",
        "STALE QUERY ANSWER",
      ));
    });
    expect(screen.queryByText("STALE QUERY ANSWER")).toBeNull();
    expect(mocks.isIntelligenceQueryResponseBoundToReport).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /Supporting evidence and tools/i }));
    expect((screen.getByLabelText(/Question about the selected run/i) as HTMLInputElement).value).toBe("");
  });

  it("locks Race questions and case-dependent controls when the provider errors", () => {
    mocks.caseContext = {
      engineeringCase: null,
      revision: null,
      status: "error",
      error: "Provider failed with technical detail.",
      retry: mocks.retryCase,
    };
    const { rerender } = render(<EngineerTab {...props} />);

    expect(screen.getByText("Current Engineering Case unavailable")).toBeTruthy();
    expect(screen.getByText("Retry the current case before using the briefing or questions.")).toBeTruthy();
    expect(screen.queryByText("Provider failed with technical detail.")).toBeNull();
    expect(screen.getByLabelText("Question about the current case").hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Retry current case" }));
    expect(mocks.retryCase).toHaveBeenCalledTimes(1);
    expect(mocks.fetchRunIntelligence).not.toHaveBeenCalled();
    expect(mocks.queryRunIntelligence).not.toHaveBeenCalled();

    mocks.caseContext = {
      engineeringCase: null,
      revision: null,
      status: "loading",
      error: null,
      retry: mocks.retryCase,
    };
    rerender(<EngineerTab {...props} />);
    expect(screen.getByText("Binding current case…")).toBeTruthy();
    expect(screen.getByLabelText("Question about the current case").hasAttribute("disabled")).toBe(true);
  });
});
