import { describe, expect, it } from "vitest";

import { selectionReducer } from "./TelemetrySelectionContext";
import type { TelemetrySelection } from "./types";

const selectedEvent: TelemetrySelection = {
  selectedRunId: "run-a",
  selectedLap: 4,
  selectedLapScope: "single_lap",
  selectedSampleIndex: 44,
  selectedLapDistFt: 1234,
  selectedLapPct: 20,
  selectedEventId: "event-a",
  selectedChannel: "yaw_rate",
  selectedMode: "race",
  selectedWorkspace: "overview",
  selectionSource: "track_map",
};

describe("focusEvidence transaction", () => {
  it("clears an incompatible event and sample when focusing a P20 episode", () => {
    const next = selectionReducer(selectedEvent, {
      type: "FOCUS_EVIDENCE",
      evidence: {
        runId: "run-b",
        lapNumber: 7,
        lapScope: "track_zone",
        lapPct: 61,
        zoneId: "awareness:p20-b",
        zoneStartPct: 60,
        zoneEndPct: 62,
        producerId: "p20.engineering-awareness",
        artifactId: "p20-b",
        system: "platform_response",
      },
      workspace: "platform_trace",
    });

    expect(next.selectedRunId).toBe("run-b");
    expect(next.selectedEventId).toBeNull();
    expect(next.selectedSampleIndex).toBeNull();
    expect(next.selectedLapDistFt).toBeNull();
    expect(next.selectedProducerId).toBe("p20.engineering-awareness");
    expect(next.selectedArtifactId).toBe("p20-b");
    expect(next.selectedSystem).toBe("platform_response");
    expect(next.selectedWorkspace).toBe("platform_trace");
  });

  it("stores Crew artifact identity without pretending it is a platform event", () => {
    const next = selectionReducer(selectedEvent, {
      type: "FOCUS_EVIDENCE",
      evidence: {
        runId: "run-c",
        lapNumber: 8,
        artifactId: "crew-artifact",
        producerId: "p27.context",
        sourceRunId: "run-c",
        sourceSetupId: "setup-c",
      },
    });

    expect(next.selectedEventId).toBeNull();
    expect(next.selectedArtifactId).toBe("crew-artifact");
    expect(next.selectedSourceRunId).toBe("run-c");
    expect(next.selectedSourceSetupId).toBe("setup-c");
  });
});
