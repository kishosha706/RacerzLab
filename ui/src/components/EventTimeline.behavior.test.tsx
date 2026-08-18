import { fireEvent, render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { describe, expect, it } from "vitest";
import {
  TelemetrySelectionProvider,
  useTelemetryCursor,
  useTelemetrySelection,
} from "../store/TelemetrySelectionContext";
import { EventTimeline } from "./EventTimeline";

function TimelineHarness() {
  const { loadRun } = useTelemetrySelection();
  const cursor = useTelemetryCursor();
  useEffect(() => loadRun("run-alpha", 4), [loadRun]);
  return (
    <>
      <EventTimeline
        platformEvents={[]}
        eventVisibilityMode="actionable"
        workspace="platform_trace"
        lapDurationSeconds={60}
      />
      <output data-testid="hover-position">{cursor.hoverLapPct ?? "none"}</output>
    </>
  );
}

describe("full-lap playback scrubber", () => {
  it("synchronizes physical lap position even when no event anchors exist", async () => {
    render(
      <TelemetrySelectionProvider>
        <TimelineHarness />
      </TelemetrySelectionProvider>,
    );
    const scrubber = await screen.findByRole("slider", {
      name: "Scrub continuously through the selected lap by physical track position",
    });
    fireEvent.change(scrubber, { target: { value: "42.5" } });
    expect(screen.getByTestId("hover-position").textContent).toBe("42.5");
    expect(screen.getByRole("button", { name: "Start playback" }).hasAttribute("disabled")).toBe(false);
  });
});
