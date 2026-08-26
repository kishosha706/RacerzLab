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

const exactCaseFocus: TelemetrySelection = {
  ...selectedEvent,
  selectedProducerId: "p32.compare",
  selectedArtifactId: "artifact-a",
  selectedCaseId: "case-a",
  selectedCaseRevision: "revision-a",
  selectedCaseSha256: "case-sha-a",
  selectedMechanismIds: ["mechanism-a"],
  selectedResponseRelationId: "relation-a",
  selectedComponentIds: ["component-a"],
  selectedEffectIds: ["effect-a"],
  selectedControlKeys: ["control-a"],
  selectedP19CauseIds: ["cause-a"],
  selectedQuantityIds: ["quantity-a"],
  selectedDiscriminatorId: "discriminator-a",
  selectedWorkflowId: "workflow-a",
  selectedWorkflowRevision: "workflow-revision-a",
  selectedSystem: "compare",
  selectedCompareRole: "test",
  selectedSourceRunId: "run-a",
  selectedSourceSetupId: "setup-a",
};

function expectSemanticFocusCleared(selection: TelemetrySelection) {
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
    selectedWorkflowId: null,
    selectedWorkflowRevision: null,
    selectedSystem: null,
    selectedCompareRole: null,
    selectedSourceRunId: null,
    selectedSourceSetupId: null,
  });
}

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

describe("manual context semantic reset", () => {
  it("clears the complete exact-case identity when the driver selects another lap", () => {
    const next = selectionReducer(exactCaseFocus, { type: "SELECT_LAP", lap: 9 });

    expectSemanticFocusCleared(next);
    expect(next).toMatchObject({
      selectedLap: 9,
      selectedEventId: null,
      selectedSampleIndex: null,
      selectedChannel: null,
      selectedZoneId: null,
    });
  });

  it("clears the complete exact-case identity for atomic comparison and context selections", () => {
    const actions: Parameters<typeof selectionReducer>[1][] = [
      { type: "SELECT_COMPARE_RUN", runId: "run-b" },
      { type: "SELECT_SAMPLE", sampleIndex: 90, source: "trace_cursor" },
      { type: "SELECT_EVENT", eventId: "event-b", source: "priority_stack" },
      { type: "SELECT_CHANNEL", channel: "speed", source: "channel_catalog" },
      { type: "SELECT_SETUP_KEY", setupKey: "front_arb" },
      { type: "SELECT_ZONE", zoneId: "turn-1" },
      { type: "SET_WORKSPACE", workspace: "laps", source: "manual" },
      {
        type: "FOCUS_EVENT",
        eventId: "event-b",
        lap: 5,
        sampleIndex: 55,
        lapDistFt: 1500,
        lapPct: 30,
        workspace: "platform_trace",
        source: "event_timeline",
      },
    ];

    actions.forEach((action) => expectSemanticFocusCleared(selectionReducer(exactCaseFocus, action)));
  });

  it("preserves semantic identity for a semantic handoff's non-manual workspace navigation", () => {
    const next = selectionReducer(exactCaseFocus, {
      type: "SET_WORKSPACE",
      workspace: "engineer",
      source: "compare_verdict",
    });

    expect(next.selectedCaseId).toBe("case-a");
    expect(next.selectedMechanismIds).toEqual(["mechanism-a"]);
  });
});
