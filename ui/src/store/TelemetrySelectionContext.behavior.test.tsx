import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  TelemetrySelectionProvider,
  useTelemetrySelection,
} from "./TelemetrySelectionContext";

function FocusHarness() {
  const {
    selection,
    focusTelemetryEvent,
    focusEvidence,
    selectLap,
    selectRun,
    setWorkspace,
  } = useTelemetrySelection();
  return (
    <>
      <button
        type="button"
        onClick={() => focusTelemetryEvent(
          "event-a", 4, 44, 1234, 20, "platform_trace", "track_map",
        )}
      >
        Focus event
      </button>
      <button
        type="button"
        onClick={() => focusEvidence({
          runId: "run-b",
          lapNumber: 7,
          lapPct: 61,
          producerId: "p20.engineering-awareness",
          artifactId: "episode-b",
          caseId: "case-b",
          caseRevision: "revision-b",
          caseSha256: "case-sha-b",
          mechanismIds: ["mechanism-b"],
          responseRelationId: "relation-b",
          componentIds: ["component-b"],
          effectIds: ["effect-b"],
          controlKeys: ["control-b"],
          p19CauseIds: ["cause-b"],
          quantityIds: ["quantity-b"],
          discriminatorId: "discriminator-b",
          system: "platform_response",
          compareRole: "test",
          sourceRunId: "run-b",
          sourceSetupId: "setup-b",
          zoneId: "awareness:episode-b",
          zoneStartPct: 60,
          zoneEndPct: 62,
        }, "platform_trace")}
      >
        Focus P20 episode
      </button>
      <button type="button" onClick={() => selectRun("run-c")}>Select run</button>
      <button type="button" onClick={() => selectLap(9)}>Select lap</button>
      <button type="button" onClick={() => setWorkspace("laps", "manual")}>Open Laps manually</button>
      <output data-testid="selection">{JSON.stringify(selection)}</output>
    </>
  );
}

describe("TelemetrySelectionProvider evidence behavior", () => {
  afterEach(() => cleanup());

  it("renders one coherent physical reality after an event-to-episode transition", () => {
    render(
      <TelemetrySelectionProvider>
        <FocusHarness />
      </TelemetrySelectionProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Focus event" }));
    expect(screen.getByTestId("selection").textContent).toContain('"selectedEventId":"event-a"');

    fireEvent.click(screen.getByRole("button", { name: "Focus P20 episode" }));
    const selection = JSON.parse(screen.getByTestId("selection").textContent ?? "{}");
    expect(selection).toMatchObject({
      selectedRunId: "run-b",
      selectedLap: 7,
      selectedEventId: null,
      selectedSampleIndex: null,
      selectedLapDistFt: null,
      selectedLapPct: 61,
      selectedProducerId: "p20.engineering-awareness",
      selectedArtifactId: "episode-b",
      selectedSystem: "platform_response",
      selectedZoneStartPct: 60,
      selectedZoneEndPct: 62,
      selectedWorkspace: "platform_trace",
    });
  });

  it.each([
    ["Select run"],
    ["Select lap"],
    ["Open Laps manually"],
  ])("renders no stale exact-case identity after %s", (actionName) => {
    render(
      <TelemetrySelectionProvider>
        <FocusHarness />
      </TelemetrySelectionProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Focus P20 episode" }));
    expect(screen.getByTestId("selection").textContent).toContain('"selectedCaseId":"case-b"');

    fireEvent.click(screen.getByRole("button", { name: actionName }));
    const selection = JSON.parse(screen.getByTestId("selection").textContent ?? "{}");
    expect(selection).toMatchObject({
      selectedProducerId: null,
      selectedArtifactId: null,
      selectedCaseId: null,
      selectedCaseRevision: null,
      selectedCaseSha256: null,
      selectedMechanismIds: [],
      selectedResponseRelationId: null,
      selectedComponentIds: [],
      selectedEffectIds: [],
      selectedControlKeys: [],
      selectedP19CauseIds: [],
      selectedQuantityIds: [],
      selectedDiscriminatorId: null,
      selectedSystem: null,
      selectedCompareRole: null,
      selectedSourceRunId: null,
      selectedSourceSetupId: null,
    });
  });
});
