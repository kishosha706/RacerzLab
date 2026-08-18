import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TelemetrySelectionProvider } from "../store/TelemetrySelectionContext";
import type { ChannelCatalogItem, RunOverview } from "../types/telemetry";
import { RawChannelsTab } from "./RawChannelsTab";


const overview = {
  run_id: "run-1",
  session: {
    run_id: "run-1",
    telemetry_rate_hz: 60,
    variable_count: 2,
  },
} as RunOverview;

const channels = [
  {
    name: "lf_tires_used",
    type: "int",
    engineering_role: "pit_snapshot",
    engineering_admission_state: "pit_boundary_only",
  },
  {
    name: "speed_mps",
    type: "float",
    engineering_role: "admitted_analysis",
    engineering_admission_state: "admitted",
  },
] as ChannelCatalogItem[];


describe("Telemetry Capabilities continuous-lane authority", () => {
  it("never promotes a pit snapshot into continuous on-track evidence", () => {
    render(
      <TelemetrySelectionProvider>
        <RawChannelsTab overview={overview} trace={null} channels={channels} />
      </TelemetrySelectionProvider>,
    );

    const pitSnapshotAction = screen.getByTitle(
      "Pit-boundary snapshots cannot become continuous on-track evidence",
    ) as HTMLButtonElement;
    const continuousAction = screen.getByTitle(
      "Open one observation-only custom Platform lane",
    ) as HTMLButtonElement;

    expect(pitSnapshotAction.disabled).toBe(true);
    expect(continuousAction.disabled).toBe(false);
  });
});
