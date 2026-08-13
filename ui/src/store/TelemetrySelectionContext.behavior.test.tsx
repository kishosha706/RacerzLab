import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  TelemetrySelectionProvider,
  useTelemetrySelection,
} from "./TelemetrySelectionContext";

function FocusHarness() {
  const { selection, focusTelemetryEvent, focusEvidence } = useTelemetrySelection();
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
          system: "platform_response",
          zoneId: "awareness:episode-b",
          zoneStartPct: 60,
          zoneEndPct: 62,
        }, "platform_trace")}
      >
        Focus P20 episode
      </button>
      <output data-testid="selection">{JSON.stringify(selection)}</output>
    </>
  );
}

describe("TelemetrySelectionProvider evidence behavior", () => {
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
});
