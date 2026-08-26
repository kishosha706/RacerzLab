import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EngineeringMissionStrip } from "./EngineeringMissionStrip";

const state = vi.hoisted(() => ({
  focusEvidence: vi.fn(),
  engineeringCase: null as any,
  selection: {} as any,
}));

vi.mock("../store/EngineeringCaseContext", () => ({
  useEngineeringCase: () => ({
    status: "ready",
    error: null,
    retry: vi.fn(),
    revision: { case_revision: 3 },
    engineeringCase: state.engineeringCase,
  }),
}));

vi.mock("../store/TelemetrySelectionContext", () => ({
  useTelemetrySelection: () => ({
    selection: state.selection,
    focusEvidence: state.focusEvidence,
  }),
}));

const caseId = `p3543case_${"a".repeat(24)}`;
const caseSha = "b".repeat(64);
const caseRevision = "c".repeat(64);

function responseArtifact(artifactId: string, producerId: string, sourceLaps: number[]) {
  return {
    artifact_id: artifactId,
    case_id: caseId,
    case_revision_sha256: caseRevision,
    run_id: "run-1",
    session_id: "session-1",
    setup_id: "setup-1",
    source_producer_id: producerId,
    source_lap_numbers: sourceLaps,
    lap_pct_start: 10,
    lap_pct_end: 20,
  };
}

function engineeringCase() {
  return {
    case_id: caseId,
    case_sha256: caseSha,
    case_revision_sha256: caseRevision,
    run_id: "run-1",
    session_id: "session-1",
    setup_id: "setup-1",
    mission: {
      what: "+0.128 s center to exit",
      where: "T3 · 62.1–71.4%",
      why_it_matters: "Matched steering demand with reduced yaw response",
      uncertain: "Front tire demand versus platform",
      next: "Collect the exact discriminator",
      done_when: "Three clean laps clear the contract",
      source_authority: "p19_measurement_mirror",
      source_artifact_ids: ["artifact-1"],
      setup_authorized: false,
    },
    semantic_focus: {
      case_id: caseId,
      case_revision_sha256: caseRevision,
      lap_numbers: [1, 2],
      lap_pct_start: 62.1,
      lap_pct_end: 71.4,
      artifact_id: "artifact-1",
      mechanism_ids: [],
      response_relation_id: null,
      component_ids: [],
      effect_ids: [],
      control_keys: [],
      p19_cause_ids: [],
      phase: "center",
    },
    response_artifacts: [
      responseArtifact("unrelated-artifact", "wrong-producer", [9]),
      responseArtifact("artifact-1", "exact-producer", [7]),
    ],
    quantity_observability: [],
    active_discriminator_id: "discriminator-1",
  };
}

describe("EngineeringMissionStrip", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    state.focusEvidence.mockReset();
    state.engineeringCase = engineeringCase();
    state.selection = {
      selectedRunId: "run-1",
      selectedLap: 4,
      selectedLapScope: "single_lap",
      selectedLapPct: 31,
      selectedWorkspace: "laps",
      selectionSource: "manual",
    };
  });

  it("focuses the full decision scope through the exact semantic-focus artifact", () => {
    render(<EngineeringMissionStrip />);
    expect(screen.getByLabelText("Current Engineering Case mission").getAttribute("data-mode")).toBe("race");
    expect(screen.getAllByText("Next")).toHaveLength(1);
    expect(screen.getByText("Collect the exact discriminator")).toBeTruthy();
    expect(screen.getByText("Lap 4 · 31.0%")).toBeTruthy();
    expect(screen.getByText("Laps 1, 2 · 62.1–71.4%")).toBeTruthy();
    expect(screen.getByText("Lap 7 · 10.0–20.0%")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Focus decision scope/i }));
    expect(state.focusEvidence).toHaveBeenCalledTimes(1);
    expect(state.focusEvidence.mock.calls[0][0]).toMatchObject({
      runId: "run-1",
      lapNumber: 1,
      lapScope: "lap_window",
      lapWindowStart: 1,
      lapWindowEnd: 2,
      representativeLap: 1,
      producerId: "exact-producer",
      artifactId: "artifact-1",
      caseSha256: caseSha,
      discriminatorId: "discriminator-1",
      zoneStartPct: 62.1,
      zoneEndPct: 71.4,
    });
  });

  it("keeps Race mode decision-first and reserves explanatory fields for Learning mode", () => {
    const { rerender } = render(<EngineeringMissionStrip />);

    expect(screen.getByText("Where")).toBeTruthy();
    expect(screen.getByText("Next")).toBeTruthy();
    expect(screen.getByText("Done when")).toBeTruthy();
    expect(screen.queryByText("What")).toBeNull();
    expect(screen.queryByText("Why")).toBeNull();
    expect(screen.queryByText("Uncertain")).toBeNull();

    state.selection = { ...state.selection, selectedMode: "learning" };
    rerender(<EngineeringMissionStrip />);

    expect(screen.getByLabelText("Current Engineering Case mission").getAttribute("data-mode")).toBe("learning");
    expect(screen.getByText("What")).toBeTruthy();
    expect(screen.getByText("Why")).toBeTruthy();
    expect(screen.getByText("Uncertain")).toBeTruthy();
  });

  it("fails closed when the semantic-focus artifact is not in the exact case revision", () => {
    state.engineeringCase.response_artifacts = [responseArtifact("unrelated-artifact", "wrong-producer", [9])];
    render(<EngineeringMissionStrip />);

    expect(screen.getByText("No exact response artifact")).toBeTruthy();
    const button = screen.getByRole("button", { name: /Focus decision scope/i });
    expect(button.hasAttribute("disabled")).toBe(true);
    fireEvent.click(button);
    expect(state.focusEvidence).not.toHaveBeenCalled();
  });

  it("hides the handoff only when the complete case, artifact, lap-window, and zone scope already match", () => {
    state.selection = {
      selectedRunId: "run-1",
      selectedLap: 1,
      selectedLapScope: "lap_window",
      selectedLapWindowStart: 1,
      selectedLapWindowEnd: 2,
      selectedRepresentativeLap: 1,
      selectedLapPct: 62.1,
      selectedZoneStartPct: 62.1,
      selectedZoneEndPct: 71.4,
      selectedCaseId: caseId,
      selectedCaseRevision: caseRevision,
      selectedCaseSha256: caseSha,
      selectedArtifactId: "artifact-1",
    };
    render(<EngineeringMissionStrip />);

    expect(screen.queryByRole("button", { name: /Focus decision scope/i })).toBeNull();
  });

  it("offers a semantic breadcrumb back to the prior viewing scope", () => {
    const { rerender } = render(<EngineeringMissionStrip />);
    fireEvent.click(screen.getByRole("button", { name: /Focus decision scope/i }));

    state.selection = {
      ...state.selection,
      selectedLap: 1,
      selectedLapScope: "lap_window",
      selectedLapWindowStart: 1,
      selectedLapWindowEnd: 2,
      selectedRepresentativeLap: 1,
      selectedLapPct: 62.1,
      selectedZoneStartPct: 62.1,
      selectedZoneEndPct: 71.4,
      selectedCaseId: caseId,
      selectedCaseRevision: caseRevision,
      selectedCaseSha256: caseSha,
      selectedArtifactId: "artifact-1",
    };
    rerender(<EngineeringMissionStrip />);

    fireEvent.click(screen.getByRole("button", { name: /Return to previous focus/i }));
    expect(state.focusEvidence).toHaveBeenCalledTimes(2);
    expect(state.focusEvidence.mock.calls[1]).toEqual([
      expect.objectContaining({
        runId: "run-1",
        lapNumber: 4,
        lapScope: "single_lap",
        lapPct: 31,
        caseSha256: null,
      }),
      "laps",
    ]);
  });
});
