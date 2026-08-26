import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ControlledWorkflow } from "../types/telemetry";
import { ControlledTestRibbon } from "./ControlledTestRibbon";

function workflow(stageRunIds: ControlledWorkflow["stage_run_ids"]): ControlledWorkflow {
  return {
    workflow_id: "workflow-1",
    status: Object.keys(stageRunIds).length === 3 ? "a2_recorded" : "planned",
    source_run_id: "run-a",
    complaint: "Center-to-exit push",
    packet: { decision: "test" },
    stage_run_ids: stageRunIds,
  } as ControlledWorkflow;
}

describe("ControlledTestRibbon", () => {
  afterEach(() => cleanup());

  it("presents workflow progress as evidence status with one neutral navigation control", () => {
    const onOpen = vi.fn();
    render(
      <ControlledTestRibbon
        workflow={workflow({})}
        currentIntelligenceAuthority={null}
        intelligenceAuthorityStatus="idle"
        intelligenceAuthorityRecovery=""
        onOpen={onOpen}
      />,
    );

    expect(screen.getByText("Status: Baseline A pending")).toBeTruthy();
    expect(screen.getByText("Current")).toBeTruthy();
    expect(screen.getAllByText("Pending")).toHaveLength(2);
    expect(screen.queryByText("Record baseline A")).toBeNull();
    const review = screen.getByRole("button", { name: "Review controlled-test evidence" });
    fireEvent.click(review);
    expect(onOpen).toHaveBeenCalledWith("workflow-1");
  });

  it("reports scoring as pending without publishing a scoring command", () => {
    render(
      <ControlledTestRibbon
        workflow={workflow({ A: "run-a", B: "run-b", A2: "run-a2" })}
        currentIntelligenceAuthority={null}
        intelligenceAuthorityStatus="idle"
        intelligenceAuthorityRecovery=""
        onOpen={vi.fn()}
      />,
    );

    expect(screen.getByText("Status: Scoring pending")).toBeTruthy();
    expect(screen.getAllByText("Verified")).toHaveLength(3);
    expect(screen.queryByText("Score the controlled test")).toBeNull();
    expect(screen.getByRole("button", { name: "Review controlled-test evidence" })).toBeTruthy();
  });
});
