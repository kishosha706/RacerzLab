import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EngineeringMissionStrip } from "./EngineeringMissionStrip";

const state = vi.hoisted(() => ({ focusEvidence: vi.fn() }));

vi.mock("../store/EngineeringCaseContext", () => ({
  useEngineeringCase: () => ({
    status: "ready",
    error: null,
    retry: vi.fn(),
    revision: { case_revision: 3 },
    engineeringCase: {
      case_id: `p3543case_${"a".repeat(24)}`,
      case_sha256: "b".repeat(64),
      case_revision_sha256: "c".repeat(64),
      run_id: "run-1",
      setup_id: "setup-1",
      mission: {
        what: "+0.128 s center to exit",
        where: "T3 · 62.1–71.4%",
        why_it_matters: "Matched steering demand with reduced yaw response",
        uncertain: "Front tire demand versus platform",
        next: "Collect the exact discriminator",
        done_when: "Three clean laps clear the contract",
        source_authority: "p19_measurement_mirror",
        source_artifact_ids: [],
        setup_authorized: false,
      },
      semantic_focus: {
        lap_numbers: [1], lap_pct_start: 62.1, lap_pct_end: 71.4,
        artifact_id: "artifact-1", mechanism_ids: [], response_relation_id: null,
        component_ids: [], effect_ids: [], control_keys: [], p19_cause_ids: [], phase: "center",
      },
      response_artifacts: [],
      quantity_observability: [],
      active_discriminator_id: "discriminator-1",
    },
  }),
}));

vi.mock("../store/TelemetrySelectionContext", () => ({
  useTelemetrySelection: () => ({
    selection: { selectedLap: 4, selectedLapPct: 31 },
    focusEvidence: state.focusEvidence,
  }),
}));

describe("EngineeringMissionStrip", () => {
  it("renders one canonical NEXT and distinguishes viewing from decision scope", () => {
    render(<EngineeringMissionStrip />);
    expect(screen.getAllByText("Next")).toHaveLength(1);
    expect(screen.getByText("Collect the exact discriminator")).toBeTruthy();
    expect(screen.getByText("Lap 4 · 31.0%")).toBeTruthy();
    expect(screen.getByText("Lap 1 · 62.1%")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Focus decision scope/i }));
    expect(state.focusEvidence).toHaveBeenCalledTimes(1);
    expect(state.focusEvidence.mock.calls[0][0]).toMatchObject({
      runId: "run-1",
      lapNumber: 1,
      caseSha256: "b".repeat(64),
      discriminatorId: "discriminator-1",
    });
  });
});
